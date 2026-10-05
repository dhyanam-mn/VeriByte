"""Usage: python -m minilang (tokens|ast) <file.ml>"""
import sys

from .ast_printer import dump
from .errors import MiniLangError
from .lexer import tokenize
from .parser import parse


def main(argv) -> int:
    if len(argv) != 3 or argv[1] not in ("tokens", "ast"):
        print(__doc__)
        return 2
    with open(argv[2], encoding="utf-8") as fh:
        src = fh.read()
    try:
        if argv[1] == "tokens":
            for t in tokenize(src):
                print(t)
        else:
            print(dump(parse(src)), end="")
    except MiniLangError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
