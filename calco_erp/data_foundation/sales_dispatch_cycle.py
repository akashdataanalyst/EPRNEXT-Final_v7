from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import frappe
from frappe.utils import add_days, now_datetime, nowtime, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_work_order_stock_entry

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    CUSTOMER,
    FG_ITEM,
    FG_WAREHOUSE,
    FG_QTY,
    RM_WAREHOUSE,
    STANDARD_SELLING,
    SUPPLIER,
    WIP_WAREHOUSE,
    create_quality_inspection,
    ensure_batch,
    get_fg_bom,
    verify_master_data,
)


def verification_dir() -> Path:
    path = Path(__file__).resolve().parent / "generated" / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def unique_suffix(label: str) -> str:
    stamp = now_datetime().strftime("%Y%m%d%H%M%S")
    return f"{slug(label)}-{stamp}"


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


def meta_has_field(doctype: str, fieldname: str) -> bool:
    return bool(frappe.get_meta(doctype).get_field(fieldname))


def build_components_for_qty(fg_qty: float) -> tuple[str, list[dict[str, float]]]:
    bom_name, components_per_100 = get_fg_bom(FG_ITEM)
    factor = fg_qty / 100.0
    components = [
        {"item_code": row["item_code"], "qty": round(float(row["qty"]) * factor, 6)}
        for row in components_per_100
    ]
    return bom_name, components


