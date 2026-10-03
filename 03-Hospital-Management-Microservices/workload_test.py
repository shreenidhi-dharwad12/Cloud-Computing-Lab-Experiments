import requests
import time
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


print("=" * 70)
print("HOSPITAL MANAGEMENT MICROSERVICES - WORKLOAD TEST")
print("=" * 70)
print(f"Target API: {URL}")
print(f"Requests per workload: {REQUESTS_PER_LEVEL}")
print()

print(
    f"{'Workload':<12}"
    f"{'Requests':<10}"
    f"{'Success':<10}"
    f"{'Failed':<10}"
    f"{'Avg RT (ms)':<15}"
    f"{'Throughput (req/s)':<20}"
)

print("-" * 70)

for workers in WORKLOADS:

    results = []

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(send_request)
            for _ in range(REQUESTS_PER_LEVEL)
        ]

        for future in as_completed(futures):
            results.append(future.result())

    total_time = time.perf_counter() - start_time

    successful = sum(1 for success, _ in results if success)
    failed = len(results) - successful

    average_response_time = (
        sum(elapsed for _, elapsed in results) / len(results)
    )

    throughput = len(results) / total_time

    print(
        f"{workers:<12}"
        f"{len(results):<10}"
        f"{successful:<10}"
        f"{failed:<10}"
        f"{average_response_time * 1000:<15.2f}"
        f"{throughput:<20.2f}"
    )

print()
print("Workload levels completed: 1, 2, 4, 8, 16")