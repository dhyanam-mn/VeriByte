"""Tests for the code generator, serializer, and disassembler."""

import io
import struct
import tempfile
from pathlib import Path
import unittest

from minilang.parser import parse
from semantic import analyze
from codegen import (
    generate, serialize, load_bytecode, write_bytecode,
    disassemble, disassemble_function, disassemble_functions,
    BCFunction, BCModule, BytecodeFormatError, Op,
)


def _compile_source(src: str):
    prog = parse(src)
    st = analyze(prog)
    fns = generate(prog, st)
    entry_func = next(i for i, f in enumerate(fns) if f.name == "main")
    return fns, entry_func


class TestSerializeDeserialize(unittest.TestCase):
    def test_roundtrip(self):
        src = """\
func add(a: int, b: int): int {
    return a + b;
}
func main(): int {
    print(add(2, 3));
    return 0;
}
"""
        fns, entry = _compile_source(src)
        raw = serialize(fns, entry)
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(raw)
            module = load_bytecode(tmp_path)
            self.assertEqual(module.version, 1)
            self.assertEqual(module.entry_func, entry)
            self.assertEqual(len(module.functions), len(fns))

            for orig, loaded in zip(fns, module.functions):
                self.assertEqual(orig.name, loaded.name)
                self.assertEqual(orig.param_types, loaded.param_types)
                self.assertEqual(orig.return_type, loaded.return_type)
                self.assertEqual(orig.num_locals, loaded.num_locals)
                self.assertEqual(orig.local_types, loaded.local_types)
                self.assertEqual(orig.max_stack, loaded.max_stack)
                self.assertEqual(orig.code, loaded.code)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_bad_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(b"NOPE" + b"\x00" * 20)
            with self.assertRaises(BytecodeFormatError) as ctx:
                load_bytecode(tmp_path)
            self.assertIn("bad magic", str(ctx.exception))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_unsupported_version(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # magic SBVM, version 2
            tmp_path.write_bytes(b"SBVM" + bytes([2]) + b"\x00" * 20)
            with self.assertRaises(BytecodeFormatError) as ctx:
                load_bytecode(tmp_path)
            self.assertIn("unsupported version", str(ctx.exception))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_truncated_header(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(b"SBV")
            with self.assertRaises(BytecodeFormatError) as ctx:
                load_bytecode(tmp_path)
            self.assertIn("truncated", str(ctx.exception))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_invalid_type_byte(self):
        # valid header, 1 function with bad param type byte 99
        data = bytearray(b"SBVM")
        data.append(1)  # version
        data.extend(struct.pack("<H", 1))  # 1 func
        data.extend(struct.pack("<H", 0))  # entry 0
        data.append(1)  # name_len
        data.extend(b"f")
        data.append(1)  # 1 param
        data.append(99)  # invalid param type
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(bytes(data))
            with self.assertRaises(BytecodeFormatError) as ctx:
                load_bytecode(tmp_path)
            self.assertIn("invalid param type", str(ctx.exception))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_entry_out_of_bounds(self):
        data = bytearray(b"SBVM")
        data.append(1)
        data.extend(struct.pack("<H", 1))  # 1 func
        data.extend(struct.pack("<H", 5))  # entry 5 >= 1
        data.append(1)
        data.extend(b"m")
        data.append(0)  # 0 params
        data.append(0)  # return int
        data.extend(struct.pack("<H", 0))  # 0 locals
        data.extend(struct.pack("<H", 0))  # max_stack 0
        data.extend(struct.pack("<I", 0))  # code_len 0
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(bytes(data))
            with self.assertRaises(BytecodeFormatError) as ctx:
                load_bytecode(tmp_path)
            self.assertIn("entry_func index", str(ctx.exception))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestGoldenDisassembly(unittest.TestCase):
    def test_factorial_disassembly(self):
        src = """\
func fact(n: int): int {
    if (n <= 1) { return 1; }
    return n * fact(n - 1);
}
func main(): int {
    print(fact(5));
    return 0;
}
"""
        fns, entry = _compile_source(src)
        dis = disassemble_functions(fns)
        expected = """\
== fact(int): int  locals=1  max_stack=3 ==
  0000  LOAD           0
  0003  PUSH_INT       1
  0008  LE
  0009  JMP_IF_FALSE   18
  0012  PUSH_INT       1
  0017  RET
  0018  LOAD           0
  0021  LOAD           0
  0024  PUSH_INT       1
  0029  SUB
  0030  CALL           0
  0033  MUL
  0034  RET

== main(): int  locals=0  max_stack=1 ==
  0000  PUSH_INT       5
  0005  CALL           0
  0008  PRINT
  0009  PUSH_INT       0
  0014  RET"""
        self.assertEqual(dis.strip(), expected.strip())

    def test_simple_program_disassembly(self):
        src = """\
func main(): int {
    let x: int = 42;
    print(x);
    return 0;
}
"""
        fns, entry = _compile_source(src)
        dis = disassemble_function(fns[0])
        expected = """\
== main(): int  locals=1  max_stack=1 ==
  0000  PUSH_INT       42
  0005  STORE          0
  0008  LOAD           0
  0011  PRINT
  0012  PUSH_INT       0
  0017  RET"""
        self.assertEqual(dis.strip(), expected.strip())


class TestJumpTargets(unittest.TestCase):
    def test_if_else_jump_targets(self):
        src = """\
func test(x: int): int {
    let r: int = 0;
    if (x > 0) {
        r = 1;
    } else {
        r = 2;
    }
    return r;
}
func main(): int { return test(1); }
"""
        fns, entry = _compile_source(src)
        fn = fns[0]
        code = fn.code

        # Let's inspect instructions by parsing opcodes
        # 0000 PUSH_INT 0
        # 0005 STORE 1 (r)
        # 0008 LOAD 0 (x)
        # 0011 PUSH_INT 0
        # 0016 GT
        # 0017 JMP_IF_FALSE <else_offset>
        # ... then body: PUSH 1, STORE 1
        # ... JMP <end_offset>
        # else_offset: PUSH 2, STORE 1
        # end_offset: LOAD 1, RET
        self.assertEqual(code[17], Op.JMP_IF_FALSE)
        else_target = struct.unpack_from("<H", code, 18)[0]
        # At else_target, opcode should be PUSH_INT
        self.assertEqual(code[else_target], Op.PUSH_INT)

        # The JMP in the then-branch precedes else_target
        jmp_op_offset = else_target - 3
        self.assertEqual(code[jmp_op_offset], Op.JMP)
        end_target = struct.unpack_from("<H", code, jmp_op_offset + 1)[0]
        # At end_target, opcode should be LOAD (loading r for return)
        self.assertEqual(code[end_target], Op.LOAD)

    def test_while_jump_targets(self):
        src = """\
func loop(n: int): int {
    let i: int = 0;
    while (i < n) {
        i = i + 1;
    }
    return i;
}
func main(): int { return loop(5); }
"""
        fns, entry = _compile_source(src)
        fn = fns[0]
        code = fn.code

        # i = 0 (PUSH 0, STORE 1) takes 8 bytes.
        # Loop condition starts at offset 8: LOAD 1 (i)
        loop_cond_start = 8
        self.assertEqual(code[loop_cond_start], Op.LOAD)

        # After LOAD 1 (8), LOAD 0 (11), LT (14) -> offset 15 is JMP_IF_FALSE
        jmp_if_false_offset = 15
        self.assertEqual(code[jmp_if_false_offset], Op.JMP_IF_FALSE)
        exit_target = struct.unpack_from("<H", code, jmp_if_false_offset + 1)[0]

        # The loop body ends with JMP back to loop_cond_start
        jmp_back_offset = exit_target - 3
        self.assertEqual(code[jmp_back_offset], Op.JMP)
        target_back = struct.unpack_from("<H", code, jmp_back_offset + 1)[0]
        self.assertEqual(target_back, loop_cond_start)

        # At exit_target, it should be LOAD 1 (for return)
        self.assertEqual(code[exit_target], Op.LOAD)


class TestMaxStack(unittest.TestCase):
    def test_nested_binary_expr(self):
        # 1 + (2 * (3 + 4)) -> evaluation depth:
        # PUSH 1 (1)
        # PUSH 2 (2)
        # PUSH 3 (3)
        # PUSH 4 (4)
        # ADD -> depth 3
        # MUL -> depth 2
        # ADD -> depth 1
        # max depth = 4
        src = """\
func main(): int {
    return 1 + (2 * (3 + 4));
}
"""
        fns, entry = _compile_source(src)
        self.assertEqual(fns[0].max_stack, 4)

    def test_call_args_max_stack(self):
        # calling add(1, 2 + 3):
        # PUSH 1 (1)
        # PUSH 2 (2)
        # PUSH 3 (3)
        # ADD -> depth 2
        # CALL -> pops 2, pushes 1
        # max stack = 3
        src = """\
func add(a: int, b: int): int { return a + b; }
func main(): int {
    return add(1, 2 + 3);
}
"""
        fns, entry = _compile_source(src)
        main_fn = fns[1]
        self.assertEqual(main_fn.max_stack, 3)

    def test_unary_and_logical(self):
        # !(true && false)
        # PUSH_BOOL (1)
        # PUSH_BOOL (2)
        # AND -> (1)
        # NOT -> (1)
        # max_stack = 2
        src = """\
func main(): int {
    let b: bool = !(true && false);
    return 0;
}
"""
        fns, entry = _compile_source(src)
        main_fn = fns[0]
        self.assertEqual(main_fn.max_stack, 2)


if __name__ == "__main__":
    unittest.main()
