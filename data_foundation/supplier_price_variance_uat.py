from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import cint, flt, now_datetime, nowtime, today
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
PO_RATE = 1.0
INVOICE_RATE = 1.25
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


def create_purchase_order(qty: float, rate: float, suffix: str) -> str:
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
            "supplier_quotation": f"CALCO-PRICE-VAR-{suffix}",
            "items": [
                {
                    "item_code": ITEM_CODE,
                    "item_name": frappe.db.get_value("Item", ITEM_CODE, "item_name"),
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "rate": rate,
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
        row.rate = PO_RATE
        row.base_rate = PO_RATE

    pr.insert(ignore_permissions=True)
    qi_name = create_manual_qi(pr.name, batch_no, QTY)

    pr.reload()
    for row in pr.items:
        row.quality_inspection = qi_name
    pr.save(ignore_permissions=True)
    pr.submit()
    return pr.name, qi_name


def create_purchase_invoice(purchase_receipt: str, invoice_rate: float, suffix: str) -> str:
    invoice = make_purchase_invoice(purchase_receipt)
    invoice.bill_no = f"CALCO-PRICE-VAR-PI-{suffix}"
    invoice.bill_date = today()
    invoice.posting_date = today()
    invoice.due_date = today()
    for row in invoice.items:
        row.rate = invoice_rate
        row.price_list_rate = invoice_rate
        row.base_rate = invoice_rate
        row.qty = QTY
        row.stock_qty = QTY
        row.amount = flt(invoice_rate) * flt(QTY)
        row.base_amount = row.amount
    invoice.set_missing_values()
    invoice.calculate_taxes_and_totals()
    invoice.insert(ignore_permissions=True)
    invoice.submit()
    return invoice.name


def attempt_purchase_invoice(purchase_receipt: str, invoice_rate: float, suffix: str) -> dict[str, object]:
    invoice_name = ""
    blocked_message = ""
    submitted = False
    try:
        invoice_name = create_purchase_invoice(purchase_receipt, invoice_rate, suffix)
        submitted = True
    except Exception:
        blocked_message = frappe.get_traceback()
    return {
        "purchase_invoice": invoice_name,
        "submitted": submitted,
        "blocked_message": blocked_message,
    }


def get_gl_entries(voucher_type: str, voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "GL Entry",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no},
        fields=[
            "account",
            "debit",
            "credit",
            "against",
            "party_type",
            "party",
            "remarks",
        ],
        order_by="posting_date asc, creation asc",
        limit_page_length=100,
    )


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


def get_bin_snapshot(item_code: str, warehouse: str) -> dict[str, float]:
    row = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "valuation_rate", "stock_value"],
        as_dict=True,
    )
    if not row:
        return {"actual_qty": 0.0, "valuation_rate": 0.0, "stock_value": 0.0}
    return {
        "actual_qty": flt(row.actual_qty),
        "valuation_rate": flt(row.valuation_rate),
        "stock_value": flt(row.stock_value),
    }


def get_maintain_same_rate() -> int:
    return cint(frappe.db.get_single_value("Buying Settings", "maintain_same_rate") or 0)


def set_maintain_same_rate(value: int) -> None:
    frappe.db.set_single_value("Buying Settings", "maintain_same_rate", cint(value))
    frappe.clear_cache()


def get_over_billing_allowance() -> float:
    return flt(frappe.db.get_single_value("Accounts Settings", "over_billing_allowance") or 0)


def set_over_billing_allowance(value: float) -> None:
    frappe.db.set_single_value("Accounts Settings", "over_billing_allowance", flt(value))
    frappe.clear_cache()


def get_item_over_billing_allowance() -> float:
    if not meta_has_field("Item", "over_billing_allowance"):
        return 0.0
    return flt(frappe.db.get_value("Item", ITEM_CODE, "over_billing_allowance") or 0)


def set_item_over_billing_allowance(value: float) -> None:
    if meta_has_field("Item", "over_billing_allowance"):
        frappe.db.set_value(
            "Item",
            ITEM_CODE,
            "over_billing_allowance",
            flt(value),
            update_modified=False,
        )


def summarize_payable(gl_entries: list[dict[str, object]]) -> dict[str, object]:
    supplier_account = get_party_account("Supplier", SUPPLIER, COMPANY)
    payable_rows = [row for row in gl_entries if row["account"] == supplier_account]
    return {
        "supplier_account": supplier_account,
        "rows": payable_rows,
        "credit_total": flt(sum(flt(row["credit"]) for row in payable_rows)),
        "debit_total": flt(sum(flt(row["debit"]) for row in payable_rows)),
    }


