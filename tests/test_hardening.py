"""Regression and hardening tests for bug fixes and robustness improvements."""

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from minilang.errors import LexError
from minilang.lexer import tokenize
from minilang.parser import parse
from semantic import SemanticError, analyze
from codegen import (
    generate, serialize, load_bytecode,
    BCFunction, BCModule, BytecodeFormatError, Op,
)
from codegen.generator import _FuncBuilder, _Label
from semantic.symtab import SymbolTable
from vm import VM, verify
from tools.fuzz import run_fuzzer


class TestHardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_malformed_ascii_func_name_in_loader(self):
        """Malformed non-ASCII function name in .bc file must raise BytecodeFormatError."""
        # Construct header: SBVM, version 1, num_funcs 1, entry_func 0
        data = bytearray(b"SBVM\x01\x01\x00\x00\x00")
        # func[0]: name_len 2, non-ASCII bytes 0xFF 0xFE
        data.extend(b"\x02\xff\xfe")
        # params: 0
        data.append(0)
        # ret: int (0)
        data.append(0)
        # locals: 0
        data.extend(b"\x00\x00")
        # max_stack: 1
        data.extend(b"\x01\x00")
        # code: 0 bytes
        data.extend(b"\x00\x00\x00\x00")

        bc_path = self.tmp / "bad_name.bc"
        bc_path.write_bytes(data)

        with self.assertRaises(BytecodeFormatError) as ctx:
            load_bytecode(bc_path)
        self.assertIn("invalid ASCII function name", str(ctx.exception))

    def test_cli_handles_bytecode_format_error_cleanly(self):
        """CLI commands (verify, run, disasm, optimize) print one-line error and exit 1 on malformed file."""
        bc_path = self.tmp / "corrupt.bc"
        bc_path.write_bytes(b"NOT_A_VALID_BYTECODE_FILE")

        for subcmd in ["verify", "run", "disasm", "optimize"]:
            res = subprocess.run(
                [sys.executable, "svm.py", subcmd, str(bc_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 1, f"subcmd {subcmd} should exit 1")
            self.assertTrue(
                "error:" in res.stderr or "bad magic" in res.stderr,
                f"subcmd {subcmd} should output clean error: {res.stderr}",
            )

    def test_jump_into_instruction_middle_rejected_before_opt(self):
        """A jump into the middle of an instruction passed to run --opt or optimize is rejected by verifier first."""
        # Create function with PUSH_INT 10 (5 bytes: 0x01 0x0A 0x00 0x00 0x00), then JMP 2 (into offset 2)
        code = bytearray()
        code.append(Op.PUSH_INT.value)
        code.extend(struct.pack("<i", 10))  # offsets 1..4
        code.append(Op.JMP.value)           # offset 5
        code.extend(struct.pack("<H", 2))   # offset 6..7 -> jumps to offset 2!
        code.append(Op.RET.value)           # offset 8

        fn = BCFunction(
            name="main",
            param_types=[],
            return_type="int",
            num_locals=0,
            local_types=[],
            max_stack=2,
            code=bytes(code),
        )
        mod_bytes = serialize([fn], 0)
        bc_path = self.tmp / "bad_jump.bc"
        bc_path.write_bytes(mod_bytes)

        # svm.py run --opt bad_jump.bc
        res_run = subprocess.run(
            [sys.executable, "svm.py", "run", str(bc_path), "--opt"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_run.returncode, 1)
        self.assertIn("verification failed", res_run.stderr)
        self.assertIn("BAD_JUMP", res_run.stderr)

        # svm.py optimize bad_jump.bc
        res_opt = subprocess.run(
            [sys.executable, "svm.py", "optimize", str(bc_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_opt.returncode, 1)
        self.assertIn("verification failed", res_opt.stderr)

    def test_serializer_validations(self):
        """serialize raises clear ValueError for name > 255 bytes, non-ASCII name, params > 255, or jump target > 65535."""
        # Long name > 255 bytes
        long_name = "a" * 256
        fn_long = BCFunction(long_name, [], "int", 0, [], 1, b"")
        with self.assertRaises(ValueError) as ctx:
            serialize([fn_long], 0)
        self.assertIn("exceeds 255 bytes", str(ctx.exception))

        # Non-ASCII name
        fn_unicode = BCFunction("f\u00fc", [], "int", 0, [], 1, b"")
        with self.assertRaises(ValueError) as ctx:
            serialize([fn_unicode], 0)
        self.assertIn("not valid ASCII", str(ctx.exception))

        # Params > 255
        many_params = ["int"] * 256
        fn_many_params = BCFunction("foo", many_params, "int", 256, many_params, 1, b"")
        with self.assertRaises(ValueError) as ctx:
            serialize([fn_many_params], 0)
        self.assertIn("parameter count exceeds 255", str(ctx.exception))

        # Jump target > 65535 via jump_targets attribute
        fn_bad_jump = BCFunction("main", [], "int", 0, [], 1, b"", jump_targets=[70000])
        with self.assertRaises(ValueError) as ctx:
            serialize([fn_bad_jump], 0)
        self.assertIn("jump target 70000 exceeds 65535", str(ctx.exception))

        # Jump target > 65535 via patch_jumps in generator
        builder = _FuncBuilder({"main": 0}, SymbolTable())
        lbl = builder.new_label()
        builder.emit_jump(Op.JMP, lbl)
        lbl.offset = 70000
        with self.assertRaises(ValueError) as ctx:
            builder.patch_jumps()
        self.assertIn("exceeds 16-bit max", str(ctx.exception))

    def test_integer_literal_bounds_and_min_int(self):
        """Reject literals > 2147483647; allow -2147483648 and run it successfully."""
        # > 2147483647
        src_over = "func main(): int { let x: int = 2147483648; return x; }"
        with self.assertRaises(SemanticError) as ctx:
            analyze(parse(src_over))
        self.assertIn("exceeds 32-bit signed max 2147483647", str(ctx.exception))

        src_over2 = "func main(): int { return 9999999999; }"
        with self.assertRaises(SemanticError) as ctx:
            analyze(parse(src_over2))
        self.assertIn("exceeds 32-bit signed max 2147483647", str(ctx.exception))

        # Underflow beyond -2147483648
        src_under = "func main(): int { let x: int = -2147483649; return x; }"
        with self.assertRaises(SemanticError) as ctx:
            analyze(parse(src_under))
        self.assertIn("exceeds 32-bit signed max 2147483647", str(ctx.exception))

        # Exactly -2147483648 allowed
        src_min = "func main(): int { let x: int = -2147483648; return x; }"
        prog = parse(src_min)
        st = analyze(prog)
        fns = generate(prog, st)
        mod = BCModule(version=1, entry_func=0, functions=fns)
        verify(mod)
        vm = VM()
        ret = vm.run(mod)
        self.assertEqual(ret, -2147483648)

    def test_lexer_ascii_only_validation(self):
        """Non-ASCII characters in identifiers or numbers are rejected by lexer."""
        # Unicode accented letter
        with self.assertRaises(LexError):
            tokenize("func caf\u00e9(): int { return 0; }")

        # Greek letter identifier
        with self.assertRaises(LexError):
            tokenize("let \u03b1: int = 1;")

        # Unicode superscript digit
        with self.assertRaises(LexError):
            tokenize("let x: int = 1\u00b2;")

        # Arabic-indic digit
        with self.assertRaises(LexError):
            tokenize("let x: int = \u0661;")

    def test_fuzz_with_opt_no_crashes(self):
        """Fuzz run including --opt verifies and executes with 0 soundness bugs."""
        records, summary = run_fuzzer(
            examples_dir=Path("examples"),
            num_mutations=30,
            seed=12345,
            opt=True,
        )
        self.assertEqual(summary["soundness_violations"], 0)
        self.assertGreater(summary["total"], 0)


if __name__ == "__main__":
    unittest.main()
