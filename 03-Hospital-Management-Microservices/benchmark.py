"""
Workload benchmark + resource monitor for the Hospital Management microservices.

This is the ONE script used to produce every number in the report.

What it does
------------
1. Checks that the stack is up (GET /health/dependencies on appointment-service).
2. Starts ONE background `docker stats` stream for the three containers. Every
   line it prints (about one per container per second) is stored with a
   timestamp in results/resource_samples.csv.
3. Records an idle baseline (no load) for a few seconds.
4. Sends warm-up requests (not measured).
5. For each repetition (default 3) and each concurrency level
   (default 1, 2, 4, 8, 16) it runs one measured load run:
     - N client worker threads (N = concurrency level) send requests. Each
       worker sends one request, waits for the full response, then
       immediately sends the next one (closed-loop load). So at any moment
       exactly N requests are in flight.
     - A run stops when it has sent at least --requests requests (default
       500) AND has lasted at least --min-duration seconds (default 10). The
       time floor guarantees ~10 docker stats samples per run even at high
       throughput, so CPU/memory are measured DURING the load.
     - It records the response time of every request, successes, failures,
       and the time window of the run.
     - CPU / memory samples whose timestamps fall inside the run window are
       used to compute the average AND peak CPU / memory for EACH container
       separately.
   Repetitions are interleaved (W1..W5, then W1..W5 again, ...) so slow drift
   on the machine affects all levels equally.
6. Writes:
     results/runs.csv              one row per (repetition, level)
     results/workload_results.csv  final table: mean over repetitions
     results/resource_samples.csv  every raw docker stats sample
     results/run_info.json         settings + machine info for this run

Then run:  python generate_graphs.py   and   python generate_report.py

Usage
-----
    python benchmark.py
    python benchmark.py --requests 500 --min-duration 10 --repetitions 3
"""

import argparse
import csv
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests

CONTAINERS = ["patient-service", "doctor-service", "appointment-service"]
RESULTS_DIR = "results"

# docker stats computes CPU% over roughly the second BEFORE it prints a line,
# so a sample stamped at time t mostly describes (t - 1 s, t]. Shifting the
# window by this lag makes each run use the samples that describe it.
SAMPLE_LAG_SECONDS = 1.0

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MEMORY_UNITS_TO_MIB = {
    "b": 1 / (1024 * 1024),
    "kib": 1 / 1024, "kb": 1000 / (1024 * 1024),
    "mib": 1.0, "mb": 1000 * 1000 / (1024 * 1024),
    "gib": 1024.0, "gb": 1000 ** 3 / (1024 * 1024),
    "tib": 1024.0 * 1024,
}


# ----------------------------------------------------------------------------
# Resource monitoring (docker stats, running for the whole benchmark)
# ----------------------------------------------------------------------------

def memory_to_mib(text):
    """'27.02MiB' -> 27.02 ; '1.2GiB' -> 1228.8 ; '512KiB' -> 0.5"""
    match = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text)
    if not match:
        raise ValueError(f"cannot parse memory value: {text!r}")
    value, unit = match.groups()
    return float(value) * MEMORY_UNITS_TO_MIB[unit.lower()]


