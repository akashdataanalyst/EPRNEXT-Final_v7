import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class FinalQCRelease(Document):
    def validate(self):
        if self.batch_production_record:
            record = frappe.get_doc("Batch Production Record", self.batch_production_record)
            self.stock_entry = record.stock_entry
            self.item_code = record.item_code
            self.batch_no = record.fg_batch_no

        if not self.status:
            self.status = "Pending"

    def before_submit(self):
        if self.status not in ("Released", "Hold", "Rejected"):
            frappe.throw("Final QC Release must be Released, Hold, or Rejected before submit.")

        if self.status == "Released":
            required = ["moisture", "mfi", "ash", "density"]
            missing = [field for field in required if self.get(field) in (None, "")]
            if missing:
                frappe.throw("Moisture, MFI, Ash, and Density are mandatory for Released Final QC.")

            if self.quality_inspection:
                inspection = frappe.get_doc("Quality Inspection", self.quality_inspection)
                if inspection.docstatus != 1 or inspection.status != "Accepted":
                    frappe.throw("Released Final QC requires a submitted Accepted Quality Inspection.")

            self.released_on = self.released_on or now_datetime()

    def on_submit(self):
        if self.status == "Released":
            self.create_or_update_coa()
            if self.batch_production_record:
                record = frappe.get_doc("Batch Production Record", self.batch_production_record)
                record.db_set("status", "Released", update_modified=False)

    def create_or_update_coa(self):
        if self.coa_record and frappe.db.exists("COA Record", self.coa_record):
            coa = frappe.get_doc("COA Record", self.coa_record)
        elif frappe.db.exists("COA Record", {"final_qc_release": self.name}):
            coa_name = frappe.db.get_value("COA Record", {"final_qc_release": self.name}, "name")
            coa = frappe.get_doc("COA Record", coa_name)
        else:
            coa = frappe.new_doc("COA Record")

        coa.final_qc_release = self.name
        coa.item_code = self.item_code
        coa.batch_no = self.batch_no
        coa.issue_date = self.released_on
        coa.moisture = self.moisture
        coa.mfi = self.mfi
        coa.ash = self.ash
        coa.density = self.density
        coa.status = "Issued"

        if coa.is_new():
            coa.insert(ignore_permissions=True)
        else:
            coa.save(ignore_permissions=True)

        self.db_set("coa_record", coa.name, update_modified=False)
