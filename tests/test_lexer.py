import unittest

from minilang.errors import LexError
from minilang.lexer import tokenize
from minilang.tokens import TT


def types(src):
    return [t.type for t in tokenize(src)]


class TestLexer(unittest.TestCase):
    def test_keywords_vs_identifiers(self):
        self.assertEqual(types("func funcx let letter"),
                         [TT.FUNC, TT.ID, TT.LET, TT.ID, TT.EOF])

    def test_int_literal_and_ops(self):
        self.assertEqual(types("12+3*4"),
                         [TT.INT_LIT, TT.PLUS, TT.INT_LIT, TT.STAR, TT.INT_LIT, TT.EOF])

    def test_two_char_operators_longest_match(self):
        self.assertEqual(types("<= >= == != && || < > = !"), [
            TT.LE, TT.GE, TT.EQ, TT.NE, TT.AND, TT.OR, TT.LT, TT.GT,
            TT.ASSIGN, TT.NOT, TT.EOF])

    def test_comments_skipped(self):
        self.assertEqual(types("1 // hi\n/* a\nb */ 2"),
                         [TT.INT_LIT, TT.INT_LIT, TT.EOF])

    def test_positions(self):
        toks = tokenize("let\n  x")
        self.assertEqual((toks[0].line, toks[0].col), (1, 1))
        self.assertEqual((toks[1].line, toks[1].col), (2, 3))

    def test_bool_and_type_keywords(self):
        self.assertEqual(types("int bool true false"),
                         [TT.INT, TT.BOOL, TT.TRUE, TT.FALSE, TT.EOF])

    def test_unexpected_character(self):
        with self.assertRaises(LexError) as cm:
            tokenize("x # y")
        self.assertEqual((cm.exception.line, cm.exception.col), (1, 3))

    def test_invalid_number_literal(self):
        with self.assertRaises(LexError):
            tokenize("12abc")

    def test_unterminated_block_comment(self):
        with self.assertRaises(LexError):
            tokenize("/* never closed")


if __name__ == "__main__":
    unittest.main()