class DockerStatsSampler:
    """Runs `docker stats` (streaming) in the background and keeps every sample."""

    def __init__(self, containers):
        self.containers = containers
        self.samples = []          # (timestamp, container, cpu_percent, mem_mib)
        self.lock = threading.Lock()
        self.process = None
        self.thread = None
        self.error = None

    def start(self):
        command = [
            "docker", "stats",
            "--format", "{{.Name}},{{.CPUPerc}},{{.MemUsage}}",
            *self.containers,
        ]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        for raw_line in self.process.stdout:
            timestamp = time.perf_counter()
            line = ANSI_ESCAPE.sub("", raw_line).strip()
            parts = line.split(",", 2)
            if len(parts) != 3 or parts[0] not in self.containers:
                continue
            name, cpu_text, mem_text = parts
            try:
                cpu = float(cpu_text.strip().rstrip("%"))
                mem = memory_to_mib(mem_text.split("/")[0])
            except (ValueError, KeyError):
                continue   # e.g. "--" while a container is restarting
            with self.lock:
                self.samples.append((timestamp, name, cpu, mem))
        if self.process.poll() not in (None, 0):
            self.error = self.process.stderr.read()

    def wait_for_first_samples(self, timeout=15):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            with self.lock:
                seen = {name for _, name, _, _ in self.samples}
            if seen >= set(self.containers):
                return True
            if self.process.poll() is not None:
                break
            time.sleep(0.2)
        return False

    def window(self, start, end):
        """Samples that describe the time interval [start, end]."""
        low, high = start + SAMPLE_LAG_SECONDS, end + SAMPLE_LAG_SECONDS
        with self.lock:
            return [s for s in self.samples if low < s[0] <= high]

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def summarise_resources(samples, containers):
    """Average and peak CPU / memory for each container from a list of samples."""
    summary = {}
    for name in containers:
        cpu = [s[2] for s in samples if s[1] == name]
        mem = [s[3] for s in samples if s[1] == name]
        summary[name] = {
            "cpu_avg": statistics.fmean(cpu) if cpu else float("nan"),
            "cpu_peak": max(cpu) if cpu else float("nan"),
            "mem_avg": statistics.fmean(mem) if mem else float("nan"),
            "mem_peak": max(mem) if mem else float("nan"),
            "samples": len(cpu),
        }
    return summary


# ----------------------------------------------------------------------------
# Load generation
# ----------------------------------------------------------------------------

def send_request(url, timeout):
    """One HTTP GET. Returns (ok, response_time_seconds, outcome_label)."""
    start = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout)
        elapsed = time.perf_counter() - start
        ok = response.status_code == 200
        return ok, elapsed, f"HTTP {response.status_code}"
    except requests.Timeout:
        return False, time.perf_counter() - start, "Timeout"
    except requests.ConnectionError:
        return False, time.perf_counter() - start, "ConnectionError"
    except requests.RequestException as error:
        return False, time.perf_counter() - start, type(error).__name__


def run_load(url, concurrency, min_requests, min_duration, timeout):
    """
    Closed-loop load: `concurrency` worker threads send requests. Each worker
    sends a request, waits for the full response, then sends the next one.
    The run stops once BOTH at least `min_requests` requests have been sent
    AND at least `min_duration` seconds have passed. The duration floor makes
    sure even fast runs last long enough for docker stats (about one sample
    per second) to measure CPU and memory during the load.
    """
    results = []
    results_lock = threading.Lock()
    sent = [0]
    sent_lock = threading.Lock()
    start_barrier = threading.Barrier(concurrency + 1)
    run_start = [0.0]

    def worker():
        start_barrier.wait()            # all workers start together
        while True:
            with sent_lock:
                done_count = sent[0] >= min_requests
                done_time = time.perf_counter() - run_start[0] >= min_duration
                if done_count and done_time:
                    return
                sent[0] += 1
            outcome = send_request(url, timeout)
            with results_lock:
                results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for thread in threads:
        thread.start()

    run_start[0] = time.perf_counter()
    start_barrier.wait()
    start = run_start[0]
    for thread in threads:
        thread.join()
    end = time.perf_counter()
    return results, start, end


