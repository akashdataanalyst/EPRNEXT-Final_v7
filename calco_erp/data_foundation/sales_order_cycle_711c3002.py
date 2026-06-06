from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import frappe
from frappe.utils import add_days, flt, now_datetime, nowtime, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_work_order_stock_entry
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from erpnext.stock.utils import get_stock_balance

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    FG_WAREHOUSE,
    RM_WAREHOUSE,
    STANDARD_SELLING,
    SUPPLIER,
    WIP_WAREHOUSE,
    create_quality_inspection,
    ensure_batch,
    verify_master_data,
)
from calco_erp.machine_setup import MACHINE_FIELD, OPERATOR_FIELD, SHIFT_FIELD


ITEM_CODE = "711C3002E"
ORDER_QTY = 10000.0
CUSTOMER = "Test Manufacturing Customer"
TEST_MACHINE = "Line 1"
TEST_SHIFT = "A Shift"
TEST_OPERATOR_NAME = "Test Extruder Operator"
TEST_OPERATOR_CODE = "EMP-CALCO-OP-001"


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


def ensure_operator_employee() -> str:
    existing = frappe.db.get_value(
        "Employee",
        {"employee_name": TEST_OPERATOR_NAME},
        "name",
    )
    if existing:
        return existing

    employee = frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "Test",
            "last_name": "Operator",
            "employee_name": TEST_OPERATOR_NAME,
            "company": COMPANY,
            "status": "Active",
            "date_of_joining": today(),
            "date_of_birth": "1990-01-01",
            "gender": "Male",
            "department": "Production - CPPL",
            "designation": "Extruder Operator",
        }
    )
    employee.insert(ignore_permissions=True)
    return employee.name


def get_fg_bom(item_code: str) -> tuple[str, list[dict[str, float]]]:
    bom_name = frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "docstatus": 1}, "name")
    if not bom_name:
        frappe.throw(f"No submitted default BOM found for {item_code}.")

    items = frappe.get_all("BOM Item", filters={"parent": bom_name}, fields=["item_code", "qty"], order_by="idx asc")
    return bom_name, [{"item_code": row["item_code"], "qty": flt(row["qty"])} for row in items]


def build_components_for_qty(item_code: str, qty: float) -> tuple[str, list[dict[str, float]]]:
    bom_name, components_per_100 = get_fg_bom(item_code)
    factor = qty / 100.0
    components = [
        {"item_code": row["item_code"], "qty": round(flt(row["qty"]) * factor, 6)}
        for row in components_per_100
    ]
    return bom_name, components


def get_stock_snapshot(components: list[dict[str, float]]) -> list[dict[str, float]]:
    snapshot = []
    for component in components:
        available_qty = flt(get_stock_balance(component["item_code"], RM_WAREHOUSE))
        snapshot.append(
            {
                "item_code": component["item_code"],
                "required_qty": round(component["qty"], 6),
                "available_qty": round(available_qty, 6),
                "shortage_qty": round(max(component["qty"] - available_qty, 0), 6),
            }
        )
    return snapshot


def ensure_inspection_flags(fg_item: str, components: list[dict[str, float]]) -> None:
    for component in components:
        if frappe.db.exists("Item", component["item_code"]):
            frappe.db.set_value(
                "Item",
                component["item_code"],
                "inspection_required_before_purchase",
                1,
                update_modified=False,
            )

    if frappe.db.exists("Item", fg_item):
        if "inspection_required_before_delivery" in frappe.get_meta("Item").get_valid_columns():
            frappe.db.set_value(
                "Item",
                fg_item,
                "inspection_required_before_delivery",
                1,
                update_modified=False,
            )
        if "inspection_required_before_manufacturing" in frappe.get_meta("Item").get_valid_columns():
            frappe.db.set_value(
                "Item",
                fg_item,
                "inspection_required_before_manufacturing",
                1,
                update_modified=False,
            )


def set_tracking_fields(doc, machine: str, operator: str, shift_type: str):
    if meta_has_field(doc.doctype, MACHINE_FIELD):
        doc.set(MACHINE_FIELD, machine)
    if meta_has_field(doc.doctype, OPERATOR_FIELD):
        doc.set(OPERATOR_FIELD, operator)
    if meta_has_field(doc.doctype, SHIFT_FIELD):
        doc.set(SHIFT_FIELD, shift_type)


