from __future__ import annotations

from frappe.utils import getdate


def build_common_conditions(filters: dict | None) -> tuple[str, dict[str, object]]:
    filters = filters or {}
    conditions = ["pce.docstatus = 1"]
    params: dict[str, object] = {}

    if filters.get("from_date"):
        params["from_date"] = getdate(filters["from_date"])
        conditions.append("date(pce.posting_datetime) >= %(from_date)s")
    if filters.get("to_date"):
        params["to_date"] = getdate(filters["to_date"])
        conditions.append("date(pce.posting_datetime) <= %(to_date)s")
    if filters.get("warehouse"):
        params["warehouse"] = filters["warehouse"]
        conditions.append("pce.warehouse = %(warehouse)s")
    if filters.get("rm_code"):
        params["rm_code"] = filters["rm_code"]
        conditions.append("item.rm_code = %(rm_code)s")
    if filters.get("fg_code"):
        params["fg_code"] = filters["fg_code"]
        conditions.append("pce.fg_code = %(fg_code)s")
    if filters.get("fg_batch_no"):
        params["fg_batch_no"] = filters["fg_batch_no"]
        conditions.append("pce.fg_batch_no = %(fg_batch_no)s")
    if filters.get("production_line"):
        params["production_line"] = filters["production_line"]
        conditions.append("pce.production_line = %(production_line)s")
    if filters.get("category"):
        params["category"] = filters["category"]
        conditions.append("item.category = %(category)s")

    return " and ".join(conditions), params