def percentile(values, pct):
    """Nearest-rank percentile (pct in 0..100)."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def check_stack(base_url):
    try:
        response = requests.get(f"{base_url}/health/dependencies", timeout=5)
    except requests.RequestException as error:
        sys.exit(
            f"Cannot reach appointment-service at {base_url} ({error}).\n"
            "Start the stack first:  docker compose up -d --build"
        )
    if response.status_code != 200:
        sys.exit(f"Stack is not healthy: {response.text}")
    print(f"Stack healthy: {response.json()['dependencies']}")


def docker_version():
    try:
        return subprocess.check_output(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            text=True, timeout=10,
        ).strip()
    except Exception:  # noqa: BLE001 - informational only
        return "unknown"


def fmt(value, digits=2):
    return "" if value != value else f"{value:.{digits}f}"   # NaN -> ""


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5003",
                        help="appointment-service base URL (127.0.0.1 avoids slow "
                             "IPv6 'localhost' lookups on Windows)")
    parser.add_argument("--endpoint", default="/appointments/1",
                        help="end-to-end endpoint under test (uses all 3 services)")
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8, 16],
                        help="concurrency levels (client worker threads)")
    parser.add_argument("--requests", type=int, default=500,
                        help="minimum requests per run (per level per repetition)")
    parser.add_argument("--min-duration", type=float, default=10.0,
                        help="minimum duration of each run in seconds, so that "
                             "docker stats collects enough samples")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=50,
                        help="unmeasured warm-up requests before the test")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="client timeout per request in seconds")
    parser.add_argument("--baseline-seconds", type=float, default=5.0,
                        help="idle period measured before any load")
    parser.add_argument("--cooldown", type=float, default=3.0,
                        help="pause between runs so resource samples do not mix")
    args = parser.parse_args()

    url = args.base_url.rstrip("/") + args.endpoint
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=" * 78)
    print("HOSPITAL MANAGEMENT MICROSERVICES - WORKLOAD BENCHMARK")
    print("=" * 78)
    print(f"Target            : GET {url}")
    print(f"Concurrency levels: {args.levels}")
    print(f"Each run          : >= {args.requests} requests and >= {args.min_duration:.0f} s")
    print(f"Repetitions       : {args.repetitions}")
    print(f"Warm-up requests  : {args.warmup}")
    print()

    check_stack(args.base_url.rstrip("/"))

    sampler = DockerStatsSampler(CONTAINERS)
    sampler.start()
    if not sampler.wait_for_first_samples():
        sampler.stop()
        sys.exit(f"docker stats produced no samples. {sampler.error or ''}\n"
                 "Is Docker running and are the three containers up?")

    run_rows = []
    try:
        # ---- idle baseline ------------------------------------------------
        print(f"Measuring idle baseline for {args.baseline_seconds:.0f} s ...")
        base_start = time.perf_counter()
        time.sleep(args.baseline_seconds)
        base_end = time.perf_counter()
        baseline = summarise_resources(sampler.window(base_start, base_end), CONTAINERS)

        # ---- warm-up --------------------------------------------------------
        print(f"Warm-up: {args.warmup} requests (not recorded) ...")
        for _ in range(args.warmup):
            send_request(url, args.timeout)
        time.sleep(args.cooldown)

        # ---- measured runs -------------------------------------------------
        print()
        header = (f"{'Rep':<4}{'Load':<6}{'Conc':>5}{'Sent':>6}{'Fail':>6}"
                  f"{'Avg RT ms':>11}{'p95 ms':>9}{'Req/s':>9}"
                  f"{'CPU% pat/doc/app':>22}{'Samp':>6}")
        print(header)
        print("-" * len(header))

        for rep in range(1, args.repetitions + 1):
            for index, level in enumerate(args.levels, start=1):
                results, start, end = run_load(url, level, args.requests,
                                               args.min_duration, args.timeout)
                time.sleep(SAMPLE_LAG_SECONDS + 0.2)   # let the last samples arrive
                duration = end - start

                times_ms = [t * 1000 for ok, t, _ in results if ok]
                successes = len(times_ms)
                failures = len(results) - successes
                outcomes = {}
                for ok, _, label in results:
                    if not ok:
                        outcomes[label] = outcomes.get(label, 0) + 1

                resources = summarise_resources(sampler.window(start, end), CONTAINERS)

                row = {
                    "Workload": f"W{index}",
                    "Concurrency": level,
                    "Repetition": rep,
                    "Requests": len(results),
                    "Success": successes,
                    "Failed": failures,
                    "FailureTypes": ";".join(f"{k}={v}" for k, v in outcomes.items()),
                    "Duration_s": duration,
                    "Throughput_req_s": successes / duration,
                    "RT_avg_ms": statistics.fmean(times_ms) if times_ms else float("nan"),
                    "RT_median_ms": statistics.median(times_ms) if times_ms else float("nan"),
                    "RT_p95_ms": percentile(times_ms, 95),
                    "RT_min_ms": min(times_ms) if times_ms else float("nan"),
                    "RT_max_ms": max(times_ms) if times_ms else float("nan"),
                }
                for name in CONTAINERS:
                    r = resources[name]
                    row[f"{name}_CPU_avg_pct"] = r["cpu_avg"]
                    row[f"{name}_CPU_peak_pct"] = r["cpu_peak"]
                    row[f"{name}_MEM_avg_MiB"] = r["mem_avg"]
                    row[f"{name}_MEM_peak_MiB"] = r["mem_peak"]
                    row[f"{name}_samples"] = r["samples"]
                row["Total_CPU_avg_pct"] = sum(resources[n]["cpu_avg"] for n in CONTAINERS)
                row["Total_MEM_avg_MiB"] = sum(resources[n]["mem_avg"] for n in CONTAINERS)
                run_rows.append(row)

                min_samples = min(resources[n]["samples"] for n in CONTAINERS)
                cpu_text = "/".join(fmt(resources[n]["cpu_avg"], 1) or "-" for n in CONTAINERS)
                print(f"{rep:<4}{row['Workload']:<6}{level:>5}{len(results):>6}{failures:>6}"
                      f"{row['RT_avg_ms']:>11.2f}{row['RT_p95_ms']:>9.2f}"
                      f"{row['Throughput_req_s']:>9.2f}{cpu_text:>22}{min_samples:>6}")
                if failures:
                    print(f"    ! failures in this run: {row['FailureTypes']}")
                if min_samples < 2:
                    print("    ! fewer than 2 docker stats samples in this run - "
                          "increase --min-duration for reliable CPU/memory numbers")

                time.sleep(args.cooldown)
    finally:
        sampler.stop()

    # ---- write raw per-run results ----------------------------------------
    run_fields = list(run_rows[0].keys())
    with open(os.path.join(RESULTS_DIR, "runs.csv"), "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=run_fields)
        writer.writeheader()
        for row in run_rows:
            writer.writerow({k: (fmt(v, 3) if isinstance(v, float) else v)
                             for k, v in row.items()})

    # ---- aggregate over repetitions ---------------------------------------
    final_rows = []
    for index, level in enumerate(args.levels, start=1):
        rows = [r for r in run_rows if r["Concurrency"] == level]

        def mean(key):
            values = [r[key] for r in rows if r[key] == r[key]]
            return statistics.fmean(values) if values else float("nan")

        def stdev(key):
            values = [r[key] for r in rows if r[key] == r[key]]
            return statistics.stdev(values) if len(values) > 1 else 0.0

        def peak(key):
            values = [r[key] for r in rows if r[key] == r[key]]
            return max(values) if values else float("nan")

        final = {
            "Workload": f"W{index}",
            "Concurrency": level,
            "Repetitions": len(rows),
            "Requests_total": sum(r["Requests"] for r in rows),
            "Success_total": sum(r["Success"] for r in rows),
            "Failed_total": sum(r["Failed"] for r in rows),
            "RT_avg_ms": mean("RT_avg_ms"),
            "RT_avg_std_ms": stdev("RT_avg_ms"),
            "RT_median_ms": mean("RT_median_ms"),
            "RT_p95_ms": mean("RT_p95_ms"),
            "RT_max_ms": peak("RT_max_ms"),
            "Throughput_req_s": mean("Throughput_req_s"),
            "Throughput_std_req_s": stdev("Throughput_req_s"),
        }
        for name in CONTAINERS:
            final[f"{name}_CPU_avg_pct"] = mean(f"{name}_CPU_avg_pct")
            final[f"{name}_CPU_peak_pct"] = peak(f"{name}_CPU_peak_pct")
            final[f"{name}_MEM_avg_MiB"] = mean(f"{name}_MEM_avg_MiB")
            final[f"{name}_MEM_peak_MiB"] = peak(f"{name}_MEM_peak_MiB")
            final[f"{name}_samples"] = sum(r[f"{name}_samples"] for r in rows)
        final["Total_CPU_avg_pct"] = mean("Total_CPU_avg_pct")
        final["Total_MEM_avg_MiB"] = mean("Total_MEM_avg_MiB")
        final_rows.append(final)

    # Idle baseline row (concurrency 0) so the load can be compared to idle.
    idle = {key: "" for key in final_rows[0]}
    idle.update({"Workload": "Idle", "Concurrency": 0, "Repetitions": 1,
                 "Requests_total": 0, "Success_total": 0, "Failed_total": 0})
    for name in CONTAINERS:
        b = baseline[name]
        idle[f"{name}_CPU_avg_pct"] = b["cpu_avg"]
        idle[f"{name}_CPU_peak_pct"] = b["cpu_peak"]
        idle[f"{name}_MEM_avg_MiB"] = b["mem_avg"]
        idle[f"{name}_MEM_peak_MiB"] = b["mem_peak"]
        idle[f"{name}_samples"] = b["samples"]
    idle["Total_CPU_avg_pct"] = sum(baseline[n]["cpu_avg"] for n in CONTAINERS)
    idle["Total_MEM_avg_MiB"] = sum(baseline[n]["mem_avg"] for n in CONTAINERS)

    with open(os.path.join(RESULTS_DIR, "workload_results.csv"), "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(final_rows[0].keys()))
        writer.writeheader()
        for row in [idle] + final_rows:
            writer.writerow({k: (fmt(v, 3) if isinstance(v, float) else v)
                             for k, v in row.items()})

    # ---- raw resource samples (evidence) -----------------------------------
    t0 = sampler.samples[0][0] if sampler.samples else 0.0
    with open(os.path.join(RESULTS_DIR, "resource_samples.csv"), "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["t_seconds", "container", "cpu_percent", "mem_mib"])
        for ts, name, cpu, mem in sampler.samples:
            writer.writerow([f"{ts - t0:.3f}", name, f"{cpu:.2f}", f"{mem:.2f}"])

    with open(os.path.join(RESULTS_DIR, "run_info.json"), "w") as file:
        json.dump({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "target": f"GET {url}",
            "levels": args.levels,
            "min_requests_per_run": args.requests,
            "min_duration_per_run_s": args.min_duration,
            "repetitions": args.repetitions,
            "warmup_requests": args.warmup,
            "client_timeout_s": args.timeout,
            "load_model": "closed loop: N worker threads, each sends the next "
                          "request as soon as the previous response arrives",
            "throughput_definition": "successful requests / wall-clock duration of run",
            "host_os": platform.platform(),
            "host_cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "docker_server": docker_version(),
        }, file, indent=2)

    # ---- final observation table ------------------------------------------
    print()
    print("=" * 78)
    print(f"FINAL OBSERVATION TABLE (mean of {args.repetitions} repetitions per level)")
    print("=" * 78)
    print(f"{'Load':<6}{'Conc':>5}{'Fail':>6}{'Avg RT ms':>11}{'p95 ms':>9}"
          f"{'Req/s':>9}{'CPU avg %':>11}{'Mem avg MiB':>13}")
    print(f"{'Idle':<6}{0:>5}{'-':>6}{'-':>11}{'-':>9}{'-':>9}"
          f"{idle['Total_CPU_avg_pct']:>11.2f}{idle['Total_MEM_avg_MiB']:>13.2f}")
    for r in final_rows:
        print(f"{r['Workload']:<6}{r['Concurrency']:>5}{r['Failed_total']:>6}"
              f"{r['RT_avg_ms']:>11.2f}{r['RT_p95_ms']:>9.2f}"
              f"{r['Throughput_req_s']:>9.2f}{r['Total_CPU_avg_pct']:>11.2f}"
              f"{r['Total_MEM_avg_MiB']:>13.2f}")
    print("(CPU/Mem = sum of the 3 containers; per-service values are in the CSV)")
    print()
    print("Saved: results/workload_results.csv, results/runs.csv, "
          "results/resource_samples.csv, results/run_info.json")
    print("Next : python generate_graphs.py  &&  python generate_report.py")


if __name__ == "__main__":
    main()
