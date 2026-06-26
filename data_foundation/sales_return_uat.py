from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import flt, nowtime, today
from erpnext.accounts.party import get_party_account
from erpnext.controllers.sales_and_purchase_return import make_return_doc

from calco_erp.calco_complaint_capa.doctype.technical_assistance_ticket.technical_assistance_ticket import (
    build_traceability_data,
)
from calco_erp.data_foundation.phase2_uat_validation import get_sales_invoice_delivery_context
from calco_erp.data_foundation.sales_order_cycle_711c3002 import submit_dispatch_clearance
from calco_erp.data_foundation.manufacturing_test_cycle import COMPANY, FG_WAREHOUSE


SOURCE_SALES_INVOICE = "ACC-SINV-2026-00004"


def verification_dir() -> Path:
    path = Path(__file__).resolve().parent / "generated" / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_delivery_note_return(
    delivery_note: str,
    item_code: str,
    batch_no: str,
    final_qc_release: str,
) -> tuple[str, str]:
    doc = make_return_doc("Delivery Note", delivery_note)
    doc.posting_date = today()
    doc.posting_time = nowtime()

    for row in doc.items:
        if row.item_code == item_code:
            row.warehouse = FG_WAREHOUSE
            if hasattr(row, "batch_no"):
                row.batch_no = batch_no

    doc.insert(ignore_permissions=True)
    dispatch_clearance = submit_dispatch_clearance(doc.name, item_code, batch_no, final_qc_release)
    doc.submit()
    return doc.name, dispatch_clearance


def create_credit_note(sales_invoice: str) -> str:
    doc = make_return_doc("Sales Invoice", sales_invoice)
    doc.posting_date = today()
    doc.posting_time = nowtime()
    if hasattr(doc, "update_stock"):
        doc.update_stock = 0
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def get_stock_ledger_entries(voucher_no: str, item_code: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Delivery Note", "voucher_no": voucher_no, "item_code": item_code},
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
        filters={"voucher_type": "Sales Invoice", "voucher_no": voucher_no},
        fields=["account", "debit", "credit", "party_type", "party", "against", "remarks"],
        order_by="posting_date asc, creation asc",
        limit_page_length=50,
    )


def summarize_customer_balance(customer: str, credit_note: str) -> dict[str, object]:
    receivable_account = get_party_account("Customer", customer, COMPANY)
    entries = [row for row in get_gl_entries(credit_note) if row["account"] == receivable_account]
    return {
        "receivable_account": receivable_account,
        "rows": entries,
        "credit_total": flt(sum(flt(row["credit"]) for row in entries)),
        "debit_total": flt(sum(flt(row["debit"]) for row in entries)),
    }


def build_report() -> dict[str, object]:
    context = get_sales_invoice_delivery_context(SOURCE_SALES_INVOICE)
    source_invoice = frappe.get_doc("Sales Invoice", SOURCE_SALES_INVOICE)
    trace = build_traceability_data(context["item_code"], context["fg_batch_no"], context["delivery_note"])

    delivery_note_return, dispatch_clearance = create_delivery_note_return(
        context["delivery_note"],
        context["item_code"],
        context["fg_batch_no"],
        trace["final_qc_release"],
    )
    credit_note = create_credit_note(SOURCE_SALES_INVOICE)

    dn_return_doc = frappe.get_doc("Delivery Note", delivery_note_return)
    credit_note_doc = frappe.get_doc("Sales Invoice", credit_note)
    stock_ledger = get_stock_ledger_entries(delivery_note_return, context["item_code"])
    customer_balance = summarize_customer_balance(source_invoice.customer, credit_note)

    positive_return_qty = flt(sum(max(flt(row["actual_qty"]), 0) for row in stock_ledger))
    expected_return_qty = flt(abs(dn_return_doc.items[0].qty)) if dn_return_doc.items else 0

    report = {
        "summary": {
            "sales_return_document": "PASS" if dn_return_doc.docstatus == 1 and dn_return_doc.is_return else "FAIL",
            "fg_batch_returned_to_fg_warehouse": "PASS"
            if any(
                row["warehouse"] == FG_WAREHOUSE
                and row.get("batch_no") == context["fg_batch_no"]
                and flt(row["actual_qty"]) > 0
                for row in stock_ledger
            )
            else "FAIL",
            "credit_note": "PASS" if credit_note_doc.docstatus == 1 and credit_note_doc.is_return else "FAIL",
            "stock_ledger_adjustment": "PASS"
            if positive_return_qty == expected_return_qty and positive_return_qty > 0
            else "FAIL",
            "customer_balance_impact": "PASS"
            if flt(customer_balance["credit_total"]) == abs(flt(credit_note_doc.grand_total))
            else "FAIL",
        },
        "source_sales_invoice": SOURCE_SALES_INVOICE,
        "customer": source_invoice.customer,
        "item_code": context["item_code"],
        "fg_batch_no": context["fg_batch_no"],
        "source_delivery_note": context["delivery_note"],
        "return_document": delivery_note_return,
        "credit_note": credit_note,
        "dispatch_clearance": dispatch_clearance,
        "validations": {
            "delivery_note_return_qty": expected_return_qty,
            "stock_ledger_return_qty": positive_return_qty,
            "stock_ledger": stock_ledger,
            "credit_note_grand_total": flt(credit_note_doc.grand_total),
            "credit_note_outstanding_amount": flt(credit_note_doc.outstanding_amount),
            "customer_balance": customer_balance,
            "final_qc_release_reused": trace["final_qc_release"],
        },
    }

    output_path = verification_dir() / "sales_return_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


def inspect_return_document(name: str) -> dict[str, object]:
    doc = frappe.get_doc("Delivery Note", name)
    items = []
    for row in doc.items:
        bundle_entries = []
        bundle_name = getattr(row, "serial_and_batch_bundle", "")
        if bundle_name:
            bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
            bundle_entries = [
                {
                    "batch_no": getattr(entry, "batch_no", ""),
                    "qty": flt(getattr(entry, "qty", 0)),
                    "warehouse": getattr(entry, "warehouse", ""),
                }
                for entry in bundle.get("entries", [])
            ]
        items.append(
            {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "warehouse": row.warehouse,
                "batch_no": getattr(row, "batch_no", ""),
                "serial_and_batch_bundle": bundle_name,
                "bundle_entries": bundle_entries,
            }
        )
    return {
        "name": doc.name,
        "is_return": doc.is_return,
        "return_against": doc.return_against,
        "items": items,
    }


def inspect_sales_return_uat() -> dict[str, object]:
    name = frappe.db.get_value(
        "Delivery Note",
        {"is_return": 1, "return_against": "MAT-DN-2026-00008", "docstatus": 1},
        "name",
        order_by="creation desc",
    )
    if not name:
        return {}
    return inspect_return_document(name)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
