from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, nowtime, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_work_order_stock_entry

from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    FG_WAREHOUSE,
    WIP_WAREHOUSE,
    create_quality_inspection,
    ensure_batch,
)
from calco_erp.data_foundation.sales_dispatch_cycle import ensure_customer
from calco_erp.data_foundation.sales_order_cycle_711c3002 import (
    TEST_MACHINE,
    TEST_SHIFT,
    build_components_for_qty,
    create_final_qc,
    create_manufacture_stock_entry,
    create_purchase_receipt,
    create_readiness_check,
    create_rm_qc_and_release,
    create_work_order,
    ensure_operator_employee,
    ensure_inspection_flags,
    get_fg_bom,
    meta_has_field,
    set_tracking_fields,
    slug,
    submit_work_order,
    unique_suffix,
)


REWORK_WAREHOUSE = "Rework - CPPL"
FAILED_STATUSES = ("Hold", "Rejected")
FAILED_BATCH_ITEM = "710C0031A"
FAILED_BATCH_QTY = 1000.0


def verification_dir() -> Path:
    path = Path(__file__).resolve().parent / "generated" / "verification"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_rework_warehouse() -> str:
    if frappe.db.exists("Warehouse", REWORK_WAREHOUSE):
        return REWORK_WAREHOUSE

    warehouse = frappe.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": "Rework",
            "company": COMPANY,
            "parent_warehouse": "All Warehouses - CPPL",
        }
    )
    warehouse.insert(ignore_permissions=True)
    return warehouse.name


def has_released_final_qc(item_code: str, batch_no: str) -> bool:
    return bool(
        frappe.db.exists(
            "Final QC Release",
            {
                "item_code": item_code,
                "batch_no": batch_no,
                "status": "Released",
                "docstatus": 1,
            },
        )
    )


def get_latest_failed_batch() -> dict[str, object] | None:
    rows = frappe.get_all(
        "Final QC Release",
        filters={"status": ("in", list(FAILED_STATUSES)), "docstatus": 1},
        fields=["name", "item_code", "batch_no", "batch_production_record", "status", "released_on"],
        order_by="creation desc",
        limit_page_length=50,
    )
    for row in rows:
        qty = get_batch_balance(row["item_code"], row["batch_no"], FG_WAREHOUSE)
        if qty > 0 and not has_released_final_qc(row["item_code"], row["batch_no"]):
            row["available_qty"] = qty
            row["source"] = "existing_failed_batch"
            return row
    return None


def get_batch_balance(item_code: str, batch_no: str, warehouse: str) -> float:
    result = frappe.db.sql(
        """
        select coalesce(sum(actual_qty), 0)
        from `tabStock Ledger Entry`
        where is_cancelled = 0
          and item_code = %s
          and batch_no = %s
          and warehouse = %s
        """,
        (item_code, batch_no, warehouse),
    )
    return flt(result[0][0] if result else 0)


