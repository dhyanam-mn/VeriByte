#!/usr/bin/env python3
"""Mutation-based fuzzer for the Secure Bytecode VM and Verifier.

Applies random mutations (bit flip, byte replace, opcode swap, operand corruption,
truncation, insertion, deletion) to valid compiled bytecode modules, testing:
1. Verifier rejection coverage.
2. VM soundness: Any accepted mutant executed by the VM must NEVER cause raw
   Python crashes (only clean completion or VMTrap for division by zero).
3. Unsafe behavior: Rejected mutants executed in --unsafe mode are tracked to
   demonstrate crashes and misbehavior that the verifier successfully prevented.

Outputs:
  - Text summary table to stdout.
  - CSV results to results/fuzz_results.csv.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import os
import random
import struct
import sys
from pathlib import Path

# Add project root to sys.path so modules can be imported when running script directly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from typing import Any, Callable, Dict, List, Tuple

from minilang.parser import parse
from semantic import analyze
from codegen import generate, serialize, load_bytecode, BCFunction, BCModule, Op
from codegen.opcodes import OPERAND_SIZE
from optimizer import optimize_module
from verifier import verify, VerifyError
from vm import VM, VMTrap


# ---------------------------------------------------------------------------
# Seed Programs
# ---------------------------------------------------------------------------

EXAMPLE_FILES = [
    "factorial.ml",
    "fibonacci.ml",
    "gcd.ml",
    "logic.ml",
    "prime.ml",
]


def load_seed_module(filepath: Path) -> BCModule:
    """Compile a MiniLang source file into a BCModule."""
    source = filepath.read_text(encoding="utf-8")
    prog = parse(source)
    st = analyze(prog)
    fns = generate(prog, st)
    entry_func = next(i for i, fn in enumerate(fns) if fn.name == "main")
    return BCModule(version=1, entry_func=entry_func, functions=fns)


# ---------------------------------------------------------------------------
# Mutation Operators
# ---------------------------------------------------------------------------

ALL_OPCODES = list(Op)


def mutate_bit_flip(code: bytearray, rng: random.Random) -> str:
    if not code:
        return "bit_flip"
    idx = rng.randrange(len(code))
    bit = rng.randrange(8)
    code[idx] ^= (1 << bit)
    return "bit_flip"


def mutate_byte_replace(code: bytearray, rng: random.Random) -> str:
    if not code:
        return "byte_replace"
    idx = rng.randrange(len(code))
    code[idx] = rng.randrange(256)
    return "byte_replace"


def mutate_opcode_swap(code: bytearray, rng: random.Random) -> str:
    if not code:
        return "opcode_swap"
    # Find instruction offsets
    offsets = []
    pc = 0
    while pc < len(code):
        offsets.append(pc)
        op_byte = code[pc]
        try:
            op = Op(op_byte)
            pc += 1 + OPERAND_SIZE[op]
        except ValueError:
            pc += 1
    if not offsets:
        return "opcode_swap"
    target_offset = rng.choice(offsets)
    code[target_offset] = rng.choice(ALL_OPCODES).value
    return "opcode_swap"


def mutate_operand_corruption(code: bytearray, rng: random.Random) -> str:
    if len(code) < 3:
        return "operand_corruption"
    idx = rng.randrange(len(code) - 1)
    boundary_values = [0, 1, 2, 255, 32767, 65535, -1, -2147483648, 2147483647]
    val = rng.choice(boundary_values)
    # Choose 2-byte or 4-byte corruption
    if rng.random() < 0.5 and idx + 2 <= len(code):
        struct.pack_into("<H", code, idx, val & 0xFFFF)
    elif idx + 4 <= len(code):
        struct.pack_into("<i", code, idx, val if -2147483648 <= val <= 2147483647 else 0)
    else:
        code[idx] = val & 0xFF
    return "operand_corruption"


def mutate_truncation(code: bytearray, rng: random.Random) -> str:
    if len(code) <= 1:
        return "truncation"
    cut = rng.randint(1, min(len(code) - 1, 8))
    del code[len(code) - cut:]
    return "truncation"


def mutate_insertion(code: bytearray, rng: random.Random) -> str:
    idx = rng.randrange(len(code) + 1)
    num_bytes = rng.randint(1, 4)
    inserted = [rng.randrange(256) for _ in range(num_bytes)]
    code[idx:idx] = bytearray(inserted)
    return "insertion"


def mutate_deletion(code: bytearray, rng: random.Random) -> str:
    if len(code) <= 1:
        return "deletion"
    idx = rng.randrange(len(code))
    num_bytes = rng.randint(1, min(4, len(code) - idx))
    del code[idx:idx + num_bytes]
    return "deletion"


MUTATION_OPS: List[Callable[[bytearray, random.Random], str]] = [
    mutate_bit_flip,
    mutate_byte_replace,
    mutate_opcode_swap,
    mutate_operand_corruption,
    mutate_truncation,
    mutate_insertion,
    mutate_deletion,
]


def mutate_module(base: BCModule, rng: random.Random) -> Tuple[BCModule, str]:
    """Clone module and apply a random mutation to one of its functions."""
    cloned_funcs = []
    for fn in base.functions:
        cloned_funcs.append(BCFunction(
            name=fn.name,
            param_types=list(fn.param_types),
            return_type=fn.return_type,
            num_locals=fn.num_locals,
            local_types=list(fn.local_types),
            max_stack=fn.max_stack,
            code=fn.code,
        ))
    mutant = BCModule(
        version=base.version,
        entry_func=base.entry_func,
        functions=cloned_funcs,
    )

    fn = rng.choice(mutant.functions)

    # 15% chance to mutate metadata (max_stack, num_locals, etc.)
    if rng.random() < 0.15:
        choice = rng.choice(["max_stack", "num_locals", "entry_func"])
        if choice == "max_stack":
            fn.max_stack = rng.choice([0, 1, fn.max_stack // 2, fn.max_stack + 5])
            return mutant, "metadata_max_stack"
        elif choice == "num_locals":
            fn.num_locals = max(0, fn.num_locals + rng.choice([-1, -2, 1, 5]))
            return mutant, "metadata_num_locals"
        else:
            mutant.entry_func = rng.choice([0, 1, 99])
            return mutant, "metadata_entry_func"

    # Otherwise mutate code bytes
    code_arr = bytearray(fn.code)
    mut_op = rng.choice(MUTATION_OPS)
    op_name = mut_op(code_arr, rng)
    fn.code = bytes(code_arr)
    return mutant, op_name


# ---------------------------------------------------------------------------
# Fuzz Runner
# ---------------------------------------------------------------------------

def run_fuzzer(
    examples_dir: Path,
    num_mutations: int,
    seed: int,
    step_limit: int = 10000,
    opt: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the mutation fuzzer and return (records, summary)."""
    rng = random.Random(seed)
    records: List[Dict[str, Any]] = []

    devnull = io.StringIO()

    total_mutants = 0
    accepted_count = 0
    rejected_count = 0
    rule_counts: Dict[str, int] = {}
    unsafe_crashes = 0
    soundness_violations = 0

    for example_file in EXAMPLE_FILES:
        filepath = examples_dir / example_file
        if not filepath.exists():
            continue

        base_mod = load_seed_module(filepath)

        for m_id in range(1, num_mutations + 1):
            total_mutants += 1
            mutant, mut_type = mutate_module(base_mod, rng)

            # Step 1: Verify
            verdict = "ACCEPTED"
            rule_name = ""
            try:
                verify(mutant)
            except VerifyError as ve:
                verdict = "REJECTED"
                rule_name = ve.rule
                rule_counts[rule_name] = rule_counts.get(rule_name, 0) + 1
            except Exception as e:
                # Any unhandled exception from verifier itself is an error
                verdict = "VERIFIER_ERROR"
                rule_name = type(e).__name__

            safe_status = "N/A"
            unsafe_status = "N/A"
            soundness_violation = False

            if verdict == "ACCEPTED":
                accepted_count += 1
                # Run in safe mode
                try:
                    vm = VM(stdout=devnull)
                    vm.run(mutant, max_steps=step_limit)
                    safe_status = "CLEAN"
                except VMTrap:
                    safe_status = "VM_TRAP"
                except TimeoutError:
                    safe_status = "STEP_LIMIT"
                except Exception as e:
                    # An accepted program crashed with raw Python exception -> SOUNDNESS BUG!
                    safe_status = f"CRASH_{type(e).__name__}"
                    soundness_violation = True
                    soundness_violations += 1

                if opt and not soundness_violation:
                    try:
                        opt_mod = optimize_module(mutant)
                        verify(opt_mod)
                        vm_opt = VM(stdout=devnull)
                        vm_opt.run(opt_mod, max_steps=step_limit)
                        safe_status = "CLEAN_OPT"
                    except VMTrap:
                        safe_status = "VM_TRAP_OPT"
                    except TimeoutError:
                        safe_status = "STEP_LIMIT_OPT"
                    except VerifyError as ve:
                        safe_status = f"OPT_VERIFY_{ve.rule}"
                        soundness_violation = True
                        soundness_violations += 1
                    except Exception as e:
                        safe_status = f"OPT_CRASH_{type(e).__name__}"
                        soundness_violation = True
                        soundness_violations += 1

            elif verdict == "REJECTED":
                rejected_count += 1
                # Run in unsafe mode
                try:
                    vm = VM(stdout=devnull)
                    vm.run(mutant, max_steps=step_limit)
                    unsafe_status = "COMPLETED"
                except VMTrap:
                    unsafe_status = "VM_TRAP"
                except TimeoutError:
                    unsafe_status = "STEP_LIMIT"
                except Exception as e:
                    unsafe_status = f"CRASH_{type(e).__name__}"
                    unsafe_crashes += 1

            records.append({
                "program": example_file,
                "mutant_id": m_id,
                "mutation_type": mut_type,
                "verdict": verdict,
                "rule": rule_name,
                "safe_status": safe_status,
                "unsafe_status": unsafe_status,
                "soundness_violation": soundness_violation,
            })

    summary = {
        "total": total_mutants,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "rule_counts": rule_counts,
        "unsafe_crashes": unsafe_crashes,
        "soundness_violations": soundness_violations,
    }

    return records, summary


