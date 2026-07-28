from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness.agentforge_harness.generators import (
    gateway_records,
    vector_records,
    write_jsonl,
)
from harness.agentforge_harness.replay import (
    ReplayError,
    load_scenarios,
    replay_all,
    validate_scenario,
)
from harness.agentforge_harness.verify import verify_all


class ReplayGeneratorVerifyTest(unittest.TestCase):
    def test_all_required_replays_and_fixtures_pass(self) -> None:
        self.assertEqual(9, replay_all())
        result = verify_all()
        self.assertEqual(12, result["fake_llm_scenarios"])
        self.assertEqual(6, result["mock_mcp_scenarios"])

    def test_replay_rejects_non_contiguous_sequence(self) -> None:
        scenario = copy.deepcopy(load_scenarios()[0])
        scenario["events"][0]["sequence"] = 1
        with self.assertRaises(ReplayError):
            validate_scenario(scenario)

    def test_generators_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            write_jsonl(gateway_records(12, 20260728, 3), first)
            write_jsonl(gateway_records(12, 20260728, 3), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            vectors_a = root / "vectors-a.jsonl"
            vectors_b = root / "vectors-b.jsonl"
            write_jsonl(vector_records(10, 8, 20260728, 2), vectors_a)
            write_jsonl(vector_records(10, 8, 20260728, 2), vectors_b)
            self.assertEqual(vectors_a.read_bytes(), vectors_b.read_bytes())
            record = json.loads(vectors_a.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(8, len(record["vector"]))
            self.assertIn("tenant_id", record)

    def test_invalid_parameters_do_not_leave_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid.jsonl"
            with self.assertRaises(ValueError):
                write_jsonl(vector_records(2, 0, 1), output)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_name("invalid.jsonl.tmp").exists())


if __name__ == "__main__":
    unittest.main()
