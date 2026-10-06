# Secure Bytecode VM with a Static Verifier (VeriByte)

Compiler Design project implementing an end-to-end language pipeline and secure stack-based bytecode virtual machine with a static verifier.

```
MiniLang source -> Lexer -> Parser -> AST -> Semantic Analysis -> Code Generator -> Optimizer
                                                                                        |
                                 untrusted / fuzzed bytecode -------------------------->+--> Static Verifier --> Bytecode VM
```

The verifier proves a bytecode file is stack-safe, jump-safe, and type-safe **before** the VM runs it. The VM refuses unverified code, preventing runtime vulnerabilities.

---

## Status

| Phase | Review | State | Implementation |
|---|---|---|---|
| Problem, novelty, architecture | 1 | Done | Project proposal & architecture |
| Grammar (EBNF) | 1 | Done | `docs/GRAMMAR.md` |
| Bytecode ISA + file format | 1 | Done | `docs/ISA.md` |
| Verifier paper design | 1 | Done | `docs/VERIFIER_DESIGN.md` |
| Lexer, parser, AST, CLI | 1 | Done | `minilang/` |
| Semantic analysis | 2 | Done | `semantic/` (symbol table, scopes, type checker) |
| Code generator, disassembler, VM | 2 | Done | `codegen/`, `vm/` |
| Static verifier, fuzzing | 3 | Done | `verifier/`, `tests/malicious/`, `tools/fuzz.py` |
| Optimization, benchmarks, final report | Final | Done | `optimizer/`, `tools/bench.py`, `docs/REPORT_RESULTS.md` |

---

## Quick Start (Python 3.10+)

Run the full test suite (161 tests):

```bash
python -m unittest discover -s tests -t .
```

---

## Command Line Interface (`svm.py`)

The unified CLI `svm.py` provides commands for every stage of the compilation, optimization, verification, and execution pipeline:

### 1. Compile MiniLang to Bytecode
Compile a `.ml` source file into binary bytecode (`.bc`).
```bash
python svm.py compile examples/factorial.ml -o factorial.bc
python svm.py compile examples/logic.ml -o logic.opt.bc --opt    # with optimizations
```

### 2. Optimize Bytecode
Run bytecode constant folding, peephole optimizations, and dead code elimination:
```bash
python svm.py optimize factorial.bc -o factorial.opt.bc
```

### 3. Disassemble Bytecode
Print a human-readable assembly listing with instruction offsets and function signatures:
```bash
python svm.py disasm factorial.bc
```

### 4. Statically Verify Bytecode
Verify type safety, jump bounds, stack bounds, and frame integrity without executing the file:
```bash
python svm.py verify factorial.bc
```

### 5. Execute Program (Run)
Execute either `.bc` bytecode or `.ml` source files:
```bash
python svm.py run factorial.bc              # verifies and executes bytecode
python svm.py run examples/factorial.ml     # compiles, verifies, and executes
python svm.py run examples/logic.ml --opt   # compiles, optimizes, verifies, and executes
python svm.py run bad.bc --unsafe           # demo mode: bypasses verifier
```

---

## Demonstration

Run the automated interactive demo showing how the verifier prevents crashes:

- **Linux / macOS**: `./demo/demo.sh`
- **Windows**: `demo\demo.bat`

---

## Project Layout

```
minilang/       Hand-written lexer, recursive-descent parser, AST definitions, printer
semantic/       Two-pass semantic analyzer, symbol table with block scopes, type checker
codegen/        AST to bytecode generator, .bc binary serializer, loader, disassembler
vm/             Stack machine interpreter, call frames, 32-bit signed wraparound, VMTrap
verifier/       Static verifier: decoder, CFG jump check, worklist abstract interpreter
optimizer/      Bytecode optimizer: constant folding, push-pop, double negation, jump threading
tools/
  fuzz.py       Differential mutation fuzzer testing verifier soundness
  bench.py      Performance benchmark suite (scaling, verifier overhead, optimizer impact)
demo/           Interactive demonstration scripts (demo.sh, demo.bat)
tests/          Unit tests across all modules (161 tests)
  malicious/    26 crafted .bc files isolating every verifier rule violation
results/        Fuzzing results (fuzz_results.csv) and benchmark data (bench.csv, bench.png)
docs/           Specifications (GRAMMAR.md, ISA.md, VERIFIER_DESIGN.md, REPORT_RESULTS.md)
svm.py          Unified command line tool
```
