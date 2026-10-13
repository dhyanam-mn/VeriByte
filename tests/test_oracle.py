"""Tests for verifier module header, loop back-edge LOCAL_UNSET, VM checked mode invariants, and soundness oracle meta-test."""

import io
import struct
import unittest
from pathlib import Path

from codegen.generator import BCFunction
from codegen.opcodes import Op
from codegen.serializer import BCModule
from tools.fuzz import run_fuzzer
from verifier import verify, VerifyError
import verifier.verifier as verifier_mod
from vm import VM, VMInvariantError, VMTrap


# Helper builders
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


class TestModuleHeaderVerification(unittest.TestCase):
    """Test module-level header checks in verify_module_header."""

    def test_empty_functions_list(self):
        mod = make_module(functions=[])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "BAD_CALL")

    def test_entry_func_out_of_range(self):
        mod = make_module(functions=[make_fn(code=push_int(0) + ret())], entry_func=1)
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "BAD_CALL")

    def test_entry_func_not_named_main(self):
        fn = make_fn(name="start", code=push_int(0) + ret())
        mod = make_module(functions=[fn])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "BAD_CALL")

    def test_entry_func_params_or_return_mismatch(self):
        fn = make_fn(name="main", param_types=["int"], code=push_int(0) + ret())
        mod = make_module(functions=[fn])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "BAD_CALL")

    def test_local_types_length_mismatch(self):
        fn = make_fn(num_locals=2, local_types=["int"], code=push_int(0) + ret())
        mod = make_module(functions=[fn])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "LOCAL_RANGE")

    def test_num_locals_less_than_params(self):
        fn = BCFunction(
            name="helper",
            param_types=["int", "int"],
            return_type="int",
            num_locals=1,
            local_types=["int"],
            max_stack=10,
            code=push_int(0) + ret(),
        )
        mod = make_module(functions=[make_fn(code=push_int(0) + ret()), fn])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "LOCAL_RANGE")

    def test_param_types_do_not_match_initial_local_types(self):
        fn = BCFunction(
            name="helper",
            param_types=["int"],
            return_type="int",
            num_locals=1,
            local_types=["bool"],
            max_stack=10,
            code=push_int(0) + ret(),
        )
        mod = make_module(functions=[make_fn(code=push_int(0) + ret()), fn])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "LOCAL_TYPE")


class TestLoopBackEdgeLocalUnset(unittest.TestCase):
    """Test loop back-edge where a local is loaded inside a loop but unset on back-edge or entry."""

    def test_loop_back_edge_unset(self):
        # Local 0 is uninitialized initially.
        # Loop body at offset 0:
        # 0: LOAD 0  (fails: on first entry local 0 is UNSET)
        # 3: POP
        # 4: PUSH_INT 10
        # 9: STORE 0
        # 12: JMP 0  (on backedge local 0 is int, but merge with initial entry -> CONFLICT/UNSET)
        code = load(0) + pop() + push_int(10) + store(0) + jmp(0)
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        with self.assertRaises(VerifyError) as ctx:
            verify(mod)
        self.assertEqual(ctx.exception.rule, "LOCAL_UNSET")


