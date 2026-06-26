from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, today


COMMERCIAL_APPROVAL_DOCTYPE = "Purchase Commercial Approval"
APPROVAL_PENDING_STATUS = "Draft"
APPROVAL_APPROVED_STATUS = "Approved"
APPROVAL_REJECTED_STATUS = "Rejected"


def ensure_supplier_quotation_commercial_approvals(doc, method=None):
    if not doc or doc.doctype != "Supplier Quotation" or int(doc.docstatus or 0) != 1:
        return []

    created = []
    for evaluation in evaluate_supplier_quotation(doc):
        if not evaluation["approval_required"]:
            continue
        if get_existing_commercial_approval(evaluation):
            continue
        approval = create_commercial_approval(evaluation)
        created.append(approval.name)
    return created


def validate_purchase_order_commercial_approval_gate(doc, method=None):
    if not doc or doc.doctype != "Purchase Order":
        return

    blocking_rows = []
    supplier_quotation_names = {row.get("supplier_quotation") for row in doc.get("items", []) if row.get("supplier_quotation")}
    if not supplier_quotation_names:
        return

    for supplier_quotation_name in supplier_quotation_names:
        if frappe.db.get_value("Supplier Quotation", supplier_quotation_name, "docstatus") != 1:
            continue

        supplier_quotation = frappe.get_doc("Supplier Quotation", supplier_quotation_name)
        ensure_supplier_quotation_commercial_approvals(supplier_quotation)

        evaluations = evaluate_supplier_quotation(supplier_quotation)
        evaluations_by_item = defaultdict(list)
        for evaluation in evaluations:
            evaluations_by_item[evaluation["item_code"]].append(evaluation)

        for row in doc.get("items", []):
            if row.get("supplier_quotation") != supplier_quotation_name:
                continue

            row_evaluations = evaluations_by_item.get(row.get("item_code")) or []
            for evaluation in row_evaluations:
                if not evaluation["approval_required"]:
                    continue

                approval_doc = evaluation.get("approval_doc")
                approval_status = normalize_approval_status(approval_doc.get("approval_status") if approval_doc else None)
                if approval_status != APPROVAL_APPROVED_STATUS.lower():
                    blocking_rows.append(
                        {
                            "supplier_quotation": supplier_quotation_name,
                            "item_code": evaluation.get("item_code"),
                            "item_name": evaluation.get("item_name"),
                            "quoted_rate": evaluation.get("quoted_rate"),
                            "benchmark_rate": evaluation.get("benchmark_rate"),
                            "benchmark_source": evaluation.get("benchmark_source"),
                            "approval": approval_doc.get("name") if approval_doc else None,
                            "approval_status": approval_doc.get("approval_status") if approval_doc else APPROVAL_PENDING_STATUS,
                            "benchmark_missing": evaluation.get("benchmark_missing"),
                        }
                    )

    if not blocking_rows:
        return

    row_lines = []
    has_missing_benchmark = any(row["benchmark_missing"] for row in blocking_rows)
    for row in blocking_rows:
        if row["benchmark_missing"]:
            detail = _(
                "{0} ({1}) in {2}: benchmark rate is missing; approval status {3}{4}"
            ).format(
                row["item_code"],
                row["item_name"] or "-",
                row["supplier_quotation"],
                row["approval_status"],
                f" [{row['approval']}]" if row["approval"] else "",
            )
        else:
            detail = _(
                "{0} ({1}) in {2}: quoted {3} vs benchmark {4} from {5}; approval status {6}{7}"
            ).format(
                row["item_code"],
                row["item_name"] or "-",
                row["supplier_quotation"],
                frappe.format_value(row["quoted_rate"], {"fieldtype": "Currency"}),
                frappe.format_value(row["benchmark_rate"], {"fieldtype": "Currency"}),
                row["benchmark_source"] or _("Unknown Source"),
                row["approval_status"],
                f" [{row['approval']}]" if row["approval"] else "",
            )
        row_lines.append(detail)

    if has_missing_benchmark:
        message = _("Commercial Approval is required because benchmark rate is missing.")
    else:
        message = _("Commercial Approval is required because quoted rate is higher than benchmark.")

    frappe.throw(message + "<br><br>" + "<br>".join(row_lines))


def evaluate_supplier_quotation(doc) -> list[dict]:
    evaluations = []
    for row in doc.get("items", []):
        item_code = row.get("item_code")
        if not item_code:
            continue

        benchmark = get_benchmark_rate(item_code)
        quoted_rate = get_supplier_quotation_item_rate(row)
        benchmark_rate = benchmark.get("rate")
        benchmark_missing = benchmark_rate is None
        approval_required = benchmark_missing or flt(quoted_rate) > flt(benchmark_rate or 0)
        approval_doc = get_existing_commercial_approval_for_row(doc.name, row.name)

        evaluations.append(
            {
                "supplier_quotation": doc.name,
                "supplier_quotation_item": row.name,
                "material_request": row.get("material_request"),
                "request_for_quotation": row.get("request_for_quotation"),
                "supplier": doc.get("supplier"),
                "item_code": item_code,
                "item_name": row.get("item_name"),
                "uom": row.get("uom") or row.get("stock_uom"),
                "qty": flt(row.get("qty") or 0),
                "quoted_rate": quoted_rate,
                "benchmark_rate": benchmark_rate,
                "benchmark_source": benchmark.get("source"),
                "benchmark_reference": benchmark.get("reference"),
                "benchmark_missing": benchmark_missing,
                "variance_amount": flt(quoted_rate) - flt(benchmark_rate or 0),
                "variance_percent": ((flt(quoted_rate) - flt(benchmark_rate)) / flt(benchmark_rate) * 100) if flt(benchmark_rate) else 0,
                "approval_required": approval_required,
                "approval_doc": approval_doc,
            }
        )
    return evaluations