def create_sales_order(fg_qty: float, suffix: str) -> tuple[str, str]:
    customer = ensure_customer()
    item_meta = frappe.get_meta("Sales Order Item")
    item_row = {
        "item_code": FG_ITEM,
        "item_name": frappe.db.get_value("Item", FG_ITEM, "item_name"),
        "qty": fg_qty,
        "uom": "Kg",
        "stock_uom": "Kg",
        "conversion_factor": 1,
        "rate": 100,
    }
    if item_meta.get_field("delivery_date"):
        item_row["delivery_date"] = add_days(today(), 2)
    if item_meta.get_field("schedule_date"):
        item_row["schedule_date"] = add_days(today(), 2)

    so = frappe.get_doc(
        {
            "doctype": "Sales Order",
            "customer": customer,
            "transaction_date": today(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "selling_price_list": STANDARD_SELLING,
            "price_list_currency": "INR",
            "plc_conversion_rate": 1,
            "po_no": f"CALCO-SO-{suffix}",
            "items": [item_row],
        }
    )
    so.insert(ignore_permissions=True)
    so.submit()
    return so.name, so.items[0].name


def create_purchase_receipt(components: list[dict[str, float]], suffix: str) -> tuple[str, dict[str, str]]:
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
        batch_id = ensure_batch(f"RM-{suffix}-{slug(component['item_code'])}", component["item_code"])
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

    pr.reload()
    for row in pr.items:
        row.quality_inspection = inspection_map[(row.item_code, row.batch_no)]

    pr.save(ignore_permissions=True)
    pr.submit()
    return pr.name, batch_map


def create_rm_qc_and_release(purchase_receipt: str, release: bool) -> tuple[list[str], list[str], list[str]]:
    inward_docs = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty"],
        limit_page_length=500,
    )

    qc_docs: list[str] = []
    release_docs: list[str] = []
    inward_names = [row["name"] for row in inward_docs]

    for inward in inward_docs:
        qi_name = frappe.db.get_value(
            "Quality Inspection",
            {
                "reference_type": "Purchase Receipt",
                "reference_name": purchase_receipt,
                "item_code": inward["item_code"],
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

        if release:
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

    return inward_names, qc_docs, release_docs


def create_production_plan(bom_name: str, sales_order: str | None, sales_order_item: str | None, fg_qty: float) -> str:
    item_meta = frappe.get_meta("Production Plan Item")
    item_row = {
        "item_code": FG_ITEM,
        "bom_no": bom_name,
        "planned_qty": fg_qty,
        "stock_uom": "Kg",
        "planned_start_date": now_datetime(),
    }
    if sales_order and item_meta.get_field("sales_order"):
        item_row["sales_order"] = sales_order
    if sales_order_item and item_meta.get_field("sales_order_item"):
        item_row["sales_order_item"] = sales_order_item

    plan = frappe.get_doc(
        {
            "doctype": "Production Plan",
            "company": COMPANY,
            "posting_date": today(),
            "po_items": [item_row],
        }
    )
    plan.insert(ignore_permissions=True)
    plan.submit()
    return plan.name


def create_work_order(
    bom_name: str,
    production_plan: str,
    fg_qty: float,
    sales_order: str | None = None,
    sales_order_item: str | None = None,
) -> tuple[str, str]:
    payload = {
        "doctype": "Work Order",
        "company": COMPANY,
        "production_item": FG_ITEM,
        "bom_no": bom_name,
        "qty": fg_qty,
        "planned_start_date": now_datetime(),
        "production_plan": production_plan,
        "fg_warehouse": FG_WAREHOUSE,
        "wip_warehouse": WIP_WAREHOUSE,
        "source_warehouse": RM_WAREHOUSE,
        "skip_transfer": 1,
    }
    work_order_meta = frappe.get_meta("Work Order")
    if sales_order and work_order_meta.get_field("sales_order"):
        payload["sales_order"] = sales_order
    if sales_order_item and work_order_meta.get_field("sales_order_item"):
        payload["sales_order_item"] = sales_order_item

    work_order = frappe.get_doc(payload)
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


def create_manufacture_stock_entry(work_order: str, fg_qty: float, batch_map: dict[str, str], fg_batch_suffix: str) -> tuple[str, str, str]:
    fg_batch = ensure_batch(f"FG-{fg_batch_suffix}-{slug(FG_ITEM)}", FG_ITEM)
    entry = frappe.get_doc(make_work_order_stock_entry(work_order, "Manufacture", fg_qty))

    for row in entry.items:
        if row.is_finished_item:
            row.batch_no = fg_batch
            row.t_warehouse = FG_WAREHOUSE
        else:
            row.batch_no = batch_map[row.item_code]
            row.s_warehouse = RM_WAREHOUSE

    entry.insert(ignore_permissions=True)
    entry.submit()

    batch_record = frappe.db.get_value("Batch Production Record", {"stock_entry": entry.name}, "name")
    if not batch_record:
        frappe.throw(f"Batch Production Record was not created for Stock Entry {entry.name}.")

    return entry.name, fg_batch, batch_record


def create_final_qc(batch_record: str, stock_entry: str, fg_batch: str) -> tuple[str, str, str]:
    qi_name = create_quality_inspection("Stock Entry", stock_entry, FG_ITEM, FG_QTY, fg_batch, "In Process")
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
    release.reload()
    return qi_name, release.name, release.coa_record


def create_delivery_note(sales_order: str, sales_order_item: str, fg_qty: float, fg_batch: str) -> tuple[frappe.model.document.Document, str]:
    item_meta = frappe.get_meta("Delivery Note Item")
    dn_item = {
        "item_code": FG_ITEM,
        "item_name": frappe.db.get_value("Item", FG_ITEM, "item_name"),
        "qty": fg_qty,
        "uom": "Kg",
        "stock_uom": "Kg",
        "conversion_factor": 1,
        "warehouse": FG_WAREHOUSE,
        "batch_no": fg_batch,
        "rate": 100,
    }
    if item_meta.get_field("against_sales_order"):
        dn_item["against_sales_order"] = sales_order
    if item_meta.get_field("so_detail"):
        dn_item["so_detail"] = sales_order_item

    dn = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "customer": ensure_customer(),
            "posting_date": today(),
            "posting_time": nowtime(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "selling_price_list": STANDARD_SELLING,
            "price_list_currency": "INR",
            "plc_conversion_rate": 1,
            "items": [dn_item],
        }
    )
    dn.insert(ignore_permissions=True)

    dn_qi = create_quality_inspection("Delivery Note", dn.name, FG_ITEM, fg_qty, fg_batch, "Outgoing")
    dn.reload()
    if dn.items and meta_has_field("Delivery Note Item", "quality_inspection"):
        dn.items[0].quality_inspection = dn_qi
        dn.save(ignore_permissions=True)

    return dn, dn_qi


def submit_dispatch_clearance(delivery_note: str, final_qc_release: str) -> str:
    clearance = frappe.get_doc(
        {
            "doctype": "Dispatch Clearance",
            "delivery_note": delivery_note,
            "final_qc_release": final_qc_release,
            "status": "Cleared",
        }
    )
    clearance.insert(ignore_permissions=True)
    clearance.submit()
    return clearance.name


def build_traceability(stock_entry: str, fg_batch: str, sales_order: str, delivery_note: str) -> dict[str, object]:
    stock_entry_doc = frappe.get_doc("Stock Entry", stock_entry)
    consumption = []
    production = []
    for row in stock_entry_doc.items:
        entry = {
            "item_code": row.item_code,
            "qty": float(row.qty or 0),
            "batch_no": row.batch_no,
            "source_warehouse": row.s_warehouse,
            "target_warehouse": row.t_warehouse,
            "is_finished_item": int(bool(row.is_finished_item)),
        }
        if row.is_finished_item:
            production.append(entry)
        else:
            consumption.append(entry)

    return {
        "sales_order": sales_order,
        "manufacture_stock_entry": stock_entry,
        "delivery_note": delivery_note,
        "rm_batch_consumption": consumption,
        "fg_batch_produced": production,
        "fg_batch_dispatched": {
            "item_code": FG_ITEM,
            "batch_no": fg_batch,
            "warehouse": FG_WAREHOUSE,
        },
    }


def run_positive_cycle() -> dict[str, object]:
    suffix = unique_suffix("sales-cycle")
    bom_name, components = build_components_for_qty(FG_QTY)
    sales_order, sales_order_item = create_sales_order(FG_QTY, suffix)
    purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
    inward_docs, qc_docs, release_docs = create_rm_qc_and_release(purchase_receipt, release=True)
    production_plan = create_production_plan(bom_name, sales_order, sales_order_item, FG_QTY)
    work_order, readiness = create_work_order(bom_name, production_plan, FG_QTY, sales_order, sales_order_item)
    stock_entry, fg_batch, batch_record = create_manufacture_stock_entry(work_order, FG_QTY, batch_map, suffix)
    quality_inspection, final_qc_release, coa_record = create_final_qc(batch_record, stock_entry, fg_batch)
    delivery_note_doc, dispatch_qi = create_delivery_note(sales_order, sales_order_item, FG_QTY, fg_batch)
    dispatch_clearance = submit_dispatch_clearance(delivery_note_doc.name, final_qc_release)
    delivery_note_doc.submit()
    coa_attachments = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Delivery Note",
            "attached_to_name": delivery_note_doc.name,
            "file_name": ("like", "COA-%"),
        },
        fields=["name", "file_name", "file_url"],
        limit_page_length=100,
    )

    return {
        "sales_order": sales_order,
        "sales_order_item": sales_order_item,
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
        "final_quality_inspection": quality_inspection,
        "final_qc_release": final_qc_release,
        "coa_record": coa_record,
        "delivery_note": delivery_note_doc.name,
        "dispatch_quality_inspection": dispatch_qi,
        "dispatch_clearance": dispatch_clearance,
        "coa_attachments": coa_attachments,
        "traceability": build_traceability(stock_entry, fg_batch, sales_order, delivery_note_doc.name),
    }