class TestVMCheckedModeInvariants(unittest.TestCase):
    """Test that VM(checked=True) raises VMInvariantError for all soundness invariants."""

    def test_arithmetic_operands_must_be_int(self):
        # Push bool then ADD
        code = push_bool(True) + push_int(1) + add() + ret()
        fn = make_fn(code=code)
        mod = make_module([fn])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operands for ADD must be int", str(ctx.exception))

    def test_arithmetic_sub_operands_must_be_int(self):
        code = push_int(1) + push_bool(False) + sub() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError):
            vm.run(mod)

    def test_comparison_operands_must_be_int(self):
        code = push_bool(True) + push_int(1) + lt() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operands for LT must be int", str(ctx.exception))

    def test_logic_operands_must_be_bool(self):
        code = push_int(1) + push_bool(True) + and_() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operands for AND must be bool", str(ctx.exception))

    def test_not_operand_must_be_bool(self):
        code = push_int(1) + not_() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operand for NOT must be bool", str(ctx.exception))

    def test_jmp_if_false_condition_must_be_bool(self):
        code = push_int(1) + jmp_if_false(8) + push_int(0) + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("JMP_IF_FALSE condition must be bool", str(ctx.exception))

    def test_eq_operand_types_must_match(self):
        code = push_int(1) + push_bool(True) + eq() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operands for EQ must have matching types", str(ctx.exception))

    def test_ne_operand_types_must_match(self):
        code = push_int(1) + push_bool(True) + ne() + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("operands for NE must have matching types", str(ctx.exception))

    def test_load_uninitialized_local_raises_invariant_error(self):
        code = load(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("LOAD from uninitialized local slot", str(ctx.exception))

    def test_load_out_of_range_local_raises_invariant_error(self):
        code = load(5) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("local index 5 >= num_locals 1", str(ctx.exception))

    def test_store_wrong_type_raises_invariant_error(self):
        code = push_bool(True) + store(0) + push_int(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("STORE to local slot 0 expected int, got bool", str(ctx.exception))

    def test_store_out_of_range_local_raises_invariant_error(self):
        code = push_int(42) + store(3) + push_int(0) + ret()
        mod = make_module([make_fn(num_locals=1, local_types=["int"], code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("local index 3 >= num_locals 1", str(ctx.exception))

    def test_stack_depth_exceeds_max_stack(self):
        # max_stack = 1, but we push 2 items
        code = push_int(1) + push_int(2) + add() + ret()
        mod = make_module([make_fn(max_stack=1, code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("exceeds max_stack 1", str(ctx.exception))

    def test_ret_wrong_stack_depth(self):
        # RET with 2 items on stack
        code = push_int(1) + push_int(2) + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("does not leave exactly one value", str(ctx.exception))

    def test_ret_wrong_return_type(self):
        # Expects int, returns bool
        code = push_bool(True) + ret()
        mod = make_module([make_fn(return_type="int", code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("RET in main expected int, got bool", str(ctx.exception))

    def test_pc_not_instruction_start(self):
        # Jump into middle of PUSH_INT (e.g. target 2)
        code = jmp(2) + push_int(42) + ret()
        mod = make_module([make_fn(code=code)])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("is not a valid instruction start", str(ctx.exception))

    def test_call_argument_type_mismatch(self):
        callee = make_fn(
            name="helper",
            param_types=["bool"],
            return_type="int",
            num_locals=1,
            local_types=["bool"],
            code=push_int(0) + ret(),
        )
        main_code = push_int(42) + call(1) + ret()
        mod = make_module([make_fn(name="main", code=main_code), callee])
        vm = VM(checked=True)
        with self.assertRaises(VMInvariantError) as ctx:
            vm.run(mod)
        self.assertIn("CALL arg 0 to helper expected bool, got int", str(ctx.exception))

    def test_call_depth_exceeded_raises_vmtrap(self):
        # Infinite recursion
        fn = make_fn(name="main", code=call(0) + ret())
        mod = make_module([fn])
        vm = VM(max_call_depth=50)
        with self.assertRaises(VMTrap) as ctx:
            vm.run(mod)
        self.assertIn("call depth exceeded", str(ctx.exception))


class TestSoundnessOracleMetaTest(unittest.TestCase):
    """Test that weakening the verifier produces a detectable soundness violation via VM(checked=True)."""

    def test_weakened_verifier_soundness_violation(self):
        # Create a module that pushes bool and int then ADDs them
        bad_code = push_bool(True) + push_int(5) + add() + ret()
        mod = make_module([make_fn(code=bad_code)])

        # Normally, verifier catches this
        with self.assertRaises(VerifyError):
            verify(mod)

        # When weakened by disabling CHECK_STACK_TYPE_ADD:
        old_val = verifier_mod.CHECK_STACK_TYPE_ADD
        try:
            verifier_mod.CHECK_STACK_TYPE_ADD = False
            # Verifier now accepts it!
            verify(mod)

            # VM in checked mode MUST catch the soundness violation!
            vm = VM(stdout=io.StringIO(), checked=True)
            with self.assertRaises(VMInvariantError):
                vm.run(mod)
        finally:
            verifier_mod.CHECK_STACK_TYPE_ADD = old_val


if __name__ == "__main__":
    unittest.main()
