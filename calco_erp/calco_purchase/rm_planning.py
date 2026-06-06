from __future__ import annotations

import calendar
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from calco_erp.dashboard_utils import get_doc_route, get_list_route


RM_ITEM_GROUP = "Raw Material"
RM_STORE_WAREHOUSE = "Stores - CPPL"
APPROVED_MATRIX_STATUSES = ("Approved", "Conditional Approval")
HEALTH_META = {
    "Critical": {"color": "red", "rank": 0},
    "Low": {"color": "yellow", "rank": 1},
    "Healthy": {"color": "green", "rank": 2},
    "Overstock": {"color": "purple", "rank": 3},
}


@dataclass
class LeadTimeStat:
    average_days: float = 0.0
    minimum_days: float = 0.0
    maximum_days: float = 0.0
    last_three: list[float] | None = None
    on_time_percentage: float = 0.0
    sample_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "average_days": round(self.average_days, 2),
            "minimum_days": round(self.minimum_days, 2),
            "maximum_days": round(self.maximum_days, 2),
            "last_three": [round(value, 2) for value in (self.last_three or [])],
            "on_time_percentage": round(self.on_time_percentage, 2),
            "sample_count": self.sample_count,
        }


def _clean_planning_kwargs(kwargs: dict[str, object] | None) -> dict[str, object]:
    cleaned = dict(kwargs or {})
    cleaned.pop("cmd", None)
    cleaned.pop("method", None)
    return cleaned


@frappe.whitelist()
def get_dashboard_data(*args, **kwargs) -> dict[str, object]:
    kwargs = _clean_planning_kwargs(kwargs)
    category = kwargs.get("category")
    item_code = kwargs.get("item_code")
    supplier = kwargs.get("supplier")
    inventory_health = kwargs.get("inventory_health")
    supplier_type = kwargs.get("supplier_type")
    current_season = kwargs.get("current_season")
    only_items_requiring_purchase = kwargs.get("only_items_requiring_purchase", 0)
    only_critical_items = kwargs.get("only_critical_items", 0)
    report_date = kwargs.get("report_date")

    planning_date = getdate(report_date or nowdate())
    month_start = planning_date.replace(day=1)
    month_end = planning_date.replace(day=calendar.monthrange(planning_date.year, planning_date.month)[1])
    month_days = month_end.day

    filters = {
        "category": (category or "").strip(),
        "item_code": (item_code or "").strip(),
        "supplier": (supplier or "").strip(),
        "inventory_health": (inventory_health or "").strip(),
        "supplier_type": (supplier_type or "").strip(),
        "current_season": (current_season or "").strip(),
        "only_items_requiring_purchase": cint(only_items_requiring_purchase),
        "only_critical_items": cint(only_critical_items),
    }

    items = get_rm_items(filters)
    item_codes = [row["item_code"] for row in items]
    parameters = get_planning_parameter_map(item_codes)
    projection_map = get_monthly_projection_requirement_map(month_start, month_end)
    stock_map = get_store_stock_map(item_codes)
    open_po_map = get_open_po_map(item_codes)
    reorder_map = get_item_reorder_defaults(item_codes)
    supplier_rows = get_supplier_matrix_rows(item_codes)
    lead_time_data = get_lead_time_data(item_codes)

    rows = []
    for item in items:
        code = item["item_code"]
        parameter = parameters.get(code, {})
        supplier_profile = resolve_supplier_profile(code, parameter, supplier_rows.get(code, []))
        lead_stats = resolve_lead_time_stats(code, supplier_profile.get("supplier"), lead_time_data)
        row = build_dashboard_row(
            item=item,
            parameter=parameter,
            supplier_profile=supplier_profile,
            lead_stats=lead_stats,
            projection_qty=flt(projection_map.get(code) or 0),
            month_days=month_days,
            current_stock=flt(stock_map.get(code) or 0),
            open_po_qty=flt(open_po_map.get(code) or 0),
            reorder_defaults=reorder_map.get(code, {}),
            planning_date=planning_date,
        )
        if not dashboard_row_matches_filters(row, filters):
            continue
        rows.append(row)

    rows.sort(key=lambda row: (HEALTH_META.get(row["inventory_health"], {}).get("rank", 9), row["item_code"]))
    analytics = build_lead_time_analytics(rows, lead_time_data)
    cards = build_dashboard_cards(rows)

    return {
        "report_date": str(planning_date),
        "month_days": month_days,
        "warehouse": RM_STORE_WAREHOUSE,
        "cards": cards,
        "rows": rows,
        "lead_time_analytics": analytics,
        "filters": filters,
        "formulas": {
            "safety_stock": "Selected Daily Consumption × Safety Days",
            "reorder_level": "(Selected Daily Consumption × Lead Time Days) + Safety Stock",
            "maximum_level": "Reorder Level + (Selected Daily Consumption × Review Period Days)",
            "projected_available_qty": "Current RM Store Stock + Open PO / In Transit Qty",
            "coverage_days": "Projected Available Qty / Selected Daily Consumption",
            "suggested_order_qty": "MAX(0, Maximum Level + Production Requirement - Current RM Store Stock - Open PO / In Transit Qty)",
        },
    }


