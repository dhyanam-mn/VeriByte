"""Tests for the semantic analyzer.

Organization:
  - TestValidPrograms: ≥3 programs that must type-check cleanly.
  - One test class per rejection rule, each with ≥2 failing programs.

Every test parses real MiniLang source and feeds it to `analyze()`.
"""

import unittest
from minilang.parser import parse
from semantic import analyze, SemanticError


# ===================================================================
# Helpers
# ===================================================================

def _analyze(src: str):
    """Parse and analyze; return the SymbolTable on success."""
    return analyze(parse(src))


def _must_fail(test_case, src: str, *, snippet: str | None = None):
    """Assert that analysis raises SemanticError.

    If *snippet* is given, check that the error message contains it.
    """
    with test_case.assertRaises(SemanticError) as ctx:
        _analyze(src)
    if snippet:
        test_case.assertIn(snippet, str(ctx.exception))


# ===================================================================
# Valid programs
# ===================================================================

class TestValidPrograms(unittest.TestCase):
    """At least 3 well-typed programs that must pass the analyzer."""

    def test_gcd(self):
        src = """\
func gcd(a: int, b: int): int {
    while (b != 0) {
        let t: int = b;
        b = a % b;
        a = t;
    }
    return a;
}
func main(): int {
    print(gcd(48, 18));
    return 0;
}
"""
        st = _analyze(src)
        self.assertIn("gcd", st.functions)
        self.assertIn("main", st.functions)

    def test_factorial(self):
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
        st = _analyze(src)
        self.assertEqual(st.functions["fact"].return_type, "int")

    def test_fibonacci(self):
        src = """\
func fib(n: int): int {
    let a: int = 0;
    let b: int = 1;
    let i: int = 0;
    while (i < n) {
        let t: int = a + b;
        a = b;
        b = t;
        i = i + 1;
    }
    return a;
}
func main(): int {
    print(fib(10));
    return 0;
}
"""
        _analyze(src)

    def test_prime_checker(self):
        src = """\
func is_prime(n: int): bool {
    if (n < 2) { return false; }
    let d: int = 2;
    while (d * d <= n) {
        if (n % d == 0) { return false; }
        d = d + 1;
    }
    return true;
}
func main(): int {
    let k: int = 2;
    while (k < 30) {
        if (is_prime(k)) { print(k); }
        k = k + 1;
    }
    return 0;
}
"""
        _analyze(src)

    def test_logic(self):
        src = """\
func in_range(x: int, lo: int, hi: int): bool {
    return x >= lo && x <= hi || !(x != 0);
}
func main(): int {
    if (in_range(5, 1, 10)) { print(1); } else { print(0); }
    return 0;
}
"""
        _analyze(src)

    def test_nested_scopes_shadow(self):
        """A variable in an inner block shadows the outer; both get separate slots."""
        src = """\
func main(): int {
    let x: int = 1;
    {
        let x: int = 2;
        print(x);
    }
    print(x);
    return 0;
}
"""
        _analyze(src)

    def test_forward_call(self):
        """A function may call another that is defined later (forward reference)."""
        src = """\
func main(): int {
    print(helper());
    return 0;
}
func helper(): int {
    return 42;
}
"""
        _analyze(src)

    def test_mutual_recursion(self):
        """Two functions calling each other."""
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
    if (is_even(4)) { print(1); } else { print(0); }
    return 0;
}
"""
        _analyze(src)

    def test_expr_stmt_call(self):
        """Expression statement whose result is discarded (valid, call for side-effects)."""
        src = """\
func noop(): int { return 0; }
func main(): int {
    noop();
    return 0;
}
"""
        _analyze(src)


# ===================================================================
# Rejection tests — grouped by rule
# ===================================================================

class TestUndeclaredVariable(unittest.TestCase):
    def test_read_undeclared(self):
        src = """\
func main(): int {
    print(x);
    return 0;
}
"""
        _must_fail(self, src, snippet="undeclared variable 'x'")

    def test_assign_undeclared(self):
        src = """\
func main(): int {
    y = 5;
    return 0;
}
"""
        _must_fail(self, src, snippet="undeclared variable 'y'")

    def test_undeclared_in_expr(self):
        src = """\
func main(): int {
    return a + 1;
}
"""
        _must_fail(self, src, snippet="undeclared variable 'a'")


class TestUndeclaredFunction(unittest.TestCase):
    def test_call_missing_func(self):
        src = """\
func main(): int {
    print(foo(1));
    return 0;
}
"""
        _must_fail(self, src, snippet="undeclared function 'foo'")

    def test_call_var_as_func(self):
        src = """\
func main(): int {
    let x: int = 5;
    print(x(1));
    return 0;
}
"""
        _must_fail(self, src, snippet="undeclared function 'x'")


class TestDuplicateDeclaration(unittest.TestCase):
    def test_dup_let_same_scope(self):
        src = """\
