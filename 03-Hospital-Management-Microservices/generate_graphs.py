"""
Generate the performance graphs from results/workload_results.csv.

Flow:  benchmark.py  ->  results/workload_results.csv  ->  generate_graphs.py
No numbers are typed in by hand: every value is read from the CSV.

Graphs (saved in graphs/):
  01-response-time.png      Concurrency vs average (+/- std dev) and p95 response time
  02-throughput.png         Concurrency vs throughput (+/- std dev)
  03-cpu-utilization.png    Concurrency vs CPU % for each microservice (avg and peak)
  04-memory-utilization.png Concurrency vs memory for each microservice (avg and peak)
  05-resource-by-service.png  CPU and memory per service at the highest load level
"""

import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CSV_FILE = os.path.join("results", "workload_results.csv")
GRAPH_DIR = "graphs"

SERVICES = ["patient-service", "doctor-service", "appointment-service"]
# Fixed colour per service (same colour in every graph)
COLORS = {
    "patient-service": "#2a78d6",
    "doctor-service": "#eb6834",
    "appointment-service": "#1baf7a",
}
TEXT = "#52514e"
GRID = "#e4e3df"


def number(value):
    return float(value) if value not in ("", None) else float("nan")


def load_rows():
    if not os.path.exists(CSV_FILE):
        sys.exit(f"{CSV_FILE} not found - run  python benchmark.py  first.")
    with open(CSV_FILE, newline="") as file:
        rows = list(csv.DictReader(file))
    load_rows_ = [r for r in rows if r["Workload"] != "Idle"]
    idle = next((r for r in rows if r["Workload"] == "Idle"), None)
    load_rows_.sort(key=lambda r: int(r["Concurrency"]))
    return load_rows_, idle


def style_axes(ax, levels, ylabel, title):
    ax.set_xscale("log", base=2)
    ax.set_xticks(levels)
    ax.set_xticklabels([str(level) for level in levels])
    ax.minorticks_off()
    ax.set_xlabel("Concurrency level (client worker threads)", color=TEXT)
    ax.set_ylabel(ylabel, color=TEXT)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#b5b4ae")
    ax.tick_params(colors=TEXT)
    ax.set_ylim(bottom=0)


def save(fig, name):
    path = os.path.join(GRAPH_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"  {path}")


def label_points(ax, xs, ys, fmt):
    """Label first and last point only (keeps the chart readable)."""
    # Placed beside the marker (not above it) so the error bars never cross it.
    ax.annotate(fmt.format(ys[0]), (xs[0], ys[0]), textcoords="offset points",
                xytext=(10, -3), ha="left", va="center", fontsize=9, color=TEXT)
    ax.annotate(fmt.format(ys[-1]), (xs[-1], ys[-1]), textcoords="offset points",
                xytext=(-10, -3), ha="right", va="center", fontsize=9, color=TEXT)


