#!/usr/bin/env python3
"""Benchmark suite for Secure Bytecode VM: verification scaling, verifier overhead, and optimizer impact.

Benchmarks:
1. Verification time vs bytecode size (generated programs of increasing size).
2. VM execution time with vs without static verifier (measuring verification overhead).
3. VM execution time with vs without optimizer (measuring size reduction and speedup).

Outputs:
  - Text summary tables to stdout.
  - CSV results to results/bench.csv.
  - Graphical plots to results/bench.png (using matplotlib).
"""

from __future__ import annotations

import csv
import io
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from minilang.parser import parse
from semantic import analyze
from codegen import generate, BCFunction, BCModule, Op
from optimizer import optimize_module
from verifier import verify
from vm import VM


# ---------------------------------------------------------------------------
# Benchmark 1: Verification Time vs Bytecode Size
# ---------------------------------------------------------------------------

def generate_sized_program(num_statements: int) -> str:
    """Generate a valid MiniLang program with a specified number of statements."""
    lines = ["func main(): int {", "    let s: int = 0;"]
    for i in range(num_statements):
        val = (i * 7 + 3) % 100
        lines.append(f"    s = s + {val};")
    lines.append("    return s;")
    lines.append("}")
    return "\n".join(lines)


def bench_verification_scaling(statement_counts: List[int]) -> List[Dict[str, Any]]:
    results = []
    print("\n--- 1. Verification Scaling Benchmark ---")
    print(f"{'Stmts':>8s} | {'Size (bytes)':>14s} | {'Verify Time (ms)':>18s} | {'Throughput (KB/s)':>18s}")
    print("-" * 66)

    for count in statement_counts:
        src = generate_sized_program(count)
        prog = parse(src)
        st = analyze(prog)
        fns = generate(prog, st)
        entry = next(i for i, f in enumerate(fns) if f.name == "main")
        mod = BCModule(version=1, entry_func=entry, functions=fns)

        total_bytes = sum(len(f.code) for f in mod.functions)

        # Warm-up
        verify(mod)

        # Timed runs
        iterations = 20 if count < 1000 else 5
        start_ns = time.perf_counter_ns()
        for _ in range(iterations):
            verify(mod)
        elapsed_ms = (time.perf_counter_ns() - start_ns) / (iterations * 1_000_000)

        throughput_kb_s = (total_bytes / 1024) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

        print(f"{count:>8d} | {total_bytes:>14d} | {elapsed_ms:>18.4f} | {throughput_kb_s:>18.1f}")

        results.append({
            "category": "verification_scaling",
            "name": f"scale_{count}_stmts",
            "statements": count,
            "bytecode_bytes": total_bytes,
            "verify_time_ms": elapsed_ms,
            "throughput_kb_s": throughput_kb_s,
        })

    return results


# ---------------------------------------------------------------------------
# Benchmark 2: VM Run Time With vs Without Verifier
# ---------------------------------------------------------------------------

BENCHMARK_PROGRAMS = {
    "Factorial": """\
func fact(n: int): int {
    if (n <= 1) { return 1; }
    return n * fact(n - 1);
}
func main(): int {
    let i: int = 0;
    let r: int = 0;
    while (i < 500) {
        r = fact(10);
        i = i + 1;
    }
    return r;
}
""",
    "Fibonacci": """\
func fib(n: int): int {
    let a: int = 0;
    let b: int = 1;
    let i: int = 0;
    while (i < n) {
        let t: int = a + b;
        a = b;
        b = t;
        i = i + 1;
    }
    return a;
}
func main(): int {
    let i: int = 0;
    let r: int = 0;
    while (i < 500) {
        r = fib(25);
        i = i + 1;
    }
    return r;
}
""",
    "GCD Loop": """\
func gcd(a: int, b: int): int {
    while (b != 0) {
        let t: int = b;
        b = a % b;
        a = t;
    }
    return a;
}
func main(): int {
    let i: int = 0;
    let r: int = 0;
    while (i < 1000) {
        r = gcd(1071, 462);
        i = i + 1;
    }
    return r;
}
""",
    "Prime Sieve": """\
func is_prime(n: int): bool {
    if (n < 2) { return false; }
    let d: int = 2;
    while (d * d <= n) {
        if (n % d == 0) { return false; }
        d = d + 1;
    }
    return true;
}
func main(): int {
    let count: int = 0;
    let k: int = 2;
    while (k < 300) {
        if (is_prime(k)) { count = count + 1; }
        k = k + 1;
    }
    return count;
}
""",
}