def create_sales_order(item_code: str, qty: float, suffix: str) -> tuple[str, str]:
    customer = ensure_customer()
    item_meta = frappe.get_meta("Sales Order Item")
    item_row = {
        "item_code": item_code,
        "item_name": frappe.db.get_value("Item", item_code, "item_name"),
        "qty": qty,
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
            flt(row.qty),
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


def create_rm_qc_and_release(purchase_receipt: str) -> tuple[list[str], list[str], list[str]]:
    inward_docs = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty"],
        limit_page_length=500,
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


def create_production_plan(item_code: str, bom_name: str, sales_order: str, sales_order_item: str, qty: float) -> str:
    item_meta = frappe.get_meta("Production Plan Item")
    item_row = {
        "item_code": item_code,
        "bom_no": bom_name,
        "planned_qty": qty,
        "stock_uom": "Kg",
        "planned_start_date": now_datetime(),
    }
    if item_meta.get_field("sales_order"):
        item_row["sales_order"] = sales_order
    if item_meta.get_field("sales_order_item"):
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
    item_code: str,
    bom_name: str,
    production_plan: str | None,
    sales_order: str,
    sales_order_item: str,
    qty: float,
    machine: str,
    operator: str,
    shift_type: str,
) -> str:
    payload = {
        "doctype": "Work Order",
        "company": COMPANY,
        "production_item": item_code,
        "bom_no": bom_name,
        "qty": qty,
        "planned_start_date": now_datetime(),
        "production_plan": production_plan,
        "fg_warehouse": FG_WAREHOUSE,
        "wip_warehouse": WIP_WAREHOUSE,
        "source_warehouse": RM_WAREHOUSE,
        "skip_transfer": 1,
    }
    work_order_meta = frappe.get_meta("Work Order")
    if production_plan:
        payload["production_plan"] = production_plan
    if work_order_meta.get_field("sales_order"):
        payload["sales_order"] = sales_order
    if work_order_meta.get_field("sales_order_item"):
        payload["sales_order_item"] = sales_order_item

    work_order = frappe.get_doc(payload)
    set_tracking_fields(work_order, machine, operator, shift_type)
    work_order.insert(ignore_permissions=True)
    return work_order.name


def create_readiness_check(work_order: str) -> str:
    readiness = frappe.get_doc(
        {
            "doctype": "Material Readiness Check",
            "work_order": work_order,
            "status": "Ready",
        }
    )
    readiness.insert(ignore_permissions=True)
    readiness.submit()
    return readiness.name


def submit_work_order(work_order: str) -> None:
    frappe.get_doc("Work Order", work_order).submit()


def create_manufacture_stock_entry(
    work_order: str,
    item_code: str,
    qty: float,
    batch_map: dict[str, str],
    fg_batch_suffix: str,
    machine: str,
    operator: str,
    shift_type: str,
) -> tuple[str, str, str, list[dict[str, object]]]:
    fg_batch = ensure_batch(f"FG-{fg_batch_suffix}-{slug(item_code)}", item_code)
    entry = frappe.get_doc(make_work_order_stock_entry(work_order, "Manufacture", qty))
    set_tracking_fields(entry, machine, operator, shift_type)

    consumption_rows: list[dict[str, object]] = []
    for row in entry.items:
        if row.is_finished_item:
            row.batch_no = fg_batch
            row.t_warehouse = FG_WAREHOUSE
            continue

        row.batch_no = batch_map[row.item_code]
        row.s_warehouse = RM_WAREHOUSE
        consumption_rows.append(
            {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "batch_no": row.batch_no,
                "source_warehouse": row.s_warehouse,
            }
        )

    entry.insert(ignore_permissions=True)
    entry.submit()

    batch_record = frappe.db.get_value("Batch Production Record", {"stock_entry": entry.name}, "name")
    if not batch_record:
        frappe.throw(f"Batch Production Record was not created for Stock Entry {entry.name}.")

    return entry.name, fg_batch, batch_record, consumption_rows


def create_final_qc(item_code: str, qty: float, batch_record: str, stock_entry: str, fg_batch: str) -> tuple[str, str, str]:
    qi_name = create_quality_inspection("Stock Entry", stock_entry, item_code, qty, fg_batch, "In Process")
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