def create_failed_batch_for_rework(operator: str) -> dict[str, object]:
    item_code = FAILED_BATCH_ITEM
    qty = FAILED_BATCH_QTY
    suffix = unique_suffix(f"rework-failed-{item_code}")
    bom_name, components = build_components_for_qty(item_code, qty)
    ensure_inspection_flags(item_code, components)

    purchase_receipt, batch_map = create_purchase_receipt(components, suffix)
    inward_docs, qc_docs, release_docs = create_rm_qc_and_release(purchase_receipt)
    work_order = create_work_order(
        item_code,
        bom_name,
        None,
        "",
        "",
        qty,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    readiness = create_readiness_check(work_order)
    submit_work_order(work_order)
    stock_entry, fg_batch, batch_record, _consumption = create_manufacture_stock_entry(
        work_order,
        item_code,
        qty,
        batch_map,
        suffix,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    quality_inspection = create_quality_inspection("Stock Entry", stock_entry, item_code, qty, fg_batch, "In Process")
    final_qc_release = frappe.get_doc(
        {
            "doctype": "Final QC Release",
            "batch_production_record": batch_record,
            "quality_inspection": quality_inspection,
            "status": "Hold",
        }
    )
    final_qc_release.insert(ignore_permissions=True)
    final_qc_release.submit()
    final_qc_release.reload()

    return {
        "source": "manufactured_failed_batch",
        "name": final_qc_release.name,
        "item_code": item_code,
        "batch_no": fg_batch,
        "batch_production_record": batch_record,
        "status": final_qc_release.status,
        "available_qty": qty,
        "created_records": {
            "bom": bom_name,
            "purchase_receipt": purchase_receipt,
            "rm_inward_validations": inward_docs,
            "rm_qc_decisions": qc_docs,
            "rm_release_notes": release_docs,
            "work_order": work_order,
            "material_readiness_check": readiness,
            "manufacture_stock_entry": stock_entry,
            "quality_inspection": quality_inspection,
            "final_qc_release": final_qc_release.name,
        },
    }


def validate_failed_batch_dispatch_block(item_code: str, batch_no: str, qty: float) -> dict[str, object]:
    savepoint = "rework_failed_batch_dispatch_block"
    frappe.db.sql(f"SAVEPOINT {savepoint}")
    blocked = False
    blocked_message = ""
    delivery_note_name = ""

    try:
        dn = frappe.get_doc(
            {
                "doctype": "Delivery Note",
                "customer": ensure_customer(),
                "posting_date": today(),
                "posting_time": nowtime(),
                "company": COMPANY,
                "currency": "INR",
                "conversion_rate": 1,
                "items": [
                    {
                        "item_code": item_code,
                        "item_name": frappe.db.get_value("Item", item_code, "item_name"),
                        "qty": qty,
                        "uom": "Kg",
                        "stock_uom": "Kg",
                        "conversion_factor": 1,
                        "warehouse": FG_WAREHOUSE,
                        "batch_no": batch_no,
                        "rate": 100,
                    }
                ],
            }
        )
        dn.insert(ignore_permissions=True)
        delivery_note_name = dn.name
        outgoing_qi = create_quality_inspection("Delivery Note", dn.name, item_code, qty, batch_no, "Outgoing")
        dn.reload()
        if dn.items and meta_has_field("Delivery Note Item", "quality_inspection"):
            dn.items[0].quality_inspection = outgoing_qi
            dn.save(ignore_permissions=True)
        dn.submit()
    except Exception as exc:
        blocked = True
        blocked_message = str(exc)
    finally:
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    return {
        "blocked": blocked,
        "blocked_message": blocked_message,
        "attempted_delivery_note": delivery_note_name,
    }


def normalize_bundle_rows(stock_entry) -> None:
    for row in stock_entry.items:
        if not row.get("serial_and_batch_bundle"):
            continue

        if getattr(row, "batch_no", None):
            row.batch_no = ""
            row.db_set("batch_no", "", update_modified=False)
        if getattr(row, "serial_no", None):
            row.serial_no = ""
            row.db_set("serial_no", "", update_modified=False)


def move_failed_batch_to_rework(item_code: str, batch_no: str, qty: float) -> str:
    transfer = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "purpose": "Material Transfer",
            "stock_entry_type": "Material Transfer",
            "company": COMPANY,
            "posting_date": today(),
            "posting_time": nowtime(),
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "s_warehouse": FG_WAREHOUSE,
                    "t_warehouse": REWORK_WAREHOUSE,
                    "batch_no": batch_no,
                }
            ],
        }
    )
    transfer.insert(ignore_permissions=True)
    transfer.make_bundle_using_old_serial_batch_fields()
    normalize_bundle_rows(transfer)
    transfer.submit()
    return transfer.name


