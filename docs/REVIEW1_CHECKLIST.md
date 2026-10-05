# Review 1 Checklist

- [x] Problem identification and objectives (project report, Sections 3-4)
- [x] Literature survey (Section 5) and novelty (Section 6)
- [x] System architecture diagram (Section 7.1)
- [x] MiniLang grammar finalized: docs/GRAMMAR.md
- [x] Bytecode ISA and file format finalized: docs/ISA.md
- [x] Verifier design on paper: docs/VERIFIER_DESIGN.md
- [x] Tech stack finalized, repository structure created
- [x] Working lexer and parser with AST dump and CLI
- [x] 8 example programs (5 valid, 3 invalid) and 22 unit tests

## Demo script (about 3 minutes)

1. `python -m minilang tokens examples/gcd.ml | head -20`   (lexer)
2. `python -m minilang ast examples/factorial.ml`            (parser, AST)
3. `python -m minilang ast examples/logic.ml`                (precedence, else-if, unary)
4. `python -m minilang ast examples/bad_syntax_2.ml`         (error with line/col)
5. `python -m minilang tokens examples/bad_lex.ml`           (lexical error)
6. `python -m unittest discover -s tests -t . -v`            (tests)
7. Show docs/ISA.md and docs/VERIFIER_DESIGN.md, then explain what comes next.