def create_delivery_note(item_code: str, qty: float, sales_order: str, sales_order_item: str, fg_batch: str) -> tuple[frappe.model.document.Document, str]:
    item_meta = frappe.get_meta("Delivery Note Item")
    dn_item = {
        "item_code": item_code,
        "item_name": frappe.db.get_value("Item", item_code, "item_name"),
        "qty": qty,
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

    dn_qi = create_quality_inspection("Delivery Note", dn.name, item_code, qty, fg_batch, "Outgoing")
    dn.reload()
    if dn.items and meta_has_field("Delivery Note Item", "quality_inspection"):
        dn.items[0].quality_inspection = dn_qi
        dn.save(ignore_permissions=True)
    return dn, dn_qi


def submit_dispatch_clearance(delivery_note: str, item_code: str, batch_no: str, final_qc_release: str) -> str:
    clearance = frappe.get_doc(
        {
            "doctype": "Dispatch Clearance",
            "delivery_note": delivery_note,
            "item_code": item_code,
            "batch_no": batch_no,
            "final_qc_release": final_qc_release,
            "status": "Cleared",
        }
    )
    clearance.insert(ignore_permissions=True)
    clearance.submit()
    return clearance.name


def create_sales_invoice_from_delivery_note(delivery_note: str) -> str:
    invoice = make_sales_invoice(delivery_note)
    if invoice.get("set_posting_time") is not None:
        invoice.set_posting_time = 1
    invoice.insert(ignore_permissions=True)
    invoice.submit()
    return invoice.name


def get_stock_ledger_entries(voucher_type: str, voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no},
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
        order_by="creation asc",
        limit_page_length=500,
    )


def compare_requirement_vs_consumption(
    required_components: list[dict[str, float]],
    actual_consumption: list[dict[str, object]],
) -> list[dict[str, object]]:
    actual_map = defaultdict(float)
    for row in actual_consumption:
        actual_map[row["item_code"]] += flt(row["qty"])

    comparison = []
    for component in required_components:
        actual_qty = round(actual_map[component["item_code"]], 6)
        required_qty = round(component["qty"], 6)
        comparison.append(
            {
                "item_code": component["item_code"],
                "required_qty": required_qty,
                "actual_qty": actual_qty,
                "variance_qty": round(actual_qty - required_qty, 6),
            }
        )
    return comparison


def build_traceability(stock_entry: str, work_order: str, fg_batch: str, delivery_note: str) -> dict[str, object]:
    stock_entry_doc = frappe.get_doc("Stock Entry", stock_entry)
    rm_batches = []
    fg_rows = []
    for row in stock_entry_doc.items:
        payload = {
            "item_code": row.item_code,
            "qty": flt(row.qty),
            "batch_no": row.batch_no,
            "source_warehouse": row.s_warehouse,
            "target_warehouse": row.t_warehouse,
            "is_finished_item": int(bool(row.is_finished_item)),
        }
        if row.is_finished_item:
            fg_rows.append(payload)
        else:
            rm_batches.append(payload)

    return {
        "work_order": work_order,
        "manufacture_stock_entry": stock_entry,
        "delivery_note": delivery_note,
        "rm_batches": rm_batches,
        "fg_batch": fg_batch,
        "fg_rows": fg_rows,
    }


def negative_dispatch_without_final_qc(item_code: str, qty: float, bom_name: str, components: list[dict[str, float]], machine: str, operator: str, shift_type: str) -> dict[str, object]:
    savepoint = f"neg_dispatch_without_final_qc_{slug(item_code).lower()}"
    frappe.db.savepoint(savepoint)
    try:
        suffix = unique_suffix(f"neg-dn-{item_code}")
        sales_order, sales_order_item = create_sales_order(item_code, qty, suffix)
        purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
        create_rm_qc_and_release(purchase_receipt)
        production_plan = create_production_plan(item_code, bom_name, sales_order, sales_order_item, qty)
        work_order = create_work_order(item_code, bom_name, production_plan, sales_order, sales_order_item, qty, machine, operator, shift_type)
        create_readiness_check(work_order)
        submit_work_order(work_order)
        _, fg_batch, _, _ = create_manufacture_stock_entry(work_order, item_code, qty, batch_map, suffix, machine, operator, shift_type)
        dn, _ = create_delivery_note(item_code, qty, sales_order, sales_order_item, fg_batch)
        dn.submit()
        return {"passed": False, "message": "Delivery Note submitted unexpectedly without final QC release.", "delivery_note": dn.name}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        return {"passed": True, "message": str(exc)}