def create_rework_bom(item_code: str, qty: float, suffix: str) -> str:
    bom = frappe.get_doc(
        {
            "doctype": "BOM",
            "item": item_code,
            "quantity": qty,
            "uom": "Kg",
            "is_default": 0,
            "is_active": 1,
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "source_warehouse": REWORK_WAREHOUSE,
                    "do_not_explode": 1,
                }
            ],
        }
    )
    if meta_has_field("BOM", "rm_cost_as_per"):
        bom.rm_cost_as_per = "Valuation Rate"
    if meta_has_field("BOM", "transfer_material_against"):
        bom.transfer_material_against = "Work Order"
    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom.name


def create_rework_work_order(item_code: str, bom_name: str, qty: float, operator: str) -> tuple[str, str]:
    work_order = frappe.get_doc(
        {
            "doctype": "Work Order",
            "company": COMPANY,
            "production_item": item_code,
            "bom_no": bom_name,
            "qty": qty,
            "planned_start_date": now_datetime(),
            "fg_warehouse": FG_WAREHOUSE,
            "wip_warehouse": WIP_WAREHOUSE,
            "source_warehouse": REWORK_WAREHOUSE,
            "skip_transfer": 1,
        }
    )
    set_tracking_fields(work_order, TEST_MACHINE, operator, TEST_SHIFT)
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


def _build_linked_manufacture_entry(
    work_order: str,
    item_code: str,
    qty: float,
    failed_batch_no: str,
    new_batch_no: str,
    operator: str,
):
    entry = frappe.get_doc(make_work_order_stock_entry(work_order, "Manufacture", qty))
    set_tracking_fields(entry, TEST_MACHINE, operator, TEST_SHIFT)
    if hasattr(entry, "fg_completed_qty"):
        entry.fg_completed_qty = qty

    for row in entry.items:
        if row.is_finished_item:
            row.batch_no = new_batch_no
            row.s_warehouse = None
            row.t_warehouse = FG_WAREHOUSE
            continue

        row.batch_no = failed_batch_no
        row.s_warehouse = REWORK_WAREHOUSE
        row.t_warehouse = WIP_WAREHOUSE

    return entry


def _build_manual_manufacture_entry(
    work_order: str,
    item_code: str,
    qty: float,
    failed_batch_no: str,
    new_batch_no: str,
    operator: str,
):
    entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "purpose": "Manufacture",
            "stock_entry_type": "Manufacture",
            "company": COMPANY,
            "posting_date": today(),
            "posting_time": nowtime(),
            "work_order": work_order,
            "from_bom": 0,
            "fg_completed_qty": qty,
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "s_warehouse": REWORK_WAREHOUSE,
                    "t_warehouse": WIP_WAREHOUSE,
                    "batch_no": failed_batch_no,
                },
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1,
                    "s_warehouse": None,
                    "t_warehouse": FG_WAREHOUSE,
                    "batch_no": new_batch_no,
                    "is_finished_item": 1,
                    "allow_zero_valuation_rate": 1,
                },
            ],
        }
    )
    set_tracking_fields(entry, TEST_MACHINE, operator, TEST_SHIFT)
    return entry


def create_rework_manufacture(
    work_order: str,
    item_code: str,
    qty: float,
    failed_batch_no: str,
    operator: str,
    suffix: str,
) -> tuple[str, str, str, str]:
    new_batch_no = ensure_batch(f"FG-REWORK-{suffix}-{slug(item_code)}", item_code)
    last_error = ""

    for mode, builder in (
        ("linked_work_order", _build_linked_manufacture_entry),
        ("manual_fallback", _build_manual_manufacture_entry),
    ):
        savepoint = f"rework_manufacture_{mode}"
        frappe.db.sql(f"SAVEPOINT {savepoint}")
        try:
            entry = builder(work_order, item_code, qty, failed_batch_no, new_batch_no, operator)
            entry.insert(ignore_permissions=True)
            if hasattr(entry, "fg_completed_qty"):
                entry.fg_completed_qty = qty
            entry.submit()
            batch_record = frappe.db.get_value("Batch Production Record", {"stock_entry": entry.name}, "name")
            if not batch_record:
                frappe.throw(f"Batch Production Record was not created for Stock Entry {entry.name}.")
            return entry.name, new_batch_no, batch_record, mode
        except Exception:
            last_error = frappe.get_traceback()
            frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    frappe.throw(f"Rework manufacture failed.\n{last_error}")


