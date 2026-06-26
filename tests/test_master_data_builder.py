import unittest

from calco_erp.data_foundation.master_data_builder import build_bom_templates, build_exception_reports


class TestMasterDataBuilder(unittest.TestCase):
    def test_exception_reports_flag_missing_and_invalid_formulations(self):
        rm_rows = [
            {"SKU Code": "RM-001", "Category": "Additive", "Item Name": "Additive 1"},
        ]
        fg_rows = [
            {"SKU Code": "FG-001", "Category": "PP", "Item Name": "Compound 1"},
        ]
        formulation_rows = [
            {"Product Code": "FG-001", "Revision Code": 1, "RM Code": "RM-001", "Dosage (%)": 99},
            {"Product Code": "FG-001", "Revision Code": 1, "RM Code": "", "Dosage (%)": 1},
            {"Product Code": "FG-002", "Revision Code": 1, "RM Code": "RM-404", "Dosage (%)": 0},
        ]

        exceptions = build_exception_reports(rm_rows, fg_rows, formulation_rows)

        self.assertEqual(len(exceptions["missing_fg_references"]), 1)
        self.assertEqual(len(exceptions["missing_rm_references"]), 2)
        self.assertEqual(len(exceptions["invalid_formulation_values"]), 1)

    def test_bom_templates_keep_only_valid_revision_groups(self):
        fg_rows = [
            {"SKU Code": "FG-001", "Category": "PP", "Item Name": "Compound 1"},
        ]
        formulation_rows = [
            {"Product Code": "FG-001", "Revision Code": 1, "RM Code": "RM-001", "Dosage (%)": 60},
            {"Product Code": "FG-001", "Revision Code": 1, "RM Code": "RM-002", "Dosage (%)": 40},
            {"Product Code": "FG-001", "Revision Code": 2, "RM Code": "RM-001", "Dosage (%)": 60},
            {"Product Code": "FG-001", "Revision Code": 2, "RM Code": "RM-002", "Dosage (%)": 35},
        ]
        exceptions = {
            "missing_fg_references": [],
            "missing_rm_references": [],
            "invalid_formulation_values": [],
            "bom_total_mismatches": [
                {"product_code": "FG-001", "revision_code": "2", "valid_line_count": 2, "total_dosage_percent": 95}
            ],
        }

        bom_headers, bom_items = build_bom_templates(fg_rows, formulation_rows, exceptions)

        self.assertEqual(len(bom_headers), 1)
        self.assertEqual(bom_headers[0]["name"], "BOM-FG-001-R1")
        self.assertEqual(len(bom_items), 2)


if __name__ == "__main__":
    unittest.main()
