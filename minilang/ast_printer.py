from dataclasses import fields, is_dataclass
from typing import Any

from .ast_nodes import Node


def dump(node: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, list):
        return "".join(dump(n, indent) for n in node)
    if not is_dataclass(node):
        return f"{pad}{node!r}\n"
    scalars, children = [], []
    for f in fields(node):
        if f.name in ("line", "col"):
            continue
        v = getattr(node, f.name)
        if isinstance(v, (Node, list)) and v != []:
            children.append((f.name, v))
        else:
            scalars.append(f"{f.name}={v!r}")
    out = f"{pad}{type(node).__name__}({', '.join(scalars)})\n"
    for name, v in children:
        out += f"{pad}  .{name}\n" + dump(v, indent + 2)
    return out
