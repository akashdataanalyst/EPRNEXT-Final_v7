from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from calco_erp.calco_purchase.master_data_governance import (
    RM_QUALITY_TEMPLATE,
    create_or_update_planning_parameter,
    create_or_update_supplier_matrix_row,
    get_default_supplier_type_for_supplier,
    normalize_request_code,
)


class NewRMRequest(Document):
    def validate(self):
        self.rm_code = normalize_request_code(self.rm_code)
        self.rm_name = (self.rm_name or "").strip()
        self.description = (self.description or "").strip()
        self.recommended_material_type = (self.recommended_material_type or "").strip()
        self.application_suitability = (self.application_suitability or "").strip()
        self.technical_review_remarks = (self.technical_review_remarks or "").strip()
        self.document_readiness_remarks = (self.document_readiness_remarks or "").strip()
        self.required_incoming_tests = (self.required_incoming_tests or "").strip()
        self.quality_review_remarks = (self.quality_review_remarks or "").strip()
        self.purchase_payment_terms = (self.purchase_payment_terms or "").strip()
        self.commercial_remarks = (self.commercial_remarks or "").strip()
        if not self.status:
            self.status = "Draft"
        self.validate_duplicate_rm()
        self.validate_stage_reviews()

    def on_update(self):
        if self.status == "ERP Creation" and not frappe.utils.cint(self.erp_creation_completed):
            self.run_erp_creation()

    def validate_duplicate_rm(self):
        existing = frappe.db.get_value("Item", self.rm_code, ["name", "item_group"], as_dict=True)
        if existing and existing.name != (self.created_item or ""):
            frappe.throw(
                _("Item {0} already exists in ERP under Item Group {1}. Use the existing Item instead of a new RM Request.").format(
                    existing.name,
                    existing.item_group,
                )
            )

    def run_erp_creation(self):
        self.validate_erp_creation_prerequisites()
        item = self.create_item()
        planning_parameter = create_or_update_planning_parameter(
            item_code=item.name,
            preferred_supplier=self.preferred_supplier,
            current_season=self.current_season,
            manual_lead_time_days=self.manual_lead_time_days,
            safety_days=self.safety_days,
            review_period_days=self.review_period_days,
            minimum_order_qty=self.minimum_order_qty,
            purchase_pack_size=self.purchase_pack_size,
        )

        matrix_name = ""
        if self.preferred_supplier:
            matrix_name = create_or_update_supplier_matrix_row(
                item_code=item.name,
                supplier=self.preferred_supplier,
                supplier_type=get_default_supplier_type_for_supplier(self.preferred_supplier),
                approval_status="Approved",
            )

        self.db_set(
            {
                "created_item": item.name,
                "created_planning_parameter": planning_parameter,
                "created_supplier_matrix": matrix_name,
                "erp_creation_completed": 1,
                "creation_log": self.build_creation_log(item.name, planning_parameter, matrix_name),
                "preferred_supplier": self.preferred_supplier,
                "status": "Completed",
            },
            update_modified=False,
        )

    def create_item(self):
        item = frappe.new_doc("Item")
        item.item_code = self.rm_code
        item.item_name = self.rm_name
        item.item_group = "Raw Material"
        item.stock_uom = self.stock_uom or "Kg"
        item.is_stock_item = 1
        item.include_item_in_manufacturing = 1
        item.valuation_method = "Moving Average"
        item.has_batch_no = 1
        item.inspection_required_before_purchase = 1
        item.quality_inspection_template = RM_QUALITY_TEMPLATE
        item.custom_enable_rm_qc = 1
        item.allow_alternative_item = 0
        item.disabled = 0
        item.description = self.description or ""
        item.insert(ignore_permissions=True)
        return item

    def build_creation_log(self, item_name: str, planning_parameter: str, matrix_name: str) -> str:
        parts = [f"Created Item: {item_name}"]
        if planning_parameter:
            parts.append(f"Created RM Planning Parameter: {planning_parameter}")
        if matrix_name:
            parts.append(f"Created Supplier Approval Matrix: {matrix_name}")
        return "\n".join(parts)

    def validate_stage_reviews(self):
        before = self.get_doc_before_save()
        previous_status = (before.status or "").strip() if before else ""
        current_status = (self.status or "").strip()

        if previous_status == "Technical Review" and current_status in {"Quality Review", "Rejected"}:
            self.require_technical_review(current_status)
        if previous_status == "Technical Review" and current_status in {"Document & Sample Readiness"}:
            self.require_technical_review("Document & Sample Readiness")
        if previous_status == "Document & Sample Readiness" and current_status in {"Quality Review", "Rejected"}:
            self.require_document_readiness(current_status)
        if previous_status == "Quality Review" and current_status in {"Purchase Review", "Rejected"}:
            self.require_quality_review(current_status)
        if previous_status == "Purchase Review" and current_status in {"ERP Creation", "Rejected"}:
            self.require_purchase_review(current_status)

    def validate_erp_creation_prerequisites(self):
        self.require_technical_review("Document & Sample Readiness")
        self.require_document_readiness("Quality Review")
        self.require_quality_review("Purchase Review")
        self.require_purchase_review("ERP Creation")

    def require_technical_review(self, target_status: str):
        required = {
            "Technical Review Remarks": self.technical_review_remarks,
            "Existing Alternative Available?": self.existing_alternative_available,
            "Recommended Material Type": self.recommended_material_type,
            "Application Suitability": self.application_suitability,
            "Technical Approval Attachment": self.technical_approval_attachment,
            "Technical Decision": self.technical_decision,
        }
        self.throw_if_missing(required, "Technical Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.technical_decision != expected_decision:
            frappe.throw(_("Technical Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def require_quality_review(self, target_status: str):
        required = {
            "MSDS Available?": self.msds_available,
            "TDS Available?": self.tds_available,
            "COA Available?": self.coa_available,
            "Required Incoming Tests": self.required_incoming_tests,
            "Quality Review Remarks": self.quality_review_remarks,
            "Quality Approval Attachment": self.quality_approval_attachment,
            "Quality Decision": self.quality_decision,
        }
        self.throw_if_missing(required, "Quality Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.quality_decision != expected_decision:
            frappe.throw(_("Quality Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def require_document_readiness(self, target_status: str):
        required = {
            "TDS Attachment": self.tds_attachment,
            "MSDS Attachment": self.msds_attachment,
            "TC / COA Attachment": self.tc_coa_attachment,
            "Sample Available?": self.sample_available,
            "Sample Required?": self.sample_required,
            "Document Readiness Remarks": self.document_readiness_remarks,
            "Document Readiness Decision": self.document_readiness_decision,
        }
        self.throw_if_missing(required, "Document & Sample Readiness")

        if self.sample_required == "Yes":
            if not self.sample_quantity_kg or frappe.utils.flt(self.sample_quantity_kg) <= 0:
                frappe.throw(_("Document & Sample Readiness requires Sample Quantity Kg greater than 0 when Sample Required is Yes."))
            if self.sample_received_by_quality != "Yes":
                frappe.throw(_("Document & Sample Readiness requires Sample Received By Quality to be Yes when Sample Required is Yes."))
            if not self.sample_received_date:
                frappe.throw(_("Document & Sample Readiness requires Sample Received Date when Sample Required is Yes."))

        expected_decision = "Incomplete" if target_status == "Rejected" else "Complete"
        if self.document_readiness_decision != expected_decision:
            frappe.throw(
                _("Document Readiness Decision must be {0} before moving to {1}.").format(
                    expected_decision, target_status
                )
            )

    def require_purchase_review(self, target_status: str):
        required = {
            "Commercial Feasibility": self.commercial_feasibility_decision,
            "Target Rate": self.purchase_target_rate,
            "Lead Time Days": self.purchase_lead_time_days,
            "MOQ": self.purchase_moq,
            "Purchase Pack Size": self.purchase_pack_size,
            "Commercial Remarks": self.commercial_remarks,
            "Purchase Decision": self.purchase_decision,
        }
        self.throw_if_missing(required, "Purchase Review")
        expected_decision = "Rejected" if target_status == "Rejected" else "Approved"
        if self.purchase_decision != expected_decision:
            frappe.throw(_("Purchase Decision must be {0} before moving to {1}.").format(expected_decision, target_status))

    def throw_if_missing(self, required: dict[str, object], stage_label: str):
        missing = [label for label, value in required.items() if value in (None, "", [])]
        if missing:
            frappe.throw(_("{0} cannot be approved/rejected until these fields are completed: {1}").format(stage_label, ", ".join(missing)))
