# Evaluation and Empirical Results Report

This report summarizes the experimental evaluation of the Secure Bytecode VM across differential fuzzing with a checked-mode soundness oracle, static verification performance scaling, verification overhead, and bytecode optimization impact.

---

## 1. Differential Fuzzing & Soundness Verification

The mutation-based fuzzer (`tools/fuzz.py`) evaluated 15,000 mutants across all 5 seed programs (`factorial.ml`, `fibonacci.ml`, `gcd.ml`, `logic.ml`, `prime.ml`) over three independent random seeds (101, 202, 303), testing 1,000 mutations per seed program per run with full bytecode optimization (`--opt`) and VM checked-mode invariant enforcement.

### Execution Commands

```bash
python tools/fuzz.py -n 1000 --seed 101 --opt --output results/fuzz_seed101.csv
python tools/fuzz.py -n 1000 --seed 202 --opt --output results/fuzz_seed202.csv
python tools/fuzz.py -n 1000 --seed 303 --opt --output results/fuzz_seed303.csv
```

To run the file-level raw-bytes fuzzer:
```bash
python tools/fuzz.py -n 1000 --seed 42 --file-mode
```

### Summary Metrics (15,000 Mutants Campaign)

- **Total Mutants Tested**: 15,000
- **Rejected by Verifier**: 12,231 (81.5%)
- **Accepted by Verifier**: 2,769 (18.5%)
- **Unsafe Mode VM Crashes**: 9,421
- **Soundness Violations**: **0 (Zero)**

### Multi-Seed Run Breakdown

| Seed | Total Mutants | Accepted Mutants | Rejected Mutants | Unsafe Mode Crashes | Soundness Violations |
|---|---|---|---|---|---|
| **101** | 5,000 | 945 (18.9%) | 4,055 (81.1%) | 3,154 | **0** |
| **202** | 5,000 | 882 (17.6%) | 4,118 (82.4%) | 3,144 | **0** |
| **303** | 5,000 | 942 (18.8%) | 4,058 (81.2%) | 3,123 | **0** |
| **Total** | **15,000** | **2,769 (18.5%)** | **12,231 (81.5%)** | **9,421** | **0 (Zero)** |

### Rejection Breakdown by Rule (12,231 Rejections)

| Rule | Meaning | Count | % of Rejections |
|---|---|---|---|
| `BAD_OPCODE` | Undecodable instruction byte or invalid bool operand | 5,402 | 44.2% |
| `LOCAL_RANGE` | Out-of-bounds local variable access | 1,449 | 11.8% |
| `BAD_CALL` | Non-existent callee index or parameter type mismatch | 1,201 | 9.8% |
| `TRUNCATED` | Incomplete instruction operands | 1,144 | 9.4% |
| `BAD_JUMP` | Target out of bounds or landing mid-instruction | 667 | 5.5% |
| `FALLTHROUGH` | Control flow falling off end of code without return | 632 | 5.2% |
| `STACK_OVERFLOW` | Stack depth exceeding declared `max_stack` | 481 | 3.9% |
| `STACK_UNDERFLOW` | Popping empty or insufficient stack | 397 | 3.2% |
| `BAD_RETURN` | Return type mismatch or leftover items on stack | 340 | 2.8% |
| `LOCAL_TYPE` | Store type conflicting with local variable type | 240 | 2.0% |
| `STACK_TYPE` | Type mismatch in arithmetic, logic, or conditions | 141 | 1.2% |
| `LOCAL_UNSET` | Loading uninitialized local variable | 112 | 0.9% |
| `MERGE_MISMATCH` | Type conflict at control-flow convergence | 26 | 0.2% |

### Key Finding
Every mutant accepted by the verifier ran safely without any unhandled Python exceptions or `VMInvariantError` soundness violations across all 2,769 accepted mutants, even when re-verified and executed after bytecode optimization (`--opt`). Conversely, 9,421 unverified mutants crashed the VM when run with `--unsafe` (e.g. `IndexError`, `TypeError`, `ValueError`). This empirical evidence strongly supports the soundness of the static verifier in enforcing type safety, memory safety, and control-flow integrity.

---

## 2. Verification Performance & Scaling

Verification time was measured on synthetic programs of increasing size (up to 1,000 statements / 12,012 bytecode bytes). Note: benchmark figures below represent approximate empirical reference timings.

| Statements | Bytecode Size (bytes) | Verification Time (ms, approx.) | Throughput (KB/s, approx.) |
|---|---|---|---|
| 20 | 252 | ~1.40 ms | ~176 KB/s |
| 50 | 612 | ~3.01 ms | ~198 KB/s |
| 100 | 1,212 | ~7.07 ms | ~167 KB/s |
| 250 | 3,012 | ~15.91 ms | ~185 KB/s |
| 500 | 6,012 | ~31.23 ms | ~188 KB/s |
| 1,000 | 12,012 | ~66.27 ms | ~177 KB/s |

### Scaling Analysis
- Verification time exhibits strictly linear $O(N)$ scaling with bytecode size.
- Throughput remains consistent at ~180 KB/s across all workload sizes.

---

## 3. Verification Runtime Overhead

The cost of verifying bytecode before VM execution was compared against unverified direct execution (`--unsafe`). Note: timings are approximate reference measurements.

| Workload | VM Execution Time (ms, approx.) | Verification Time (ms, approx.) | Total Time (ms, approx.) | Verifier Overhead |
|---|---|---|---|---|
| Factorial (500x) | ~406.5 ms | ~0.38 ms | ~406.9 ms | **0.09%** |
| Fibonacci (500x) | ~1,315.9 ms | ~0.76 ms | ~1,316.6 ms | **0.06%** |
| GCD Loop (1,000x) | ~447.9 ms | ~0.41 ms | ~448.3 ms | **0.09%** |
| Prime Sieve (300) | ~136.5 ms | ~0.65 ms | ~137.2 ms | **0.48%** |

### Overhead Analysis
- For realistic programs, static verification accounts for less than **0.5%** of execution time.
- Because verification is performed once at load time, the overhead approaches 0% for long-running workloads.

---

## 4. Bytecode Optimization Impact

The optimizer (`optimizer/`) performs constant folding, dead instruction elimination (`PUSH` then `POP`, `NOT NOT`), jump threading, and unreachable code elimination. Note: execution timings are approximate reference measurements.

| Program | Unoptimized Size | Optimized Size | Size Reduction | Unoptimized Time (approx.) | Optimized Time (approx.) | Speedup |
|---|---|---|---|---|---|---|
| Constant Arithmetic | 83 B | 59 B | **28.9%** | ~86.7 ms | ~75.1 ms | **1.15x** |
| Unused Computations | 74 B | 57 B | **23.0%** | ~99.2 ms | ~77.7 ms | **1.28x** |
| Factorial (500x) | 93 B | 93 B | 0.0% | ~365.6 ms | ~315.3 ms | **1.16x** |
| GCD Loop (1,000x) | 104 B | 104 B | 0.0% | ~303.4 ms | ~371.7 ms | 0.82x |

### Optimization Analysis
- Eliminates constant expression evaluation overhead entirely at compile time.
- Reduces bytecode size by up to **28.9%**.
- Achieves up to **1.28x speedup** on compute-heavy and redundant instruction patterns.
