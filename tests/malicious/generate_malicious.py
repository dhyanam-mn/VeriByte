"""Generate crafted malicious .bc files for all 13 verifier rules."""

import struct
from pathlib import Path

from codegen.generator import BCFunction
from codegen.opcodes import Op
from codegen.serializer import BCModule, write_bytecode
from verifier import verify, VerifyError


def push_int(v: int) -> bytes:
    return bytes([Op.PUSH_INT]) + struct.pack("<i", v)


def push_bool(v: bool) -> bytes:
    return bytes([Op.PUSH_BOOL, 1 if v else 0])


def pop() -> bytes:
    return bytes([Op.POP])


def dup() -> bytes:
    return bytes([Op.DUP])


def add() -> bytes:
    return bytes([Op.ADD])


def and_() -> bytes:
    return bytes([Op.AND])


def load(idx: int) -> bytes:
    return bytes([Op.LOAD]) + struct.pack("<H", idx)


def store(idx: int) -> bytes:
    return bytes([Op.STORE]) + struct.pack("<H", idx)


def jmp(target: int) -> bytes:
    return bytes([Op.JMP]) + struct.pack("<H", target)


def jmp_if_false(target: int) -> bytes:
    return bytes([Op.JMP_IF_FALSE]) + struct.pack("<H", target)


def call(func_idx: int) -> bytes:
    return bytes([Op.CALL]) + struct.pack("<H", func_idx)


def ret() -> bytes:
    return bytes([Op.RET])


def make_fn(name="main", param_types=None, return_type="int",
            num_locals=None, local_types=None, max_stack=10, code=b"") -> BCFunction:
    param_types = param_types or []
    if local_types is None:
        local_types = list(param_types)
    if num_locals is None:
        num_locals = len(local_types)
    return BCFunction(name, param_types, return_type, num_locals, local_types, max_stack, code)


def make_module(functions=None, entry_func=0) -> BCModule:
    if functions is None:
        functions = [make_fn(code=push_int(0) + ret())]
    return BCModule(version=1, entry_func=entry_func, functions=functions)


