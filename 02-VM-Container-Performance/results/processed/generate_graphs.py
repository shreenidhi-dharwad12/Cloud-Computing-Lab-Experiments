import os
import pandas as pd
import matplotlib.pyplot as plt

os.makedirs("results/figures", exist_ok=True)

df = pd.read_csv("results/data/benchmark_results.csv")

# CPU comparison
plt.figure(figsize=(8,5))
plt.bar(["VM", "Container"], [df.loc[0, "VM"], df.loc[0, "Container"]])
plt.title("CPU Performance Comparison")
plt.ylabel("Events per Second")
plt.tight_layout()
plt.savefig("results/figures/01-cpu-comparison.png", dpi=200)
plt.close()

# Network comparison
plt.figure(figsize=(8,5))
plt.bar(["VM", "Container"], [df.loc[1, "VM"], df.loc[1, "Container"]])
plt.title("Network Throughput Comparison")
plt.ylabel("Gbit/sec")
plt.tight_layout()
plt.savefig("results/figures/02-network-comparison.png", dpi=200)
plt.close()

# Container memory result
plt.figure(figsize=(8,5))
plt.bar(["Container"], [df.loc[2, "Container"]])
plt.title("Container Memory Performance")
plt.ylabel("MiB/sec")
plt.tight_layout()
plt.savefig("results/figures/03-container-memory-performance.png", dpi=200)
plt.close()

print("=" * 55)
print("GRAPHS GENERATED SUCCESSFULLY")
print("=" * 55)
print("1. results/figures/01-cpu-comparison.png")
print("2. results/figures/02-network-comparison.png")
print("3. results/figures/03-container-memory-performance.png")
