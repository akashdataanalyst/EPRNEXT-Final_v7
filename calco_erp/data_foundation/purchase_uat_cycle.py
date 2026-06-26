from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, nowtime, today
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.party import get_party_account
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    RM_WAREHOUSE,
    STANDARD_BUYING,
    SUPPLIER,
    ensure_batch,
    ensure_supplier,
)


ITEM_CODE = "JE25 OG"
QTY = 1000.0
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


def ensure_item_ready_for_incoming_qc(item_code: str) -> None:
    if meta_has_field("Item", "inspection_required_before_purchase"):
        frappe.db.set_value(
            "Item",
            item_code,
            "inspection_required_before_purchase",
            0,
            update_modified=False,
        )
    if meta_has_field("Item", "custom_enable_rm_qc"):
        frappe.db.set_value(
            "Item",
            item_code,
            "custom_enable_rm_qc",
            1,
            update_modified=False,
        )
    if meta_has_field("Item", "quality_inspection_template"):
        frappe.db.set_value(
            "Item",
            item_code,
            "quality_inspection_template",
            QC_TEMPLATE,
            update_modified=False,
        )


def create_purchase_order(item_code: str, qty: float, suffix: str) -> str:
    supplier = ensure_supplier()
    item_row = {
        "item_code": item_code,
        "item_name": frappe.db.get_value("Item", item_code, "item_name"),
        "qty": qty,
        "uom": "Kg",
        "stock_uom": "Kg",
        "conversion_factor": 1,
        "rate": 1,
        "warehouse": RM_WAREHOUSE,
        "schedule_date": today(),
    }

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
            "supplier_quotation": f"CALCO-PO-{suffix}",
            "items": [item_row],
        }
    )
    po.insert(ignore_permissions=True)
    po.submit()
    return po.name


def create_purchase_receipt_from_po(purchase_order: str, batch_no: str) -> tuple[str, str]:
    pr = make_purchase_receipt(purchase_order)
    pr.posting_date = today()
    pr.posting_time = nowtime()
    pr.company = COMPANY

    for row in pr.items:
        row.warehouse = RM_WAREHOUSE
        row.batch_no = batch_no
        row.qty = QTY
        row.received_qty = QTY
        row.stock_qty = QTY
        row.rejected_qty = 0
        row.uom = "Kg"
        row.stock_uom = "Kg"
        row.conversion_factor = 1
        row.rate = row.rate or 1
        row.base_rate = row.base_rate or 1

    pr.insert(ignore_permissions=True)

    qi_name = create_rm_quality_inspection(pr.name, batch_no, QTY)

    pr.reload()
    for row in pr.items:
        row.quality_inspection = qi_name
    pr.save(ignore_permissions=True)
    pr.submit()
    return pr.name, qi_name


