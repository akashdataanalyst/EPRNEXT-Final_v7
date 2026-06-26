from __future__ import annotations

from collections import defaultdict
from datetime import date

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from calco_erp.dashboard_utils import (
    get_doc_route,
    get_list_route,
    make_card,
    make_chart,
    make_drilldown,
    make_drilldown_row,
)


@frappe.whitelist()
def get_dashboard_data(
    supplier: str | None = None,
    item: str | None = None,
    month: str | None = None,
    quarter: str | None = None,
    supplier_type: str | None = None,
) -> dict[str, object]:
    filters = build_filters(supplier=supplier, item=item, month=month, quarter=quarter, supplier_type=supplier_type)
    matrix_summary = get_supplier_matrix_summary(filters)
    procurement = build_procurement_section(filters)
    supplier_section = build_supplier_section(filters, matrix_summary)
    delivery = build_delivery_section(filters, matrix_summary["supplier_type_map"])
    quality = build_quality_section(filters, matrix_summary["supplier_type_map"])
    commercial = build_commercial_section(filters, matrix_summary["supplier_type_map"])
    risk = build_risk_section(filters, matrix_summary, delivery["supplier_delivery_map"], quality, commercial)

    return {
        "title": "Purchase Performance Dashboard",
        "as_of": str(nowdate()),
        "period_label": filters["period_label"],
        "sections": [
            procurement,
            supplier_section,
            delivery["section"],
            quality["section"],
            commercial,
            risk,
        ],
    }


def build_filters(
    supplier: str | None = None,
    item: str | None = None,
    month: str | None = None,
    quarter: str | None = None,
    supplier_type: str | None = None,
) -> dict[str, object]:
    supplier = (supplier or "").strip() or None
    item = (item or "").strip() or None
    supplier_type = (supplier_type or "").strip() or None
    date_from, date_to, period_label = resolve_period(month=month, quarter=quarter)
    return {
        "supplier": supplier,
        "item": item,
        "supplier_type": supplier_type,
        "date_from": date_from,
        "date_to": date_to,
        "period_label": period_label,
    }


def resolve_period(month: str | None = None, quarter: str | None = None) -> tuple[date | None, date | None, str]:
    if month:
        year_str, month_str = month.split("-", 1)
        year = int(year_str)
        month_number = int(month_str)
        start = getdate(f"{year}-{month_number:02d}-01")
        end = add_days(add_days(start, 32).replace(day=1), -1)
        return start, end, start.strftime("%b %Y")

    if quarter:
        year_str, quarter_str = quarter.split("-Q", 1)
        year = int(year_str)
        quarter_number = int(quarter_str)
        start_month = ((quarter_number - 1) * 3) + 1
        start = getdate(f"{year}-{start_month:02d}-01")
        end = add_days(add_days(add_days(start, 95).replace(day=1), -1), 0)
        return start, end, f"Q{quarter_number} {year}"

    return None, None, "All Time"


