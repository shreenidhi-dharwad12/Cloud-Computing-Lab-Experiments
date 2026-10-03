import matplotlib.pyplot as plt

# ============================================================
# FINAL WORKLOAD TEST RESULTS
# ============================================================

workload = [1, 2, 4, 8, 16]

# Average response time in milliseconds
response_time = [20.93, 28.37, 35.10, 52.45, 79.88]

# Throughput in requests per second
throughput = [46.95, 65.68, 107.66, 127.87, 133.20]

# Average CPU utilization in percentage
cpu = [0.03, 0.03, 0.03, 0.03, 0.04]

# Average memory usage in MiB
memory = [24.15, 24.04, 24.11, 24.09, 24.23]


# ============================================================
# GRAPH 1: CONCURRENT REQUESTS VS RESPONSE TIME
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    workload,
    response_time,
    marker="o"
)

plt.xlabel("Concurrent Requests")
plt.ylabel("Average Response Time (ms)")
plt.title("Concurrent Requests vs Average Response Time")

plt.grid(True)
plt.tight_layout()

plt.savefig(
    "graphs/01-response-time.png",
    dpi=200
)

plt.close()


# ============================================================
# GRAPH 2: CONCURRENT REQUESTS VS THROUGHPUT
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    workload,
    throughput,
    marker="o"
)

plt.xlabel("Concurrent Requests")
plt.ylabel("Throughput (requests/second)")
plt.title("Concurrent Requests vs Throughput")

plt.grid(True)
plt.tight_layout()

plt.savefig(
    "graphs/02-throughput.png",
    dpi=200
)

plt.close()


# ============================================================
# GRAPH 3: CONCURRENT REQUESTS VS CPU UTILIZATION
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    workload,
    cpu,
    marker="o"
)

plt.xlabel("Concurrent Requests")
plt.ylabel("Average CPU Utilization (%)")
plt.title("Concurrent Requests vs CPU Utilization")

plt.grid(True)
plt.tight_layout()

plt.savefig(
    "graphs/03-cpu-utilization.png",
    dpi=200
)

plt.close()


# ============================================================
# GRAPH 4: CONCURRENT REQUESTS VS MEMORY UTILIZATION
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    workload,
    memory,
    marker="o"
)

plt.xlabel("Concurrent Requests")
plt.ylabel("Average Memory Usage (MiB)")
plt.title("Concurrent Requests vs Memory Utilization")

plt.grid(True)
plt.tight_layout()

plt.savefig(
    "graphs/04-memory-utilization.png",
    dpi=200
)

plt.close()


# ============================================================
# COMPLETION MESSAGE
# ============================================================

print("=" * 60)
print("ALL 4 GRAPHS GENERATED SUCCESSFULLY!")
print("=" * 60)

print()
print("Generated files:")

print("1. graphs/01-response-time.png")
print("2. graphs/02-throughput.png")
print("3. graphs/03-cpu-utilization.png")
print("4. graphs/04-memory-utilization.png")

print()
print("Using final W1-W5 workload measurements.")