func main(): int {
    let x: int = 1;
    let x: int = 2;
    return x;
}
"""
        _must_fail(self, src, snippet="duplicate declaration")

    def test_dup_param_and_let(self):
        """A let with the same name as a parameter in the function scope."""
        src = """\
func f(a: int): int {
    let a: int = 5;
    return a;
}
func main(): int { return f(1); }
"""
        _must_fail(self, src, snippet="duplicate declaration")

    def test_dup_params(self):
        src = """\
func f(a: int, a: int): int { return a; }
func main(): int { return f(1, 2); }
"""
        _must_fail(self, src, snippet="duplicate parameter")

    def test_dup_function_name(self):
        src = """\
func foo(): int { return 1; }
func foo(): int { return 2; }
func main(): int { return foo(); }
"""
        _must_fail(self, src, snippet="duplicate function")


class TestAssignTypeMismatch(unittest.TestCase):
    def test_assign_bool_to_int(self):
        src = """\
func main(): int {
    let x: int = 0;
    x = true;
    return x;
}
"""
        _must_fail(self, src, snippet="assignment type mismatch")

    def test_assign_int_to_bool(self):
        src = """\
func main(): int {
    let flag: bool = true;
    flag = 42;
    return 0;
}
"""
        _must_fail(self, src, snippet="assignment type mismatch")


class TestInitializerTypeMismatch(unittest.TestCase):
    def test_let_int_with_bool(self):
        src = """\
func main(): int {
    let x: int = true;
    return x;
}
"""
        _must_fail(self, src, snippet="initializer type mismatch")

    def test_let_bool_with_int(self):
        src = """\
func main(): int {
    let b: bool = 0;
    return 0;
}
"""
        _must_fail(self, src, snippet="initializer type mismatch")


class TestNonBoolCondition(unittest.TestCase):
    def test_if_int_condition(self):
        src = """\
func main(): int {
    if (1) { return 1; }
    return 0;
}
"""
        _must_fail(self, src, snippet="if condition must be bool")

    def test_while_int_condition(self):
        src = """\
func main(): int {
    while (1) { return 0; }
    return 0;
}
"""
        _must_fail(self, src, snippet="while condition must be bool")

    def test_if_int_expr_condition(self):
        src = """\
func main(): int {
    let x: int = 5;
    if (x) { return 1; }
    return 0;
}
"""
        _must_fail(self, src, snippet="if condition must be bool")


class TestArithmeticOperandTypes(unittest.TestCase):
    def test_add_bool_left(self):
        src = """\
func main(): int {
    return true + 1;
}
"""
        _must_fail(self, src, snippet="left operand of '+' must be int")

    def test_sub_bool_right(self):
        src = """\
func main(): int {
    return 1 - false;
}
"""
        _must_fail(self, src, snippet="right operand of '-' must be int")

    def test_mul_bools(self):
        src = """\
func main(): int {
    return true * false;
}
"""
        _must_fail(self, src, snippet="left operand of '*' must be int")

    def test_div_bool(self):
        src = """\
func main(): int {
    return true / 1;
}
"""
        _must_fail(self, src, snippet="left operand of '/' must be int")

    def test_mod_bool(self):
        src = """\
func main(): int {
    return 1 % true;
}
"""
        _must_fail(self, src, snippet="right operand of '%' must be int")

    def test_unary_neg_bool(self):
        src = """\
func main(): int {
    return -true;
}
"""
        _must_fail(self, src, snippet="unary '-' requires int")


class TestBooleanOperandTypes(unittest.TestCase):
    def test_and_int_left(self):
        src = """\
func main(): int {
    let b: bool = 1 && true;
    return 0;
}
"""
        _must_fail(self, src, snippet="left operand of '&&' must be bool")

    def test_and_int_right(self):
        src = """\
func main(): int {
    let b: bool = true && 0;
    return 0;
}
"""
        _must_fail(self, src, snippet="right operand of '&&' must be bool")

    def test_or_int(self):
        src = """\
func main(): int {
    let b: bool = 1 || 0;
    return 0;
}
"""
        _must_fail(self, src, snippet="left operand of '||' must be bool")

    def test_not_int(self):
        src = """\
func main(): int {
    let b: bool = !5;
    return 0;
}
"""
        _must_fail(self, src, snippet="unary '!' requires bool")


class TestEqualityOperandTypes(unittest.TestCase):
    def test_eq_mixed(self):
        src = """\
func main(): int {
    let b: bool = 1 == true;
    return 0;
}
"""
        _must_fail(self, src, snippet="'==' requires same types")

    def test_ne_mixed(self):
        src = """\
func main(): int {
    let b: bool = false != 0;
    return 0;
}
"""
        _must_fail(self, src, snippet="'!=' requires same types")


class TestRelationalOperandTypes(unittest.TestCase):
    def test_lt_bool(self):
        src = """\
