# Fuzzing and Soundness Evaluation

## Overview

A mutation-based differential fuzzer (`tools/fuzz.py`) was developed to evaluate the robustness of the static bytecode verifier and test the soundness of the execution guarantees.

The fuzzer operates across three dimensions:
1. **Instruction Mutations**: Bit flips, byte substitutions, opcode swaps, truncation, byte insertion, and byte deletion.
2. **Control Flow Mutations**: Branch target corruption, out-of-range jumps, and jumps landing mid-instruction.
3. **Metadata Mutations**: Stack depth tampering (`max_stack`), locals tampering (`num_locals`), and invalid entry functions.

## Results Summary

A campaign of 250 mutants across all 5 seed programs (`factorial.ml`, `fibonacci.ml`, `gcd.ml`, `logic.ml`, `prime.ml`) produced the following results:

- **Total Mutants Tested**: 250
- **Rejected by Verifier**: 206 (82.4%)
- **Accepted by Verifier**: 44 (17.6%)
- **Unsafe Mode VM Crashes**: 165
- **Soundness Violations**: **0 (Zero)**

### Rule Rejection Distribution

| Rule | Rejection Count | Percentage |
|---|---|---|
| `BAD_OPCODE` | 113 | 54.9% |
| `LOCAL_RANGE` | 21 | 10.2% |
| `TRUNCATED` | 16 | 7.8% |
| `FALLTHROUGH` | 16 | 7.8% |
| `BAD_JUMP` | 12 | 5.8% |
| `BAD_CALL` | 11 | 5.3% |
| `STACK_OVERFLOW` | 5 | 2.4% |
| `STACK_UNDERFLOW` | 5 | 2.4% |
| `STACK_TYPE` | 4 | 1.9% |
| `BAD_RETURN` | 3 | 1.5% |

## Soundness Findings

Every mutant accepted by the static verifier executed safely in the VM without encountering any raw Python runtime exceptions (such as `IndexError`, `TypeError`, or memory corruption).

Conversely, when unverified mutants rejected by the verifier were executed in `--unsafe` mode:
- 165 mutants caused catastrophic unhandled VM failures (`IndexError: pop from empty list`, `IndexError: list assignment index out of range`, `TypeError`, or `ValueError`).
- This confirms that the verifier successfully isolates and prevents genuine vulnerabilities that would otherwise compromise execution safety.
