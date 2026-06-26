import unittest

from calco_erp.calco_quality.fg_quantity_rules import get_quantity_multiplier, get_required_test_count


class TestFgQuantityRules(unittest.TestCase):
    def test_quantity_multiplier_uses_five_mt_slabs(self):
        self.assertEqual(get_quantity_multiplier(5.0), 1)
        self.assertEqual(get_quantity_multiplier(10.0), 2)
        self.assertEqual(get_quantity_multiplier(15.0), 3)
        self.assertEqual(get_quantity_multiplier(5.01), 2)

    def test_required_tests_use_multiplier_sample_and_frequency(self):
        self.assertEqual(get_required_test_count(1, 2, 3), 6)
        self.assertEqual(get_required_test_count(2, 2, 3), 12)
        self.assertEqual(get_required_test_count(3, 2, 3), 18)

    def test_required_tests_skip_non_positive_inputs(self):
        self.assertEqual(get_required_test_count(0, 2, 3), 0)
        self.assertEqual(get_required_test_count(2, 0, 3), 0)
        self.assertEqual(get_required_test_count(2, 2, 0), 0)


if __name__ == "__main__":
    unittest.main()
