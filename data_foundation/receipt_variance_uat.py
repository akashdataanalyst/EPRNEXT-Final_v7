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
UNDER_RECEIPT_QTY = 700.0
OVER_RECEIPT_QTY = 1100.0
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


def get_receipt_allowance_config() -> dict[str, object]:
    return {
        "stock_settings_over_delivery_receipt_allowance": flt(
            frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance") or 0
        ),
        "item_over_delivery_receipt_allowance": flt(
            frappe.db.get_value("Item", ITEM_CODE, "over_delivery_receipt_allowance") or 0
        ),
    }


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
            "supplier_quotation": f"CALCO-VARIANCE-PO-{suffix}",
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


def create_manual_qi(reference_name: str, batch_no: str, qty: float) -> str:
    qi = frappe.get_doc(
        {
            "doctype": "Quality Inspection",
            "report_date": today(),
            "inspection_type": "Incoming",
            "reference_type": "Purchase Receipt",
            "reference_name": reference_name,
            "item_code": ITEM_CODE,
            "batch_no": batch_no,
            "sample_size": qty,
            "inspected_by": "Administrator",
            "manual_inspection": 1,
            "quality_inspection_template": QC_TEMPLATE,
            "status": "Accepted",
        }
    )
    qi.insert(ignore_permissions=True)
    qi.submit()
    return qi.name


def attempt_purchase_receipt(purchase_order: str, qty: float, batch_no: str) -> dict[str, object]:
    savepoint = f"receipt_variance_{slug(batch_no).replace('-', '_')}"
    frappe.db.sql(f"SAVEPOINT {savepoint}")

    pr_name = ""
    qi_name = ""
    submitted = False
    blocked_message = ""

    try:
        pr = make_purchase_receipt(purchase_order)
        pr.posting_date = today()
        pr.posting_time = nowtime()
        pr.company = COMPANY

        for row in pr.items:
            row.warehouse = RM_WAREHOUSE
            row.batch_no = batch_no
            row.qty = qty
            row.received_qty = qty
            row.stock_qty = qty
            row.rejected_qty = 0
            row.uom = "Kg"
            row.stock_uom = "Kg"
            row.conversion_factor = 1
            row.rate = row.rate or 1
            row.base_rate = row.base_rate or 1

        pr.insert(ignore_permissions=True)
        pr_name = pr.name
        qi_name = create_manual_qi(pr.name, batch_no, qty)

        pr.reload()
        for row in pr.items:
            row.quality_inspection = qi_name
        pr.save(ignore_permissions=True)
        pr.submit()
        submitted = True
    except Exception:
        blocked_message = frappe.get_traceback()
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    return {
        "purchase_receipt": pr_name,
        "quality_inspection": qi_name,
        "submitted": submitted,
        "blocked_message": blocked_message,
    }


def get_po_status(purchase_order: str) -> dict[str, object]:
    po = frappe.get_doc("Purchase Order", purchase_order)
    row = po.items[0]
    ordered_qty = flt(row.qty)
    received_qty = flt(getattr(row, "received_qty", 0))
    return {
        "status": po.status,
        "per_received": flt(po.per_received),
        "ordered_qty": ordered_qty,
        "received_qty": received_qty,
        "pending_qty": ordered_qty - received_qty,
    }


def get_stock_ledger_entries(voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Purchase Receipt", "voucher_no": voucher_no, "item_code": ITEM_CODE},
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


def get_gl_entries(voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "GL Entry",
        filters={"voucher_type": "Purchase Receipt", "voucher_no": voucher_no},
        fields=["account", "debit", "credit", "against", "remarks"],
        order_by="posting_date asc, creation asc",
        limit_page_length=50,
    )


def run_under_receipt() -> dict[str, object]:
    suffix = unique_suffix("under")
    po = create_purchase_order(PO_QTY, suffix)
    batch_no = ensure_batch(f"RM-under-receipt-{suffix}", ITEM_CODE)
    receipt = attempt_purchase_receipt(po, UNDER_RECEIPT_QTY, batch_no)
    po_status = get_po_status(po)
    return {
        "purchase_order": po,
        "purchase_receipt": receipt["purchase_receipt"],
        "quality_inspection": receipt["quality_inspection"],
        "batch_no": batch_no,
        "allowed": receipt["submitted"],
        "blocked_message": receipt["blocked_message"],
        "po_status": po_status,
        "stock_ledger": get_stock_ledger_entries(receipt["purchase_receipt"]) if receipt["purchase_receipt"] else [],
        "gl_entries": get_gl_entries(receipt["purchase_receipt"]) if receipt["purchase_receipt"] else [],
    }


def run_over_receipt() -> dict[str, object]:
    suffix = unique_suffix("over")
    po = create_purchase_order(PO_QTY, suffix)
    batch_no = ensure_batch(f"RM-over-receipt-{suffix}", ITEM_CODE)
    receipt = attempt_purchase_receipt(po, OVER_RECEIPT_QTY, batch_no)
    po_status = get_po_status(po)
    return {
        "purchase_order": po,
        "purchase_receipt": receipt["purchase_receipt"],
        "quality_inspection": receipt["quality_inspection"],
        "batch_no": batch_no,
        "allowed": receipt["submitted"],
        "blocked_message": receipt["blocked_message"],
        "po_status": po_status,
        "stock_ledger": get_stock_ledger_entries(receipt["purchase_receipt"]) if receipt["purchase_receipt"] else [],
        "gl_entries": get_gl_entries(receipt["purchase_receipt"]) if receipt["purchase_receipt"] else [],
    }


def build_report() -> dict[str, object]:
    ensure_supplier()
    ensure_item_ready_for_qc()
    config = get_receipt_allowance_config()
    under = run_under_receipt()
    over = run_over_receipt()

    report = {
        "config": config,
        "under_receipt": {
            **under,
            "result": "PASS"
            if under["allowed"]
            and flt(under["po_status"]["pending_qty"]) == (PO_QTY - UNDER_RECEIPT_QTY)
            else "FAIL",
        },
        "over_receipt": {
            **over,
            "result": "PASS"
            if (
                (over["allowed"] and flt(over["po_status"]["received_qty"]) == OVER_RECEIPT_QTY)
                or (not over["allowed"] and bool(over["blocked_message"]))
            )
            else "FAIL",
        },
        "summary": {
            "under_receipt": "PASS"
            if under["allowed"]
            and flt(under["po_status"]["pending_qty"]) == (PO_QTY - UNDER_RECEIPT_QTY)
            else "FAIL",
            "over_receipt": "PASS"
            if (
                (over["allowed"] and flt(over["po_status"]["received_qty"]) == OVER_RECEIPT_QTY)
                or (not over["allowed"] and bool(over["blocked_message"]))
            )
            else "FAIL",
        },
    }

    output_path = verification_dir() / "receipt_variance_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
