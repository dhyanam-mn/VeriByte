"""Tests for bytecode optimizer: constant folding, peephole rules, and correctness."""

import io
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from minilang.parser import parse
from semantic import analyze
from codegen import generate, load_bytecode, BCFunction, BCModule, Op
from optimizer import optimize_function, optimize_module
from verifier import verify
from vm import VM, VMTrap


def _compile_module(src: str) -> BCModule:
    prog = parse(src)
    st = analyze(prog)
    fns = generate(prog, st)
    entry = next(i for i, f in enumerate(fns) if f.name == "main")
    return BCModule(version=1, entry_func=entry, functions=fns)


class TestOptimizerOnExamples(unittest.TestCase):
    """Every valid example must optimize, verify cleanly, and produce identical output."""

    def _check_example(self, filename: str, expected_ret: int, expected_out: str):
        path = Path("examples") / filename
        source = path.read_text(encoding="utf-8")
        mod = _compile_module(source)

        # Unoptimized execution
        out_raw = io.StringIO()
        ret_raw = VM(stdout=out_raw).run(mod)

        # Optimize
        opt_mod = optimize_module(mod)

        # Must pass static verifier!
        verify(opt_mod)

        # Optimized execution
        out_opt = io.StringIO()
        ret_opt = VM(stdout=out_opt).run(opt_mod)

        self.assertEqual(ret_opt, ret_raw)
        self.assertEqual(out_opt.getvalue(), out_raw.getvalue())
        self.assertEqual(ret_opt, expected_ret)
        self.assertEqual(out_opt.getvalue(), expected_out)

    def test_factorial(self):
        self._check_example("factorial.ml", 0, "120\n")

    def test_fibonacci(self):
        self._check_example("fibonacci.ml", 0, "55\n")

    def test_gcd(self):
        self._check_example("gcd.ml", 0, "6\n")

    def test_logic(self):
        self._check_example("logic.ml", -9, "1\n")

    def test_prime(self):
        expected_primes = "".join(f"{p}\n" for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29])
        self._check_example("prime.ml", 0, expected_primes)


class TestConstantFolding(unittest.TestCase):
    """Targeted tests verifying constant folding rules."""

    def test_arithmetic_folding(self):
        # 1 + 2 * 3 -> 7
        src = """\
func main(): int {
    return 1 + 2 * 3;
}
"""
        mod = _compile_module(src)
        opt_mod = optimize_module(mod)
        verify(opt_mod)

        # The optimized code should have fewer instructions
        self.assertLess(len(opt_mod.functions[0].code), len(mod.functions[0].code))
        res = VM().run(opt_mod)
        self.assertEqual(res, 7)

    def test_boolean_folding(self):
        # (true && false) || (true == true) -> true
        src = """\
func main(): int {
    if ((true && false) || (1 == 1)) {
        return 42;
    }
    return 0;
}
"""
        mod = _compile_module(src)
        opt_mod = optimize_module(mod)
        verify(opt_mod)
        res = VM().run(opt_mod)
        self.assertEqual(res, 42)

    def test_unary_folding(self):
        # -(-10) -> 10, !(!true) -> true
        src = """\
func main(): int {
    let x: int = -(-10);
    let b: bool = !(!true);
    if (b) { return x; }
    return 0;
}
"""
        mod = _compile_module(src)
        opt_mod = optimize_module(mod)
        verify(opt_mod)
        res = VM().run(opt_mod)
        self.assertEqual(res, 10)

    def test_div_by_zero_not_folded_at_compile_time(self):
        # Constant division by zero should NOT be folded so that runtime trap triggers
        src = """\
func main(): int {
    return 10 / 0;
}
"""
        mod = _compile_module(src)
        opt_mod = optimize_module(mod)
        # Should verify
        verify(opt_mod)
        # Should raise VMTrap at runtime
        with self.assertRaises(VMTrap):
            VM().run(opt_mod)


class TestPeepholePatterns(unittest.TestCase):
    """Peephole patterns: push-pop, double negation, redundant jumps."""

    def test_push_pop_elimination(self):
        src = """\
func main(): int {
    12345;
    return 42;
}
"""
        mod = _compile_module(src)
        # Unoptimized has PUSH_INT 12345, POP
        opt_mod = optimize_module(mod)
        verify(opt_mod)
        res = VM().run(opt_mod)
        self.assertEqual(res, 42)
        # Length of main should be smaller (PUSH_INT + POP eliminated)
        self.assertLess(len(opt_mod.functions[0].code), len(mod.functions[0].code))

    def test_control_flow_and_while_loop_integrity(self):
        src = """\
func loop(n: int): int {
    let s: int = 0;
    let i: int = 0;
    while (i < n) {
        s = s + i;
        i = i + 1;
    }
    return s;
}
func main(): int {
    return loop(10);
}
"""
        mod = _compile_module(src)
        opt_mod = optimize_module(mod)
        verify(opt_mod)
        res = VM().run(opt_mod)
        self.assertEqual(res, 45)


class TestOptimizerCLI(unittest.TestCase):
    """Test CLI commands: compile --opt, optimize, and run --opt."""

    def test_compile_opt_and_run(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Compile with --opt
            subprocess.run([sys.executable, "svm.py", "compile", "--opt", "examples/logic.ml", "-o", str(tmp_path)],
                           check=True, capture_output=True)
            # Verify
            proc_v = subprocess.run([sys.executable, "svm.py", "verify", str(tmp_path)],
                                    capture_output=True, text=True)
            self.assertEqual(proc_v.returncode, 0)
            # Run
            proc_r = subprocess.run([sys.executable, "svm.py", "run", str(tmp_path)],
                                    capture_output=True, text=True)
            self.assertEqual(proc_r.stdout.strip(), "1")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_optimize_subcommand(self):
        with tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp1, \
             tempfile.NamedTemporaryFile(suffix=".bc", delete=False) as tmp2:
            p1, p2 = Path(tmp1.name), Path(tmp2.name)
        try:
            # Compile unoptimized
            subprocess.run([sys.executable, "svm.py", "compile", "examples/logic.ml", "-o", str(p1)],
                           check=True, capture_output=True)
            # Run svm.py optimize
            proc_opt = subprocess.run([sys.executable, "svm.py", "optimize", str(p1), "-o", str(p2)],
                                      capture_output=True, text=True)
            self.assertEqual(proc_opt.returncode, 0)
            self.assertIn("optimized", proc_opt.stdout)

            # Verified and runnable
            proc_run = subprocess.run([sys.executable, "svm.py", "run", str(p2)],
                                      capture_output=True, text=True)
            self.assertEqual(proc_run.stdout.strip(), "1")
        finally:
            if p1.exists(): p1.unlink()
            if p2.exists(): p2.unlink()


if __name__ == "__main__":
    unittest.main()
