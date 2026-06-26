import frappe
from frappe.model.document import Document

from calco_erp.machine_setup import (
    MACHINE_FIELD,
    OPERATOR_FIELD,
    SHIFT_FIELD,
    ensure_valid_machine,
    ensure_valid_operator,
    ensure_valid_shift,
)


class BatchProductionRecord(Document):
    def validate(self):
        if not self.status:
            self.status = "Completed"

        tracked_fields = resolve_tracking_fields(self.stock_entry, self.work_order)
        self.machine = self.machine or tracked_fields["machine"]
        self.operator = self.operator or tracked_fields["operator"]
        self.shift_type = self.shift_type or tracked_fields["shift_type"]

        if not self.stock_entry or not self.item_code or not self.fg_batch_no:
            frappe.throw("Stock Entry, production item, and FG batch are mandatory.")
        if not self.machine:
            frappe.throw("Machine is mandatory for Batch Production Record.")
        if not self.operator:
            frappe.throw("Operator is mandatory for Batch Production Record.")
        if not self.shift_type:
            frappe.throw("Shift is mandatory for Batch Production Record.")

        ensure_valid_machine(self.machine)
        ensure_valid_operator(self.operator)
        ensure_valid_shift(self.shift_type)


def create_from_stock_entry(doc, method=None):
    if (doc.get("stock_entry_type") or doc.get("purpose")) != "Manufacture":
        return

    if frappe.db.exists("Batch Production Record", {"stock_entry": doc.name}):
        return

    finished_row = next((row for row in doc.get("items", []) if row.get("is_finished_item")), None)
    if not finished_row or not finished_row.get("batch_no"):
        frappe.throw("Manufacture Stock Entry must contain a finished item row with Batch No.")

    work_order = frappe.get_doc("Work Order", doc.work_order) if doc.get("work_order") else None
    tracked_fields = resolve_tracking_fields(doc.name, doc.work_order)

    record = frappe.get_doc(
        {
            "doctype": "Batch Production Record",
            "stock_entry": doc.name,
            "work_order": doc.work_order,
            "production_plan": work_order.production_plan if work_order else "",
            "machine": tracked_fields["machine"],
            "operator": tracked_fields["operator"],
            "shift_type": tracked_fields["shift_type"],
            "item_code": finished_row.item_code,
            "fg_batch_no": finished_row.batch_no,
            "produced_qty": finished_row.qty,
            "status": "Completed",
        }
    )

    for row in doc.get("items", []):
        if row.get("is_finished_item") or not row.get("item_code") or not row.get("batch_no"):
            continue
        record.append(
            "materials",
            {
                "item_code": row.item_code,
                "batch_no": row.batch_no,
                "qty": row.qty,
                "source_warehouse": row.s_warehouse,
            },
        )

    record.insert(ignore_permissions=True)
    record.submit()


def resolve_tracking_fields(stock_entry_name: str | None, work_order_name: str | None) -> dict[str, str]:
    values = {"machine": "", "operator": "", "shift_type": ""}

    if stock_entry_name:
        values["machine"] = (frappe.db.get_value("Stock Entry", stock_entry_name, MACHINE_FIELD) or "").strip()
        values["operator"] = (frappe.db.get_value("Stock Entry", stock_entry_name, OPERATOR_FIELD) or "").strip()
        values["shift_type"] = (frappe.db.get_value("Stock Entry", stock_entry_name, SHIFT_FIELD) or "").strip()

    if work_order_name:
        values["machine"] = values["machine"] or (
            frappe.db.get_value("Work Order", work_order_name, MACHINE_FIELD) or ""
        ).strip()
        values["operator"] = values["operator"] or (
            frappe.db.get_value("Work Order", work_order_name, OPERATOR_FIELD) or ""
        ).strip()
        values["shift_type"] = values["shift_type"] or (
            frappe.db.get_value("Work Order", work_order_name, SHIFT_FIELD) or ""
        ).strip()

    return values