def build_procurement_section(filters: dict[str, object]) -> dict[str, object]:
    rfqs = get_open_rfqs(filters)
    quotations = get_open_supplier_quotations(filters)
    approvals = get_pending_commercial_approvals(filters)
    purchase_orders = get_open_purchase_orders(filters)
    delayed_pos = get_delayed_purchase_orders(filters)

    cards = [
        make_card(
            "Open RFQs",
            len(rfqs),
            route=get_list_route("Request for Quotation"),
            route_doctype="Request for Quotation",
            route_options=build_route_options(docstatus=1),
        ),
        make_card(
            "Open Supplier Quotations",
            len(quotations),
            route=get_list_route("Supplier Quotation"),
            route_doctype="Supplier Quotation",
            route_options=build_route_options(docstatus=["<", 2], supplier=filters["supplier"]),
        ),
        make_card(
            "Pending Commercial Approvals",
            len(approvals),
            route=get_list_route("Purchase Commercial Approval"),
            route_doctype="Purchase Commercial Approval",
            route_options=build_route_options(approval_status=["in", ["Draft", "Reopened"]], supplier=filters["supplier"], item_code=filters["item"]),
        ),
        make_card(
            "Open POs",
            len(purchase_orders),
            route=get_list_route("Purchase Order"),
            route_doctype="Purchase Order",
            route_options=build_route_options(docstatus=1, supplier=filters["supplier"]),
        ),
        make_card(
            "Delayed POs",
            len(delayed_pos),
            route=get_list_route("Purchase Order"),
            route_doctype="Purchase Order",
            route_options=build_route_options(docstatus=1, supplier=filters["supplier"]),
        ),
    ]

    charts = [
        make_chart(
            "procurement-pipeline",
            "Procurement Pipeline",
            ["RFQs", "Supplier Quotations", "Commercial Approvals", "Open POs", "Delayed POs"],
            [{"name": "Count", "values": [len(rfqs), len(quotations), len(approvals), len(purchase_orders), len(delayed_pos)]}],
            colors=["#0f766e"],
        )
    ]

    drilldowns = [
        make_drilldown(
            "Latest Procurement Records",
            [
                *[make_drilldown_row("Request for Quotation", row["name"], meta=f"RFQ | {row.get('transaction_date') or '-'}") for row in rfqs[:4]],
                *[make_drilldown_row("Supplier Quotation", row["name"], meta=f"{row.get('supplier') or '-'} | {row.get('transaction_date') or '-'}") for row in quotations[:4]],
                *[make_drilldown_row("Purchase Order", row["name"], meta=f"{row.get('supplier') or '-'} | {row.get('schedule_date') or '-'}") for row in purchase_orders[:4]],
            ],
        )
    ]

    return {
        "key": "procurement",
        "title": "Procurement Health",
        "cards": cards,
        "charts": charts,
        "drilldowns": drilldowns,
    }


def build_supplier_section(filters: dict[str, object], matrix_summary: dict[str, object]) -> dict[str, object]:
    rows = matrix_summary["rows"]
    approved_count = sum(1 for row in rows if (row.get("approval_status") or "").lower() == "approved")
    conditional_count = sum(1 for row in rows if (row.get("approval_status") or "").lower() == "conditional approval")
    blocked_count = sum(1 for row in rows if (row.get("approval_status") or "").lower() == "blocked")
    active_count = len(rows)

    delivery_scores = matrix_summary["delivery_scores"]
    quality_scores = matrix_summary["quality_scores"]
    matrix_ratings = [flt(row.get("supplier_rating") or 0) for row in rows if flt(row.get("supplier_rating") or 0) > 0]
    avg_delivery = round(sum(delivery_scores.values()) / len(delivery_scores), 2) if delivery_scores else 0
    avg_quality = round(sum(quality_scores.values()) / len(quality_scores), 2) if quality_scores else 0
    avg_overall = round(sum(matrix_ratings) / len(matrix_ratings), 2) if matrix_ratings else round((avg_delivery + avg_quality) / 2, 2)

    cards = [
        make_card("Active Suppliers", active_count, route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(supplier_type=filters["supplier_type"], item_code=filters["item"])),
        make_card("Approved Suppliers", approved_count, route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(approval_status="Approved", supplier_type=filters["supplier_type"], item_code=filters["item"])),
        make_card("Conditional Suppliers", conditional_count, route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(approval_status="Conditional Approval", supplier_type=filters["supplier_type"], item_code=filters["item"])),
        make_card("Blocked Suppliers", blocked_count, route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(approval_status="Blocked", supplier_type=filters["supplier_type"], item_code=filters["item"])),
        make_card("Supplier Delivery Rating", avg_delivery, suffix="%", route=get_list_route("Purchase Receipt"), route_doctype="Purchase Receipt", route_options=build_route_options(supplier=filters["supplier"])),
        make_card("Supplier Quality Rating", avg_quality, suffix="%", route=get_list_route("Quality Inspection"), route_doctype="Quality Inspection", route_options=build_route_options(reference_type="Purchase Receipt")),
        make_card("Overall Supplier Rating", avg_overall, suffix="%", route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(supplier_type=filters["supplier_type"], item_code=filters["item"])),
    ]

    status_counts = defaultdict(int)
    top_rated = []
    for row in rows:
        status_counts[row.get("approval_status") or "Unknown"] += 1
        top_rated.append((row.get("supplier"), flt(row.get("supplier_rating") or 0)))
    top_rated.sort(key=lambda entry: (-entry[1], entry[0] or ""))

    charts = [
        make_chart(
            "supplier-status",
            "Supplier Status Mix",
            list(status_counts.keys()),
            [{"name": "Suppliers", "values": list(status_counts.values())}],
            chart_type="donut",
            colors=["#15803d", "#d97706", "#b91c1c", "#475569"],
        ),
        make_chart(
            "top-supplier-ratings",
            "Top Supplier Ratings",
            [entry[0] for entry in top_rated[:8]],
            [{"name": "Rating", "values": [entry[1] for entry in top_rated[:8]]}],
            colors=["#2563eb"],
            suffix="%",
        ),
    ]

    drilldowns = [
        make_drilldown(
            "Supplier Approval Snapshot",
            [
                make_drilldown_row(
                    "Supplier Approval Matrix",
                    row["name"],
                    label=row.get("supplier") or row["name"],
                    meta=f"{row.get('approval_status') or '-'} | {row.get('supplier_type') or '-'} | Rating {flt(row.get('supplier_rating') or 0)}",
                )
                for row in rows[:10]
            ],
        )
    ]

    return {
        "key": "supplier",
        "title": "Supplier Performance",
        "cards": cards,
        "charts": charts,
        "drilldowns": drilldowns,
    }


