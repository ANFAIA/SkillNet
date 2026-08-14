"""Focused tests for the offline R1-R8 experiment oracle."""

from __future__ import annotations

import unittest
from pathlib import Path

from output.harness.architecture_rounds import EvidenceLedger, load_config, run, sanitize


CONFIG = Path(__file__).with_name("architecture_rounds.json")


class ArchitectureRoundsTest(unittest.TestCase):
    def test_all_rounds_pass_the_declared_gates(self) -> None:
        report = run(load_config(CONFIG))

        self.assertTrue(report["passed"])
        self.assertEqual([item["round"] for item in report["rounds"]], [f"R{index}" for index in range(1, 9)])
        self.assertTrue(all(item["passed"] for item in report["rounds"]))

    def test_gate_failure_is_visible(self) -> None:
        config = load_config(CONFIG)
        config["rounds"]["R6"]["gates"][1]["threshold"] = 1

        report = run(config, ["R6"])

        self.assertFalse(report["passed"])
        self.assertFalse(report["rounds"][0]["gates"][1]["passed"])

    def test_evidence_is_idempotent(self) -> None:
        ledger = EvidenceLedger()

        self.assertTrue(ledger.record("same-attempt", 1.0, 0.4))
        self.assertFalse(ledger.record("same-attempt", 1.0, 0.4))
        self.assertEqual(ledger.mastery, 0.4)

    def test_reports_redact_credentials(self) -> None:
        value = sanitize({
            "password": "do-not-keep",
            "nested": ["Bearer abc.def.ghi", "sk-examplecredential123"],
        })

        self.assertEqual(value["password"], "[REDACTED]")
        self.assertNotIn("abc.def.ghi", str(value))
        self.assertNotIn("sk-examplecredential123", str(value))


if __name__ == "__main__":
    unittest.main()
