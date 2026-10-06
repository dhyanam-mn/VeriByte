"""Verifier error reporting."""


class VerifyError(Exception):
    """Raised when static bytecode verification fails."""

    def __init__(self, func_name: str, offset: int, mnemonic: str, rule: str,
                 expected: str = "", actual: str = ""):
        self.func_name = func_name
        self.offset = offset
        self.mnemonic = mnemonic
        self.rule = rule
        self.expected = expected
        self.actual = actual

        lines = [f"verify error in function '{func_name}' at offset {offset} ({mnemonic}):"]
        lines.append(f"  rule: {rule}")
        if expected:
            lines.append(f"  expected: {expected}")
        if actual:
            lines.append(f"  actual: {actual}")
        super().__init__("\n".join(lines))
