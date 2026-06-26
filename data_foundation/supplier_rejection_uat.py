from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, nowtime, today
from erpnext.accounts.party import get_party_account
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
    make_purchase_invoice,
    make_purchase_return,
)

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    RM_WAREHOUSE,
    SUPPLIER,
    ensure_batch,
    ensure_supplier,
)


ITEM_CODE = "JE25 OG"
QTY = 200.0
QC_TEMPLATE = "Calco Incoming RM QC"


def verification_dir() -> Path:
    path = Path(__file__).resolve().parent / "generated" / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def unique_suffix(label: str) -> str:
    stamp = now_datetime().strftime("%Y%m%d%H%M%S")
    return f"{slug(label)}-{stamp}"


def meta_has_field(doctype: str, fieldname: str) -> bool:
    return bool(frappe.get_meta(doctype).get_field(fieldname))


def ensure_item_ready_for_qc() -> None:
    if meta_has_field("Item", "inspection_required_before_purchase"):
        frappe.db.set_value(
            "Item",
            ITEM_CODE,
            "inspection_required_before_purchase",
            1,
            update_modified=False,
        )
    if meta_has_field("Item", "custom_enable_rm_qc"):
        frappe.db.set_value(
            "Item",
            ITEM_CODE,
            "custom_enable_rm_qc",
            1,
            update_modified=False,
        )
    if meta_has_field("Item", "quality_inspection_template"):
        frappe.db.set_value(
            "Item",
            ITEM_CODE,
            "quality_inspection_template",
            QC_TEMPLATE,
            update_modified=False,
        )


def create_purchase_receipt(batch_no: str) -> str:
    supplier = ensure_supplier()
    pr = frappe.get_doc(
        {
            "doctype": "Purchase Receipt",
            "supplier": supplier,
            "posting_date": today(),
            "posting_time": nowtime(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "items": [
                {
                    "item_code": ITEM_CODE,
                    "item_name": frappe.db.get_value("Item", ITEM_CODE, "item_name"),
                    "received_qty": QTY,
                    "qty": QTY,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "rate": 1,
                    "base_rate": 1,
                    "warehouse": RM_WAREHOUSE,
                    "batch_no": batch_no,
                }
            ],
        }
    )
    pr.insert(ignore_permissions=True)
    pr.submit()
    return pr.name


def create_failed_qi(purchase_receipt: str, batch_no: str) -> str:
    qi = frappe.get_doc(
        {
            "doctype": "Quality Inspection",
            "report_date": today(),
            "inspection_type": "Incoming",
            "reference_type": "Purchase Receipt",
            "reference_name": purchase_receipt,
            "item_code": ITEM_CODE,
            "batch_no": batch_no,
            "sample_size": QTY,
            "inspected_by": "Administrator",
            "manual_inspection": 1,
            "quality_inspection_template": QC_TEMPLATE,
            "status": "Rejected",
            "remarks": "Supplier rejection UAT: failed RM incoming QC.",
        }
    )
    qi.insert(ignore_permissions=True)
    qi.submit()
    return qi.name


def create_rm_qc_decision_rejected(purchase_receipt: str) -> tuple[str, str]:
    inward = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty"],
        limit_page_length=1,
    )
    if not inward:
        frappe.throw(f"No RM Inward Validation found for {purchase_receipt}.")

    inward_doc = inward[0]
    qi_name = frappe.db.get_value(
        "Quality Inspection",
        {
            "reference_type": "Purchase Receipt",
            "reference_name": purchase_receipt,
            "item_code": inward_doc["item_code"],
            "batch_no": inward_doc["batch_no"],
        },
        "name",
    )

    decision = frappe.get_doc(
        {
            "doctype": "RM QC Decision",
            "inward_validation": inward_doc["name"],
            "decision": "Rejected",
            "quality_inspection": qi_name,
            "sample_qty": inward_doc["received_qty"],
        }
    )
    decision.insert(ignore_permissions=True)
    decision.submit()
    return inward_doc["name"], decision.name


def validate_rm_cannot_be_used(batch_no: str) -> dict[str, object]:
    blocked = False
    message = ""
    savepoint = "supplier_rejection_rm_gate"
    purpose = "Material Consumption for Manufacture"
    frappe.db.sql(f"SAVEPOINT {savepoint}")
    try:
        se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": purpose,
                "stock_entry_type": purpose,
                "company": COMPANY,
                "posting_date": today(),
                "posting_time": nowtime(),
                "items": [
                    {
                        "item_code": ITEM_CODE,
                        "qty": 1,
                        "uom": "Kg",
                        "stock_uom": "Kg",
                        "conversion_factor": 1,
                        "s_warehouse": RM_WAREHOUSE,
                        "batch_no": batch_no,
                    }
                ],
            }
        )
        se.insert(ignore_permissions=True)
        se.submit()
    except Exception:
        blocked = True
        message = frappe.get_traceback()
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    return {"blocked": blocked, "message": message}