def bench_verifier_overhead() -> List[Dict[str, Any]]:
    results = []
    print("\n--- 2. VM Run Time With vs Without Verifier ---")
    print(f"{'Program':<14s} | {'VM Only (ms)':>14s} | {'Verify (ms)':>14s} | {'Total (ms)':>14s} | {'Overhead (%)':>14s}")
    print("-" * 76)

    devnull = io.StringIO()

    for name, src in BENCHMARK_PROGRAMS.items():
        prog = parse(src)
        st = analyze(prog)
        fns = generate(prog, st)
        entry = next(i for i, f in enumerate(fns) if f.name == "main")
        mod = BCModule(version=1, entry_func=entry, functions=fns)

        # Warm-up
        VM(stdout=devnull).run(mod)
        verify(mod)

        # Measure verification time
        v_runs = 20
        v_start = time.perf_counter_ns()
        for _ in range(v_runs):
            verify(mod)
        v_time_ms = (time.perf_counter_ns() - v_start) / (v_runs * 1_000_000)

        # Measure VM execution time without verification
        r_runs = 10
        r_start = time.perf_counter_ns()
        for _ in range(r_runs):
            VM(stdout=devnull).run(mod)
        vm_time_ms = (time.perf_counter_ns() - r_start) / (r_runs * 1_000_000)

        total_with_verify = vm_time_ms + v_time_ms
        overhead_pct = (v_time_ms / vm_time_ms) * 100 if vm_time_ms > 0 else 0

        print(f"{name:<14s} | {vm_time_ms:>14.3f} | {v_time_ms:>14.4f} | {total_with_verify:>14.3f} | {overhead_pct:>13.2f}%")

        results.append({
            "category": "verifier_overhead",
            "name": name,
            "vm_time_ms": vm_time_ms,
            "verify_time_ms": v_time_ms,
            "total_time_ms": total_with_verify,
            "overhead_pct": overhead_pct,
        })

    return results


# ---------------------------------------------------------------------------
# Benchmark 3: With vs Without Optimizer
# ---------------------------------------------------------------------------

OPTIMIZER_PROGRAMS = {
    "Constant Arithmetic": """\
func main(): int {
    let i: int = 0;
    let acc: int = 0;
    while (i < 1000) {
        acc = acc + (1 + 2 * 3 - (4 + 5));
        i = i + 1;
    }
    return acc;
}
""",
    "Unused Computations": """\
func main(): int {
    let i: int = 0;
    let s: int = 0;
    while (i < 1000) {
        100 + 200;
        !(!true);
        s = s + i;
        i = i + 1;
    }
    return s;
}
""",
    "Factorial (500x)": BENCHMARK_PROGRAMS["Factorial"],
    "GCD Loop (1000x)": BENCHMARK_PROGRAMS["GCD Loop"],
}


def bench_optimizer_impact() -> List[Dict[str, Any]]:
    results = []
    print("\n--- 3. With vs Without Optimizer ---")
    print(f"{'Program':<22s} | {'Unopt (B)':>10s} | {'Opt (B)':>8s} | {'Saved (%)':>10s} | {'Unopt (ms)':>11s} | {'Opt (ms)':>9s} | {'Speedup':>9s}")
    print("-" * 88)

    devnull = io.StringIO()

    for name, src in OPTIMIZER_PROGRAMS.items():
        prog = parse(src)
        st = analyze(prog)
        fns = generate(prog, st)
        entry = next(i for i, f in enumerate(fns) if f.name == "main")
        mod_unopt = BCModule(version=1, entry_func=entry, functions=fns)
        mod_opt = optimize_module(mod_unopt)

        size_unopt = sum(len(f.code) for f in mod_unopt.functions)
        size_opt = sum(len(f.code) for f in mod_opt.functions)
        size_saved_pct = ((size_unopt - size_opt) / size_unopt) * 100 if size_unopt > 0 else 0

        # Measure run time unoptimized
        runs = 10
        t0 = time.perf_counter_ns()
        for _ in range(runs):
            VM(stdout=devnull).run(mod_unopt)
        time_unopt = (time.perf_counter_ns() - t0) / (runs * 1_000_000)

        # Measure run time optimized
        t1 = time.perf_counter_ns()
        for _ in range(runs):
            VM(stdout=devnull).run(mod_opt)
        time_opt = (time.perf_counter_ns() - t1) / (runs * 1_000_000)

        speedup = time_unopt / time_opt if time_opt > 0 else 1.0

        print(f"{name:<22s} | {size_unopt:>10d} | {size_opt:>8d} | {size_saved_pct:>9.1f}% | {time_unopt:>11.3f} | {time_opt:>9.3f} | {speedup:>8.2f}x")

        results.append({
            "category": "optimizer_impact",
            "name": name,
            "unopt_bytes": size_unopt,
            "opt_bytes": size_opt,
            "size_saved_pct": size_saved_pct,
            "unopt_time_ms": time_unopt,
            "opt_time_ms": time_opt,
            "speedup": speedup,
        })

    return results


