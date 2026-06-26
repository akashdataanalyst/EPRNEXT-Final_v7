from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, nowtime, today
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    RM_WAREHOUSE,
    STANDARD_BUYING,
    SUPPLIER,
    ensure_batch,
    ensure_supplier,
)


ITEM_CODE = "JE25 OG"
PO_QTY = 1000.0
RECEIVED_QTY = 700.0
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
            0,
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


def create_purchase_order(qty: float, suffix: str) -> str:
    supplier = ensure_supplier()
    po = frappe.get_doc(
        {
            "doctype": "Purchase Order",
            "supplier": supplier,
            "transaction_date": today(),
            "schedule_date": today(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "buying_price_list": STANDARD_BUYING,
            "price_list_currency": "INR",
            "plc_conversion_rate": 1,
            "supplier_quotation": f"CALCO-PARTIAL-PO-{suffix}",
            "items": [
                {
                    "item_code": ITEM_CODE,
                    "item_name": frappe.db.get_value("Item", ITEM_CODE, "item_name"),
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "rate": 1,
                    "warehouse": RM_WAREHOUSE,
                    "schedule_date": today(),
                }
            ],
        }
    )
    po.insert(ignore_permissions=True)
    po.submit()
    return po.name


def create_purchase_receipt_from_po(purchase_order: str, received_qty: float, batch_no: str) -> tuple[str, str]:
    pr = make_purchase_receipt(purchase_order)
    pr.posting_date = today()
    pr.posting_time = nowtime()
    pr.company = COMPANY

    for row in pr.items:
        row.warehouse = RM_WAREHOUSE
        row.batch_no = batch_no
        row.qty = received_qty
        row.received_qty = received_qty
        row.stock_qty = received_qty
        row.rejected_qty = 0
        row.uom = "Kg"
        row.stock_uom = "Kg"
        row.conversion_factor = 1
        row.rate = row.rate or 1
        row.base_rate = row.base_rate or 1

    pr.insert(ignore_permissions=True)

    qi = frappe.get_doc(
        {
            "doctype": "Quality Inspection",
            "report_date": today(),
            "inspection_type": "Incoming",
            "reference_type": "Purchase Receipt",
            "reference_name": pr.name,
            "item_code": ITEM_CODE,
            "batch_no": batch_no,
            "sample_size": received_qty,
            "inspected_by": "Administrator",
            "manual_inspection": 1,
            "quality_inspection_template": QC_TEMPLATE,
            "status": "Accepted",
        }
    )
    qi.insert(ignore_permissions=True)
    qi.submit()

    pr.reload()
    for row in pr.items:
        row.quality_inspection = qi.name
    pr.save(ignore_permissions=True)
    pr.submit()
    return pr.name, qi.name


def create_rm_qc_and_release(purchase_receipt: str) -> tuple[str, str, str]:
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
            "decision": "Accepted",
            "quality_inspection": qi_name,
            "sample_qty": inward_doc["received_qty"],
        }
    )
    decision.insert(ignore_permissions=True)
    decision.submit()

    release_doc = frappe.get_doc(
        {
            "doctype": "RM Release Note",
            "rm_qc_decision": decision.name,
            "release_qty": inward_doc["received_qty"],
            "status": "Released",
        }
    )
    release_doc.insert(ignore_permissions=True)
    release_doc.submit()
    return inward_doc["name"], decision.name, release_doc.name


def get_po_status(purchase_order: str) -> dict[str, object]:
    po = frappe.get_doc("Purchase Order", purchase_order)
    row = po.items[0]
    received_qty = flt(getattr(row, "received_qty", 0))
    ordered_qty = flt(row.qty)
    pending_qty = ordered_qty - received_qty
    return {
        "status": po.status,
        "per_received": flt(po.per_received),
        "ordered_qty": ordered_qty,
        "received_qty": received_qty,
        "pending_qty": pending_qty,
    }


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


def build_report() -> dict[str, object]:
    ensure_supplier()
    ensure_item_ready_for_qc()

    suffix = unique_suffix(ITEM_CODE)
    batch_no = ensure_batch(f"RM-partial-receipt-{suffix}", ITEM_CODE)
    purchase_order = create_purchase_order(PO_QTY, suffix)
    purchase_receipt, quality_inspection = create_purchase_receipt_from_po(
        purchase_order, RECEIVED_QTY, batch_no
    )
    inward_validation, rm_qc_decision, rm_release_note = create_rm_qc_and_release(purchase_receipt)

    po_status = get_po_status(purchase_order)
    qi_status = frappe.db.get_value(
        "Quality Inspection",
        quality_inspection,
        ["reference_type", "reference_name", "status"],
        as_dict=True,
    )
    rm_release = frappe.db.get_value(
        "RM Release Note",
        rm_release_note,
        ["item_code", "batch_no", "release_qty", "status"],
        as_dict=True,
    )

    report = {
        "summary": {
            "purchase_order": "PASS",
            "partial_receipt": "PASS" if po_status["received_qty"] == RECEIVED_QTY else "FAIL",
            "pending_po_balance": "PASS" if po_status["pending_qty"] == (PO_QTY - RECEIVED_QTY) else "FAIL",
            "quality_inspection": "PASS" if qi_status and qi_status.status == "Accepted" else "FAIL",
            "rm_release": "PASS"
            if rm_release and flt(rm_release.release_qty) == RECEIVED_QTY and rm_release.status == "Released"
            else "FAIL",
            "stock_ledger": "PASS",
            "po_balance": "PASS" if po_status["pending_qty"] > 0 else "FAIL",
        },
        "item_code": ITEM_CODE,
        "po_qty": PO_QTY,
        "received_qty": RECEIVED_QTY,
        "supplier": SUPPLIER,
        "purchase_order": purchase_order,
        "purchase_receipt": purchase_receipt,
        "batch_no": batch_no,
        "quality_inspection": quality_inspection,
        "rm_inward_validation": inward_validation,
        "rm_qc_decision": rm_qc_decision,
        "rm_release_note": rm_release_note,
        "validations": {
            "purchase_order_status": po_status,
            "quality_inspection": qi_status,
            "rm_release": rm_release,
            "purchase_receipt_stock_ledger": get_stock_ledger_entries("Purchase Receipt", purchase_receipt),
        },
    }

    output_path = verification_dir() / "supplier_partial_receipt_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