def main():
    rows, idle = load_rows()
    os.makedirs(GRAPH_DIR, exist_ok=True)
    levels = [int(r["Concurrency"]) for r in rows]
    reps = rows[0]["Repetitions"]
    note = f"Mean of {reps} repetitions per level; error bars = std dev across repetitions"

    print("Generating graphs from", CSV_FILE)

    # 1. Response time ------------------------------------------------------
    avg = [number(r["RT_avg_ms"]) for r in rows]
    std = [number(r["RT_avg_std_ms"]) for r in rows]
    p95 = [number(r["RT_p95_ms"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(levels, avg, yerr=std, marker="o", markersize=6, linewidth=2,
                capsize=4, color="#2a78d6", label="Average")
    ax.plot(levels, p95, marker="s", markersize=5, linewidth=2, linestyle="--",
            color="#eb6834", label="95th percentile")
    label_points(ax, levels, avg, "{:.1f} ms")
    style_axes(ax, levels, "Response time (ms)", "Concurrency vs Response Time")
    ax.legend(frameon=False)
    fig.text(0.01, 0.005, note, fontsize=8, color=TEXT)
    save(fig, "01-response-time.png")

    # 2. Throughput ---------------------------------------------------------
    thr = [number(r["Throughput_req_s"]) for r in rows]
    thr_std = [number(r["Throughput_std_req_s"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(levels, thr, yerr=thr_std, marker="o", markersize=6, linewidth=2,
                capsize=4, color="#2a78d6")
    label_points(ax, levels, thr, "{:.1f}")
    style_axes(ax, levels, "Throughput (successful requests / s)",
               "Concurrency vs Throughput")
    fig.text(0.01, 0.005, note, fontsize=8, color=TEXT)
    save(fig, "02-throughput.png")

    # 3 & 4. CPU and memory per service ------------------------------------
    for metric, unit, title, filename in (
        ("CPU", "pct", "Concurrency vs CPU Utilization (per service)",
         "03-cpu-utilization.png"),
        ("MEM", "MiB", "Concurrency vs Memory Usage (per service)",
         "04-memory-utilization.png"),
    ):
        fig, ax = plt.subplots(figsize=(8, 5))
        for service in SERVICES:
            avg_values = [number(r[f"{service}_{metric}_avg_{unit}"]) for r in rows]
            peak_values = [number(r[f"{service}_{metric}_peak_{unit}"]) for r in rows]
            ax.plot(levels, avg_values, marker="o", markersize=6, linewidth=2,
                    color=COLORS[service], label=f"{service} (avg)")
            ax.plot(levels, peak_values, marker="^", markersize=6, linewidth=1,
                    linestyle=":", color=COLORS[service], alpha=0.8,
                    label=f"{service} (peak)")
        ylabel = "CPU utilization (%)" if metric == "CPU" else "Memory usage (MiB)"
        style_axes(ax, levels, ylabel, title)
        ax.legend(frameon=False, fontsize=8, ncol=1)
        footer = "docker stats sampled ~1/s during each run"
        if idle:
            idle_total = number(idle[f"Total_{metric}_avg_{'pct' if metric == 'CPU' else 'MiB'}"])
            footer += (f"; idle total = {idle_total:.2f} %" if metric == "CPU"
                       else f"; idle total = {idle_total:.1f} MiB")
        fig.text(0.01, 0.005, footer, fontsize=8, color=TEXT)
        save(fig, filename)

    # 5. Which service uses the most resources (highest load level) ---------
    top = rows[-1]
    fig, (ax_cpu, ax_mem) = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, metric, unit, label in (
        (ax_cpu, "CPU", "pct", "Average CPU (%)"),
        (ax_mem, "MEM", "MiB", "Average memory (MiB)"),
    ):
        values = [number(top[f"{s}_{metric}_avg_{unit}"]) for s in SERVICES]
        bars = ax.bar(range(len(SERVICES)), values, width=0.6,
                      color=[COLORS[s] for s in SERVICES], edgecolor="white", linewidth=2)
        for bar, value in zip(bars, values):
            ax.annotate(f"{value:.2f}", (bar.get_x() + bar.get_width() / 2, value),
                        textcoords="offset points", xytext=(0, 4), ha="center",
                        fontsize=9, color=TEXT)
        ax.set_xticks(range(len(SERVICES)))
        ax.set_xticklabels([s.replace("-service", "") for s in SERVICES], color=TEXT)
        ax.set_ylabel(label, color=TEXT)
        ax.set_title(label, loc="left", fontsize=11, fontweight="bold")
        ax.grid(True, axis="y", color=GRID)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.set_ylim(bottom=0)
    fig.suptitle(f"Resource usage per microservice at {top['Workload']} "
                 f"(concurrency {top['Concurrency']})", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")
    save(fig, "05-resource-by-service.png")

    print("Done.")


if __name__ == "__main__":
    main()
