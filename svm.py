#!/usr/bin/env python3
"""CLI for the Secure Bytecode VM toolchain.

Usage:
    python svm.py compile file.ml -o out.bc
    python svm.py disasm out.bc
    python svm.py verify out.bc
    python svm.py run out.bc [--unsafe]
    python svm.py run file.ml [--unsafe]
"""

import argparse
import sys
from pathlib import Path

from minilang.parser import parse
from semantic import analyze
from codegen import generate, write_bytecode, load_bytecode, disassemble, BCModule
from vm import VM, verify
from verifier import VerifyError


def cmd_compile(args: argparse.Namespace) -> None:
    source = open(args.file, encoding="utf-8").read()
    prog = parse(source)
    st = analyze(prog)
    functions = generate(prog, st)

    # Find main's index
    entry_func = next(
        i for i, fn in enumerate(functions) if fn.name == "main"
    )

    out_path = args.output
    if out_path is None:
        out_path = args.file.rsplit(".", 1)[0] + ".bc"
    write_bytecode(out_path, functions, entry_func)
    print(f"wrote {out_path}")


def cmd_disasm(args: argparse.Namespace) -> None:
    module = load_bytecode(args.file)
    print(disassemble(module), end="")


def cmd_verify(args: argparse.Namespace) -> None:
    module = load_bytecode(args.file)
    try:
        verify(module)
        print(f"verified {args.file}")
    except VerifyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if path.suffix == ".ml":
        source = path.read_text(encoding="utf-8")
        prog = parse(source)
        st = analyze(prog)
        functions = generate(prog, st)
        entry_func = next(
            i for i, fn in enumerate(functions) if fn.name == "main"
        )
        module = BCModule(version=1, entry_func=entry_func, functions=functions)
    else:
        module = load_bytecode(path)

    if not args.unsafe:
        try:
            verify(module)
        except VerifyError as e:
            print(f"verification failed:\n{e}", file=sys.stderr)
            sys.exit(1)

    vm = VM()
    ret = vm.run(module)
    return ret if isinstance(ret, int) else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Secure Bytecode VM toolchain")
    sub = parser.add_subparsers(dest="command")

    p_compile = sub.add_parser("compile", help="Compile MiniLang to .bc")
    p_compile.add_argument("file", help="MiniLang source file (.ml)")
    p_compile.add_argument("-o", "--output", help="Output .bc path")

    p_disasm = sub.add_parser("disasm", help="Disassemble a .bc file")
    p_disasm.add_argument("file", help="Bytecode file (.bc)")

    p_verify = sub.add_parser("verify", help="Verify a .bc file")
    p_verify.add_argument("file", help="Bytecode file (.bc)")

    p_run = sub.add_parser("run", help="Run a .bc or .ml program")
    p_run.add_argument("file", help="Bytecode file (.bc) or source (.ml)")
    p_run.add_argument("--unsafe", action="store_true", help="Skip bytecode verification")

    args = parser.parse_args()
    if args.command == "compile":
        cmd_compile(args)
    elif args.command == "disasm":
        cmd_disasm(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "run":
        ret = cmd_run(args)
        sys.exit(ret)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