func main(): int {
    let b: bool = true < false;
    return 0;
}
"""
        _must_fail(self, src, snippet="left operand of '<' must be int")

    def test_ge_bool(self):
        src = """\
func main(): int {
    let b: bool = true >= false;
    return 0;
}
"""
        _must_fail(self, src, snippet="left operand of '>=' must be int")


class TestCallArity(unittest.TestCase):
    def test_too_few_args(self):
        src = """\
func add(a: int, b: int): int { return a + b; }
func main(): int { return add(1); }
"""
        _must_fail(self, src, snippet="expects 2 argument(s), got 1")

    def test_too_many_args(self):
        src = """\
func one(): int { return 1; }
func main(): int { return one(1, 2); }
"""
        _must_fail(self, src, snippet="expects 0 argument(s), got 2")


class TestCallArgTypes(unittest.TestCase):
    def test_wrong_arg_type(self):
        src = """\
func f(x: int): int { return x; }
func main(): int { return f(true); }
"""
        _must_fail(self, src, snippet="argument 1 of 'f' must be int")

    def test_wrong_second_arg(self):
        src = """\
func g(a: int, b: bool): int { if (b) { return a; } return 0; }
func main(): int { return g(1, 2); }
"""
        _must_fail(self, src, snippet="argument 2 of 'g' must be bool")


class TestReturnWithoutValue(unittest.TestCase):
    def test_bare_return(self):
        src = """\
func f(): int {
    return;
}
func main(): int { return f(); }
"""
        _must_fail(self, src, snippet="return without a value")

    def test_bare_return_in_branch(self):
        src = """\
func f(x: int): int {
    if (x > 0) { return; }
    return 0;
}
func main(): int { return f(1); }
"""
        _must_fail(self, src, snippet="return without a value")


class TestReturnTypeMismatch(unittest.TestCase):
    def test_return_bool_for_int(self):
        src = """\
func f(): int {
    return true;
}
func main(): int { return f(); }
"""
        _must_fail(self, src, snippet="return type mismatch")

    def test_return_int_for_bool(self):
        src = """\
func f(): bool {
    return 42;
}
func main(): int {
    if (f()) { return 1; }
    return 0;
}
"""
        _must_fail(self, src, snippet="return type mismatch")


class TestMissingMain(unittest.TestCase):
    def test_no_main(self):
        src = """\
func helper(): int { return 0; }
"""
        _must_fail(self, src, snippet="missing 'main'")

    def test_main_with_params(self):
        src = """\
func main(x: int): int { return x; }
"""
        _must_fail(self, src, snippet="'main' must take no parameters")

    def test_main_returns_bool(self):
        src = """\
func main(): bool { return true; }
"""
        _must_fail(self, src, snippet="'main' must return int")


class TestMissingReturn(unittest.TestCase):
    """Functions where some path does not return."""

    def test_no_return_at_all(self):
        src = """\
func f(): int {
    let x: int = 5;
}
func main(): int { return f(); }
"""
        _must_fail(self, src, snippet="may not return on all paths")

    def test_return_only_in_if(self):
        src = """\
func f(x: int): int {
    if (x > 0) { return x; }
}
func main(): int { return f(1); }
"""
        _must_fail(self, src, snippet="may not return on all paths")

    def test_return_in_while_only(self):
        """While loop doesn't guarantee return (condition could be false)."""
        src = """\
func f(n: int): int {
    while (n > 0) { return n; }
}
func main(): int { return f(1); }
"""
        _must_fail(self, src, snippet="may not return on all paths")


# ===================================================================
# Annotation tests — ensure the analyzer adds codegen info
# ===================================================================

class TestAnnotations(unittest.TestCase):
    def test_resolved_types(self):
        src = """\
func main(): int {
    let x: int = 1 + 2;
    let b: bool = x > 0;
    return x;
}
"""
        prog = parse(src)
        analyze(prog)
        fn = prog.functions[0]
        # Check that the return expression has resolved_type
        ret_stmt = fn.body.stmts[-1]
        self.assertEqual(ret_stmt.value.resolved_type, "int")

    def test_local_slots(self):
        src = """\
func f(a: int, b: bool): int {
    let c: int = 0;
    {
        let d: int = 1;
    }
    return a;
}
func main(): int { return f(1, true); }
"""
        prog = parse(src)
        st = analyze(prog)
        fn = prog.functions[0]
        # f has 4 locals: a(0), b(1), c(2), d(3)
        self.assertEqual(fn.num_locals, 4)

    def test_shadowed_slots_differ(self):
        src = """\
func main(): int {
    let x: int = 1;
    {
        let x: int = 2;
    }
    return x;
}
"""
        prog = parse(src)
        analyze(prog)
        fn = prog.functions[0]
        # Two distinct slots for the two x's
        self.assertEqual(fn.num_locals, 2)


if __name__ == "__main__":
    unittest.main()