def build_delivery_section(filters: dict[str, object], supplier_type_map: dict[str, str]) -> dict[str, object]:
    rows = get_delivery_rows(filters, supplier_type_map)
    on_time_count = sum(1 for row in rows if row["is_on_time"])
    eligible_count = sum(1 for row in rows if row["schedule_date"])
    on_time_pct = round((on_time_count * 100.0 / eligible_count), 2) if eligible_count else 0
    avg_lead_time = round(sum(row["actual_lead_time"] for row in rows) / len(rows), 2) if rows else 0
    accuracy_values = [row["lead_time_accuracy"] for row in rows if row["lead_time_accuracy"] is not None]
    lead_time_accuracy = round(sum(accuracy_values) / len(accuracy_values), 2) if accuracy_values else 0

    supplier_delivery_map = defaultdict(list)
    delayed_rows = []
    for row in rows:
        supplier_delivery_map[row["supplier"]].append(row)
        if row["schedule_date"] and not row["is_on_time"]:
            delayed_rows.append(row)

    supplier_bars = []
    for supplier, supplier_rows in supplier_delivery_map.items():
        eligible = [row for row in supplier_rows if row["schedule_date"]]
        if not eligible:
            continue
        supplier_bars.append(
            (
                supplier,
                round(sum(1 for row in eligible if row["is_on_time"]) * 100.0 / len(eligible), 2),
            )
        )
    supplier_bars.sort(key=lambda entry: (-entry[1], entry[0]))

    section = {
        "key": "delivery",
        "title": "Delivery Performance",
        "cards": [
            make_card("On-Time Delivery %", on_time_pct, suffix="%", route=get_list_route("Purchase Receipt"), route_doctype="Purchase Receipt", route_options=build_route_options(supplier=filters["supplier"])),
            make_card("Avg Lead Time", avg_lead_time, suffix=" days", route=get_list_route("Purchase Receipt"), route_doctype="Purchase Receipt", route_options=build_route_options(supplier=filters["supplier"])),
            make_card("Lead Time Accuracy", lead_time_accuracy, suffix="%", route=get_list_route("Purchase Receipt"), route_doctype="Purchase Receipt", route_options=build_route_options(supplier=filters["supplier"])),
        ],
        "charts": [
            make_chart(
                "delivery-by-supplier",
                "On-Time Delivery by Supplier",
                [entry[0] for entry in supplier_bars[:8]],
                [{"name": "On-Time %", "values": [entry[1] for entry in supplier_bars[:8]]}],
                colors=["#0891b2"],
                suffix="%",
            )
        ],
        "drilldowns": [
            make_drilldown(
                "Delayed Deliveries",
                [
                    make_drilldown_row(
                        "Purchase Receipt",
                        row["purchase_receipt"],
                        label=row["supplier"],
                        meta=f"{row['item_code']} | Planned {row['schedule_date']} | Actual {row['posting_date']}",
                    )
                    for row in delayed_rows[:10]
                ],
            )
        ],
    }
    return {"section": section, "supplier_delivery_map": supplier_delivery_map}


