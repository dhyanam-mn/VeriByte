"""Bytecode binary serializer and loader (.bc format).

Implements the binary file format from docs/ISA.md exactly:
  magic "SBVM", version 1, little-endian multi-byte fields.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Union

from .generator import BCFunction


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class BytecodeFormatError(Exception):
    """Raised when a .bc file is truncated, has a bad magic, or is otherwise
    malformed."""
    pass


# ---------------------------------------------------------------------------
# Structured representation (for the loader)
# ---------------------------------------------------------------------------

@dataclass
class BCModule:
    """Top-level container returned by `load_bytecode`."""
    version: int
    entry_func: int
    functions: List[BCFunction]


# ---------------------------------------------------------------------------
# Type encoding helpers
# ---------------------------------------------------------------------------

_TYPE_TO_BYTE = {"int": 0, "bool": 1}
_BYTE_TO_TYPE = {0: "int", 1: "bool"}


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def serialize(functions: List[BCFunction], entry_func: int) -> bytes:
    """Serialize a compiled program to the .bc binary format."""
    buf = bytearray()

    # Header
    buf.extend(b"SBVM")               # magic
    buf.append(1)                      # version
    buf.extend(struct.pack("<H", len(functions)))   # num_funcs
    buf.extend(struct.pack("<H", entry_func))       # entry_func

    for fn in functions:
        # name
        name_bytes = fn.name.encode("ascii")
        buf.append(len(name_bytes))
        buf.extend(name_bytes)

        # params
        buf.append(len(fn.param_types))
        for pt in fn.param_types:
            buf.append(_TYPE_TO_BYTE[pt])

        # return type
        buf.append(_TYPE_TO_BYTE[fn.return_type])

        # num_locals (u16) and local_types
        buf.extend(struct.pack("<H", fn.num_locals))
        for lt in fn.local_types:
            buf.append(_TYPE_TO_BYTE[lt])

        # max_stack (u16)
        buf.extend(struct.pack("<H", fn.max_stack))

        # code_len (u32) and code
        buf.extend(struct.pack("<I", len(fn.code)))
        buf.extend(fn.code)

    return bytes(buf)


def write_bytecode(path: Union[str, Path], functions: List[BCFunction],
                   entry_func: int) -> None:
    """Serialize and write to a file."""
    data = serialize(functions, entry_func)
    Path(path).write_bytes(data)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _read(f: BinaryIO, n: int, what: str) -> bytes:
    """Read exactly `n` bytes or raise BytecodeFormatError."""
    data = f.read(n)
    if len(data) < n:
        raise BytecodeFormatError(
            f"truncated {what}: expected {n} bytes, got {len(data)}")
    return data


def load_bytecode(path: Union[str, Path]) -> BCModule:
    """Load a .bc file and return a BCModule.

    Raises BytecodeFormatError on any structural problem.
    """
    with open(path, "rb") as f:
        # Header
        magic = _read(f, 4, "magic")
        if magic != b"SBVM":
            raise BytecodeFormatError(
                f"bad magic: expected b'SBVM', got {magic!r}")

        version = struct.unpack("B", _read(f, 1, "version"))[0]
        if version != 1:
            raise BytecodeFormatError(
                f"unsupported version {version}")

        num_funcs = struct.unpack("<H", _read(f, 2, "num_funcs"))[0]
        entry_func = struct.unpack("<H", _read(f, 2, "entry_func"))[0]

        functions: List[BCFunction] = []
        for i in range(num_funcs):
            # name
            name_len = struct.unpack("B", _read(f, 1, f"func[{i}].name_len"))[0]
            name = _read(f, name_len, f"func[{i}].name").decode("ascii")

            # params
            num_params = struct.unpack("B", _read(f, 1, f"func[{i}].num_params"))[0]
            param_type_bytes = _read(f, num_params, f"func[{i}].param_types")
            param_types = []
            for b in param_type_bytes:
                if b not in _BYTE_TO_TYPE:
                    raise BytecodeFormatError(
                        f"func[{i}] ({name}): invalid param type byte {b}")
                param_types.append(_BYTE_TO_TYPE[b])

            # return type
            ret_byte = struct.unpack("B", _read(f, 1, f"func[{i}].return_type"))[0]
            if ret_byte not in _BYTE_TO_TYPE:
                raise BytecodeFormatError(
                    f"func[{i}] ({name}): invalid return type byte {ret_byte}")
            return_type = _BYTE_TO_TYPE[ret_byte]

            # locals
            num_locals = struct.unpack("<H", _read(f, 2, f"func[{i}].num_locals"))[0]
            local_type_bytes = _read(f, num_locals, f"func[{i}].local_types")
            local_types = []
            for b in local_type_bytes:
                if b not in _BYTE_TO_TYPE:
                    raise BytecodeFormatError(
                        f"func[{i}] ({name}): invalid local type byte {b}")
                local_types.append(_BYTE_TO_TYPE[b])

            # max_stack
            max_stack = struct.unpack("<H", _read(f, 2, f"func[{i}].max_stack"))[0]

            # code
            code_len = struct.unpack("<I", _read(f, 4, f"func[{i}].code_len"))[0]
            code = _read(f, code_len, f"func[{i}].code")

            functions.append(BCFunction(
                name=name,
                param_types=param_types,
                return_type=return_type,
                num_locals=num_locals,
                local_types=local_types,
                max_stack=max_stack,
                code=code,
            ))

        if entry_func >= len(functions):
            raise BytecodeFormatError(
                f"entry_func index {entry_func} >= num_funcs {len(functions)}")

        return BCModule(version=version, entry_func=entry_func,
                        functions=functions)
