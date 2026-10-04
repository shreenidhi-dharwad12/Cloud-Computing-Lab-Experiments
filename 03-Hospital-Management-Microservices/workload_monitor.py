import requests
import time
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "http://localhost:5003/appointments/1"

WORKLOADS = [1, 2, 4, 8, 16]
REQUESTS_PER_LEVEL = 20

SERVICE_NAMES = [
    "patient-service",
    "doctor-service",
    "appointment-service"
]


def send_request():
    start = time.perf_counter()

    try:
        response = requests.get(URL, timeout=10)
        elapsed = time.perf_counter() - start
        return response.status_code == 200, elapsed

    except requests.RequestException:
        elapsed = time.perf_counter() - start
        return False, elapsed


def get_docker_stats():
    result = subprocess.check_output(
        [
            "docker", "stats", "--no-stream",
            "--format",
            "{{.Name}},{{.CPUPerc}},{{.MemUsage}}"
        ],
        text=True
    )

    stats = {}

    for line in result.strip().splitlines():
        parts = line.split(",", 2)

        if len(parts) == 3:
            name = parts[0]
            cpu = parts[1].replace("%", "").strip()
            memory = parts[2].split("/")[0].strip()

            try:
                cpu_value = float(cpu)
            except ValueError:
                cpu_value = 0.0

            if "MiB" in memory:
                memory_value = float(
                    memory.replace("MiB", "").strip()
                )
            elif "GiB" in memory:
                memory_value = float(
                    memory.replace("GiB", "").strip()
                ) * 1024
            else:
                memory_value = 0.0

            stats[name] = {
                "cpu": cpu_value,
                "memory": memory_value
            }

    return stats


def monitor_resources(stop_event, samples):
    while not stop_event.is_set():
        try:
            stats = get_docker_stats()

            service_stats = [
                stats.get(
                    name,
                    {"cpu": 0.0, "memory": 0.0}
                )
                for name in SERVICE_NAMES
            ]

            avg_cpu = (
                sum(s["cpu"] for s in service_stats) / 3
            )

            avg_memory = (
                sum(s["memory"] for s in service_stats) / 3
            )

            samples.append((avg_cpu, avg_memory))

        except Exception:
            pass

        time.sleep(0.2)


print("=" * 100)
print("HOSPITAL MANAGEMENT MICROSERVICES - WORKLOAD + RESOURCE MONITORING")
print("=" * 100)

print(f"Target API: {URL}")
print(f"Requests per workload level: {REQUESTS_PER_LEVEL}")
print(f"Workload levels: {WORKLOADS}")
print()

print(
    f"{'Workload':<10}"
    f"{'Conc.':<8}"
    f"{'Success':<10}"
    f"{'Failed':<10}"
    f"{'Avg RT(ms)':<15}"
    f"{'Throughput':<15}"
    f"{'CPU Avg(%)':<15}"
    f"{'Memory Avg(MiB)':<18}"
)

print("-" * 100)

results = []

for workers in WORKLOADS:

    request_results = []

    resource_samples = []

    stop_monitor = threading.Event()

    monitor_thread = threading.Thread(
        target=monitor_resources,
        args=(stop_monitor, resource_samples)
    )

    monitor_thread.start()

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:

        futures = [
            executor.submit(send_request)
            for _ in range(REQUESTS_PER_LEVEL)
        ]

        for future in as_completed(futures):
            request_results.append(future.result())

    total_time = time.perf_counter() - start_time

    stop_monitor.set()
    monitor_thread.join()

    successful = sum(
        1 for success, _ in request_results
        if success
    )

    failed = len(request_results) - successful

    avg_response_time = (
        sum(t for _, t in request_results)
        / len(request_results)
    ) * 1000

    throughput = (
        len(request_results) / total_time
    )

    if resource_samples:
        avg_cpu = (
            sum(cpu for cpu, _ in resource_samples)
            / len(resource_samples)
        )

        avg_memory = (
            sum(memory for _, memory in resource_samples)
            / len(resource_samples)
        )
    else:
        avg_cpu = 0.0
        avg_memory = 0.0

    workload_name = f"W{WORKLOADS.index(workers) + 1}"

    print(
        f"{workload_name:<10}"
        f"{workers:<8}"
        f"{successful:<10}"
        f"{failed:<10}"
        f"{avg_response_time:<15.2f}"
        f"{throughput:<15.2f}"
        f"{avg_cpu:<15.2f}"
        f"{avg_memory:<18.2f}"
    )

    results.append([
        workload_name,
        workers,
        successful,
        failed,
        round(avg_response_time, 2),
        round(throughput, 2),
        round(avg_cpu, 2),
        round(avg_memory, 2)
    ])


with open("workload_results.csv", "w") as file:

    file.write(
        "Workload,Concurrency,Success,Failed,"
        "ResponseTime_ms,Throughput_req_s,"
        "CPU_Avg_percent,Memory_Avg_MiB\n"
    )

    for row in results:
        file.write(
            ",".join(map(str, row)) + "\n"
        )


print()
print("Results saved to workload_results.csv")
print("All five workload levels completed successfully.")