def negative_manufacture_without_released_rm(item_code: str, qty: float, bom_name: str, components: list[dict[str, float]], machine: str, operator: str, shift_type: str) -> dict[str, object]:
    savepoint = f"neg_mfg_without_release_{slug(item_code).lower()}"
    frappe.db.savepoint(savepoint)
    try:
        suffix = unique_suffix(f"neg-rm-{item_code}")
        sales_order, sales_order_item = create_sales_order(item_code, qty, suffix)
        purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
        inward_docs = frappe.get_all(
            "RM Inward Validation",
            filters={"purchase_receipt": purchase_receipt},
            fields=["name", "item_code", "batch_no", "received_qty"],
            limit_page_length=500,
        )
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

        production_plan = create_production_plan(item_code, bom_name, sales_order, sales_order_item, qty)
        work_order = create_work_order(item_code, bom_name, production_plan, sales_order, sales_order_item, qty, machine, operator, shift_type)
        readiness = frappe.get_doc(
            {
                "doctype": "Material Readiness Check",
                "work_order": work_order,
                "status": "Ready",
            }
        )
        readiness.insert(ignore_permissions=True)
        readiness.submit()
        submit_work_order(work_order)
        create_manufacture_stock_entry(work_order, item_code, qty, batch_map, suffix, machine, operator, shift_type)
        return {"passed": False, "message": "Manufacture submitted unexpectedly without released RM."}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        return {"passed": True, "message": str(exc)}


def negative_work_order_without_bom(item_code: str) -> dict[str, object]:
    savepoint = f"neg_work_order_without_bom_{slug(item_code).lower()}"
    frappe.db.savepoint(savepoint)
    try:
        work_order = frappe.get_doc(
            {
                "doctype": "Work Order",
                "company": COMPANY,
                "production_item": item_code,
                "qty": 100.0,
                "planned_start_date": now_datetime(),
                "fg_warehouse": FG_WAREHOUSE,
                "wip_warehouse": WIP_WAREHOUSE,
                "source_warehouse": RM_WAREHOUSE,
            }
        )
        work_order.insert(ignore_permissions=True)
        submit_work_order(work_order.name)
        return {"passed": False, "message": "Work Order submitted unexpectedly without BOM.", "work_order": work_order.name}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        return {"passed": True, "message": str(exc)}


def negative_readiness_without_rm_release(item_code: str, qty: float, bom_name: str, sales_order: str, sales_order_item: str, machine: str, operator: str, shift_type: str) -> dict[str, object]:
    savepoint = f"neg_readiness_without_release_{slug(item_code).lower()}"
    frappe.db.savepoint(savepoint)
    try:
        work_order = create_work_order(item_code, bom_name, None, sales_order, sales_order_item, qty, machine, operator, shift_type)
        create_readiness_check(work_order)
        return {"passed": False, "message": "Material Readiness Check became Ready unexpectedly without RM release."}
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        return {"passed": True, "message": str(exc)}