def build_genealogy(batch_record: str, original_batch: str, new_batch: str) -> dict[str, object]:
    record = frappe.get_doc("Batch Production Record", batch_record)
    consumed_batches = [row.batch_no for row in record.get("materials", [])]
    return {
        "original_batch": original_batch,
        "rework_batch_record": batch_record,
        "new_batch": new_batch,
        "consumed_batches": consumed_batches,
        "original_batch_consumed": original_batch in consumed_batches,
        "new_batch_recorded": record.fg_batch_no == new_batch,
    }


def build_report() -> dict[str, object]:
    ensure_rework_warehouse()
    operator = ensure_operator_employee()
    failed = get_latest_failed_batch() or create_failed_batch_for_rework(operator)
    item_code = failed["item_code"]
    failed_batch_no = failed["batch_no"]
    batch_qty = flt(failed.get("available_qty")) or get_batch_balance(item_code, failed_batch_no, FG_WAREHOUSE)
    if batch_qty <= 0:
        frappe.throw(f"No available stock found for failed batch {failed_batch_no} in {FG_WAREHOUSE}.")

    block_check = validate_failed_batch_dispatch_block(item_code, failed_batch_no, batch_qty)

    suffix = unique_suffix(f"rework-{item_code}")
    move_stock_entry = move_failed_batch_to_rework(item_code, failed_batch_no, batch_qty)
    rework_bom = create_rework_bom(item_code, batch_qty, suffix)
    rework_work_order, readiness = create_rework_work_order(item_code, rework_bom, batch_qty, operator)
    manufacture_stock_entry, new_batch_no, batch_record, manufacture_mode = create_rework_manufacture(
        rework_work_order,
        item_code,
        batch_qty,
        failed_batch_no,
        operator,
        suffix,
    )
    qc_record, final_qc_release, _ = create_final_qc(
        item_code,
        batch_qty,
        batch_record,
        manufacture_stock_entry,
        new_batch_no,
    )
    genealogy = build_genealogy(batch_record, failed_batch_no, new_batch_no)

    report = {
        "summary": {
            "failed_batch_selected": "PASS" if failed_batch_no else "FAIL",
            "failed_batch_dispatch_blocked": "PASS" if block_check["blocked"] else "FAIL",
            "failed_batch_moved_to_rework": "PASS" if move_stock_entry else "FAIL",
            "rework_work_order": "PASS" if rework_work_order else "FAIL",
            "manufacture_stock_entry": "PASS" if manufacture_stock_entry else "FAIL",
            "new_batch_created": "PASS" if new_batch_no else "FAIL",
            "qc_on_reworked_batch": "PASS" if qc_record and final_qc_release else "FAIL",
            "genealogy": "PASS"
            if genealogy["original_batch_consumed"] and genealogy["new_batch_recorded"]
            else "FAIL",
        },
        "failed_batch_number": failed_batch_no,
        "failed_final_qc_release": failed["name"],
        "failed_final_qc_status": failed["status"],
        "failed_batch_source": failed.get("source"),
        "failed_batch_creation_records": failed.get("created_records", {}),
        "failed_batch_qty": batch_qty,
        "dispatch_block_check": block_check,
        "move_to_rework_stock_entry": move_stock_entry,
        "rework_bom": rework_bom,
        "rework_work_order": rework_work_order,
        "material_readiness_check": readiness,
        "manufacture_stock_entry": manufacture_stock_entry,
        "manufacture_mode": manufacture_mode,
        "new_fg_batch": new_batch_no,
        "batch_production_record": batch_record,
        "new_batch_qc_record": qc_record,
        "new_batch_final_qc_release": final_qc_release,
        "genealogy": genealogy,
    }

    output_path = verification_dir() / "rework_manufacturing_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