def build_quality_section(filters: dict[str, object], supplier_type_map: dict[str, str]) -> dict[str, object]:
    receipt_rows = get_receipt_quality_rows(filters, supplier_type_map)
    total_received = sum(flt(row.get("received_qty") or 0) for row in receipt_rows)
    total_rejected = sum(flt(row.get("rejected_qty") or 0) for row in receipt_rows)
    rejection_pct = round((total_rejected * 100.0 / total_received), 2) if total_received else 0

    capa_rows = get_capa_rows(filters, supplier_type_map)
    open_capa = [row for row in capa_rows if not is_capa_closed(row)]
    overdue_capa = [row for row in open_capa if row.get("required_response_date") and getdate(row["required_response_date"]) < getdate(nowdate())]
    closed_capa = [row for row in capa_rows if is_capa_closed(row)]
    capa_closure_pct = round((len(closed_capa) * 100.0 / len(capa_rows)), 2) if capa_rows else 0

    supplier_rejections = defaultdict(float)
    for row in receipt_rows:
        supplier_rejections[row["supplier"]] += flt(row.get("rejected_qty") or 0)
    rejection_bars = sorted(supplier_rejections.items(), key=lambda entry: (-entry[1], entry[0]))

    section = {
        "key": "quality",
        "title": "Quality Performance",
        "cards": [
            make_card("RM Rejection %", rejection_pct, suffix="%", route=get_list_route("Quality Inspection"), route_doctype="Quality Inspection", route_options=build_route_options(reference_type="Purchase Receipt")),
            make_card("CAPA Closure %", capa_closure_pct, suffix="%", route=get_list_route("Supplier CAPA Request"), route_doctype="Supplier CAPA Request", route_options=build_route_options(supplier=filters["supplier"])),
            make_card("Open CAPA", len(open_capa), route=get_list_route("Supplier CAPA Request"), route_doctype="Supplier CAPA Request", route_options=build_route_options(supplier=filters["supplier"])),
            make_card("Overdue CAPA", len(overdue_capa), route=get_list_route("Supplier CAPA Request"), route_doctype="Supplier CAPA Request", route_options=build_route_options(supplier=filters["supplier"])),
        ],
        "charts": [
            make_chart(
                "supplier-rejections",
                "Top RM Rejections by Supplier",
                [entry[0] for entry in rejection_bars[:8]],
                [{"name": "Rejected Qty", "values": [entry[1] for entry in rejection_bars[:8]]}],
                colors=["#dc2626"],
                suffix=" Kg",
            )
        ],
        "drilldowns": [
            make_drilldown(
                "Open / Overdue CAPA Cases",
                [
                    make_drilldown_row(
                        "Supplier CAPA Request",
                        row["name"],
                        label=row.get("supplier") or row["name"],
                        meta=f"{row.get('item_code') or '-'} | Due {row.get('required_response_date') or '-'} | {'Closed' if is_capa_closed(row) else 'Open'}",
                    )
                    for row in (overdue_capa + open_capa)[:10]
                ],
            )
        ],
    }
    return {
        "section": section,
        "rejection_pct": rejection_pct,
        "open_capa": len(open_capa),
        "overdue_capa": len(overdue_capa),
        "capa_rows": capa_rows,
        "receipt_rows": receipt_rows,
    }


