from pathlib import Path
import sys
import tempfile
import unittest


TOOLS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIRECTORY))

import check  # noqa: E402


class JsonContractGateTests(unittest.TestCase):
    def test_resolve_pointer_supports_escaped_tokens(self) -> None:
        document = {"components": {"a/b": {"~value": 7}}}

        result = check.resolve_pointer(
            document,
            "/components/a~1b/~0value",
            check.ROOT / "contracts/example.json",
        )

        self.assertEqual(result, 7)

    def test_load_json_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=check.ROOT) as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{", encoding="utf-8")

            with self.assertRaises(check.GateError):
                check.load_json(path)

    def test_remote_reference_is_rejected(self) -> None:
        source = check.ROOT / "contracts/example.json"
        document = {"$ref": "https://example.invalid/schema.json"}

        with self.assertRaises(check.GateError):
            check.validate_references(source, document, {})

    def test_missing_local_reference_is_rejected(self) -> None:
        source = check.ROOT / "contracts/example.json"
        document = {"$ref": "./missing.schema.json#/$defs/Missing"}

        with self.assertRaises(check.GateError):
            check.validate_references(source, document, {})


if __name__ == "__main__":
    unittest.main()
