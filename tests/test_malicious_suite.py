"""Verify each handcrafted malicious .bc file on disk triggers its expected rule."""

from pathlib import Path
import unittest

from codegen.serializer import load_bytecode, BytecodeFormatError
from verifier import verify, VerifyError


EXPECTED_RULES = {
    "bad_call_1.bc": "BAD_CALL",
    "bad_call_2.bc": "BAD_CALL",
    "bad_jump_1.bc": "BAD_JUMP",
    "bad_jump_2.bc": "BAD_JUMP",
    "bad_opcode_1.bc": "BAD_OPCODE",
    "bad_opcode_2.bc": "BAD_OPCODE",
    "bad_return_1.bc": "BAD_RETURN",
    "bad_return_2.bc": "BAD_RETURN",
    "fallthrough_1.bc": "FALLTHROUGH",
    "fallthrough_2.bc": "FALLTHROUGH",
    "local_range_1.bc": "LOCAL_RANGE",
    "local_range_2.bc": "LOCAL_RANGE",
    "local_type_1.bc": "LOCAL_TYPE",
    "local_type_2.bc": "LOCAL_TYPE",
    "local_unset_1.bc": "LOCAL_UNSET",
    "local_unset_2.bc": "LOCAL_UNSET",
    "merge_mismatch_1.bc": "MERGE_MISMATCH",
    "merge_mismatch_2.bc": "MERGE_MISMATCH",
    "stack_overflow_1.bc": "STACK_OVERFLOW",
    "stack_overflow_2.bc": "STACK_OVERFLOW",
    "stack_type_1.bc": "STACK_TYPE",
    "stack_type_2.bc": "STACK_TYPE",
    "stack_underflow_1.bc": "STACK_UNDERFLOW",
    "stack_underflow_2.bc": "STACK_UNDERFLOW",
    "truncated_1.bc": "TRUNCATED",
    "truncated_2.bc": "TRUNCATED",
}


class TestMaliciousFilesOnDisk(unittest.TestCase):
    def test_all_malicious_files_trigger_expected_rules(self):
        malicious_dir = Path("tests/malicious")
        self.assertTrue(malicious_dir.exists(), "tests/malicious/ directory must exist")

        for fname, expected_rule in sorted(EXPECTED_RULES.items()):
            fpath = malicious_dir / fname
            self.assertTrue(fpath.exists(), f"File {fname} must exist on disk")

            with self.subTest(file=fname, expected=expected_rule):
                try:
                    mod = load_bytecode(fpath)
                    verify(mod)
                    self.fail(f"File {fname} was accepted by verifier, expected {expected_rule}")
                except VerifyError as e:
                    self.assertEqual(e.rule, expected_rule,
                                     f"{fname}: expected {expected_rule}, got {e.rule}")
                except BytecodeFormatError:
                    self.fail(f"{fname}: unexpected BytecodeFormatError during load")


if __name__ == "__main__":
    unittest.main()
