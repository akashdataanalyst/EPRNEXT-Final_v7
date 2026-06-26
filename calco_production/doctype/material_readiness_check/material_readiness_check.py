import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from erpnext.stock.utils import get_stock_balance


REWORK_WAREHOUSE_PREFIX = "Rework"


class MaterialReadinessCheck(Document):
    def validate(self):
        if self.work_order:
            work_order = frappe.get_doc("Work Order", self.work_order)
            self.production_item = work_order.production_item
            self.bom_no = work_order.bom_no
            self.planned_qty = work_order.qty

        if not self.checked_by:
            self.checked_by = frappe.session.user
        if not self.checked_on:
            self.checked_on = now_datetime()

        shortages = self.get_shortages()
        self.shortage_summary = "\n".join(shortages)

        if self.status == "Ready" and shortages:
            frappe.throw("Material Readiness Check cannot be Ready while BOM items are missing released RM.")

        if shortages and self.status == "Draft":
            self.status = "Blocked"
        elif not shortages and self.status in ("Draft", "Blocked"):
            self.status = "Ready"

    def get_shortages(self):
        if not self.bom_no or not self.planned_qty:
            return []

        bom_qty = frappe.db.get_value("BOM", self.bom_no, "quantity") or 1
        factor = float(self.planned_qty) / float(bom_qty or 1)

        shortages = []
        source_warehouse = ""
        if self.work_order:
            source_warehouse = (
                frappe.db.get_value("Work Order", self.work_order, "source_warehouse") or ""
            ).strip()

        bom_items = frappe.get_all(
            "BOM Item",
            filters={"parent": self.bom_no},
            fields=["item_code", "qty"],
            order_by="idx asc",
        )

        for item in bom_items:
            required_qty = float(item.qty or 0) * factor
            if source_warehouse.startswith(REWORK_WAREHOUSE_PREFIX):
                available_qty = float(get_stock_balance(item.item_code, source_warehouse) or 0)
                if available_qty + 1e-9 < required_qty:
                    shortages.append(
                        f"{item.item_code}: required {round(required_qty, 3)} Kg, available in {source_warehouse} {round(available_qty, 3)} Kg"
                    )
                continue

            released_qty = (
                frappe.db.sql(
                    """
                    select coalesce(sum(release_qty), 0)
                    from `tabRM Release Note`
                    where docstatus = 1 and status = 'Released' and item_code = %s
                    """,
                    item.item_code,
                )[0][0]
                or 0
            )
            if released_qty + 1e-9 < required_qty:
                shortages.append(
                    f"{item.item_code}: required {round(required_qty, 3)} Kg, released {round(released_qty, 3)} Kg"
                )

        return shortages