def build_commercial_section(filters: dict[str, object], supplier_type_map: dict[str, str]) -> dict[str, object]:
    rows = get_commercial_approval_rows(filters, supplier_type_map)
    variance_count = len(rows)
    variance_value = round(sum(flt(row.get("variance_amount") or 0) for row in rows), 2)
    top_cases = sorted(rows, key=lambda row: (-flt(row.get("variance_amount") or 0), row.get("name") or ""))[:10]

    charts = [
        make_chart(
            "commercial-variance",
            "Top Commercial Variance Cases",
            [row.get("supplier") or row.get("name") for row in top_cases[:8]],
            [{"name": "Variance", "values": [flt(row.get("variance_amount") or 0) for row in top_cases[:8]]}],
            colors=["#7c3aed"],
            suffix=" Rs",
        )
    ]

    drilldowns = [
        make_drilldown(
            "Top Variance Cases",
            [
                make_drilldown_row(
                    "Purchase Commercial Approval",
                    row["name"],
                    label=row.get("supplier") or row["name"],
                    meta=f"{row.get('item_code') or '-'} | Variance {flt(row.get('variance_amount') or 0)} | {row.get('approval_status') or '-'}",
                )
                for row in top_cases
            ],
        )
    ]

    return {
        "key": "commercial",
        "title": "Commercial Performance",
        "cards": [
            make_card("Commercial Variance Count", variance_count, route=get_list_route("Purchase Commercial Approval"), route_doctype="Purchase Commercial Approval", route_options=build_route_options(supplier=filters["supplier"], item_code=filters["item"])),
            make_card("Commercial Variance Value", variance_value, suffix=" Rs", route=get_list_route("Purchase Commercial Approval"), route_doctype="Purchase Commercial Approval", route_options=build_route_options(supplier=filters["supplier"], item_code=filters["item"])),
        ],
        "charts": charts,
        "drilldowns": drilldowns,
        "rows": rows,
    }


def build_risk_section(
    filters: dict[str, object],
    matrix_summary: dict[str, object],
    supplier_delivery_map: dict[str, list[dict[str, object]]],
    quality_summary: dict[str, object],
    commercial_summary: dict[str, object],
) -> dict[str, object]:
    capa_rows = quality_summary["capa_rows"]
    commercial_rows = commercial_summary["rows"]
    delivery_supplier_map = {}
    for supplier, rows in supplier_delivery_map.items():
        eligible = [row for row in rows if row["schedule_date"]]
        on_time_pct = round(sum(1 for row in eligible if row["is_on_time"]) * 100.0 / len(eligible), 2) if eligible else 100
        delivery_supplier_map[supplier] = on_time_pct

    rejection_by_supplier = defaultdict(lambda: {"received": 0.0, "rejected": 0.0})
    for row in quality_summary["receipt_rows"]:
        rejection_by_supplier[row["supplier"]]["received"] += flt(row.get("received_qty") or 0)
        rejection_by_supplier[row["supplier"]]["rejected"] += flt(row.get("rejected_qty") or 0)

    overdue_capa_by_supplier = defaultdict(int)
    open_capa_by_supplier = defaultdict(int)
    for row in capa_rows:
        supplier = row.get("supplier") or ""
        if not supplier or is_capa_closed(row):
            continue
        open_capa_by_supplier[supplier] += 1
        if row.get("required_response_date") and getdate(row["required_response_date"]) < getdate(nowdate()):
            overdue_capa_by_supplier[supplier] += 1

    pending_commercial_by_supplier = defaultdict(int)
    for row in commercial_rows:
        if (row.get("approval_status") or "") in {"Draft", "Reopened"}:
            pending_commercial_by_supplier[row.get("supplier") or ""] += 1

    risk_rows = []
    for row in matrix_summary["rows"]:
        supplier = row.get("supplier") or ""
        if not supplier:
            continue
        approval_status = (row.get("approval_status") or "").lower()
        received = rejection_by_supplier[supplier]["received"]
        rejected = rejection_by_supplier[supplier]["rejected"]
        rejection_pct = round((rejected * 100.0 / received), 2) if received else 0
        on_time_pct = delivery_supplier_map.get(supplier, 100)
        risk_score = 0
        if approval_status == "blocked":
            risk_score += 5
        elif approval_status == "conditional approval":
            risk_score += 2
        if on_time_pct < 80:
            risk_score += 2
        if rejection_pct > 5:
            risk_score += 2
        if overdue_capa_by_supplier[supplier]:
            risk_score += 3
        if pending_commercial_by_supplier[supplier]:
            risk_score += 1
        if risk_score >= 3:
            risk_rows.append(
                {
                    "supplier": supplier,
                    "risk_score": risk_score,
                    "approval_status": row.get("approval_status") or "",
                    "on_time_pct": on_time_pct,
                    "rejection_pct": rejection_pct,
                    "overdue_capa": overdue_capa_by_supplier[supplier],
                    "pending_commercial": pending_commercial_by_supplier[supplier],
                    "matrix_name": row.get("name"),
                }
            )

    risk_rows.sort(key=lambda row: (-row["risk_score"], row["supplier"]))
    return {
        "key": "risk",
        "title": "Risk Dashboard",
        "cards": [
            make_card("High Risk Suppliers", len(risk_rows), route=get_list_route("Supplier Approval Matrix"), route_doctype="Supplier Approval Matrix", route_options=build_route_options(supplier_type=filters["supplier_type"])),
        ],
        "charts": [
            make_chart(
                "risk-suppliers",
                "High Risk Suppliers",
                [row["supplier"] for row in risk_rows[:8]],
                [{"name": "Risk Score", "values": [row["risk_score"] for row in risk_rows[:8]]}],
                colors=["#b91c1c"],
            )
        ],
        "drilldowns": [
            make_drilldown(
                "High Risk Supplier Details",
                [
                    make_drilldown_row(
                        "Supplier Approval Matrix",
                        row["matrix_name"],
                        label=row["supplier"],
                        meta=f"Score {row['risk_score']} | {row['approval_status']} | OTD {row['on_time_pct']}% | Rejection {row['rejection_pct']}% | Overdue CAPA {row['overdue_capa']}",
                    )
                    for row in risk_rows[:10]
                ],
            )
        ],
    }


