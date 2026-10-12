import csv
from pathlib import Path
import unittest

from audit_legacy import audit, parse
from power_budget import calculate


class PowerBudgetTests(unittest.TestCase):
    def test_known_scenario_and_energy_balance(self):
        result = calculate(72, 0.5, 0.9)
        self.assertAlmostEqual(result["output_w"], 36)
        self.assertAlmostEqual(result["input_w"], 40)
        self.assertAlmostEqual(result["loss_w"], 4)
        self.assertAlmostEqual(result["ideal_buck_inductance_h"], 0.000514285714)
        self.assertAlmostEqual(result["input_a"] * 126,
                               result["output_w"] + result["loss_w"])

    def test_impossible_or_nonfinite_inputs_rejected(self):
        for args in [(72, 1, 1.1), (126, 1, 0.9), (72, -1, 0.9),
                     (float("nan"), 1, 0.9), (72, 1, float("inf")), (72, 1, 0)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate(*args)

    def test_discontinuous_case_flagged(self):
        self.assertFalse(calculate(72, 0.01, 0.9)["ccm_assumption_valid"])


class LegacyAuditTests(unittest.TestCase):
    def test_connector_table_matches_source(self):
        table = Path(__file__).resolve().parents[1] / "legacy_connector.csv"
        with table.open() as f:
            rows = list(csv.DictReader(f))
        expected = audit()["pad_net_assignments"]["J1"]
        self.assertEqual(len(rows), 30)
        self.assertEqual({r["pad"]: r["pcb_net"] for r in rows}, expected)

    def test_strings_and_balancing(self):
        self.assertEqual(parse('(root (value "a (b)"))'), ["root", ["value", "a (b)"]])
        for text in ["(root", "(root))", "(a)(b)"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)


if __name__ == "__main__":
    unittest.main()