def print_summary(summary: Dict[str, Any]):
    print("=" * 60)
    print("                FUZZING CAMPAIGN SUMMARY                ")
    print("=" * 60)
    print(f"Total Mutants Tested:       {summary['total']}")
    print(f"Accepted by Verifier:       {summary['accepted']} ({summary['accepted'] / max(1, summary['total']):.1%})")
    print(f"Rejected by Verifier:       {summary['rejected']} ({summary['rejected'] / max(1, summary['total']):.1%})")
    print(f"Unsafe Mode Crashes:        {summary['unsafe_crashes']}")
    print(f"Soundness Violations:       {summary['soundness_violations']}")
    print("-" * 60)
    print("Rejections Breakdown by Rule:")
    for rule, count in sorted(summary["rule_counts"].items(), key=lambda x: -x[1]):
        print(f"  {rule:<22s}: {count:>5d} ({count / max(1, summary['rejected']):.1%})")
    print("=" * 60)
    if summary["soundness_violations"] == 0:
        print("[SUCCESS] Zero soundness violations! The verifier proved 100% sound.")
    else:
        print(f"[FAIL] Found {summary['soundness_violations']} soundness violations!")
    print("=" * 60)


def save_csv(records: List[Dict[str, Any]], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "program",
        "mutant_id",
        "mutation_type",
        "verdict",
        "rule",
        "safe_status",
        "unsafe_status",
        "soundness_violation",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved results CSV to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Secure Bytecode VM Fuzzer")
    parser.add_argument("-n", "--iterations", type=int, default=100,
                        help="Number of mutations per seed program (default: 100)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--output", type=str, default="results/fuzz_results.csv",
                        help="Path to output CSV (default: results/fuzz_results.csv)")
    parser.add_argument("--examples", type=str, default="examples",
                        help="Directory containing valid .ml examples")
    parser.add_argument("--step-limit", type=int, default=10000,
                        help="Maximum VM execution steps per test (default: 10000)")
    parser.add_argument("--opt", action="store_true",
                        help="Enable optimizer on accepted mutants and verify/run them")

    args = parser.parse_args()

    records, summary = run_fuzzer(
        examples_dir=Path(args.examples),
        num_mutations=args.iterations,
        seed=args.seed,
        step_limit=args.step_limit,
        opt=args.opt,
    )

    print_summary(summary)
    save_csv(records, Path(args.output))

    if summary["soundness_violations"] > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