def execute() -> dict[str, object]:
    verification = verify_master_data()
    suffix = unique_suffix(f"so-{ITEM_CODE}")
    operator = ensure_operator_employee()
    bom_name, required_components = build_components_for_qty(ITEM_CODE, ORDER_QTY)
    ensure_inspection_flags(ITEM_CODE, required_components)
    stock_before = get_stock_snapshot(required_components)

    sales_order, sales_order_item = create_sales_order(ITEM_CODE, ORDER_QTY, suffix)
    purchase_receipt, batch_map = create_purchase_receipt(required_components, suffix)
    inward_docs, qc_docs, release_docs = create_rm_qc_and_release(purchase_receipt)
    production_plan = create_production_plan(ITEM_CODE, bom_name, sales_order, sales_order_item, ORDER_QTY)
    work_order = create_work_order(
        ITEM_CODE,
        bom_name,
        production_plan,
        sales_order,
        sales_order_item,
        ORDER_QTY,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    readiness = create_readiness_check(work_order)
    submit_work_order(work_order)
    manufacture_stock_entry, fg_batch, batch_record, actual_consumption = create_manufacture_stock_entry(
        work_order,
        ITEM_CODE,
        ORDER_QTY,
        batch_map,
        suffix,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    quality_inspection, final_qc_release, coa_record = create_final_qc(
        ITEM_CODE,
        ORDER_QTY,
        batch_record,
        manufacture_stock_entry,
        fg_batch,
    )
    delivery_note_doc, dispatch_quality_inspection = create_delivery_note(
        ITEM_CODE,
        ORDER_QTY,
        sales_order,
        sales_order_item,
        fg_batch,
    )
    dispatch_clearance = submit_dispatch_clearance(delivery_note_doc.name, ITEM_CODE, fg_batch, final_qc_release)
    delivery_note_doc.submit()
    sales_invoice = create_sales_invoice_from_delivery_note(delivery_note_doc.name)

    expected_vs_actual = compare_requirement_vs_consumption(required_components, actual_consumption)
    traceability = build_traceability(manufacture_stock_entry, work_order, fg_batch, delivery_note_doc.name)

    negatives = {
        "dispatch_without_final_qc_release": negative_dispatch_without_final_qc(
            ITEM_CODE,
            100.0,
            bom_name,
            [{"item_code": row["item_code"], "qty": round(row["qty"] / 100, 6)} for row in required_components],
            TEST_MACHINE,
            operator,
            TEST_SHIFT,
        ),
        "manufacture_without_released_rm": negative_manufacture_without_released_rm(
            ITEM_CODE,
            100.0,
            bom_name,
            [{"item_code": row["item_code"], "qty": round(row["qty"] / 100, 6)} for row in required_components],
            TEST_MACHINE,
            operator,
            TEST_SHIFT,
        ),
        "work_order_without_bom": negative_work_order_without_bom(ITEM_CODE),
        "material_readiness_without_rm_release": negative_readiness_without_rm_release(
            ITEM_CODE,
            20000.0,
            bom_name,
            sales_order,
            sales_order_item,
            TEST_MACHINE,
            operator,
            TEST_SHIFT,
        ),
    }

    result = {
        "pass_fail": {
            "sales_order": "PASS",
            "production_plan": "PASS",
            "work_order": "PASS",
            "rm_inward_qc_release": "PASS",
            "manufacture": "PASS",
            "final_qc": "PASS",
            "dispatch": "PASS",
            "sales_invoice": "PASS",
            "negative_dispatch_without_final_qc_release": "PASS" if negatives["dispatch_without_final_qc_release"]["passed"] else "FAIL",
            "negative_manufacture_without_released_rm": "PASS" if negatives["manufacture_without_released_rm"]["passed"] else "FAIL",
            "negative_work_order_without_bom": "PASS" if negatives["work_order_without_bom"]["passed"] else "FAIL",
            "negative_material_readiness_without_rm_release": "PASS" if negatives["material_readiness_without_rm_release"]["passed"] else "FAIL",
        },
        "master_data_verification": verification,
        "test_case": {
            "item_code": ITEM_CODE,
            "qty": ORDER_QTY,
            "customer": ensure_customer(),
            "supplier": ensure_supplier(),
            "operator": operator,
            "machine": TEST_MACHINE,
            "shift_type": TEST_SHIFT,
            "bom_used": bom_name,
            "sales_order": sales_order,
            "production_plan": production_plan,
            "work_order": work_order,
            "material_readiness_check": readiness,
            "purchase_receipt": purchase_receipt,
            "rm_inward_validations": inward_docs,
            "rm_qc_decisions": qc_docs,
            "rm_release_notes": release_docs,
            "rm_requirement": required_components,
            "stock_availability_before": stock_before,
            "actual_rm_consumption": actual_consumption,
            "expected_vs_actual_consumption": expected_vs_actual,
            "rm_batches_used": batch_map,
            "manufacture_stock_entry": manufacture_stock_entry,
            "batch_production_record": batch_record,
            "fg_batch": fg_batch,
            "quality_inspection": quality_inspection,
            "final_qc_release": final_qc_release,
            "coa_record": coa_record,
            "delivery_note": delivery_note_doc.name,
            "dispatch_quality_inspection": dispatch_quality_inspection,
            "dispatch_clearance": dispatch_clearance,
            "sales_invoice": sales_invoice,
            "stock_ledger": {
                "purchase_receipt": get_stock_ledger_entries("Purchase Receipt", purchase_receipt),
                "manufacture_stock_entry": get_stock_ledger_entries("Stock Entry", manufacture_stock_entry),
                "delivery_note": get_stock_ledger_entries("Delivery Note", delivery_note_doc.name),
            },
            "traceability": traceability,
        },
        "negative_controls": negatives,
    }

    output_path = verification_dir() / f"sales_order_cycle_{slug(ITEM_CODE).lower()}_result.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
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
