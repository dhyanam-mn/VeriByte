import glob
import os
import unittest

from minilang import ast_nodes as A
from minilang.errors import LexError, ParseError
from minilang.parser import parse

EX = os.path.join(os.path.dirname(__file__), "..", "examples")


def expr(src):
    prog = parse(f"func f(): int {{ return {src}; }}")
    return prog.functions[0].body.stmts[0].value


class TestParser(unittest.TestCase):
    def test_precedence_mul_over_add(self):
        e = expr("1 + 2 * 3")
        self.assertEqual((e.op, e.right.op), ("+", "*"))

    def test_left_associativity(self):
        e = expr("10 - 4 - 3")
        self.assertEqual((e.op, e.left.op, e.right.value), ("-", "-", 3))

    def test_parentheses_override(self):
        e = expr("(1 + 2) * 3")
        self.assertEqual((e.op, e.left.op), ("*", "+"))

    def test_logical_precedence_and_over_or(self):
        e = expr("a || b && c")
        self.assertEqual((e.op, e.right.op), ("||", "&&"))

    def test_unary(self):
        e = expr("-!x")
        self.assertIsInstance(e, A.UnaryExpr)
        self.assertEqual((e.op, e.operand.op), ("-", "!"))

    def test_call_with_args(self):
        e = expr("g(1, x + 2, h())")
        self.assertIsInstance(e, A.CallExpr)
        self.assertEqual(len(e.args), 3)

    def test_function_signature(self):
        f = parse("func add(a: int, b: int): int { return a + b; }").functions[0]
        self.assertEqual([(p.name, p.type_name) for p in f.params],
                         [("a", "int"), ("b", "int")])
        self.assertEqual(f.return_type, "int")

    def test_else_if_chain(self):
        prog = parse("func f(): int { if (true) { return 1; } "
                     "else if (false) { return 2; } else { return 3; } }")
        ifs = prog.functions[0].body.stmts[0]
        self.assertIsInstance(ifs.else_block.stmts[0], A.IfStmt)

    def test_assignment_vs_expression_statement(self):
        prog = parse("func f(): int { let x: int = 1; x = 2; g(x); return x; }")
        kinds = [type(s).__name__ for s in prog.functions[0].body.stmts]
        self.assertEqual(kinds, ["LetStmt", "AssignStmt", "ExprStmt", "ReturnStmt"])

    def test_example_programs(self):
        paths = sorted(glob.glob(os.path.join(EX, "*.ml")))
        self.assertGreaterEqual(len(paths), 8)
        for path in paths:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            with self.subTest(name):
                if name.startswith("bad_lex"):
                    with self.assertRaises(LexError):
                        parse(src)
                elif name.startswith("bad_syntax"):
                    with self.assertRaises(ParseError):
                        parse(src)
                else:
                    self.assertTrue(parse(src).functions)

    def test_error_reports_position(self):
        with self.assertRaises(ParseError) as cm:
            parse("func main(): int {\n  let x: int = ;\n}")
        self.assertEqual(cm.exception.line, 2)

    def test_missing_semicolon(self):
        with self.assertRaises(ParseError):
            parse("func main(): int { return 1 }")

    def test_missing_return_type(self):
        with self.assertRaises(ParseError):
            parse("func main() { return 1; }")


if __name__ == "__main__":
    unittest.main()
