"""Tests for the Bytecode Virtual Machine (interpreter)."""

import io
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from minilang.parser import parse
from semantic import analyze
from codegen import generate, write_bytecode, load_bytecode, BCFunction, BCModule, Op
from vm import VM, VMTrap, to_i32, idiv, imod


def _run_source(src: str, stdout: io.StringIO | None = None) -> tuple[int, str]:
    """Helper to compile and run MiniLang source in-memory."""
    prog = parse(src)
    st = analyze(prog)
    fns = generate(prog, st)
    entry_func = next(i for i, f in enumerate(fns) if f.name == "main")
    module = BCModule(version=1, entry_func=entry_func, functions=fns)

    out = stdout if stdout is not None else io.StringIO()
    vm = VM(stdout=out)
    ret = vm.run(module)
    return ret, out.getvalue()


class TestEndToEndExamples(unittest.TestCase):
    """Compile and run every valid example file and assert exact printed output."""

    def test_factorial(self):
        path = Path("examples/factorial.ml")
        ret, out = _run_source(path.read_text(encoding="utf-8"))
        self.assertEqual(ret, 0)
        self.assertEqual(out, "120\n")

    def test_fibonacci(self):
        path = Path("examples/fibonacci.ml")
        ret, out = _run_source(path.read_text(encoding="utf-8"))
        self.assertEqual(ret, 0)
        self.assertEqual(out, "55\n")

    def test_gcd(self):
        path = Path("examples/gcd.ml")
        ret, out = _run_source(path.read_text(encoding="utf-8"))
        self.assertEqual(ret, 0)
        self.assertEqual(out, "6\n")

    def test_prime(self):
        path = Path("examples/prime.ml")
        ret, out = _run_source(path.read_text(encoding="utf-8"))
        self.assertEqual(ret, 0)
        expected = "".join(f"{p}\n" for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29])
        self.assertEqual(out, expected)

    def test_logic(self):
        path = Path("examples/logic.ml")
        ret, out = _run_source(path.read_text(encoding="utf-8"))
        self.assertEqual(out, "1\n")
        self.assertEqual(ret, -9)


class TestArithmeticWraparound(unittest.TestCase):
    """32-bit signed integer wraparound."""

    def test_add_overflow(self):
        src = """\
func main(): int {
    let max_int: int = 2147483647;
    let res: int = max_int + 1;
    print(res);
    return res;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(ret, -2147483648)
        self.assertEqual(out, "-2147483648\n")

    def test_sub_underflow(self):
        src = """\
func main(): int {
    let min_int: int = -2147483647 - 1;
    let res: int = min_int - 1;
    print(res);
    return res;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(ret, 2147483647)
        self.assertEqual(out, "2147483647\n")

    def test_mul_overflow(self):
        src = """\
func main(): int {
    let a: int = 2147483647;
    let res: int = a * 2;
    print(res);
    return res;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(ret, -2)
        self.assertEqual(out, "-2\n")

    def test_neg_overflow(self):
        src = """\
func main(): int {
    let min_int: int = -2147483647 - 1;
    let res: int = -min_int;
    print(res);
    return res;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(ret, -2147483648)
        self.assertEqual(out, "-2147483648\n")


class TestDivisionAndModulo(unittest.TestCase):
    """Division and modulo behavior and VMTrap on zero."""

    def test_div_by_zero_traps(self):
        src = """\
func main(): int {
    let x: int = 42 / 0;
    return x;
}
"""
        with self.assertRaises(VMTrap) as ctx:
            _run_source(src)
        self.assertIn("division by zero", str(ctx.exception))

    def test_mod_by_zero_traps(self):
        src = """\
func main(): int {
    let x: int = 42 % 0;
    return x;
}
"""
        with self.assertRaises(VMTrap) as ctx:
            _run_source(src)
        self.assertIn("modulo by zero", str(ctx.exception))

    def test_truncating_division_and_modulo(self):
        # Truncate towards zero: -7 / 2 == -3, -7 % 2 == -1
        src = """\
func main(): int {
    print(-7 / 2);
    print(-7 % 2);
    print(7 / -2);
    print(7 % -2);
    return 0;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(out, "-3\n-1\n-3\n1\n")


class TestCallFramesAndRecursion(unittest.TestCase):
    """Call frames, recursion, and mutual recursion."""

    def test_mutual_recursion(self):
        src = """\
func is_even(n: int): bool {
    if (n == 0) { return true; }
    return is_odd(n - 1);
}
func is_odd(n: int): bool {
    if (n == 0) { return false; }
    return is_even(n - 1);
}
func main(): int {
    if (is_even(10)) { print(1); } else { print(0); }
    if (is_odd(10)) { print(1); } else { print(0); }
    return 0;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(out, "1\n0\n")

    def test_scope_isolation_in_frames(self):
        src = """\
func f(x: int): int {
    let a: int = 100;
    return x + a;
}
func main(): int {
    let a: int = 1;
    let b: int = f(5);
    print(a);
    print(b);
    return 0;
}
"""
        ret, out = _run_source(src)
        self.assertEqual(out, "1\n105\n")


class TestUnsafeRawFailures(unittest.TestCase):
    """Raw Python exceptions must surface for invalid bytecode without safety checks."""

    def test_stack_underflow_fails_naturally(self):
        # Construct raw bytecode with POP on empty stack
        fn = BCFunction(
            name="main",
            param_types=[],
            return_type="int",
            num_locals=0,
            local_types=[],
            max_stack=0,
            code=bytes([Op.POP]),
        )
        mod = BCModule(version=1, entry_func=0, functions=[fn])
        vm = VM()
        with self.assertRaises(IndexError):
            vm.run(mod)

    def test_bad_jump_fails_naturally(self):
        # JMP to offset 9999 out of bounds
        import struct
        code = bytearray([Op.JMP])
        code.extend(struct.pack("<H", 9999))
        fn = BCFunction(
            name="main",
            param_types=[],
            return_type="int",
            num_locals=0,
            local_types=[],
            max_stack=0,
            code=bytes(code),
        )
        mod = BCModule(version=1, entry_func=0, functions=[fn])
        vm = VM()
        with self.assertRaises(IndexError):
            vm.run(mod)


class TestCLIRun(unittest.TestCase):
    """Test running .ml and .bc files via svm.py."""

    def test_run_ml_file(self):
        proc = subprocess.run(
            [sys.executable, "svm.py", "run", "examples/factorial.ml"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "120")

    def test_run_bc_file(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Compile to tmp_path
            compile_proc = subprocess.run(
                [sys.executable, "svm.py", "compile", "examples/gcd.ml", "-o", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_proc.returncode, 0)

            # Run tmp_path
            run_proc = subprocess.run(
                [sys.executable, "svm.py", "run", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run_proc.returncode, 0)
            self.assertEqual(run_proc.stdout.strip(), "6")

            # Run with --unsafe flag
            run_unsafe = subprocess.run(
                [sys.executable, "svm.py", "run", "--unsafe", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run_unsafe.returncode, 0)
            self.assertEqual(run_unsafe.stdout.strip(), "6")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
