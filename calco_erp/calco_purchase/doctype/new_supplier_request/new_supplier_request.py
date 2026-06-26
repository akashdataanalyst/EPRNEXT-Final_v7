from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from calco_erp.calco_purchase.master_data_governance import (
    create_or_update_planning_parameter,
    create_or_update_supplier_matrix_row,
)


class NewSupplierRequest(Document):
    def validate(self):
        self.supplier_name = (self.supplier_name or "").strip()
        self.certificates_checked = (self.certificates_checked or "").strip()
        self.supplier_quality_remarks = (self.supplier_quality_remarks or "").strip()
        self.supplier_purchase_payment_terms = (self.supplier_purchase_payment_terms or "").strip()
        self.commercial_terms = (self.commercial_terms or "").strip()
        self.supplier_purchase_remarks = (self.supplier_purchase_remarks or "").strip()
        self.risk_remarks = (self.risk_remarks or "").strip()
        if not self.status:
            self.status = "Draft"
        self.validate_duplicate_supplier()
        self.validate_request_items()
        self.validate_stage_reviews()

    def on_update(self):
        if self.status == "ERP Creation" and not frappe.utils.cint(self.erp_creation_completed):
            self.run_erp_creation()

    def validate_duplicate_supplier(self):
        existing = frappe.db.get_value("Supplier", {"supplier_name": self.supplier_name}, "name")
        if existing and existing != (self.created_supplier or ""):
            frappe.throw(_("Supplier {0} already exists in ERP. Use the existing Supplier instead of a new Supplier Request.").format(existing))

    def validate_request_items(self):
        if not self.supplier_request_items:
            frappe.throw(_("At least one RM item is required to create Supplier Approval Matrix rows."))
        for row in self.supplier_request_items:
            if not row.item_code:
                frappe.throw(_("Each Supplier Request row must specify an Item Code."))
            item_group = frappe.db.get_value("Item", row.item_code, "item_group")
            if item_group != "Raw Material":
                frappe.throw(_("Supplier Request items must be Raw Material items. {0} is currently in Item Group {1}.").format(row.item_code, item_group or "-"))

    def run_erp_creation(self):
        self.validate_erp_creation_prerequisites()
        supplier_name = self.create_supplier()
        created_matrix_rows = []
        touched_planning = []

        for row in self.supplier_request_items:
            matrix_name = create_or_update_supplier_matrix_row(
                item_code=row.item_code,
                supplier=supplier_name,
                supplier_type=self.supplier_type,
                approval_status=row.approval_status or "Approved",
                supplier_rating=row.supplier_rating or getattr(self, "supplier_rating", 0),
                lead_time=row.lead_time or self.lead_time_days,
                payment_terms=row.payment_terms or self.payment_terms,
                effective_date=row.effective_date or self.effective_date,
                expiry_date=row.expiry_date or self.expiry_date,
            )
            created_matrix_rows.append(matrix_name)
            touched_planning.append(
                create_or_update_planning_parameter(
                    item_code=row.item_code,
                    preferred_supplier=supplier_name,
                )
            )

        self.db_set(
            {
                "created_supplier": supplier_name,
                "created_matrix_rows": "\n".join(created_matrix_rows),
                "created_planning_parameters": "\n".join([name for name in touched_planning if name]),
                "erp_creation_completed": 1,
                "creation_log": self.build_creation_log(supplier_name, created_matrix_rows, touched_planning),
                "status": "Completed",
            },
            update_modified=False,
        )

    def create_supplier(self) -> str:
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = self.supplier_name
        supplier.supplier_type = "Company"
        if frappe.db.exists("Supplier Group", "All Supplier Groups"):
            supplier.supplier_group = "All Supplier Groups"
        supplier.insert(ignore_permissions=True)
        return supplier.name

    def build_creation_log(self, supplier_name: str, matrix_rows: list[str], planning_rows: list[str]) -> str:
        parts = [f"Created Supplier: {supplier_name}"]
        if matrix_rows:
            parts.append("Created Supplier Approval Matrix Rows: " + ", ".join(matrix_rows))
        if planning_rows:
            parts.append("Touched RM Planning Parameters: " + ", ".join([name for name in planning_rows if name]))
        return "\n".join(parts)

    def validate_stage_reviews(self):
        before = self.get_doc_before_save()
        previous_status = (before.status or "").strip() if before else ""
        current_status = (self.status or "").strip()

        if previous_status == "Quality Review" and current_status in {"Purchase Review", "Rejected"}:
            self.require_quality_review(current_status)
        if previous_status == "Purchase Review" and current_status in {"Management Review", "Rejected"}:
            self.require_purchase_review(current_status)
        if previous_status == "Management Review" and current_status in {"ERP Creation", "Rejected"}:
            self.require_management_review(current_status)

    def validate_erp_creation_prerequisites(self):
        self.require_quality_review("Purchase Review")
        self.require_purchase_review("Management Review")
        self.require_management_review("ERP Creation")

    def require_quality_review(self, target_status: str):
        required = {
            "Certificates Checked": self.certificates_checked,
            "Quality Audit Required?": self.quality_audit_required,
            "Quality Remarks": self.supplier_quality_remarks,
            "Quality Decision": self.supplier_quality_decision,
        }
        self.throw_if_missing(required, "Quality Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.supplier_quality_decision != expected_decision:
            frappe.throw(_("Quality Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def require_purchase_review(self, target_status: str):
        required = {
            "Lead Time": self.supplier_purchase_lead_time,
            "MOQ": self.supplier_purchase_moq,
            "Payment Terms": self.supplier_purchase_payment_terms,
            "Commercial Terms": self.commercial_terms,
            "Purchase Remarks": self.supplier_purchase_remarks,
            "Purchase Decision": self.supplier_purchase_decision,
        }
        self.throw_if_missing(required, "Purchase Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.supplier_purchase_decision != expected_decision:
            frappe.throw(_("Purchase Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def require_management_review(self, target_status: str):
        required = {
            "Strategic Supplier?": self.strategic_supplier,
            "Risk Remarks": self.risk_remarks,
            "Final Approval Decision": self.final_approval_decision,
        }
        self.throw_if_missing(required, "Management Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.final_approval_decision != expected_decision:
            frappe.throw(_("Final Approval Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def throw_if_missing(self, required: dict[str, object], stage_label: str):
        missing = [label for label, value in required.items() if value in (None, "", [])]
        if missing:
            frappe.throw(_("{0} cannot be approved/rejected until these fields are completed: {1}").format(stage_label, ", ".join(missing)))