@frappe.whitelist()
def create_material_request(
    item_code: str | None = None,
    qty=None,
    required_by: str | None = None,
    warehouse: str | None = None,
    *args,
    **kwargs,
) -> dict[str, object]:
    kwargs = _clean_planning_kwargs(kwargs)
    item_code = item_code or kwargs.get("item_code")
    qty = qty if qty is not None else kwargs.get("qty")
    required_by = required_by or kwargs.get("required_by")
    warehouse = warehouse or kwargs.get("warehouse")

    qty = flt(qty or 0)
    if qty <= 0:
        frappe.throw(_("Suggested Order Qty must be greater than zero before creating a Material Request."))

    required_by_date = getdate(required_by)
    if required_by_date < getdate(nowdate()):
        frappe.throw(_("Required By date cannot be before today."))

    mr = frappe.get_doc(
        {
            "doctype": "Material Request",
            "material_request_type": "Purchase",
            "schedule_date": required_by_date,
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "warehouse": warehouse or RM_STORE_WAREHOUSE,
                    "schedule_date": required_by_date,
                }
            ],
        }
    )
    mr.insert()
    return {
        "name": mr.name,
        "route": ["Form", "Material Request", mr.name],
    }


@frappe.whitelist()
def create_bulk_material_requests(rows_json: str | None = None, *args, **kwargs) -> dict[str, object]:
    kwargs = _clean_planning_kwargs(kwargs)
    rows_json = rows_json or kwargs.get("rows_json")
    rows = json.loads(rows_json or "[]")
    valid_rows = [row for row in rows if flt(row.get("suggested_order_qty") or 0) > 0]
    if not valid_rows:
        frappe.throw(_("No rows with a positive Suggested Order Qty were selected."))

    mr = frappe.get_doc(
        {
            "doctype": "Material Request",
            "material_request_type": "Purchase",
            "items": [
                {
                    "item_code": row["item_code"],
                    "qty": flt(row["suggested_order_qty"]),
                    "warehouse": row.get("warehouse") or RM_STORE_WAREHOUSE,
                    "schedule_date": getdate(row["required_by_date"]),
                }
                for row in valid_rows
            ],
        }
    )
    mr.insert()
    return {
        "name": mr.name,
        "route": ["Form", "Material Request", mr.name],
    }


def get_rm_items(filters: dict[str, object]) -> list[dict[str, object]]:
    item_filters = {"disabled": 0, "item_group": RM_ITEM_GROUP}
    if filters.get("category"):
        item_filters["item_group"] = filters["category"]
    if filters.get("item_code"):
        item_filters["name"] = filters["item_code"]

    rows = frappe.get_all(
        "Item",
        filters=item_filters,
        fields=["name as item_code", "item_name", "item_group as category", "stock_uom", "lead_time_days", "safety_stock"],
        order_by="name asc",
    )
    return rows


def get_planning_parameter_map(item_codes: list[str]) -> dict[str, dict[str, object]]:
    if not item_codes or not frappe.db.exists("DocType", "RM Planning Parameter"):
        return {}
    rows = frappe.get_all(
        "RM Planning Parameter",
        filters={"item_code": ("in", item_codes)},
        fields=[
            "name",
            "item_code",
            "preferred_supplier",
            "daily_avg_consumption_low",
            "daily_avg_consumption_peak",
            "current_season",
            "manual_lead_time_days",
            "safety_days",
            "review_period_days",
            "minimum_order_qty",
            "purchase_pack_size",
            "is_active",
        ],
    )
    return {row["item_code"]: row for row in rows if cint(row.get("is_active") or 0)}


