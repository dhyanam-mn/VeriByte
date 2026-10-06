#!/usr/bin/env python3
"""CLI for the Secure Bytecode VM toolchain.

Usage:
    python svm.py compile file.ml -o out.bc
    python svm.py disasm out.bc
"""

import argparse
import sys

from minilang.parser import parse
from semantic import analyze
from codegen import generate, write_bytecode, load_bytecode, disassemble


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Secure Bytecode VM toolchain")
    sub = parser.add_subparsers(dest="command")

    p_compile = sub.add_parser("compile", help="Compile MiniLang to .bc")
    p_compile.add_argument("file", help="MiniLang source file (.ml)")
    p_compile.add_argument("-o", "--output", help="Output .bc path")

    p_disasm = sub.add_parser("disasm", help="Disassemble a .bc file")
    p_disasm.add_argument("file", help="Bytecode file (.bc)")

    args = parser.parse_args()
    if args.command == "compile":
        cmd_compile(args)
    elif args.command == "disasm":
        cmd_disasm(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
