from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, today
from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

from calco_erp.calco_purchase.commercial_approval import (
    COMMERCIAL_APPROVAL_DOCTYPE,
    get_benchmark_rate,
)
from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    RM_WAREHOUSE,
    STANDARD_BUYING,
    ensure_supplier,
)


def verification_dir() -> Path:
    path = Path(__file__).resolve().parent / "generated" / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def unique_suffix(label: str) -> str:
    return now_datetime().strftime("%Y%m%d%H%M%S") + "-" + slug(label)


def ensure_item(item_code: str, item_name: str, *, standard_rate: float | None = None, last_purchase_rate: float | None = None) -> str:
    if not frappe.db.exists("Item", item_code):
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_name,
                "item_group": "Raw Material",
                "stock_uom": "Kg",
                "is_stock_item": 1,
                "include_item_in_manufacturing": 1,
                "valuation_method": "FIFO",
                "standard_rate": flt(standard_rate or 0),
                "last_purchase_rate": flt(last_purchase_rate or 0),
            }
        ).insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Item", item_code, "item_name", item_name, update_modified=False)

    frappe.db.set_value("Item", item_code, "standard_rate", flt(standard_rate or 0), update_modified=False)
    frappe.db.set_value("Item", item_code, "last_purchase_rate", flt(last_purchase_rate or 0), update_modified=False)
    return item_code


def ensure_supplier_matrix(item_code: str, supplier: str):
    existing = frappe.db.get_value(
        "Supplier Approval Matrix",
        {"item_code": item_code, "supplier": supplier},
        "name",
    )
    payload = {
        "item_code": item_code,
        "supplier": supplier,
        "supplier_type": "Local",
        "approval_status": "Approved",
        "effective_date": today(),
    }
    if existing:
        frappe.db.set_value("Supplier Approval Matrix", existing, payload, update_modified=False)
        return existing

    doc = frappe.get_doc({"doctype": "Supplier Approval Matrix", **payload})
    doc.insert(ignore_permissions=True)
    return doc.name