# ---------------------------------------------------------------------------
# Plotting & CSV Export
# ---------------------------------------------------------------------------

def save_csv_results(all_results: List[Dict[str, Any]], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    all_keys = set()
    for row in all_results:
        all_keys.update(row.keys())
    fieldnames = ["category", "name"] + sorted(k for k in all_keys if k not in ("category", "name"))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
    print(f"\nSaved benchmark results to {out_path}")


def generate_plots(scaling: List[Dict[str, Any]],
                   overhead: List[Dict[str, Any]],
                   optimizer: List[Dict[str, Any]],
                   out_path: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[Notice] matplotlib is not available; skipping plot generation.")
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.patch.set_facecolor("#f8f9fa")

    # Plot 1: Verification Time vs Bytecode Size
    ax1 = axes[0]
    sizes = [row["bytecode_bytes"] for row in scaling]
    v_times = [row["verify_time_ms"] for row in scaling]
    ax1.plot(sizes, v_times, marker="o", color="#1f77b4", linewidth=2, markersize=6)
    ax1.set_title("Verification Time vs Bytecode Size", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Bytecode Size (bytes)", fontsize=10)
    ax1.set_ylabel("Verification Time (ms)", fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.6)

    # Plot 2: VM Execution vs Verification Overhead
    ax2 = axes[1]
    prog_names = [row["name"] for row in overhead]
    vm_times = [row["vm_time_ms"] for row in overhead]
    ver_times = [row["verify_time_ms"] for row in overhead]
    x_indices = range(len(prog_names))
    width = 0.35

    ax2.bar([x - width/2 for x in x_indices], vm_times, width=width, label="VM Runtime", color="#2ca02c")
    ax2.bar([x + width/2 for x in x_indices], ver_times, width=width, label="Verifier Time", color="#d62728")
    ax2.set_xticks(list(x_indices))
    ax2.set_xticklabels(prog_names, rotation=15, ha="right", fontsize=9)
    ax2.set_title("VM Runtime vs Verification Time", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Time (ms)", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.6, axis="y")

    # Plot 3: Optimizer Speedup & Bytecode Reduction
    ax3 = axes[2]
    opt_names = [row["name"] for row in optimizer]
    unopt_ms = [row["unopt_time_ms"] for row in optimizer]
    opt_ms = [row["opt_time_ms"] for row in optimizer]
    x_indices3 = range(len(opt_names))

    ax3.bar([x - width/2 for x in x_indices3], unopt_ms, width=width, label="Unoptimized", color="#7f7f7f")
    ax3.bar([x + width/2 for x in x_indices3], opt_ms, width=width, label="Optimized", color="#ff7f0e")
    ax3.set_xticks(list(x_indices3))
    ax3.set_xticklabels(opt_names, rotation=15, ha="right", fontsize=9)
    ax3.set_title("Execution Time: Unopt vs Opt", fontsize=12, fontweight="bold")
    ax3.set_ylabel("Execution Time (ms)", fontsize=10)
    ax3.legend(fontsize=9)
    ax3.grid(True, linestyle="--", alpha=0.6, axis="y")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"Saved benchmark plot to {out_path}")


def main():
    statement_counts = [20, 50, 100, 250, 500, 1000]

    scaling_results = bench_verification_scaling(statement_counts)
    overhead_results = bench_verifier_overhead()
    optimizer_results = bench_optimizer_impact()

    all_results = scaling_results + overhead_results + optimizer_results

    csv_path = Path("results/bench.csv")
    png_path = Path("results/bench.png")

    save_csv_results(all_results, csv_path)
    generate_plots(scaling_results, overhead_results, optimizer_results, png_path)


if __name__ == "__main__":
    main()
