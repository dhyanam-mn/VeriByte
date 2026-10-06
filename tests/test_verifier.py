"""Comprehensive tests for the static verifier.

Tests:
1. Zero false rejects on all valid programs in examples/.
2. Hand-crafted invalid bytecode modules testing every single verifier rule (at least two tests per rule):
   - BAD_OPCODE
   - TRUNCATED
   - BAD_JUMP (out of range and mid-instruction)
   - STACK_UNDERFLOW
   - STACK_OVERFLOW
   - STACK_TYPE
   - MERGE_MISMATCH
   - LOCAL_RANGE
   - LOCAL_TYPE
   - LOCAL_UNSET
   - BAD_CALL
   - BAD_RETURN
   - FALLTHROUGH
3. CLI tests (svm.py verify, svm.py run --unsafe vs safe refusal).
"""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from minilang.parser import parse
from semantic import analyze
from codegen import generate, serialize, BCFunction, BCModule, Op
from verifier import verify, verify_function, VerifyError


# ---------------------------------------------------------------------------
# Bytecode assembly helpers
# ---------------------------------------------------------------------------

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


def sub() -> bytes:
    return bytes([Op.SUB])


def mul() -> bytes:
    return bytes([Op.MUL])


def div() -> bytes:
    return bytes([Op.DIV])


def mod() -> bytes:
    return bytes([Op.MOD])


def neg() -> bytes:
    return bytes([Op.NEG])


def and_() -> bytes:
    return bytes([Op.AND])


def or_() -> bytes:
    return bytes([Op.OR])


def not_() -> bytes:
    return bytes([Op.NOT])


def eq() -> bytes:
    return bytes([Op.EQ])


def ne() -> bytes:
    return bytes([Op.NE])


def lt() -> bytes:
    return bytes([Op.LT])


def gt() -> bytes:
    return bytes([Op.GT])


def le() -> bytes:
    return bytes([Op.LE])


def ge() -> bytes:
    return bytes([Op.GE])


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


def print_() -> bytes:
    return bytes([Op.PRINT])


def halt() -> bytes:
    return bytes([Op.HALT])


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


def assert_rule(test_case: unittest.TestCase, module: BCModule, expected_rule: str):
    with test_case.assertRaises(VerifyError) as ctx:
        verify(module)
    test_case.assertEqual(ctx.exception.rule, expected_rule,
                         f"Expected rule {expected_rule}, but got {ctx.exception.rule}:\n{ctx.exception}")


# ---------------------------------------------------------------------------
# Test Suites
# ---------------------------------------------------------------------------

class TestValidExamplesVerify(unittest.TestCase):
    """Every valid example program must verify with zero false rejects."""

    def _verify_file(self, filename: str):
        path = Path("examples") / filename
        source = path.read_text(encoding="utf-8")
        prog = parse(source)
        st = analyze(prog)
        fns = generate(prog, st)
        entry = next(i for i, f in enumerate(fns) if f.name == "main")
        module = BCModule(version=1, entry_func=entry, functions=fns)
        verify(module)

    def test_factorial(self):
        self._verify_file("factorial.ml")

    def test_fibonacci(self):
        self._verify_file("fibonacci.ml")

    def test_gcd(self):
        self._verify_file("gcd.ml")

    def test_logic(self):
        self._verify_file("logic.ml")

    def test_prime(self):
        self._verify_file("prime.ml")


class TestRuleBadOpcode(unittest.TestCase):
    """BAD_OPCODE: undecodable instruction stream."""

    def test_unknown_opcode_byte(self):
        code = bytes([0xEE]) + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_OPCODE")

    def test_invalid_bool_operand(self):
        code = bytes([Op.PUSH_BOOL, 2]) + pop() + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_OPCODE")


class TestRuleTruncated(unittest.TestCase):
    """TRUNCATED: missing operand bytes at end of stream."""

    def test_truncated_push_int(self):
        code = bytes([Op.PUSH_INT, 0x01, 0x02])  # needs 4 bytes
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "TRUNCATED")

    def test_truncated_store(self):
        code = push_int(0) + bytes([Op.STORE, 0x00])  # STORE needs 2 bytes, only 1 provided
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "TRUNCATED")