def create_supplier_quotation(item_code: str, supplier: str, rate: float, suffix: str, qty: float = 100.0) -> str:
    item_name = frappe.db.get_value("Item", item_code, "item_name")
    doc = frappe.get_doc(
        {
            "doctype": "Supplier Quotation",
            "supplier": supplier,
            "company": COMPANY,
            "transaction_date": today(),
            "currency": "INR",
            "conversion_rate": 1,
            "buying_price_list": STANDARD_BUYING,
            "price_list_currency": "INR",
            "items": [
                {
                    "item_code": item_code,
                    "item_name": item_name,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "rate": rate,
                    "base_rate": rate,
                    "amount": flt(rate) * flt(qty),
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def try_purchase_order_from_supplier_quotation(supplier_quotation: str) -> dict[str, object]:
    try:
        po = make_purchase_order(supplier_quotation)
        po.company = COMPANY
        po.transaction_date = today()
        po.schedule_date = today()
        po.currency = "INR"
        po.buying_price_list = STANDARD_BUYING
        po.price_list_currency = "INR"
        for row in po.items:
            row.warehouse = RM_WAREHOUSE
            row.schedule_date = today()
        po.insert(ignore_permissions=True)
        po.submit()
        return {"allowed": True, "purchase_order": po.name, "error": ""}
    except Exception as exc:
        return {"allowed": False, "purchase_order": "", "error": str(exc)}


def get_approval_for_supplier_quotation(supplier_quotation: str):
    rows = frappe.get_all(
        COMMERCIAL_APPROVAL_DOCTYPE,
        filters={"supplier_quotation": supplier_quotation},
        fields=["name", "approval_status", "decision", "benchmark_rate", "quoted_rate", "benchmark_source"],
        order_by="creation asc",
        limit_page_length=10,
    )
    return rows


def approve_commercial_approval(name: str, reason: str):
    doc = frappe.get_doc(COMMERCIAL_APPROVAL_DOCTYPE, name)
    doc.reason_for_higher_price = reason
    doc.decision = "Approved"
    doc.save(ignore_permissions=True)
    return doc.name


def reject_commercial_approval(name: str):
    doc = frappe.get_doc(COMMERCIAL_APPROVAL_DOCTYPE, name)
    doc.decision = "Rejected"
    doc.save(ignore_permissions=True)
    return doc.name


def create_reference_purchase_order(item_code: str, supplier: str, rate: float, suffix: str, qty: float = 10.0) -> str:
    item_name = frappe.db.get_value("Item", item_code, "item_name")
    po = frappe.get_doc(
        {
            "doctype": "Purchase Order",
            "supplier": supplier,
            "company": COMPANY,
            "transaction_date": today(),
            "schedule_date": today(),
            "currency": "INR",
            "conversion_rate": 1,
            "buying_price_list": STANDARD_BUYING,
            "price_list_currency": "INR",
            "supplier_name": supplier,
            "items": [
                {
                    "item_code": item_code,
                    "item_name": item_name,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "rate": rate,
                    "base_rate": rate,
                    "warehouse": RM_WAREHOUSE,
                    "schedule_date": today(),
                }
            ],
        }
    )
    po.insert(ignore_permissions=True)
    po.submit()
    return po.name


def write_report(report: dict[str, object], suffix: str) -> Path:
    path = verification_dir() / f"PURCHASE_COMMERCIAL_APPROVAL_UAT_{suffix}.md"
    lines = [
        "# Purchase Commercial Approval UAT",
        "",
        f"- Generated On: `{now_datetime()}`",
        "",
        "## Benchmark Proof",
        "",
    ]
    for row in report["benchmark_proof"]:
        lines.append(
            f"- `{row['item_code']}`: source `{row['source'] or 'Missing'}`, rate `{row['rate']}`, reference `{row['reference'] or '-'}`"
        )

    lines.extend(
        [
            "",
            "## Test Documents",
            "",
        ]
    )
    for row in report["documents"]:
        lines.append(
            f"- `{row['case']}`: Supplier Quotation `{row.get('supplier_quotation') or '-'}`, "
            f"Commercial Approval `{', '.join(row.get('commercial_approvals') or []) or '-'}`, "
            f"Purchase Order `{row.get('purchase_order') or '-'}`"
        )

    lines.extend(
        [
            "",
            "## PASS / FAIL",
            "",
            "| Test | Result | Notes |",
            "| --- | --- | --- |",
        ]
    )
    for row in report["results"]:
        lines.append(f"| {row['test']} | {row['result']} | {row['notes']} |")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@frappe.whitelist()
def run_purchase_commercial_approval_uat() -> dict[str, object]:
    suffix = unique_suffix("commercial-approval")
    supplier = ensure_supplier()

    item_below = ensure_item(f"CA-BELOW-{suffix}", "Commercial Approval Below", standard_rate=100)
    item_equal = ensure_item(f"CA-EQUAL-{suffix}", "Commercial Approval Equal", standard_rate=100)
    item_above_approve = ensure_item(f"CA-ABV-APP-{suffix}", "Commercial Approval Above Approve", standard_rate=100)
    item_above_reject = ensure_item(f"CA-ABV-REJ-{suffix}", "Commercial Approval Above Reject", standard_rate=100)
    item_missing = ensure_item(f"CA-MISS-{suffix}", "Commercial Approval Missing")
    item_last = ensure_item(f"CA-LAST-{suffix}", "Commercial Approval Last Purchase", standard_rate=100, last_purchase_rate=88)
    item_avg = ensure_item(f"CA-AVG-{suffix}", "Commercial Approval Average")

    for item_code in [item_below, item_equal, item_above_approve, item_above_reject, item_missing]:
        ensure_supplier_matrix(item_code, supplier)

    avg_po_numbers = [
        create_reference_purchase_order(item_avg, supplier, 70, suffix),
        create_reference_purchase_order(item_avg, supplier, 80, suffix),
        create_reference_purchase_order(item_avg, supplier, 90, suffix),
    ]
    frappe.db.set_value("Item", item_avg, "last_purchase_rate", 0, update_modified=False)

    benchmark_proof = []
    for item_code in [item_last, item_avg, item_below, item_missing]:
        benchmark = get_benchmark_rate(item_code)
        benchmark_proof.append(
            {
                "item_code": item_code,
                "source": benchmark.get("source"),
                "rate": benchmark.get("rate"),
                "reference": benchmark.get("reference"),
            }
        )

    documents = []
    results = []

    sq_below = create_supplier_quotation(item_below, supplier, 90, suffix)
    approvals_below = get_approval_for_supplier_quotation(sq_below)
    po_below = try_purchase_order_from_supplier_quotation(sq_below)
    documents.append(
        {
            "case": "Below Benchmark",
            "supplier_quotation": sq_below,
            "commercial_approvals": [row["name"] for row in approvals_below],
            "purchase_order": po_below["purchase_order"],
        }
    )
    results.append(
        {
            "test": "1. SQ rate below benchmark",
            "result": "PASS" if not approvals_below and po_below["allowed"] else "FAIL",
            "notes": f"Approval docs: {len(approvals_below)}; PO: {po_below['purchase_order'] or po_below['error']}",
        }
    )

    sq_equal = create_supplier_quotation(item_equal, supplier, 100, suffix)
    approvals_equal = get_approval_for_supplier_quotation(sq_equal)
    po_equal = try_purchase_order_from_supplier_quotation(sq_equal)
    documents.append(
        {
            "case": "Equal Benchmark",
            "supplier_quotation": sq_equal,
            "commercial_approvals": [row["name"] for row in approvals_equal],
            "purchase_order": po_equal["purchase_order"],
        }
    )
    results.append(
        {
            "test": "2. SQ rate equal benchmark",
            "result": "PASS" if not approvals_equal and po_equal["allowed"] else "FAIL",
            "notes": f"Approval docs: {len(approvals_equal)}; PO: {po_equal['purchase_order'] or po_equal['error']}",
        }
    )

    sq_above_approve = create_supplier_quotation(item_above_approve, supplier, 120, suffix)
    approvals_above_approve = get_approval_for_supplier_quotation(sq_above_approve)
    po_above_blocked = try_purchase_order_from_supplier_quotation(sq_above_approve)
    approval_to_approve = approvals_above_approve[0]["name"] if approvals_above_approve else ""
    if approval_to_approve:
        approve_commercial_approval(approval_to_approve, "Approved during automated UAT because market rate is temporarily elevated.")
    po_above_after_approval = try_purchase_order_from_supplier_quotation(sq_above_approve)
    documents.append(
        {
            "case": "Above Benchmark Approved",
            "supplier_quotation": sq_above_approve,
            "commercial_approvals": [row["name"] for row in approvals_above_approve],
            "purchase_order": po_above_after_approval["purchase_order"],
        }
    )
    results.append(
        {
            "test": "3. SQ rate above benchmark",
            "result": "PASS" if approvals_above_approve and not po_above_blocked["allowed"] else "FAIL",
            "notes": f"Approval: {approval_to_approve or '-'}; blocked message: {po_above_blocked['error'] or '-'}",
        }
    )
    results.append(
        {
            "test": "4. Approval approved",
            "result": "PASS" if po_above_after_approval["allowed"] else "FAIL",
            "notes": f"PO after approval: {po_above_after_approval['purchase_order'] or po_above_after_approval['error']}",
        }
    )

    sq_above_reject = create_supplier_quotation(item_above_reject, supplier, 125, suffix)
    approvals_above_reject = get_approval_for_supplier_quotation(sq_above_reject)
    approval_to_reject = approvals_above_reject[0]["name"] if approvals_above_reject else ""
    if approval_to_reject:
        reject_commercial_approval(approval_to_reject)
    po_after_reject = try_purchase_order_from_supplier_quotation(sq_above_reject)
    documents.append(
        {
            "case": "Above Benchmark Rejected",
            "supplier_quotation": sq_above_reject,
            "commercial_approvals": [row["name"] for row in approvals_above_reject],
            "purchase_order": po_after_reject["purchase_order"],
        }
    )
    results.append(
        {
            "test": "5. Approval rejected",
            "result": "PASS" if not po_after_reject["allowed"] else "FAIL",
            "notes": f"Approval: {approval_to_reject or '-'}; blocked message: {po_after_reject['error'] or '-'}",
        }
    )

    sq_missing = create_supplier_quotation(item_missing, supplier, 77, suffix)
    approvals_missing = get_approval_for_supplier_quotation(sq_missing)
    po_missing = try_purchase_order_from_supplier_quotation(sq_missing)
    documents.append(
        {
            "case": "Missing Benchmark",
            "supplier_quotation": sq_missing,
            "commercial_approvals": [row["name"] for row in approvals_missing],
            "purchase_order": po_missing["purchase_order"],
        }
    )
    results.append(
        {
            "test": "6. Benchmark missing",
            "result": "PASS" if approvals_missing and not po_missing["allowed"] else "FAIL",
            "notes": f"Approval: {', '.join(row['name'] for row in approvals_missing) or '-'}; blocked message: {po_missing['error'] or '-'}",
        }
    )

    report = {
        "supplier": supplier,
        "average_benchmark_purchase_orders": avg_po_numbers,
        "benchmark_proof": benchmark_proof,
        "documents": documents,
        "results": results,
    }
    report_path = write_report(report, suffix)
    report["report_path"] = str(report_path)
    return report
