import requests
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "http://localhost:5003/appointments/1"
WORKLOADS = [1, 2, 4, 8, 16]
REQUESTS_PER_LEVEL = 20


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
            cpu = parts[1].replace("%", "")
            memory = parts[2].split("/")[0].strip()

            stats[name] = {
                "cpu": float(cpu),
                "memory": memory
            }

    return stats


print("=" * 90)
print("HOSPITAL MANAGEMENT MICROSERVICES - WORKLOAD + RESOURCE MONITORING")
print("=" * 90)

print(
    f"{'Workload':<10}"
    f"{'Conc.':<8}"
    f"{'Success':<10}"
    f"{'Failed':<10}"
    f"{'Avg RT(ms)':<13}"
    f"{'Throughput':<13}"
    f"{'CPU Avg(%)':<13}"
    f"{'Memory Avg':<15}"
)

print("-" * 90)

results = []

for workers in WORKLOADS:

    request_results = []

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(send_request)
            for _ in range(REQUESTS_PER_LEVEL)
        ]

        for future in as_completed(futures):
            request_results.append(future.result())

    total_time = time.perf_counter() - start_time

    successful = sum(1 for success, _ in request_results if success)
    failed = len(request_results) - successful

    avg_response_time = (
        sum(t for _, t in request_results)
        / len(request_results)
    ) * 1000

    throughput = len(request_results) / total_time

    stats = get_docker_stats()

    service_stats = [
        stats.get("patient-service", {"cpu": 0, "memory": "0MiB"}),
        stats.get("doctor-service", {"cpu": 0, "memory": "0MiB"}),
        stats.get("appointment-service", {"cpu": 0, "memory": "0MiB"})
    ]

    avg_cpu = sum(s["cpu"] for s in service_stats) / 3

    memory_values = []

    for s in service_stats:
        memory = s["memory"]

        if "MiB" in memory:
            memory_values.append(float(memory.replace("MiB", "").strip()))
        elif "GiB" in memory:
            memory_values.append(
                float(memory.replace("GiB", "").strip()) * 1024
            )

    avg_memory = sum(memory_values) / len(memory_values)

    print(
        f"W{WORKLOADS.index(workers) + 1:<9}"
        f"{workers:<8}"
        f"{successful:<10}"
        f"{failed:<10}"
        f"{avg_response_time:<13.2f}"
        f"{throughput:<13.2f}"
        f"{avg_cpu:<13.2f}"
        f"{avg_memory:.2f} MiB"
    )

    results.append([
        f"W{WORKLOADS.index(workers) + 1}",
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
        "ResponseTime_ms,Throughput_req_s,CPU_Avg_percent,"
        "Memory_Avg_MiB\n"
    )

    for row in results:
        file.write(",".join(map(str, row)) + "\n")


print()
print("Results saved to workload_results.csv")
print("All five workload levels completed.")