class TestRuleBadJump(unittest.TestCase):
    """BAD_JUMP: target outside code or not an instruction start."""

    def test_jump_out_of_bounds(self):
        code = jmp(100) + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_JUMP")

    def test_jump_mid_instruction(self):
        # 0: PUSH_INT 42 (5 bytes: 0..4)
        # 5: JMP 2 (target 2 is inside PUSH_INT)
        code = push_int(42) + jmp(2) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_JUMP")

    def test_jump_if_false_mid_instruction(self):
        # 0: PUSH_BOOL True (2 bytes: 0, 1)
        # 2: PUSH_INT 42 (5 bytes: 2..6)
        # 7: JMP_IF_FALSE 4 (target 4 is inside PUSH_INT)
        code = push_bool(True) + push_int(42) + jmp_if_false(4) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_JUMP")


class TestRuleStackUnderflow(unittest.TestCase):
    """STACK_UNDERFLOW: pop with too few values."""

    def test_pop_empty(self):
        code = pop() + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_UNDERFLOW")

    def test_binop_with_one_value(self):
        code = push_int(1) + add() + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_UNDERFLOW")

    def test_ret_empty(self):
        code = ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_UNDERFLOW")


class TestRuleStackOverflow(unittest.TestCase):
    """STACK_OVERFLOW: depth exceeds declared max_stack."""

    def test_push_exceeds_max_stack(self):
        code = push_int(1) + push_int(2) + pop() + ret()
        mod = make_module([make_fn(max_stack=1, code=code)])
        assert_rule(self, mod, "STACK_OVERFLOW")

    def test_dup_exceeds_max_stack(self):
        code = push_int(1) + dup() + dup() + pop() + pop() + ret()
        mod = make_module([make_fn(max_stack=2, code=code)])
        assert_rule(self, mod, "STACK_OVERFLOW")


class TestRuleStackType(unittest.TestCase):
    """STACK_TYPE: operand has the wrong type."""

    def test_add_bool_and_int(self):
        code = push_bool(True) + push_int(1) + add() + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_TYPE")

    def test_and_int_operands(self):
        code = push_int(1) + push_int(2) + and_() + pop() + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_TYPE")

    def test_jmp_if_false_int_condition(self):
        # JMP_IF_FALSE requires bool condition
        code = push_int(1) + jmp_if_false(8) + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "STACK_TYPE")


class TestRuleMergeMismatch(unittest.TestCase):
    """MERGE_MISMATCH: different stack shapes meet at a join."""

    def test_depth_mismatch_at_join(self):
        # 0: PUSH_BOOL True (2 bytes)
        # 2: JMP_IF_FALSE 10 (3 bytes: 2, 3, 4)
        # 5: PUSH_INT 1 (5 bytes: 5..9)
        # 10: RET (1 byte: 10)
        # Then-branch has depth 1, Else-branch has depth 0 at offset 10!
        code = push_bool(True) + jmp_if_false(10) + push_int(1) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "MERGE_MISMATCH")

    def test_type_mismatch_at_join(self):
        # 0: PUSH_BOOL True (2 bytes)
        # 2: JMP_IF_FALSE 13 (3 bytes)
        # 5: PUSH_INT 1 (5 bytes)
        # 10: JMP 15 (3 bytes)
        # 13: PUSH_BOOL False (2 bytes)
        # 15: RET (1 byte)
        # At offset 15, then-branch stack is [int], else-branch stack is [bool]
        code = (push_bool(True) + jmp_if_false(13) +
                push_int(1) + jmp(15) +
                push_bool(False) + ret())
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "MERGE_MISMATCH")


class TestRuleLocalRange(unittest.TestCase):
    """LOCAL_RANGE: bad local variable index."""

    def test_load_out_of_range(self):
        code = load(10) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "LOCAL_RANGE")

    def test_store_out_of_range(self):
        code = push_int(0) + store(10) + push_int(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "LOCAL_RANGE")


class TestRuleLocalType(unittest.TestCase):
    """LOCAL_TYPE: storing wrong type into a declared local."""

    def test_store_bool_into_int_local(self):
        code = push_bool(True) + store(0) + push_int(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "LOCAL_TYPE")

    def test_store_int_into_bool_local(self):
        code = push_int(42) + store(0) + push_int(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["bool"], code=code)])
        assert_rule(self, mod, "LOCAL_TYPE")


class TestRuleLocalUnset(unittest.TestCase):
    """LOCAL_UNSET: reading a local variable before it is definitely assigned."""

    def test_load_uninitialized_local(self):
        # local 0 is not a parameter, never stored, so UNSET
        code = load(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "LOCAL_UNSET")

    def test_load_partially_initialized_local(self):
        # Local 0 assigned in then-branch but not in else-branch:
        # 0: PUSH_BOOL True (2 bytes)
        # 2: JMP_IF_FALSE 13 (3 bytes)
        # 5: PUSH_INT 42 (5 bytes)
        # 10: STORE 0 (3 bytes)
        # 13: LOAD 0 (3 bytes)
        # 16: RET (1 byte)
        code = (push_bool(True) + jmp_if_false(13) +
                push_int(42) + store(0) +
                load(0) + ret())
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "LOCAL_UNSET")