def get_monthly_projection_requirement_map(month_start: date, month_end: date) -> dict[str, float]:
    if not frappe.db.exists("DocType", "Production Plan Item"):
        return {}

    plan_items = frappe.db.sql(
        """
        select
            ppi.item_code,
            ppi.bom_no,
            ppi.planned_qty,
            ppi.planned_start_date,
            pp.name as production_plan,
            pp.posting_date,
            pp.from_date,
            pp.to_date
        from `tabProduction Plan Item` ppi
        inner join `tabProduction Plan` pp on pp.name = ppi.parent
        where pp.docstatus < 2
        """,
        as_dict=True,
    )

    requirement_map: dict[str, float] = defaultdict(float)
    explosion_cache: dict[str, list[dict[str, object]]] = {}
    for row in plan_items:
        if not plan_item_in_month(row, month_start, month_end):
            continue
        bom_no = (row.get("bom_no") or "").strip()
        if not bom_no:
            continue
        if bom_no not in explosion_cache:
            explosion_cache[bom_no] = frappe.get_all(
                "BOM Explosion Item",
                filters={"parent": bom_no},
                fields=["item_code", "qty_consumed_per_unit", "stock_qty"],
            )
        for bom_row in explosion_cache[bom_no]:
            qty_per_unit = flt(bom_row.get("qty_consumed_per_unit") or 0)
            if qty_per_unit <= 0:
                qty_per_unit = flt(bom_row.get("stock_qty") or 0)
            requirement_map[bom_row["item_code"]] += flt(row.get("planned_qty") or 0) * qty_per_unit

    return {key: round(value, 3) for key, value in requirement_map.items()}


def plan_item_in_month(row: dict[str, object], month_start: date, month_end: date) -> bool:
    if row.get("planned_start_date"):
        planned_start = getdate(row["planned_start_date"])
        return month_start <= planned_start <= month_end

    if row.get("from_date") or row.get("to_date"):
        from_date = getdate(row.get("from_date") or month_start)
        to_date = getdate(row.get("to_date") or month_end)
        return from_date <= month_end and to_date >= month_start

    posting_date = getdate(row.get("posting_date") or month_start)
    return month_start <= posting_date <= month_end


def get_store_stock_map(item_codes: list[str]) -> dict[str, float]:
    if not item_codes:
        return {}
    rows = frappe.db.sql(
        """
        select item_code, round(sum(actual_qty), 3) as qty
        from `tabBin`
        where warehouse = %(warehouse)s
          and item_code in %(item_codes)s
        group by item_code
        """,
        {"warehouse": RM_STORE_WAREHOUSE, "item_codes": tuple(item_codes)},
        as_dict=True,
    )
    return {row["item_code"]: flt(row["qty"]) for row in rows}


def get_open_po_map(item_codes: list[str]) -> dict[str, float]:
    if not item_codes:
        return {}
    rows = frappe.db.sql(
        """
        select
            poi.item_code,
            round(sum(greatest(poi.qty - ifnull(poi.received_qty, 0), 0)), 3) as outstanding_qty
        from `tabPurchase Order Item` poi
        inner join `tabPurchase Order` po on po.name = poi.parent
        where po.docstatus = 1
          and ifnull(po.status, '') not in ('Closed', 'Completed', 'Cancelled')
          and poi.item_code in %(item_codes)s
          and greatest(poi.qty - ifnull(poi.received_qty, 0), 0) > 0
        group by poi.item_code
        """,
        {"item_codes": tuple(item_codes)},
        as_dict=True,
    )
    return {row["item_code"]: flt(row["outstanding_qty"]) for row in rows}


def get_item_reorder_defaults(item_codes: list[str]) -> dict[str, dict[str, float]]:
    if not item_codes:
        return {}
    rows = frappe.db.sql(
        """
        select parent as item_code, max(warehouse_reorder_level) as reorder_level, max(warehouse_reorder_qty) as reorder_qty
        from `tabItem Reorder`
        where parent in %(item_codes)s
        group by parent
        """,
        {"item_codes": tuple(item_codes)},
        as_dict=True,
    )
    return {
        row["item_code"]: {
            "reorder_level": flt(row.get("reorder_level") or 0),
            "reorder_qty": flt(row.get("reorder_qty") or 0),
        }
        for row in rows
    }


