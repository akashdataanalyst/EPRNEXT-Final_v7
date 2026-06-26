from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import frappe
from frappe.utils import add_days, now_datetime, nowtime, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_work_order_stock_entry


SITE = "frontend"
SITES_PATH = "/home/frappe/frappe-bench/sites"
COMPANY = "Calco PolyTechnik Pvt Ltd"
SUPPLIER = "Test RM Supplier"
CUSTOMER = "Test Manufacturing Customer"
FG_ITEM = "710C3031"
FG_QTY = 1000.0
RM_WAREHOUSE = "Stores - CPPL"
WIP_WAREHOUSE = "Work In Progress - CPPL"
FG_WAREHOUSE = "Finished Goods - CPPL"
STANDARD_BUYING = "Standard Buying"
STANDARD_SELLING = "Standard Selling"


def generated_dir() -> Path:
    return Path(__file__).resolve().parent / "generated"


def verification_dir() -> Path:
    path = generated_dir() / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv(name: str) -> list[dict[str, str]]:
    with (generated_dir() / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def aggregate_component_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        item_code = str(row.get("item_code") or "").strip()
        if not item_code:
            continue
        totals[item_code] += float(row.get("qty") or 0)
    return dict(totals)


def write_csv(name: str, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with (verification_dir() / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def select_source_bom_headers() -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for row in read_csv("bom_header.csv"):
        item_code = (row.get("item") or "").strip()
        if not item_code:
            continue
        if row.get("is_default") == "1":
            selected[item_code] = row
        elif item_code not in selected:
            selected[item_code] = row
    return selected


def source_component_map() -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv("bom_items.csv"):
        grouped[(row.get("parent") or "").strip()].append(row)
    return grouped


def verify_master_data() -> dict[str, object]:
    fg_rows = read_csv("items_fg.csv")
    rm_rows = read_csv("items_rm.csv")
    source_headers = select_source_bom_headers()
    source_items = source_component_map()

    fg_codes = sorted({(row.get("item_code") or "").strip() for row in fg_rows if (row.get("item_code") or "").strip()})
    rm_codes = sorted({(row.get("item_code") or "").strip() for row in rm_rows if (row.get("item_code") or "").strip()})

    missing_fg_items = [{"item_code": code} for code in fg_codes if not frappe.db.exists("Item", code)]
    missing_rm_items = [{"item_code": code} for code in rm_codes if not frappe.db.exists("Item", code)]

    duplicate_items = [
        {"item_code": row[0], "count": row[1]}
        for row in frappe.db.sql(
            """
            select item_code, count(*) as cnt
            from `tabItem`
            group by item_code
            having count(*) > 1
            """
        )
    ]

    warehouses_required = [
        {"warehouse": RM_WAREHOUSE, "exists": int(bool(frappe.db.exists("Warehouse", RM_WAREHOUSE)))},
        {"warehouse": WIP_WAREHOUSE, "exists": int(bool(frappe.db.exists("Warehouse", WIP_WAREHOUSE)))},
        {"warehouse": FG_WAREHOUSE, "exists": int(bool(frappe.db.exists("Warehouse", FG_WAREHOUSE)))},
    ]

    missing_boms: list[dict[str, object]] = []
    missing_bom_components: list[dict[str, object]] = []
    bom_quantity_mismatches: list[dict[str, object]] = []

    for item_code, header in source_headers.items():
        bom_name = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_default": 1, "docstatus": 1},
            "name",
        )
        if not bom_name:
            missing_boms.append({"item_code": item_code})
            continue

        live_components = aggregate_component_rows(
            frappe.get_all("BOM Item", filters={"parent": bom_name}, fields=["item_code", "qty"], limit_page_length=500)
        )
        expected_rows = source_items.get((header.get("name") or "").strip(), [])
        expected_components = aggregate_component_rows(expected_rows)

        for component, expected_qty in expected_components.items():
            if component not in live_components:
                missing_bom_components.append(
                    {
                        "item_code": item_code,
                        "bom": bom_name,
                        "missing_component": component,
                    }
                )
                continue

            live_qty = live_components[component]
            if abs(live_qty - expected_qty) > 0.0001:
                bom_quantity_mismatches.append(
                    {
                        "item_code": item_code,
                        "bom": bom_name,
                        "component": component,
                        "expected_qty": expected_qty,
                        "live_qty": live_qty,
                    }
                )

        total_live = sum(live_components.values())
        if abs(total_live - 100.0) > 0.01:
            bom_quantity_mismatches.append(
                {
                    "item_code": item_code,
                    "bom": bom_name,
                    "component": "__TOTAL__",
                    "expected_qty": 100.0,
                    "live_qty": round(total_live, 6),
                }
            )

    write_csv("missing_fg_items.csv", missing_fg_items, ["item_code"])
    write_csv("missing_rm_items.csv", missing_rm_items, ["item_code"])
    write_csv("duplicate_item_codes_in_db.csv", duplicate_items, ["item_code", "count"])
    write_csv("warehouse_verification.csv", warehouses_required, ["warehouse", "exists"])
    write_csv("missing_boms.csv", missing_boms, ["item_code"])
    write_csv("missing_bom_components.csv", missing_bom_components, ["item_code", "bom", "missing_component"])
    write_csv(
        "bom_quantity_mismatches.csv",
        bom_quantity_mismatches,
        ["item_code", "bom", "component", "expected_qty", "live_qty"],
    )

    summary = {
        "fg_items_in_source": len(fg_codes),
        "rm_items_in_source": len(rm_codes),
        "missing_fg_items": len(missing_fg_items),
        "missing_rm_items": len(missing_rm_items),
        "duplicate_item_codes_in_db": len(duplicate_items),
        "missing_boms": len(missing_boms),
        "missing_bom_components": len(missing_bom_components),
        "bom_quantity_mismatches": len(bom_quantity_mismatches),
        "warehouses_required": warehouses_required,
    }
    (verification_dir() / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def ensure_customer() -> str:
    if frappe.db.exists("Customer", CUSTOMER):
        return CUSTOMER

    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": CUSTOMER,
            "customer_group": "Commercial",
            "territory": "India",
            "customer_type": "Company",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_supplier() -> str:
    if frappe.db.exists("Supplier", SUPPLIER):
        return SUPPLIER

    doc = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": SUPPLIER,
            "supplier_group": "Raw Material",
            "supplier_type": "Company",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_batch(batch_id: str, item_code: str) -> str:
    if frappe.db.exists("Batch", batch_id):
        return batch_id

    batch = frappe.get_doc(
        {
            "doctype": "Batch",
            "batch_id": batch_id,
            "item": item_code,
        }
    )
    batch.insert(ignore_permissions=True)
    return batch.name


def quality_inspection_payload(reference_type: str, reference_name: str, item_code: str, sample_size: float, batch_no: str | None, inspection_type: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "doctype": "Quality Inspection",
        "report_date": today(),
        "status": "Accepted",
        "inspection_type": inspection_type,
        "reference_type": reference_type,
        "reference_name": reference_name,
        "item_code": item_code,
        "sample_size": sample_size,
        "inspected_by": "Administrator",
    }
    if "batch_no" in frappe.get_meta("Quality Inspection").get_valid_columns() and batch_no:
        payload["batch_no"] = batch_no
    return payload


def create_quality_inspection(reference_type: str, reference_name: str, item_code: str, sample_size: float, batch_no: str | None, inspection_type: str) -> str:
    doc = frappe.get_doc(
        quality_inspection_payload(reference_type, reference_name, item_code, sample_size, batch_no, inspection_type)
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def get_fg_bom(item_code: str) -> tuple[str, list[dict[str, float]]]:
    bom_name = frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "docstatus": 1}, "name")
    if not bom_name:
        frappe.throw(f"No submitted default BOM found for {item_code}.")

    items = frappe.get_all("BOM Item", filters={"parent": bom_name}, fields=["item_code", "qty"], order_by="idx asc")
    return bom_name, [{"item_code": row["item_code"], "qty": float(row["qty"] or 0)} for row in items]


def create_purchase_receipt(components: list[dict[str, float]]) -> tuple[str, dict[str, str]]:
    supplier = ensure_supplier()
    batch_map: dict[str, str] = {}

    pr = frappe.get_doc(
        {
            "doctype": "Purchase Receipt",
            "supplier": supplier,
            "posting_date": today(),
            "posting_time": nowtime(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "items": [],
        }
    )

    for component in components:
        batch_id = ensure_batch(f"RM-{slug(component['item_code'])}-001", component["item_code"])
        batch_map[component["item_code"]] = batch_id
        pr.append(
            "items",
            {
                "item_code": component["item_code"],
                "item_name": frappe.db.get_value("Item", component["item_code"], "item_name"),
                "received_qty": component["qty"],
                "qty": component["qty"],
                "uom": "Kg",
                "stock_uom": "Kg",
                "conversion_factor": 1,
                "rate": 1,
                "base_rate": 1,
                "warehouse": RM_WAREHOUSE,
                "batch_no": batch_id,
            },
        )

    pr.insert(ignore_permissions=True)

    inspection_map: dict[tuple[str, str], str] = {}
    for row in pr.items:
        qi_name = create_quality_inspection(
            "Purchase Receipt",
            pr.name,
            row.item_code,
            float(row.qty or 0),
            row.batch_no,
            "Incoming",
        )
        inspection_map[(row.item_code, row.batch_no)] = qi_name

    pr = frappe.get_doc("Purchase Receipt", pr.name)
    for row in pr.items:
        row.quality_inspection = inspection_map[(row.item_code, row.batch_no)]

    pr.save(ignore_permissions=True)
    pr.submit()
    return pr.name, batch_map


def release_rm_batches(purchase_receipt: str, batch_map: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    inward_docs = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty"],
        limit_page_length=200,
    )

    qc_docs = []
    release_docs = []
    inward_names = [row["name"] for row in inward_docs]

    for inward in inward_docs:
        item_code = inward["item_code"]
        qi_name = frappe.db.get_value(
            "Quality Inspection",
            {
                "reference_type": "Purchase Receipt",
                "reference_name": purchase_receipt,
                "item_code": item_code,
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

        release = frappe.get_doc(
            {
                "doctype": "RM Release Note",
                "rm_qc_decision": decision.name,
                "release_qty": inward["received_qty"],
                "status": "Released",
            }
        )
        release.insert(ignore_permissions=True)
        release.submit()
        release_docs.append(release.name)

    return inward_names, qc_docs, release_docs


def create_production_plan(bom_name: str) -> str:
    planned_start = now_datetime()
    plan = frappe.get_doc(
        {
            "doctype": "Production Plan",
            "company": COMPANY,
            "posting_date": today(),
            "po_items": [
                {
                    "item_code": FG_ITEM,
                    "bom_no": bom_name,
                    "planned_qty": FG_QTY,
                    "stock_uom": "Kg",
                    "planned_start_date": planned_start,
                }
            ],
        }
    )
    plan.insert(ignore_permissions=True)
    plan.submit()
    return plan.name


def create_work_order(bom_name: str, production_plan: str) -> tuple[str, str]:
    work_order = frappe.get_doc(
        {
            "doctype": "Work Order",
            "company": COMPANY,
            "production_item": FG_ITEM,
            "bom_no": bom_name,
            "qty": FG_QTY,
            "planned_start_date": now_datetime(),
            "production_plan": production_plan,
            "fg_warehouse": FG_WAREHOUSE,
            "wip_warehouse": WIP_WAREHOUSE,
            "source_warehouse": RM_WAREHOUSE,
            "skip_transfer": 1,
        }
    )
    work_order.insert(ignore_permissions=True)

    readiness = frappe.get_doc(
        {
            "doctype": "Material Readiness Check",
            "work_order": work_order.name,
            "status": "Ready",
        }
    )
    readiness.insert(ignore_permissions=True)
    readiness.submit()

    work_order.submit()
    return work_order.name, readiness.name


def create_manufacture_stock_entry(work_order: str, components: list[dict[str, float]], batch_map: dict[str, str], production_plan: str) -> tuple[str, str, str]:
    fg_batch = ensure_batch(f"FG-{slug(FG_ITEM)}-001", FG_ITEM)
    entry = frappe.get_doc(make_work_order_stock_entry(work_order, "Manufacture", FG_QTY))

    for row in entry.items:
        if row.is_finished_item:
            row.batch_no = fg_batch
            row.t_warehouse = FG_WAREHOUSE
            continue

        row.batch_no = batch_map[row.item_code]
        row.s_warehouse = RM_WAREHOUSE

    entry.insert(ignore_permissions=True)
    entry.submit()

    batch_record = frappe.db.get_value("Batch Production Record", {"stock_entry": entry.name}, "name")
    if not batch_record:
        frappe.throw(f"Batch Production Record was not created for Stock Entry {entry.name}.")

    if production_plan:
        frappe.db.set_value("Batch Production Record", batch_record, "production_plan", production_plan, update_modified=False)

    return entry.name, fg_batch, batch_record


def create_final_quality(batch_record: str, stock_entry: str, fg_batch: str) -> tuple[str, str]:
    qi_name = create_quality_inspection(
        "Stock Entry",
        stock_entry,
        FG_ITEM,
        FG_QTY,
        fg_batch,
        "In Process",
    )

    release = frappe.get_doc(
        {
            "doctype": "Final QC Release",
            "batch_production_record": batch_record,
            "quality_inspection": qi_name,
            "moisture": 0.15,
            "mfi": 35.0,
            "ash": 30.0,
            "density": 1.35,
            "status": "Released",
        }
    )
    release.insert(ignore_permissions=True)
    release.submit()
    return qi_name, release.name


def create_dispatch(final_qc_release: str, fg_batch: str) -> tuple[str, str, str]:
    customer = ensure_customer()
    dn = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "customer": customer,
            "posting_date": today(),
            "posting_time": nowtime(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "selling_price_list": STANDARD_SELLING,
            "price_list_currency": "INR",
            "plc_conversion_rate": 1,
            "items": [
                {
                    "item_code": FG_ITEM,
                    "item_name": frappe.db.get_value("Item", FG_ITEM, "item_name"),
                    "qty": FG_QTY,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "warehouse": FG_WAREHOUSE,
                    "batch_no": fg_batch,
                    "rate": 100,
                }
            ],
        }
    )
    dn.insert(ignore_permissions=True)

    dn_qi = create_quality_inspection(
        "Delivery Note",
        dn.name,
        FG_ITEM,
        FG_QTY,
        fg_batch,
        "Outgoing",
    )
    dn = frappe.get_doc("Delivery Note", dn.name)
    dn.items[0].quality_inspection = dn_qi
    dn.save(ignore_permissions=True)

    clearance = frappe.get_doc(
        {
            "doctype": "Dispatch Clearance",
            "delivery_note": dn.name,
            "final_qc_release": final_qc_release,
            "status": "Cleared",
        }
    )
    clearance.insert(ignore_permissions=True)
    clearance.submit()

    dn.submit()
    return dn.name, dn_qi, clearance.name


def run_cycle() -> dict[str, object]:
    bom_name, components_per_100 = get_fg_bom(FG_ITEM)
    factor = FG_QTY / 100.0
    components = [
        {
            "item_code": row["item_code"],
            "qty": round(float(row["qty"]) * factor, 3),
        }
        for row in components_per_100
    ]

    purchase_receipt, batch_map = create_purchase_receipt(components)
    inward_docs, qc_docs, release_docs = release_rm_batches(purchase_receipt, batch_map)
    production_plan = create_production_plan(bom_name)
    work_order, readiness = create_work_order(bom_name, production_plan)
    stock_entry, fg_batch, batch_record = create_manufacture_stock_entry(work_order, components, batch_map, production_plan)
    final_qi, final_release = create_final_quality(batch_record, stock_entry, fg_batch)
    delivery_note, dispatch_qi, dispatch_clearance = create_dispatch(final_release, fg_batch)

    result = {
        "test_fg_item": FG_ITEM,
        "fg_qty": FG_QTY,
        "bom_used": bom_name,
        "rm_items_consumed": components,
        "purchase_receipt": purchase_receipt,
        "rm_inward_validations": inward_docs,
        "rm_qc_decisions": qc_docs,
        "rm_release_notes": release_docs,
        "production_plan": production_plan,
        "work_order": work_order,
        "material_readiness_check": readiness,
        "manufacture_stock_entry": stock_entry,
        "batch_production_record": batch_record,
        "fg_batch": fg_batch,
        "quality_inspection": final_qi,
        "final_qc_release": final_release,
        "delivery_note": delivery_note,
        "dispatch_quality_inspection": dispatch_qi,
        "dispatch_clearance": dispatch_clearance,
    }
    (verification_dir() / "test_cycle_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    frappe.db.commit()
    return result


def execute() -> dict[str, object]:
    verification = verify_master_data()
    cycle = run_cycle()
    result = {"verification": verification, "cycle": cycle}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    frappe.init(site=SITE, sites_path=SITES_PATH)
    frappe.connect()
    try:
        execute()
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