def get_existing_commercial_approval(evaluation: dict) -> str | None:
    return frappe.db.get_value(
        COMMERCIAL_APPROVAL_DOCTYPE,
        {"supplier_quotation_item": evaluation["supplier_quotation_item"]},
        "name",
    )


def get_existing_commercial_approval_for_row(supplier_quotation: str, supplier_quotation_item: str):
    fields = [
        "name",
        "supplier_quotation",
        "supplier_quotation_item",
        "item_code",
        "approval_status",
        "decision",
        "benchmark_rate",
        "quoted_rate",
        "variance_amount",
        "variance_percent",
        "reason_for_higher_price",
        "approved_by",
        "approval_date",
    ]
    rows = frappe.get_all(
        COMMERCIAL_APPROVAL_DOCTYPE,
        filters={"supplier_quotation": supplier_quotation, "supplier_quotation_item": supplier_quotation_item},
        fields=fields,
        order_by="creation desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def create_commercial_approval(evaluation: dict):
    approval = frappe.get_doc(
        {
            "doctype": COMMERCIAL_APPROVAL_DOCTYPE,
            "material_request": evaluation.get("material_request"),
            "request_for_quotation": evaluation.get("request_for_quotation"),
            "supplier_quotation": evaluation.get("supplier_quotation"),
            "supplier_quotation_item": evaluation.get("supplier_quotation_item"),
            "supplier": evaluation.get("supplier"),
            "item_code": evaluation.get("item_code"),
            "item_name": evaluation.get("item_name"),
            "uom": evaluation.get("uom"),
            "qty": evaluation.get("qty"),
            "benchmark_rate": evaluation.get("benchmark_rate"),
            "benchmark_source": evaluation.get("benchmark_source"),
            "benchmark_reference": evaluation.get("benchmark_reference"),
            "quoted_rate": evaluation.get("quoted_rate"),
            "variance_amount": evaluation.get("variance_amount"),
            "variance_percent": evaluation.get("variance_percent"),
            "approval_status": APPROVAL_PENDING_STATUS,
        }
    )
    approval.insert(ignore_permissions=True)
    return approval


def get_benchmark_rate(item_code: str) -> dict[str, object]:
    item_doc = frappe.get_cached_doc("Item", item_code)
    last_purchase_rate = flt(item_doc.get("last_purchase_rate"))
    if last_purchase_rate > 0:
        return {
            "rate": last_purchase_rate,
            "source": "Last Purchase Rate",
            "reference": item_code,
        }

    recent_rows = frappe.db.sql(
        """
        select
            poi.parent as purchase_order,
            poi.base_rate as base_rate,
            po.transaction_date as transaction_date
        from `tabPurchase Order Item` poi
        inner join `tabPurchase Order` po on po.name = poi.parent
        where po.docstatus = 1
          and poi.item_code = %s
          and ifnull(poi.base_rate, 0) > 0
        order by po.transaction_date desc, po.creation desc, poi.creation desc
        limit 3
        """,
        item_code,
        as_dict=True,
    )
    if recent_rows:
        average_rate = sum(flt(row.get("base_rate")) for row in recent_rows) / len(recent_rows)
        return {
            "rate": average_rate,
            "source": "Average of Last 3 Purchase Orders",
            "reference": ", ".join(row.get("purchase_order") for row in recent_rows if row.get("purchase_order")),
        }

    standard_rate = flt(item_doc.get("standard_rate"))
    if standard_rate > 0:
        return {
            "rate": standard_rate,
            "source": "Item Standard Buying Rate",
            "reference": item_code,
        }

    return {
        "rate": None,
        "source": None,
        "reference": None,
    }


def get_supplier_quotation_item_rate(row) -> float:
    return flt(row.get("base_rate") or row.get("rate") or 0)


def normalize_approval_status(value: str | None) -> str:
    return (value or "").strip().lower()


def get_commercial_approval_snapshot(supplier_quotation_names: list[str]) -> dict[str, object]:
    if not supplier_quotation_names:
        return {"evaluations": [], "approval_docs": []}

    approval_docs = frappe.get_all(
        COMMERCIAL_APPROVAL_DOCTYPE,
        filters={"supplier_quotation": ("in", supplier_quotation_names)},
        fields=[
            "name",
            "supplier_quotation",
            "supplier_quotation_item",
            "item_code",
            "item_name",
            "approval_status",
            "decision",
            "benchmark_rate",
            "benchmark_source",
            "quoted_rate",
            "variance_amount",
            "variance_percent",
            "reason_for_higher_price",
            "approved_by",
            "approval_date",
        ],
        order_by="creation asc",
        limit_page_length=0,
    )

    evaluations = []
    for supplier_quotation_name in supplier_quotation_names:
        if frappe.db.get_value("Supplier Quotation", supplier_quotation_name, "docstatus") != 1:
            continue
        doc = frappe.get_doc("Supplier Quotation", supplier_quotation_name)
        evaluations.extend(evaluate_supplier_quotation(doc))

    return {
        "evaluations": evaluations,
        "approval_docs": approval_docs,
    }


@frappe.whitelist()
def get_supplier_quotation_commercial_approval_debug(supplier_quotation: str) -> dict[str, object]:
    if not supplier_quotation:
        frappe.throw(_("Supplier Quotation is required."))

    if frappe.db.get_value("Supplier Quotation", supplier_quotation, "docstatus") != 1:
        frappe.throw(_("Supplier Quotation must be submitted first."))

    doc = frappe.get_doc("Supplier Quotation", supplier_quotation)
    ensure_supplier_quotation_commercial_approvals(doc)
    return {
        "supplier_quotation": supplier_quotation,
        "evaluations": evaluate_supplier_quotation(doc),
    }