def get_supplier_matrix_rows(item_codes: list[str]) -> dict[str, list[dict[str, object]]]:
    if not item_codes or not frappe.db.exists("DocType", "Supplier Approval Matrix"):
        return {}
    rows = frappe.get_all(
        "Supplier Approval Matrix",
        filters={
            "item_code": ("in", item_codes),
            "approval_status": ("in", APPROVED_MATRIX_STATUSES),
        },
        fields=[
            "name",
            "item_code",
            "supplier",
            "supplier_type",
            "approval_status",
            "supplier_rating",
            "lead_time",
            "payment_terms",
            "effective_date",
            "expiry_date",
        ],
        order_by="item_code asc, approval_status asc, supplier asc",
    )
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[row["item_code"]].append(row)
    return grouped


def resolve_supplier_profile(item_code: str, parameter: dict[str, object], rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "supplier": parameter.get("preferred_supplier") or "",
            "supplier_type": "",
            "approval_status": "",
            "payment_terms": "",
            "supplier_rating": 0,
        }

    preferred_supplier = (parameter.get("preferred_supplier") or "").strip()
    if preferred_supplier:
        for row in rows:
            if row.get("supplier") == preferred_supplier:
                return row

    approved = [row for row in rows if row.get("approval_status") == "Approved"]
    if approved:
        return approved[0]
    return rows[0]


def get_lead_time_data(item_codes: list[str]) -> dict[tuple[str, str], LeadTimeStat]:
    if not item_codes:
        return {}
    rows = frappe.db.sql(
        """
        select
            pri.item_code,
            po.supplier,
            datediff(pr.posting_date, po.transaction_date) as lead_time_days,
            pri.schedule_date,
            pr.posting_date
        from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr on pr.name = pri.parent
        inner join `tabPurchase Order` po on po.name = pri.purchase_order
        where pr.docstatus = 1
          and ifnull(pr.is_return, 0) = 0
          and po.docstatus = 1
          and pri.item_code in %(item_codes)s
          and pri.purchase_order is not null
          and pri.purchase_order != ''
        order by pr.posting_date desc, pr.name desc
        """,
        {"item_codes": tuple(item_codes)},
        as_dict=True,
    )

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    grouped_item_only: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        item_key = (row["item_code"], row.get("supplier") or "")
        grouped[item_key].append(row)
        grouped_item_only[(row["item_code"], "")].append(row)

    stats: dict[tuple[str, str], LeadTimeStat] = {}
    for key, sample_rows in {**grouped, **grouped_item_only}.items():
        lead_days = [flt(r.get("lead_time_days") or 0) for r in sample_rows]
        on_time_hits = 0
        eligible_rows = 0
        for sample in sample_rows:
            if sample.get("schedule_date"):
                eligible_rows += 1
                if getdate(sample["posting_date"]) <= getdate(sample["schedule_date"]):
                    on_time_hits += 1
        stats[key] = LeadTimeStat(
            average_days=(sum(lead_days) / len(lead_days)) if lead_days else 0,
            minimum_days=min(lead_days) if lead_days else 0,
            maximum_days=max(lead_days) if lead_days else 0,
            last_three=lead_days[:3],
            on_time_percentage=((on_time_hits / eligible_rows) * 100) if eligible_rows else 0,
            sample_count=len(sample_rows),
        )
    return stats


def resolve_lead_time_stats(item_code: str, supplier: str | None, lead_time_data: dict[tuple[str, str], LeadTimeStat]) -> dict[str, object]:
    supplier = (supplier or "").strip()
    if supplier and (item_code, supplier) in lead_time_data:
        return lead_time_data[(item_code, supplier)].as_dict()
    if (item_code, "") in lead_time_data:
        return lead_time_data[(item_code, "")].as_dict()
    return LeadTimeStat().as_dict()