def get_supplier_matrix_summary(filters: dict[str, object]) -> dict[str, object]:
    conditions = ["ifnull(sam.supplier, '') != ''"]
    values: dict[str, object] = {}
    if filters["supplier"]:
        conditions.append("sam.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["item"]:
        conditions.append("sam.item_code = %(item)s")
        values["item"] = filters["item"]

    rows = frappe.db.sql(
        f"""
        select
            sam.name,
            sam.supplier,
            sam.item_code,
            sam.approval_status,
            sam.supplier_type,
            sam.supplier_rating,
            sam.effective_date,
            sam.expiry_date,
            sam.modified
        from `tabSupplier Approval Matrix` sam
        where {' and '.join(conditions)}
        order by sam.modified desc
        """,
        values,
        as_dict=True,
    )

    supplier_rows = {}
    for row in rows:
        if filters["supplier_type"] and (row.get("supplier_type") or "") != filters["supplier_type"]:
            continue
        supplier_rows.setdefault(row["supplier"], row)

    delivery_rows = get_delivery_rows(filters, {supplier: row.get("supplier_type") or "" for supplier, row in supplier_rows.items()})
    quality_rows = get_receipt_quality_rows(filters, {supplier: row.get("supplier_type") or "" for supplier, row in supplier_rows.items()})
    delivery_scores = defaultdict(list)
    for row in delivery_rows:
        if row["schedule_date"]:
            delivery_scores[row["supplier"]].append(100.0 if row["is_on_time"] else 0.0)
    quality_received = defaultdict(float)
    quality_rejected = defaultdict(float)
    for row in quality_rows:
        quality_received[row["supplier"]] += flt(row.get("received_qty") or 0)
        quality_rejected[row["supplier"]] += flt(row.get("rejected_qty") or 0)

    return {
        "rows": list(supplier_rows.values()),
        "supplier_type_map": {supplier: row.get("supplier_type") or "" for supplier, row in supplier_rows.items()},
        "delivery_scores": {
            supplier: round(sum(scores) / len(scores), 2) if scores else 0
            for supplier, scores in delivery_scores.items()
        },
        "quality_scores": {
            supplier: round(max(0, 100 - (quality_rejected[supplier] * 100.0 / quality_received[supplier])), 2)
            if quality_received[supplier]
            else 100
            for supplier in supplier_rows
        },
    }


def get_open_rfqs(filters: dict[str, object]) -> list[dict[str, object]]:
    conditions = ["rfq.docstatus < 2"]
    values: dict[str, object] = {}
    joins = ["left join `tabRequest for Quotation Item` rfqi on rfqi.parent = rfq.name"]
    if filters["item"]:
        conditions.append("rfqi.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        joins.append("left join `tabRequest for Quotation Supplier` rfqs on rfqs.parent = rfq.name")
        conditions.append("rfqs.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("rfq.transaction_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    return frappe.db.sql(
        f"""
        select distinct rfq.name, rfq.status, rfq.transaction_date
        from `tabRequest for Quotation` rfq
        {' '.join(joins)}
        where {' and '.join(conditions)}
        order by rfq.transaction_date desc, rfq.modified desc
        limit 20
        """,
        values,
        as_dict=True,
    )


def get_open_supplier_quotations(filters: dict[str, object]) -> list[dict[str, object]]:
    conditions = ["sq.docstatus < 2"]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("sqi.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("sq.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("sq.transaction_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select distinct sq.name, sq.supplier, sq.status, sq.transaction_date
        from `tabSupplier Quotation` sq
        left join `tabSupplier Quotation Item` sqi on sqi.parent = sq.name
        where {' and '.join(conditions)}
        order by sq.transaction_date desc, sq.modified desc
        limit 20
        """,
        values,
        as_dict=True,
    )
    return filter_rows_by_supplier_type(rows, filters)


def get_pending_commercial_approvals(filters: dict[str, object]) -> list[dict[str, object]]:
    conditions = ["pca.approval_status in ('Draft', 'Reopened')"]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("pca.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("pca.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("date(pca.creation) between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select pca.name, pca.supplier, pca.item_code, pca.variance_amount, pca.approval_status
        from `tabPurchase Commercial Approval` pca
        where {' and '.join(conditions)}
        order by pca.creation desc
        limit 20
        """,
        values,
        as_dict=True,
    )
    return filter_rows_by_supplier_type(rows, filters)


def get_open_purchase_orders(filters: dict[str, object]) -> list[dict[str, object]]:
    conditions = ["po.docstatus = 1", "ifnull(po.status, '') not in ('Closed', 'Completed', 'Cancelled')"]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("poi.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("po.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("po.transaction_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select distinct po.name, po.supplier, po.status, po.transaction_date, po.schedule_date
        from `tabPurchase Order` po
        left join `tabPurchase Order Item` poi on poi.parent = po.name
        where {' and '.join(conditions)}
        order by po.transaction_date desc, po.modified desc
        limit 20
        """,
        values,
        as_dict=True,
    )
    return filter_rows_by_supplier_type(rows, filters)


def get_delayed_purchase_orders(filters: dict[str, object]) -> list[dict[str, object]]:
    conditions = [
        "po.docstatus = 1",
        "ifnull(po.status, '') not in ('Closed', 'Completed', 'Cancelled')",
        "poi.schedule_date < %(today)s",
        "ifnull(poi.received_qty, 0) < ifnull(poi.qty, 0)",
    ]
    values: dict[str, object] = {"today": nowdate()}
    if filters["item"]:
        conditions.append("poi.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("po.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("po.transaction_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select distinct po.name, po.supplier, poi.item_code, poi.schedule_date, poi.qty, poi.received_qty
        from `tabPurchase Order` po
        inner join `tabPurchase Order Item` poi on poi.parent = po.name
        where {' and '.join(conditions)}
        order by poi.schedule_date asc, po.modified desc
        limit 20
        """,
        values,
        as_dict=True,
    )
    return filter_rows_by_supplier_type(rows, filters)


def get_delivery_rows(filters: dict[str, object], supplier_type_map: dict[str, str]) -> list[dict[str, object]]:
    conditions = [
        "pr.docstatus = 1",
        "ifnull(pr.is_return, 0) = 0",
        "po.docstatus = 1",
        "ifnull(po.supplier, '') != ''",
    ]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("pri.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("po.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("pr.posting_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select
            pr.name as purchase_receipt,
            pr.posting_date,
            po.name as purchase_order,
            po.transaction_date,
            po.supplier,
            pri.item_code,
            pri.schedule_date,
            datediff(pr.posting_date, po.transaction_date) as actual_lead_time,
            case
                when pri.schedule_date is not null then datediff(pri.schedule_date, po.transaction_date)
                else null
            end as planned_lead_time
        from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr on pr.name = pri.parent
        inner join `tabPurchase Order` po on po.name = pri.purchase_order
        where {' and '.join(conditions)}
        order by pr.posting_date desc, pr.modified desc
        """,
        values,
        as_dict=True,
    )
    filtered = []
    for row in rows:
        if filters["supplier_type"] and supplier_type_map.get(row["supplier"]) != filters["supplier_type"]:
            continue
        planned = flt(row.get("planned_lead_time") or 0)
        actual = flt(row.get("actual_lead_time") or 0)
        row["is_on_time"] = bool(row.get("schedule_date") and getdate(row["posting_date"]) <= getdate(row["schedule_date"]))
        row["lead_time_accuracy"] = round(max(0, 100 - (abs(actual - planned) * 100 / planned)), 2) if planned > 0 else None
        filtered.append(row)
    return filtered


def get_receipt_quality_rows(filters: dict[str, object], supplier_type_map: dict[str, str]) -> list[dict[str, object]]:
    conditions = [
        "pr.docstatus = 1",
        "ifnull(pr.is_return, 0) = 0",
        "ifnull(pr.supplier, '') != ''",
    ]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("pri.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("pr.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("pr.posting_date between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select
            pr.name as purchase_receipt,
            pr.posting_date,
            pr.supplier,
            pri.item_code,
            ifnull(pri.received_qty, pri.qty) as received_qty,
            ifnull(pri.custom_rejected_qty, 0) as rejected_qty
        from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr on pr.name = pri.parent
        where {' and '.join(conditions)}
        order by pr.posting_date desc, pr.modified desc
        """,
        values,
        as_dict=True,
    )
    return [row for row in rows if not filters["supplier_type"] or supplier_type_map.get(row["supplier"]) == filters["supplier_type"]]


def get_capa_rows(filters: dict[str, object], supplier_type_map: dict[str, str]) -> list[dict[str, object]]:
    if not frappe.db.exists("DocType", "Supplier CAPA Request"):
        return []
    conditions = ["ifnull(scr.supplier, '') != ''", "scr.docstatus < 2"]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("scr.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("scr.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("date(scr.creation) between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select scr.name, scr.supplier, scr.item_code, scr.docstatus, scr.required_response_date
        from `tabSupplier CAPA Request` scr
        where {' and '.join(conditions)}
        order by scr.creation desc
        """,
        values,
        as_dict=True,
    )
    return [row for row in rows if not filters["supplier_type"] or supplier_type_map.get(row["supplier"]) == filters["supplier_type"]]


def get_commercial_approval_rows(filters: dict[str, object], supplier_type_map: dict[str, str]) -> list[dict[str, object]]:
    conditions = ["1=1"]
    values: dict[str, object] = {}
    if filters["item"]:
        conditions.append("pca.item_code = %(item)s")
        values["item"] = filters["item"]
    if filters["supplier"]:
        conditions.append("pca.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]
    if filters["date_from"]:
        conditions.append("date(pca.creation) between %(date_from)s and %(date_to)s")
        values["date_from"] = filters["date_from"]
        values["date_to"] = filters["date_to"]
    rows = frappe.db.sql(
        f"""
        select
            pca.name,
            pca.supplier,
            pca.item_code,
            pca.variance_amount,
            pca.approval_status,
            pca.quoted_rate,
            pca.benchmark_rate
        from `tabPurchase Commercial Approval` pca
        where {' and '.join(conditions)}
        order by pca.creation desc
        """,
        values,
        as_dict=True,
    )
    return [row for row in rows if not filters["supplier_type"] or supplier_type_map.get(row["supplier"]) == filters["supplier_type"]]


def filter_rows_by_supplier_type(rows: list[dict[str, object]], filters: dict[str, object]) -> list[dict[str, object]]:
    if not filters["supplier_type"]:
        return rows
    matrix_rows = get_supplier_matrix_summary({"supplier": None, "item": None, "supplier_type": None, "date_from": None, "date_to": None, "period_label": ""})
    supplier_type_map = matrix_rows["supplier_type_map"]
    return [row for row in rows if supplier_type_map.get(row.get("supplier") or "") == filters["supplier_type"]]


def is_capa_closed(row: dict[str, object]) -> bool:
    return int(row.get("docstatus") or 0) == 1


def build_route_options(**kwargs) -> dict[str, object]:
    options = {}
    for key, value in kwargs.items():
        if value in (None, "", [], {}):
            continue
        options[key] = value
    return options