def create_rm_quality_inspection(purchase_receipt: str, batch_no: str, qty: float) -> str:
    qi = frappe.get_doc(
        {
            "doctype": "Quality Inspection",
            "report_date": today(),
            "inspection_type": "Incoming",
            "reference_type": "Purchase Receipt",
            "reference_name": purchase_receipt,
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


def create_rm_qc_and_release(purchase_receipt: str) -> tuple[list[str], list[str], list[str]]:
    inward_docs = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty"],
        limit_page_length=100,
    )

    qc_docs: list[str] = []
    release_docs: list[str] = []

    for inward in inward_docs:
        qi_name = frappe.db.get_value(
            "Quality Inspection",
            {
                "reference_type": "Purchase Receipt",
                "reference_name": purchase_receipt,
                "item_code": inward["item_code"],
                "batch_no": inward["batch_no"],
            },
            "name",
        )
        decision = frappe.get_doc(
            {
                "doctype": "RM QC Decision",
                "inward_validation": inward["name"],
                "decision": "Accepted",
                "quality_inspection": qi_name,
                "sample_qty": inward["received_qty"],
            }
        )
        decision.insert(ignore_permissions=True)
        decision.submit()
        qc_docs.append(decision.name)

        release_doc = frappe.get_doc(
            {
                "doctype": "RM Release Note",
                "rm_qc_decision": decision.name,
                "release_qty": inward["received_qty"],
                "status": "Released",
            }
        )
        release_doc.insert(ignore_permissions=True)
        release_doc.submit()
        release_docs.append(release_doc.name)

    return [row["name"] for row in inward_docs], qc_docs, release_docs


def validate_rm_release_gate(batch_no: str) -> dict[str, object]:
    blocked = False
    message = ""
    savepoint = "purchase_uat_rm_gate"
    frappe.db.sql(f"SAVEPOINT {savepoint}")
    purpose = "Material Consumption for Manufacture"
    try:
        payload = {
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
        se = frappe.get_doc(payload)
        se.insert(ignore_permissions=True)
        se.submit()
    except Exception:
        blocked = True
        message = frappe.get_traceback()
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    return {"blocked": blocked, "message": message}


def create_purchase_invoice(purchase_receipt: str) -> str:
    invoice = make_purchase_invoice(purchase_receipt)
    invoice.bill_no = f"CALCO-PI-{unique_suffix(ITEM_CODE)}"
    invoice.bill_date = today()
    invoice.posting_date = today()
    invoice.due_date = today()
    invoice.insert(ignore_permissions=True)
    invoice.submit()
    return invoice.name


def get_payment_account() -> str:
    company_defaults = frappe.db.get_value(
        "Company",
        COMPANY,
        ["default_cash_account", "default_bank_account"],
        as_dict=True,
    )
    if company_defaults:
        if company_defaults.default_cash_account:
            return company_defaults.default_cash_account
        if company_defaults.default_bank_account:
            return company_defaults.default_bank_account

    rows = frappe.db.sql(
        """
        select name
        from `tabAccount`
        where company = %s
          and is_group = 0
          and account_type in ('Cash', 'Bank')
        order by
          case when account_type = 'Cash' then 0 else 1 end,
          name asc
        limit 1
        """,
        (COMPANY,),
        as_dict=True,
    )
    if not rows:
        frappe.throw(f"No cash or bank account found for {COMPANY}.")
    return rows[0]["name"]


def create_payment_entry_for_invoice(purchase_invoice: str) -> str:
    payment_entry = get_payment_entry("Purchase Invoice", purchase_invoice)
    payment_entry.posting_date = today()
    if meta_has_field("Payment Entry", "mode_of_payment"):
        mode = frappe.db.get_value("Mode of Payment", {"enabled": 1}, "name")
        if mode:
            payment_entry.mode_of_payment = mode
    if not payment_entry.paid_from:
        payment_entry.paid_from = get_payment_account()
    if not payment_entry.paid_to:
        payment_entry.paid_to = get_party_account("Supplier", SUPPLIER, COMPANY)
    if not flt(payment_entry.paid_amount):
        payment_entry.paid_amount = flt(payment_entry.received_amount) or flt(
            frappe.db.get_value("Purchase Invoice", purchase_invoice, "outstanding_amount")
        )
    if not flt(payment_entry.received_amount):
        payment_entry.received_amount = flt(payment_entry.paid_amount)
    if meta_has_field("Payment Entry", "reference_no") and not payment_entry.reference_no:
        payment_entry.reference_no = f"CALCO-PAY-{unique_suffix(ITEM_CODE)}"
    if meta_has_field("Payment Entry", "reference_date") and not payment_entry.reference_date:
        payment_entry.reference_date = today()
    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()
    return payment_entry.name


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
    ensure_item_ready_for_incoming_qc(ITEM_CODE)

    suffix = unique_suffix(ITEM_CODE)
    batch_no = ensure_batch(f"RM-purchase-uat-{suffix}", ITEM_CODE)

    purchase_order = create_purchase_order(ITEM_CODE, QTY, suffix)
    purchase_receipt, quality_inspection = create_purchase_receipt_from_po(purchase_order, batch_no)
    negative_rm_gate = validate_rm_release_gate(batch_no)
    rm_inward_docs, rm_qc_docs, rm_release_docs = create_rm_qc_and_release(purchase_receipt)
    purchase_invoice = create_purchase_invoice(purchase_receipt)
    payment_entry = create_payment_entry_for_invoice(purchase_invoice)

    pi_item_link = frappe.db.get_value("Purchase Invoice Item", {"parent": purchase_invoice}, "purchase_receipt")
    invoice_status = frappe.db.get_value(
        "Purchase Invoice",
        purchase_invoice,
        ["status", "outstanding_amount", "grand_total"],
        as_dict=True,
    )
    batch_exists = bool(frappe.db.exists("Batch", batch_no))
    qi_doc = frappe.db.get_value(
        "Quality Inspection",
        quality_inspection,
        ["reference_type", "reference_name", "status"],
        as_dict=True,
    )

    report = {
        "summary": {
            "purchase_order": "PASS",
            "purchase_receipt": "PASS",
            "batch_creation": "PASS" if batch_exists else "FAIL",
            "rm_quality_inspection": "PASS" if qi_doc and qi_doc.status == "Accepted" else "FAIL",
            "rm_release": "PASS" if rm_release_docs else "FAIL",
            "rm_release_gate_before_production_use": "PASS" if negative_rm_gate["blocked"] else "FAIL",
            "purchase_invoice": "PASS" if pi_item_link == purchase_receipt else "FAIL",
            "payment_entry": "PASS"
            if invoice_status and flt(invoice_status.outstanding_amount) == 0
            else "FAIL",
        },
        "item_code": ITEM_CODE,
        "qty": QTY,
        "supplier": SUPPLIER,
        "purchase_order": purchase_order,
        "purchase_receipt": purchase_receipt,
        "batch_no": batch_no,
        "quality_inspection": quality_inspection,
        "rm_inward_validations": rm_inward_docs,
        "rm_qc_decisions": rm_qc_docs,
        "rm_release_notes": rm_release_docs,
        "purchase_invoice": purchase_invoice,
        "payment_entry": payment_entry,
        "validations": {
            "stock_ledger_purchase_receipt": get_stock_ledger_entries("Purchase Receipt", purchase_receipt),
            "batch_exists": batch_exists,
            "quality_inspection_link": qi_doc,
            "rm_release_gate_before_production_use": negative_rm_gate,
            "purchase_invoice_link_to_receipt": pi_item_link,
            "purchase_invoice_status": invoice_status,
        },
    }

    output_path = verification_dir() / "purchase_uat_cycle_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