class TestRuleBadCall(unittest.TestCase):
    """BAD_CALL: unknown callee or argument mismatch."""

    def test_unknown_function_index(self):
        code = call(10) + ret()
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "BAD_CALL")

    def test_call_argument_type_mismatch(self):
        # Callee expects bool, caller pushes int
        callee = make_fn(name="helper", param_types=["bool"], return_type="int",
                         num_locals=1, local_types=["bool"], code=push_int(0) + ret())
        main_code = push_int(42) + call(1) + ret()
        main_fn = make_fn(name="main", return_type="int", code=main_code)
        mod = make_module([main_fn, callee])
        assert_rule(self, mod, "BAD_CALL")


class TestRuleBadReturn(unittest.TestCase):
    """BAD_RETURN: wrong return type or leftover items on stack."""

    def test_return_bool_when_int_expected(self):
        code = push_bool(True) + ret()
        mod = make_module([make_fn(return_type="int", code=code)])
        assert_rule(self, mod, "BAD_RETURN")

    def test_return_int_when_bool_expected(self):
        callee = make_fn(name="helper", return_type="bool", code=push_int(42) + ret())
        main_fn = make_fn(name="main", return_type="int", code=push_int(0) + ret())
        mod = make_module([main_fn, callee])
        assert_rule(self, mod, "BAD_RETURN")

    def test_return_leftover_stack_items(self):
        # Stack has [int, int] at RET; should only have 1 return value
        code = push_int(1) + push_int(2) + ret()
        mod = make_module([make_fn(return_type="int", code=code)])
        assert_rule(self, mod, "BAD_RETURN")


class TestRuleFallthrough(unittest.TestCase):
    """FALLTHROUGH: code runs off the end without RET or HALT."""

    def test_fallthrough_end_of_code(self):
        # Code ends with STORE 0 without RET
        code = push_int(42) + store(0)
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        assert_rule(self, mod, "FALLTHROUGH")

    def test_fallthrough_conditional_branch(self):
        # 0: PUSH_BOOL True (2 bytes)
        # 2: JMP_IF_FALSE 0 (3 bytes)
        # Falls through to offset 5 without RET!
        code = push_bool(True) + jmp_if_false(0)
        mod = make_module([make_fn(code=code)])
        assert_rule(self, mod, "FALLTHROUGH")


class TestVerifierCLI(unittest.TestCase):
    """CLI integration tests for svm.py verify and svm.py run."""

    def test_cli_verify_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Compile factorial.ml
            subprocess.run([sys.executable, "svm.py", "compile", "examples/factorial.ml", "-o", str(tmp_path)],
                           check=True, capture_output=True)
            # Run svm.py verify
            proc = subprocess.run([sys.executable, "svm.py", "verify", str(tmp_path)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("verified", proc.stdout)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_cli_verify_invalid(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Write invalid module with BAD_OPCODE
            mod = make_module([make_fn(code=bytes([0xEE]))])
            tmp_path.write_bytes(serialize(mod.functions, mod.entry_func))
            # Run svm.py verify
            proc = subprocess.run([sys.executable, "svm.py", "verify", str(tmp_path)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("BAD_OPCODE", proc.stderr)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_cli_run_refuses_invalid_unless_unsafe(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Module with STACK_UNDERFLOW (POP on empty)
            mod = make_module([make_fn(code=pop() + push_int(0) + ret())])
            tmp_path.write_bytes(serialize(mod.functions, mod.entry_func))

            # Running safely must refuse with verification error
            proc_safe = subprocess.run([sys.executable, "svm.py", "run", str(tmp_path)],
                                       capture_output=True, text=True)
            self.assertEqual(proc_safe.returncode, 1)
            self.assertIn("STACK_UNDERFLOW", proc_safe.stderr)

            # Running with --unsafe bypasses verification (crashes VM naturally with IndexError)
            proc_unsafe = subprocess.run([sys.executable, "svm.py", "run", "--unsafe", str(tmp_path)],
                                         capture_output=True, text=True)
            self.assertNotEqual(proc_unsafe.returncode, 0)
            self.assertIn("IndexError", proc_unsafe.stderr)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