def negative_dispatch_without_final_qc() -> dict[str, object]:
    savepoint = "neg_dispatch_without_final_qc"
    frappe.db.savepoint(savepoint)
    try:
        suffix = unique_suffix("neg-dn")
        fg_qty = 100.0
        bom_name, components = build_components_for_qty(fg_qty)
        sales_order, sales_order_item = create_sales_order(fg_qty, suffix)
        purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
        create_rm_qc_and_release(purchase_receipt, release=True)
        production_plan = create_production_plan(bom_name, sales_order, sales_order_item, fg_qty)
        work_order, _ = create_work_order(bom_name, production_plan, fg_qty, sales_order, sales_order_item)
        stock_entry, fg_batch, _ = create_manufacture_stock_entry(work_order, fg_qty, batch_map, suffix)
        dn, _ = create_delivery_note(sales_order, sales_order_item, fg_qty, fg_batch)
        dn.submit()
        result = {"passed": False, "message": "Delivery Note submitted unexpectedly without final QC release.", "delivery_note": dn.name}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        result = {"passed": True, "message": str(exc)}
    return result


def negative_manufacture_without_released_rm() -> dict[str, object]:
    savepoint = "neg_mfg_without_release"
    frappe.db.savepoint(savepoint)
    try:
        suffix = unique_suffix("neg-rm")
        fg_qty = 100.0
        bom_name, components = build_components_for_qty(fg_qty)
        purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
        create_rm_qc_and_release(purchase_receipt, release=False)
        production_plan = create_production_plan(bom_name, None, None, fg_qty)
        work_order, _ = create_work_order(bom_name, production_plan, fg_qty)
        create_manufacture_stock_entry(work_order, fg_qty, batch_map, suffix)
        result = {"passed": False, "message": "Manufacture Stock Entry submitted unexpectedly without RM release."}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        result = {"passed": True, "message": str(exc)}
    return result


def negative_work_order_without_bom() -> dict[str, object]:
    savepoint = "neg_work_order_without_bom"
    frappe.db.savepoint(savepoint)
    try:
        work_order = frappe.get_doc(
            {
                "doctype": "Work Order",
                "company": COMPANY,
                "production_item": FG_ITEM,
                "qty": 100.0,
                "planned_start_date": now_datetime(),
                "fg_warehouse": FG_WAREHOUSE,
                "wip_warehouse": WIP_WAREHOUSE,
                "source_warehouse": RM_WAREHOUSE,
            }
        )
        work_order.insert(ignore_permissions=True)
        work_order.submit()
        result = {"passed": False, "message": "Work Order submitted unexpectedly without BOM."}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        result = {"passed": True, "message": str(exc)}
    return result


def execute() -> dict[str, object]:
    verification = verify_master_data()
    cycle = run_positive_cycle()
    negatives = {
        "dispatch_without_final_qc_release": negative_dispatch_without_final_qc(),
        "manufacture_without_released_rm": negative_manufacture_without_released_rm(),
        "work_order_without_bom": negative_work_order_without_bom(),
    }

    result = {
        "bom_integrity": {
            "bom_quantity_mismatches": verification["bom_quantity_mismatches"],
            "status": "Clean" if verification["bom_quantity_mismatches"] == 0 else "Exception",
        },
        "cycle": cycle,
        "negative_controls": negatives,
    }
    (verification_dir() / "sales_dispatch_cycle_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    frappe.db.commit()
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    frappe.init(site="frontend", sites_path="/home/frappe/frappe-bench/sites")
    frappe.connect()
    try:
        execute()
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