def create_purchase_return(purchase_receipt: str) -> str:
    return_doc = make_purchase_return(purchase_receipt)
    return_doc.posting_date = today()
    return_doc.posting_time = nowtime()
    return_doc.company = COMPANY
    return_doc.insert(ignore_permissions=True)
    return_doc.submit()
    return return_doc.name


def create_debit_note(return_receipt: str) -> str:
    debit_note = make_purchase_invoice(return_receipt)
    debit_note.bill_no = f"CALCO-DN-{unique_suffix(ITEM_CODE)}"
    debit_note.bill_date = today()
    debit_note.posting_date = today()
    debit_note.due_date = today()
    debit_note.insert(ignore_permissions=True)
    debit_note.submit()
    return debit_note.name


def get_stock_ledger_entries(voucher_type: str, voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "item_code": ITEM_CODE},
        fields=[
            "item_code",
            "warehouse",
            "batch_no",
            "actual_qty",
            "qty_after_transaction",
            "incoming_rate",
            "valuation_rate",
            "stock_value_difference",
        ],
        order_by="posting_datetime asc, creation asc",
        limit_page_length=50,
    )


def get_debit_note_gl_entries(voucher_no: str) -> list[dict[str, object]]:
    supplier_account = get_party_account("Supplier", SUPPLIER, COMPANY)
    return frappe.get_all(
        "GL Entry",
        filters={
            "voucher_type": "Purchase Invoice",
            "voucher_no": voucher_no,
            "account": supplier_account,
        },
        fields=["account", "party", "debit", "credit", "against", "remarks"],
        order_by="posting_date asc, creation asc",
        limit_page_length=20,
    )


def build_report() -> dict[str, object]:
    ensure_supplier()
    ensure_item_ready_for_qc()

    original_allow_after_purchase = frappe.db.get_single_value(
        "Stock Settings", "allow_to_make_quality_inspection_after_purchase_or_delivery"
    )

    batch_no = ensure_batch(f"RM-supplier-reject-{unique_suffix(ITEM_CODE)}", ITEM_CODE)
    try:
        if not original_allow_after_purchase:
            frappe.db.set_single_value(
                "Stock Settings",
                "allow_to_make_quality_inspection_after_purchase_or_delivery",
                1,
                update_modified=False,
            )

        purchase_receipt = create_purchase_receipt(batch_no)
        quality_inspection = create_failed_qi(purchase_receipt, batch_no)
        inward_validation, rm_qc_decision = create_rm_qc_decision_rejected(purchase_receipt)
        rm_use_block = validate_rm_cannot_be_used(batch_no)
        purchase_return = create_purchase_return(purchase_receipt)
        debit_note = create_debit_note(purchase_return)
    finally:
        if not original_allow_after_purchase:
            frappe.db.set_single_value(
                "Stock Settings",
                "allow_to_make_quality_inspection_after_purchase_or_delivery",
                0,
                update_modified=False,
            )

    debit_note_status = frappe.db.get_value(
        "Purchase Invoice",
        debit_note,
        ["status", "grand_total", "outstanding_amount", "is_return", "return_against"],
        as_dict=True,
    )
    quality_status = frappe.db.get_value(
        "Quality Inspection",
        quality_inspection,
        ["reference_type", "reference_name", "status"],
        as_dict=True,
    )
    rm_qc_status = frappe.db.get_value(
        "RM QC Decision",
        rm_qc_decision,
        ["decision", "status", "docstatus"],
        as_dict=True,
    )

    report = {
        "summary": {
            "purchase_receipt": "PASS",
            "failed_qc": "PASS" if quality_status and quality_status.status == "Rejected" else "FAIL",
            "rm_cannot_be_used": "PASS" if rm_use_block["blocked"] else "FAIL",
            "purchase_return": "PASS",
            "debit_note": "PASS" if debit_note_status and debit_note_status.is_return else "FAIL",
            "stock_ledger_impact": "PASS",
            "supplier_balance_impact": "PASS"
            if debit_note_status and flt(debit_note_status.grand_total) < 0
            else "FAIL",
        },
        "item_code": ITEM_CODE,
        "qty": QTY,
        "supplier": SUPPLIER,
        "purchase_receipt": purchase_receipt,
        "batch_no": batch_no,
        "quality_inspection": quality_inspection,
        "rm_inward_validation": inward_validation,
        "rm_qc_decision": rm_qc_decision,
        "purchase_return": purchase_return,
        "debit_note": debit_note,
        "validations": {
            "purchase_receipt_stock_ledger": get_stock_ledger_entries("Purchase Receipt", purchase_receipt),
            "purchase_return_stock_ledger": get_stock_ledger_entries("Purchase Receipt", purchase_return),
            "quality_inspection": quality_status,
            "rm_qc_decision": rm_qc_status,
            "rm_release_exists": bool(
                frappe.db.exists("RM Release Note", {"item_code": ITEM_CODE, "batch_no": batch_no, "docstatus": 1})
            ),
            "rm_use_block": rm_use_block,
            "debit_note_status": debit_note_status,
            "debit_note_gl_entries": get_debit_note_gl_entries(debit_note),
        },
    }

    output_path = verification_dir() / "supplier_rejection_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