def build_dashboard_row(
    item: dict[str, object],
    parameter: dict[str, object],
    supplier_profile: dict[str, object],
    lead_stats: dict[str, object],
    projection_qty: float,
    month_days: int,
    current_stock: float,
    open_po_qty: float,
    reorder_defaults: dict[str, float],
    planning_date: date,
) -> dict[str, object]:
    season = ((parameter.get("current_season") or "Normal").strip().title()) or "Normal"
    normal_daily = round((projection_qty / month_days), 3) if projection_qty > 0 and month_days else 0
    low_daily = flt(parameter.get("daily_avg_consumption_low") or 0)
    peak_daily = flt(parameter.get("daily_avg_consumption_peak") or 0)
    selected_daily = {
        "Low": low_daily,
        "Peak": peak_daily,
        "Normal": normal_daily,
    }.get(season, normal_daily)

    manual_lead = flt(parameter.get("manual_lead_time_days") or 0)
    lead_time = flt(lead_stats.get("average_days") or 0) or manual_lead or flt(item.get("lead_time_days") or 0)
    safety_days = flt(parameter.get("safety_days") or 0)
    review_period_days = flt(parameter.get("review_period_days") or 0)
    safety_stock = round(selected_daily * safety_days, 3)
    reorder_level = round((selected_daily * lead_time) + safety_stock, 3)
    maximum_level = round(reorder_level + (selected_daily * review_period_days), 3)
    projected_available_qty = round(current_stock + open_po_qty, 3)
    production_requirement = round(projection_qty, 3)
    coverage_days = round(projected_available_qty / selected_daily, 2) if selected_daily > 0 else None

    suggested_order_qty = max(
        0,
        maximum_level + production_requirement - current_stock - open_po_qty,
    )
    suggested_order_qty = round_order_qty(
        suggested_order_qty,
        minimum_order_qty=flt(parameter.get("minimum_order_qty") or reorder_defaults.get("reorder_qty") or 0),
        purchase_pack_size=flt(parameter.get("purchase_pack_size") or 0),
    )

    inventory_health = classify_inventory_health(
        coverage_days=coverage_days,
        lead_time_days=lead_time,
        safety_days=safety_days,
        projected_available_qty=projected_available_qty,
        maximum_level=maximum_level,
    )
    required_by_date = get_required_by_date(planning_date, lead_time, inventory_health)

    issues = []
    if projection_qty <= 0:
        issues.append("Projection Missing")
    if not supplier_profile.get("supplier"):
        issues.append("Supplier Missing")
    if not supplier_profile.get("supplier_type"):
        issues.append("Supplier Type Missing")
    if not supplier_profile.get("payment_terms"):
        issues.append("Payment Terms Missing")

    return {
        "item_code": item["item_code"],
        "category": item.get("category") or "",
        "item_name": item.get("item_name") or "",
        "daily_avg_consumption_low": round(low_daily, 3),
        "daily_avg_consumption_normal": round(normal_daily, 3),
        "daily_avg_consumption_peak": round(peak_daily, 3),
        "current_season": season,
        "selected_daily_consumption": round(selected_daily, 3),
        "lead_time_days": round(lead_time, 2),
        "safety_days": round(safety_days, 2),
        "safety_stock": round(safety_stock, 3),
        "reorder_level": round(reorder_level, 3),
        "maximum_level": round(maximum_level, 3),
        "current_rm_store_stock": round(current_stock, 3),
        "open_po_in_transit_qty": round(open_po_qty, 3),
        "projected_available_qty": round(projected_available_qty, 3),
        "production_requirement": round(production_requirement, 3),
        "coverage_days": coverage_days,
        "inventory_health": inventory_health,
        "inventory_health_color": HEALTH_META[inventory_health]["color"],
        "suggested_order_qty": round(suggested_order_qty, 3),
        "required_by_date": str(required_by_date),
        "warehouse": RM_STORE_WAREHOUSE,
        "projection_missing": projection_qty <= 0,
        "issues": issues,
        "preferred_supplier": supplier_profile.get("supplier") or "",
        "supplier_type": supplier_profile.get("supplier_type") or "",
        "approval_status": supplier_profile.get("approval_status") or "",
        "payment_terms": supplier_profile.get("payment_terms") or "",
        "supplier_rating": flt(supplier_profile.get("supplier_rating") or 0),
        "lead_time_stats": lead_stats,
        "planning_parameter": parameter.get("name") or "",
        "item_route": get_doc_route("Item", item["item_code"]),
        "stock_ledger_route": get_list_route("Stock Ledger Entry"),
        "open_po_route": get_list_route("Purchase Order"),
        "planning_parameter_route": get_doc_route("RM Planning Parameter", parameter["name"]) if parameter.get("name") else "",
    }