def summarize_stock_related_entries(gl_entries: list[dict[str, object]]) -> dict[str, object]:
    relevant = [
        row
        for row in gl_entries
        if any(
            token in (row["account"] or "")
            for token in ("Stock In Hand", "Stock Received But Not Billed", "Expenses Included")
        )
    ]
    return {
        "rows": relevant,
        "debit_total": flt(sum(flt(row["debit"]) for row in relevant)),
        "credit_total": flt(sum(flt(row["credit"]) for row in relevant)),
    }


def summarize_price_variance(
    purchase_receipt_gl_entries: list[dict[str, object]],
    purchase_invoice_gl_entries: list[dict[str, object]],
    expected_variance: float,
) -> dict[str, object]:
    relevant = [
        row
        for row in purchase_receipt_gl_entries + purchase_invoice_gl_entries
        if any(
            token in (row["account"] or "")
            for token in ("Stock Received But Not Billed", "Stock In Hand", "Expenses Included")
        )
    ]
    net_by_account: dict[str, float] = {}
    for row in relevant:
        account = row["account"]
        net_by_account.setdefault(account, 0.0)
        net_by_account[account] += flt(row["debit"]) - flt(row["credit"])

    matched_accounts = [
        account for account, value in net_by_account.items() if abs(flt(value) - flt(expected_variance)) < 0.0001
    ]
    return {
        "expected_variance": expected_variance,
        "rows": relevant,
        "net_by_account": net_by_account,
        "observed_accounts": sorted(matched_accounts),
        "matched": bool(matched_accounts),
    }


def create_receipt_flow(suffix: str) -> dict[str, str]:
    batch_no = ensure_batch(f"RM-price-variance-{suffix}", ITEM_CODE)
    purchase_order = create_purchase_order(QTY, PO_RATE, suffix)
    purchase_receipt, quality_inspection = create_purchase_receipt_from_po(purchase_order, batch_no)
    return {
        "purchase_order": purchase_order,
        "purchase_receipt": purchase_receipt,
        "batch_no": batch_no,
        "quality_inspection": quality_inspection,
    }