def build_malicious_files(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        # 1. BAD_OPCODE
        "bad_opcode_1.bc": (
            make_module([make_fn(code=bytes([0xEE]) + push_int(0) + ret())]),
            "BAD_OPCODE",
            "Unknown opcode byte 0xEE"
        ),
        "bad_opcode_2.bc": (
            make_module([make_fn(code=bytes([Op.PUSH_BOOL, 2]) + pop() + push_int(0) + ret())]),
            "BAD_OPCODE",
            "PUSH_BOOL with invalid operand 2 (must be 0 or 1)"
        ),

        # 2. TRUNCATED
        "truncated_1.bc": (
            make_module([make_fn(code=bytes([Op.PUSH_INT, 0x01, 0x02]))]),
            "TRUNCATED",
            "PUSH_INT instruction truncated (needs 4 operand bytes, has 2)"
        ),
        "truncated_2.bc": (
            make_module([make_fn(code=push_int(0) + bytes([Op.STORE, 0x00]))]),
            "TRUNCATED",
            "STORE instruction truncated (needs 2 operand bytes, has 1)"
        ),

        # 3. BAD_JUMP
        "bad_jump_1.bc": (
            make_module([make_fn(code=jmp(100) + push_int(0) + ret())]),
            "BAD_JUMP",
            "JMP target 100 exceeds code bounds"
        ),
        "bad_jump_2.bc": (
            make_module([make_fn(code=push_int(42) + jmp(2) + ret())]),
            "BAD_JUMP",
            "JMP target 2 jumps into the middle of PUSH_INT operand"
        ),

        # 4. STACK_UNDERFLOW
        "stack_underflow_1.bc": (
            make_module([make_fn(code=pop() + push_int(0) + ret())]),
            "STACK_UNDERFLOW",
            "POP executed on empty operand stack"
        ),
        "stack_underflow_2.bc": (
            make_module([make_fn(code=push_int(1) + add() + ret())]),
            "STACK_UNDERFLOW",
            "ADD requires 2 stack operands, but only 1 is present"
        ),

        # 5. STACK_OVERFLOW
        "stack_overflow_1.bc": (
            make_module([make_fn(max_stack=1, code=push_int(1) + push_int(2) + pop() + ret())]),
            "STACK_OVERFLOW",
            "Second PUSH_INT causes stack depth 2 to exceed declared max_stack=1"
        ),
        "stack_overflow_2.bc": (
            make_module([make_fn(max_stack=2, code=push_int(1) + dup() + dup() + pop() + pop() + ret())]),
            "STACK_OVERFLOW",
            "Second DUP causes stack depth 3 to exceed declared max_stack=2"
        ),

        # 6. STACK_TYPE
        "stack_type_1.bc": (
            make_module([make_fn(code=push_bool(True) + push_int(1) + add() + ret())]),
            "STACK_TYPE",
            "ADD executed with bool and int operands (expects [int, int])"
        ),
        "stack_type_2.bc": (
            make_module([make_fn(code=push_int(1) + push_int(2) + and_() + pop() + push_int(0) + ret())]),
            "STACK_TYPE",
            "AND executed with int operands (expects [bool, bool])"
        ),

        # 7. MERGE_MISMATCH
        "merge_mismatch_1.bc": (
            make_module([make_fn(code=push_bool(True) + jmp_if_false(10) + push_int(1) + ret())]),
            "MERGE_MISMATCH",
            "Control flow join at RET has stack depth 1 from then-branch, depth 0 from else-branch"
        ),
        "merge_mismatch_2.bc": (
            make_module([make_fn(code=(push_bool(True) + jmp_if_false(13) +
                                       push_int(1) + jmp(15) +
                                       push_bool(False) + ret()))]),
            "MERGE_MISMATCH",
            "Control flow join at RET has stack slot 0 type int from then-branch, bool from else-branch"
        ),

        # 8. LOCAL_RANGE
        "local_range_1.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"], code=load(10) + ret())]),
            "LOCAL_RANGE",
            "LOAD accessed local index 10 when num_locals=1"
        ),
        "local_range_2.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"], code=push_int(0) + store(10) + push_int(0) + ret())]),
            "LOCAL_RANGE",
            "STORE accessed local index 10 when num_locals=1"
        ),

        # 9. LOCAL_TYPE
        "local_type_1.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"], code=push_bool(True) + store(0) + push_int(0) + ret())]),
            "LOCAL_TYPE",
            "STORE popped bool value into local 0 declared as int"
        ),
        "local_type_2.bc": (
            make_module([make_fn(num_locals=1, local_types=["bool"], code=push_int(42) + store(0) + push_int(0) + ret())]),
            "LOCAL_TYPE",
            "STORE popped int value into local 0 declared as bool"
        ),

        # 10. LOCAL_UNSET
        "local_unset_1.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"], code=load(0) + ret())]),
            "LOCAL_UNSET",
            "LOAD accessed local 0 before it was assigned (UNSET)"
        ),
        "local_unset_2.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"],
                                code=(push_bool(True) + jmp_if_false(13) +
                                      push_int(42) + store(0) +
                                      load(0) + ret()))]),
            "LOCAL_UNSET",
            "LOAD accessed local 0 which is UNSET along the false branch"
        ),

        # 11. BAD_CALL
        "bad_call_1.bc": (
            make_module([make_fn(code=call(10) + ret())]),
            "BAD_CALL",
            "CALL target function index 10 does not exist in function table"
        ),
        "bad_call_2.bc": (
            make_module([
                make_fn(name="main", return_type="int", code=push_int(42) + call(1) + ret()),
                make_fn(name="helper", param_types=["bool"], return_type="int",
                        num_locals=1, local_types=["bool"], code=push_int(0) + ret()),
            ]),
            "BAD_CALL",
            "CALL passed argument of type int to function expecting bool"
        ),

        # 12. BAD_RETURN
        "bad_return_1.bc": (
            make_module([make_fn(return_type="int", code=push_bool(True) + ret())]),
            "BAD_RETURN",
            "RET returned bool when function is declared to return int"
        ),
        "bad_return_2.bc": (
            make_module([
                make_fn(name="main", return_type="int", code=push_int(0) + ret()),
                make_fn(name="helper", return_type="bool", code=push_int(42) + ret()),
            ]),
            "BAD_RETURN",
            "RET in helper returned int when helper is declared to return bool"
        ),

        # 13. FALLTHROUGH
        "fallthrough_1.bc": (
            make_module([make_fn(num_locals=1, local_types=["int"], code=push_int(42) + store(0))]),
            "FALLTHROUGH",
            "Code falls off the end of instruction stream without RET, JMP, or HALT"
        ),
        "fallthrough_2.bc": (
            make_module([make_fn(code=push_bool(True) + jmp_if_false(0))]),
            "FALLTHROUGH",
            "JMP_IF_FALSE falls through past the end of the code stream"
        ),
    }

    readme_lines = [
        "# Malicious Bytecode Test Suite",
        "",
        "This directory contains crafted `.bc` bytecode files designed to test every static verifier rule.",
        "Each file isolates and violates exactly one rule from `docs/VERIFIER_DESIGN.md`.",
        "",
        "| File | Expected Rule | Description |",
        "|---|---|---|",
    ]

    for fname, (mod, rule, desc) in sorted(files.items()):
        fpath = output_dir / fname
        write_bytecode(fpath, mod.functions, mod.entry_func)

        # Verify that it indeed triggers the expected rule
        try:
            verify(mod)
            raise AssertionError(f"Expected {fname} to fail with {rule}, but verification passed!")
        except VerifyError as e:
            assert e.rule == rule, f"{fname}: expected {rule}, got {e.rule}: {e}"

        readme_lines.append(f"| `{fname}` | `{rule}` | {desc} |")

    readme_path = output_dir / "README.md"
    readme_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    print(f"Generated {len(files)} malicious bytecode files and README.md in {output_dir}")


if __name__ == "__main__":
    build_malicious_files(Path(__file__).parent)