def dashboard_row_matches_filters(row: dict[str, object], filters: dict[str, object]) -> bool:
    if filters.get("item_code") and row.get("item_code") != filters["item_code"]:
        return False
    if filters.get("inventory_health") and row["inventory_health"] != filters["inventory_health"]:
        return False
    if filters.get("supplier") and row.get("preferred_supplier") != filters["supplier"]:
        return False
    if filters.get("supplier_type") and row.get("supplier_type") != filters["supplier_type"]:
        return False
    if filters.get("current_season") and row.get("current_season") != filters["current_season"]:
        return False
    if filters.get("only_items_requiring_purchase") and flt(row.get("suggested_order_qty") or 0) <= 0:
        return False
    if filters.get("only_critical_items") and row.get("inventory_health") != "Critical":
        return False
    return True


def classify_inventory_health(
    coverage_days: float | None,
    lead_time_days: float,
    safety_days: float,
    projected_available_qty: float,
    maximum_level: float,
) -> str:
    if maximum_level > 0 and projected_available_qty >= maximum_level:
        return "Overstock"

    if coverage_days is not None and coverage_days < lead_time_days:
        return "Critical"

    if maximum_level > 0:
        projected_ratio = projected_available_qty / maximum_level
        if projected_ratio <= 0.33:
            return "Critical"
        if 0.33 < projected_ratio <= 0.66:
            return "Low"
        if 0.66 < projected_ratio <= 0.99:
            return "Healthy"

    if coverage_days is not None and lead_time_days <= coverage_days < (lead_time_days + safety_days):
        return "Low"

    return "Healthy"


def round_order_qty(qty: float, minimum_order_qty: float, purchase_pack_size: float) -> float:
    qty = flt(qty or 0)
    if qty <= 0:
        return 0
    if purchase_pack_size > 0:
        qty = math.ceil(qty / purchase_pack_size) * purchase_pack_size
    if minimum_order_qty > 0 and qty < minimum_order_qty:
        qty = minimum_order_qty
    return round(qty, 3)


def get_required_by_date(planning_date: date, lead_time_days: float, inventory_health: str) -> date:
    if inventory_health == "Critical":
        return getdate(add_days(planning_date, 2))
    return getdate(add_days(planning_date, max(0, int(math.ceil(lead_time_days or 0)))))


def build_lead_time_analytics(rows: list[dict[str, object]], lead_time_data: dict[tuple[str, str], LeadTimeStat]) -> list[dict[str, object]]:
    analytics = []
    seen = set()
    for row in rows:
        supplier = row.get("preferred_supplier") or ""
        if not supplier:
            continue
        key = (supplier, row["item_code"])
        if key in seen:
            continue
        seen.add(key)
        stat = lead_time_data.get((row["item_code"], supplier))
        if not stat:
            stat = lead_time_data.get((row["item_code"], ""))
        analytics.append(
            {
                "supplier": supplier,
                "item_code": row["item_code"],
                "average_lead_time": round((stat.average_days if stat else 0), 2),
                "min_lead_time": round((stat.minimum_days if stat else 0), 2),
                "max_lead_time": round((stat.maximum_days if stat else 0), 2),
                "last_three_receipts": [round(value, 2) for value in (stat.last_three if stat else [])],
                "on_time_percentage": round((stat.on_time_percentage if stat else 0), 2),
                "supplier_type": row.get("supplier_type") or "",
            }
        )
    analytics.sort(key=lambda row: (row["supplier"], row["item_code"]))
    return analytics


def build_dashboard_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    total_items = len(rows)
    critical = sum(1 for row in rows if row["inventory_health"] == "Critical")
    low = sum(1 for row in rows if row["inventory_health"] == "Low")
    healthy = sum(1 for row in rows if row["inventory_health"] == "Healthy")
    overstock = sum(1 for row in rows if row["inventory_health"] == "Overstock")
    requiring_purchase = sum(1 for row in rows if flt(row.get("suggested_order_qty") or 0) > 0)
    return [
        {"label": "RM Items", "value": total_items, "suffix": ""},
        {"label": "Critical", "value": critical, "suffix": ""},
        {"label": "Requiring Purchase", "value": requiring_purchase, "suffix": ""},
        {"label": "Healthy", "value": healthy + overstock, "suffix": ""},
        {"label": "Low", "value": low, "suffix": ""},
    ]