def build_report() -> dict[str, object]:
    ensure_supplier()
    ensure_item_ready_for_qc()
    original_rate_lock = get_maintain_same_rate()
    original_over_billing_allowance = get_over_billing_allowance()
    original_item_over_billing_allowance = get_item_over_billing_allowance()
    blocked_scenario_suffix = unique_suffix(f"{ITEM_CODE}-blocked")
    blocked_flow = create_receipt_flow(blocked_scenario_suffix)
    blocked_attempt = attempt_purchase_invoice(
        blocked_flow["purchase_receipt"], INVOICE_RATE, blocked_scenario_suffix
    )

    allowed_scenario_suffix = unique_suffix(f"{ITEM_CODE}-allowed")
    allowed_flow: dict[str, object] = {}
    try:
        if original_rate_lock:
            set_maintain_same_rate(0)
        if original_over_billing_allowance < 100:
            set_over_billing_allowance(100)
        if original_item_over_billing_allowance < 100:
            set_item_over_billing_allowance(100)

        before_snapshot = get_bin_snapshot(ITEM_CODE, RM_WAREHOUSE)
        allowed_flow = create_receipt_flow(allowed_scenario_suffix)
        after_receipt_snapshot = get_bin_snapshot(ITEM_CODE, RM_WAREHOUSE)
        allowed_invoice = create_purchase_invoice(
            allowed_flow["purchase_receipt"], INVOICE_RATE, allowed_scenario_suffix
        )
        after_invoice_snapshot = get_bin_snapshot(ITEM_CODE, RM_WAREHOUSE)

        expected_variance = flt((INVOICE_RATE - PO_RATE) * QTY)
        po_doc = frappe.get_doc("Purchase Order", allowed_flow["purchase_order"])
        pr_doc = frappe.get_doc("Purchase Receipt", allowed_flow["purchase_receipt"])
        pi_doc = frappe.get_doc("Purchase Invoice", allowed_invoice)

        pr_gl = get_gl_entries("Purchase Receipt", allowed_flow["purchase_receipt"])
        pi_gl = get_gl_entries("Purchase Invoice", allowed_invoice)
        pr_sle = get_stock_ledger_entries("Purchase Receipt", allowed_flow["purchase_receipt"])

        payable_summary = summarize_payable(pi_gl)
        stock_entry_summary = summarize_stock_related_entries(pi_gl)
        price_variance_summary = summarize_price_variance(pr_gl, pi_gl, expected_variance)

        allowed_flow.update(
            {
                "purchase_invoice": allowed_invoice,
                "snapshots": {
                    "before_receipt": before_snapshot,
                    "after_receipt": after_receipt_snapshot,
                    "after_invoice": after_invoice_snapshot,
                },
                "purchase_order_grand_total": flt(po_doc.grand_total),
                "purchase_receipt_grand_total": flt(pr_doc.grand_total),
                "purchase_invoice_grand_total": flt(pi_doc.grand_total),
                "purchase_receipt_stock_ledger": pr_sle,
                "purchase_receipt_gl_entries": pr_gl,
                "purchase_invoice_gl_entries": pi_gl,
                "supplier_payable": payable_summary,
                "stock_related_posting": stock_entry_summary,
                "price_variance_posting": price_variance_summary,
                "summary": {
                    "purchase_order": "PASS" if po_doc.docstatus == 1 else "FAIL",
                    "purchase_receipt": "PASS" if pr_doc.docstatus == 1 else "FAIL",
                    "purchase_invoice_with_variance": "PASS"
                    if pi_doc.docstatus == 1 and flt(pi_doc.grand_total) == flt(INVOICE_RATE * QTY)
                    else "FAIL",
                    "supplier_payable": "PASS"
                    if flt(payable_summary["credit_total"]) == flt(pi_doc.grand_total)
                    else "FAIL",
                    "stock_valuation": "PASS"
                    if after_receipt_snapshot["stock_value"] > before_snapshot["stock_value"]
                    and after_invoice_snapshot["stock_value"] >= after_receipt_snapshot["stock_value"]
                    else "FAIL",
                    "price_variance_posting": "PASS" if price_variance_summary["matched"] else "FAIL",
                },
            }
        )
    finally:
        if get_maintain_same_rate() != original_rate_lock:
            set_maintain_same_rate(original_rate_lock)
        if get_over_billing_allowance() != original_over_billing_allowance:
            set_over_billing_allowance(original_over_billing_allowance)
        if get_item_over_billing_allowance() != original_item_over_billing_allowance:
            set_item_over_billing_allowance(original_item_over_billing_allowance)

    report = {
        "summary": {
            "blocked_by_current_configuration": "PASS"
            if original_rate_lock and not blocked_attempt["submitted"] and blocked_attempt["blocked_message"]
            else "FAIL",
            "controlled_variance_execution": "PASS"
            if allowed_flow.get("summary", {}).get("purchase_invoice_with_variance") == "PASS"
            else "FAIL",
            "supplier_payable": allowed_flow.get("summary", {}).get("supplier_payable", "FAIL"),
            "stock_valuation": allowed_flow.get("summary", {}).get("stock_valuation", "FAIL"),
            "price_variance_posting": allowed_flow.get("summary", {}).get("price_variance_posting", "FAIL"),
            "config_restored": "PASS"
            if get_maintain_same_rate() == original_rate_lock
            and get_over_billing_allowance() == original_over_billing_allowance
            and get_item_over_billing_allowance() == original_item_over_billing_allowance
            else "FAIL",
        },
        "item_code": ITEM_CODE,
        "qty": QTY,
        "supplier": SUPPLIER,
        "rates": {
            "purchase_order_rate": PO_RATE,
            "purchase_receipt_rate": PO_RATE,
            "purchase_invoice_rate": INVOICE_RATE,
            "variance_per_kg": flt(INVOICE_RATE - PO_RATE),
            "expected_total_variance": flt((INVOICE_RATE - PO_RATE) * QTY),
        },
        "configuration": {
            "maintain_same_rate_before_test": original_rate_lock,
            "maintain_same_rate_after_test": get_maintain_same_rate(),
            "over_billing_allowance_before_test": original_over_billing_allowance,
            "over_billing_allowance_after_test": get_over_billing_allowance(),
            "item_over_billing_allowance_before_test": original_item_over_billing_allowance,
            "item_over_billing_allowance_after_test": get_item_over_billing_allowance(),
        },
        "blocked_attempt": {
            **blocked_flow,
            **blocked_attempt,
        },
        "allowed_scenario": allowed_flow,
    }

    output_path = verification_dir() / "supplier_price_variance_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
