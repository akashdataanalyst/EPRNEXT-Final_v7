import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from calco_erp.calco_production.doctype.production_consumption_entry import production_consumption_entry as pce


class DummyDoc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


class TestProductionConsumptionEntry(unittest.TestCase):
    def make_doc(self, items):
        return DummyDoc(
            warehouse="Main RM Warehouse",
            items=[frappe._dict(item) for item in items],
        )

    def test_validate_consumption_rows_accepts_three_rows(self):
        doc = self.make_doc(
            [
                {"rm_code": "RM-001", "rm_batch_no": "BATCH-001", "rm_qty_consumed": 10},
                {"rm_code": "RM-002", "rm_batch_no": "BATCH-002", "rm_qty_consumed": 5},
                {"rm_code": "RM-003", "rm_batch_no": "BATCH-003", "rm_qty_consumed": 3},
            ]
        )

        balances = {"BATCH-001": 20, "BATCH-002": 6, "BATCH-003": 3}
        with patch.object(pce, "validate_rm_batch") as validate_rm_batch, patch.object(
            pce, "get_batch_balance", side_effect=lambda item_code, batch_no, warehouse: balances[batch_no]
        ):
            pce.validate_consumption_rows(doc)

        self.assertEqual(validate_rm_batch.call_count, 3)
        self.assertEqual([row.available_batch_qty for row in doc.items], [20, 6, 3])

    def test_validate_consumption_rows_blocks_insufficient_stock(self):
        doc = self.make_doc(
            [{"rm_code": "RM-001", "rm_batch_no": "BATCH-001", "rm_qty_consumed": 10}]
        )
        thrower = lambda message: (_ for _ in ()).throw(frappe.ValidationError(message))

        with patch.object(pce, "_", side_effect=lambda message: message), patch.object(
            pce, "validate_rm_batch"
        ), patch.object(pce, "get_batch_balance", return_value=4), patch.object(
            pce.frappe, "throw", side_effect=thrower
        ):
            with self.assertRaises(frappe.ValidationError):
                pce.validate_consumption_rows(doc)

    def test_validate_consumption_rows_blocks_wrong_batch_for_rm(self):
        doc = self.make_doc(
            [{"rm_code": "RM-001", "rm_batch_no": "WRONG-BATCH", "rm_qty_consumed": 2}]
        )

        with patch.object(pce, "validate_rm_batch", side_effect=frappe.ValidationError("wrong batch")):
            with self.assertRaises(frappe.ValidationError):
                pce.validate_consumption_rows(doc)

    def test_validate_consumption_rows_blocks_duplicate_rm_batch(self):
        doc = self.make_doc(
            [
                {"rm_code": "RM-001", "rm_batch_no": "BATCH-001", "rm_qty_consumed": 4},
                {"rm_code": "RM-001", "rm_batch_no": "BATCH-001", "rm_qty_consumed": 5},
            ]
        )
        thrower = lambda message: (_ for _ in ()).throw(frappe.ValidationError(message))

        with patch.object(pce, "_", side_effect=lambda message: message), patch.object(
            pce, "validate_rm_batch"
        ), patch.object(pce, "get_batch_balance", return_value=100), patch.object(
            pce.frappe, "throw", side_effect=thrower
        ):
            with self.assertRaises(frappe.ValidationError):
                pce.validate_consumption_rows(doc)

    def test_create_material_issue_stock_entry_builds_one_row_per_rm_item(self):
        doc = DummyDoc(
            name="PCE-2026-0001",
            company="Calco PolyTechnik Pvt Ltd",
            warehouse="Main RM Warehouse",
            posting_datetime="2026-06-23 10:00:00",
            fg_code="FG-001",
            fg_batch_no="FG-BATCH-001",
            production_line="LINE-1",
            items=[
                frappe._dict({"rm_code": "RM-001", "rm_batch_no": "B-1", "rm_qty_consumed": 10, "category": "Prime", "challan_invoice_no": "CH-1", "remarks": "First"}),
                frappe._dict({"rm_code": "RM-002", "rm_batch_no": "B-2", "rm_qty_consumed": 5, "category": "Regrind", "challan_invoice_no": "CH-2", "remarks": "Second"}),
                frappe._dict({"rm_code": "RM-003", "rm_batch_no": "B-3", "rm_qty_consumed": 2, "category": "Additive", "challan_invoice_no": "CH-3", "remarks": "Third"}),
            ],
        )

        class Meta:
            def has_field(self, fieldname):
                return True

        def fake_get_doc(payload):
            result = DummyDoc(**payload)
            result.set = lambda fieldname, value: setattr(result, fieldname, value)
            result.insert = Mock()
            result.submit = Mock()
            return result

        fake_db = SimpleNamespace(get_value=lambda doctype, name, field: "Kg" if doctype == "Item" else None)
        with patch.object(pce, "_", side_effect=lambda message: message), patch.object(
            pce.frappe, "db", fake_db
        ), patch.object(pce, "create_outward_batch_bundle", side_effect=["BB-1", "BB-2", "BB-3"]), patch.object(
            pce.frappe, "get_doc", side_effect=fake_get_doc
        ), patch.object(pce.frappe, "get_meta", return_value=Meta()):
            result = pce.create_material_issue_stock_entry(doc)

        self.assertEqual(len(result.items), 3)
        self.assertEqual([row["item_code"] for row in result.items], ["RM-001", "RM-002", "RM-003"])
        self.assertEqual([row["serial_and_batch_bundle"] for row in result.items], ["BB-1", "BB-2", "BB-3"])

    def test_on_cancel_cancels_linked_stock_entry(self):
        doc = pce.ProductionConsumptionEntry.__new__(pce.ProductionConsumptionEntry)
        doc.stock_entry = "STE-0001"
        stock_entry = DummyDoc(docstatus=1, cancel=Mock())
        fake_db = SimpleNamespace(exists=lambda doctype, name: True)

        with patch.object(pce.frappe, "db", fake_db), patch.object(pce.frappe, "get_doc", return_value=stock_entry):
            pce.ProductionConsumptionEntry.on_cancel(doc)

        stock_entry.cancel.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
