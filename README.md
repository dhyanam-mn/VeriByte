# Secure Bytecode VM with a Static Verifier

Compiler Design project. Pipeline:

```
MiniLang source -> Lexer -> Parser -> AST -> Semantic analysis -> Bytecode
                                                        |
                       untrusted / fuzzed bytecode ---->+--> Static Verifier --> VM
```

The verifier proves a bytecode file is stack-safe, jump-safe and type-safe
**before** the VM runs it. The VM refuses unverified code.

## Status

| Phase | Review | State |
|---|---|---|
| Problem, novelty, architecture | 1 | done (see project report) |
| Grammar (EBNF) | 1 | done - `docs/GRAMMAR.md` |
| Bytecode ISA + file format | 1 | done - `docs/ISA.md` |
| Verifier paper design | 1 | done - `docs/VERIFIER_DESIGN.md` |
| Lexer, parser, AST, CLI | 1 | done, 22 tests passing |
| Semantic analysis | 2 | not started |
| Code generator, disassembler, VM | 2 | not started |
| Static verifier, fuzzing | 3 | not started |
| Optimization, benchmarks, final report | Final | not started |

## Quick start (Python 3.10+)

```bash
python -m minilang tokens examples/gcd.ml     # token stream
python -m minilang ast examples/factorial.ml  # AST dump
python -m unittest discover -s tests -t .     # run tests (pytest also works)
```

Syntax errors report line and column:

```
$ python -m minilang ast examples/bad_syntax_2.ml
error: expected ')', found RETURN 'return' (line 3, col 5)
```

## Layout

```
minilang/    lexer.py, parser.py, ast_nodes.py, ast_printer.py, tokens.py, errors.py
semantic/    (Review 2)  symbol table, type checker
codegen/     (Review 2)  AST -> bytecode, serializer, disassembler
vm/          (Review 2)  interpreter
verifier/    (Review 3)  decoder, CFG, abstract interpreter
tests/       unit tests
examples/    sample programs (valid and deliberately invalid)
docs/        grammar, ISA, verifier design, workflow
```
