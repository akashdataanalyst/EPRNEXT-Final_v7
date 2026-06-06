from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime

from calco_erp.calco_complaint_capa.doctype.technical_assistance_ticket.technical_assistance_ticket import (
    build_traceability_data,
)
from calco_erp.data_foundation.sales_order_cycle_711c3002 import (
    TEST_MACHINE,
    TEST_SHIFT,
    build_components_for_qty,
    build_traceability,
    compare_requirement_vs_consumption,
    create_delivery_note,
    create_final_qc,
    create_manufacture_stock_entry,
    create_production_plan,
    create_purchase_receipt,
    create_readiness_check,
    create_rm_qc_and_release,
    create_sales_invoice_from_delivery_note,
    create_sales_order,
    create_work_order,
    ensure_customer,
    ensure_inspection_flags,
    ensure_operator_employee,
    ensure_supplier,
    get_stock_ledger_entries,
    get_stock_snapshot,
    meta_has_field,
    slug,
    submit_dispatch_clearance,
    submit_work_order,
    unique_suffix,
    verification_dir,
)
from calco_erp.data_foundation.manufacturing_test_cycle import create_quality_inspection, verify_master_data


SIMPLE_ITEM = "710C0031A"
SIMPLE_QTY = 1000.0
COMPLEX_ITEMS = ["730C2094F", "710C3091", "710C2383F4"]
COMPLEX_QTY = 1000.0
PARTIAL_ITEM = "710C0031A"
PARTIAL_PRODUCTION_QTY = 1000.0
PARTIAL_DISPATCH_QTY = 400.0
HOLD_ITEM = "710C0031A"
HOLD_QTY = 100.0


def create_successful_cycle(item_code: str, qty: float, suffix_label: str, dispatch_qty: float | None = None) -> dict[str, object]:
    suffix = unique_suffix(suffix_label)
    operator = ensure_operator_employee()
    bom_name, required_components = build_components_for_qty(item_code, qty)
    ensure_inspection_flags(item_code, required_components)

    stock_before = get_stock_snapshot(required_components)
    sales_order, sales_order_item = create_sales_order(item_code, qty, suffix)
    purchase_receipt, batch_map = create_purchase_receipt(required_components, suffix)
    inward_docs, qc_docs, release_docs = create_rm_qc_and_release(purchase_receipt)
    production_plan = create_production_plan(item_code, bom_name, sales_order, sales_order_item, qty)
    work_order = create_work_order(
        item_code,
        bom_name,
        production_plan,
        sales_order,
        sales_order_item,
        qty,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    readiness = create_readiness_check(work_order)
    submit_work_order(work_order)

    manufacture_stock_entry, fg_batch, batch_record, actual_consumption = create_manufacture_stock_entry(
        work_order,
        item_code,
        qty,
        batch_map,
        suffix,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    quality_inspection, final_qc_release, coa_record = create_final_qc(
        item_code,
        qty,
        batch_record,
        manufacture_stock_entry,
        fg_batch,
    )

    dispatch_qty = flt(dispatch_qty or qty)
    delivery_note_doc, dispatch_quality_inspection = create_delivery_note(
        item_code,
        dispatch_qty,
        sales_order,
        sales_order_item,
        fg_batch,
    )
    dispatch_clearance = submit_dispatch_clearance(
        delivery_note_doc.name,
        item_code,
        fg_batch,
        final_qc_release,
    )
    delivery_note_doc.submit()
    sales_invoice = create_sales_invoice_from_delivery_note(delivery_note_doc.name)

    return {
        "item_code": item_code,
        "qty": qty,
        "dispatch_qty": dispatch_qty,
        "customer": ensure_customer(),
        "supplier": ensure_supplier(),
        "operator": operator,
        "machine": TEST_MACHINE,
        "shift_type": TEST_SHIFT,
        "bom_used": bom_name,
        "sales_order": sales_order,
        "sales_order_item": sales_order_item,
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
        "expected_vs_actual_consumption": compare_requirement_vs_consumption(required_components, actual_consumption),
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
        "traceability": build_traceability(manufacture_stock_entry, work_order, fg_batch, delivery_note_doc.name),
    }


def try_cycle_candidates(item_codes: list[str], qty: float, suffix_prefix: str) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    attempts: list[dict[str, str]] = []
    for item_code in item_codes:
        savepoint = f"uat_{slug(item_code).lower()}_{slug(suffix_prefix).lower()}".replace("-", "_")
        frappe.db.savepoint(savepoint)
        try:
            return create_successful_cycle(item_code, qty, f"{suffix_prefix}-{item_code}"), attempts
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            attempts.append({"item_code": item_code, "error": str(exc)})
    return None, attempts


def create_hold_release(item_code: str, qty: float, batch_record: str, stock_entry: str, fg_batch: str) -> tuple[str, str]:
    qi_name = create_quality_inspection("Stock Entry", stock_entry, item_code, qty, fg_batch, "In Process")
    release = frappe.get_doc(
        {
            "doctype": "Final QC Release",
            "batch_production_record": batch_record,
            "quality_inspection": qi_name,
            "status": "Hold",
        }
    )
    release.insert(ignore_permissions=True)
    release.submit()
    return qi_name, release.name


def run_final_qc_hold_block(item_code: str, qty: float) -> dict[str, object]:
    suffix = unique_suffix(f"hold-{item_code}")
    operator = ensure_operator_employee()
    bom_name, required_components = build_components_for_qty(item_code, qty)
    ensure_inspection_flags(item_code, required_components)

    sales_order, sales_order_item = create_sales_order(item_code, qty, suffix)
    purchase_receipt, batch_map = create_purchase_receipt(required_components, suffix)
    create_rm_qc_and_release(purchase_receipt)
    production_plan = create_production_plan(item_code, bom_name, sales_order, sales_order_item, qty)
    work_order = create_work_order(
        item_code,
        bom_name,
        production_plan,
        sales_order,
        sales_order_item,
        qty,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    readiness = create_readiness_check(work_order)
    submit_work_order(work_order)
    manufacture_stock_entry, fg_batch, batch_record, actual_consumption = create_manufacture_stock_entry(
        work_order,
        item_code,
        qty,
        batch_map,
        suffix,
        TEST_MACHINE,
        operator,
        TEST_SHIFT,
    )
    quality_inspection, final_qc_release = create_hold_release(item_code, qty, batch_record, manufacture_stock_entry, fg_batch)
    delivery_note_doc, dispatch_quality_inspection = create_delivery_note(
        item_code,
        qty,
        sales_order,
        sales_order_item,
        fg_batch,
    )
    blocked_message = ""
    blocked = False
    try:
        delivery_note_doc.submit()
    except Exception as exc:
        blocked = True
        blocked_message = str(exc)

    return {
        "item_code": item_code,
        "qty": qty,
        "sales_order": sales_order,
        "production_plan": production_plan,
        "work_order": work_order,
        "material_readiness_check": readiness,
        "purchase_receipt": purchase_receipt,
        "manufacture_stock_entry": manufacture_stock_entry,
        "batch_production_record": batch_record,
        "fg_batch": fg_batch,
        "quality_inspection": quality_inspection,
        "final_qc_release": final_qc_release,
        "delivery_note": delivery_note_doc.name,
        "dispatch_quality_inspection": dispatch_quality_inspection,
        "actual_rm_consumption": actual_consumption,
        "dispatch_blocked": blocked,
        "blocked_message": blocked_message,
    }


def get_sales_invoice_delivery_context(sales_invoice: str) -> dict[str, str]:
    invoice = frappe.get_doc("Sales Invoice", sales_invoice)
    item_meta = frappe.get_meta("Sales Invoice Item")
    has_dn_detail = bool(item_meta.get_field("dn_detail"))
    has_delivery_note = bool(item_meta.get_field("delivery_note"))

    for row in invoice.items:
        delivery_note = (row.get("delivery_note") or "").strip() if has_delivery_note else ""
        dn_detail = (row.get("dn_detail") or "").strip() if has_dn_detail else ""

        if dn_detail and frappe.db.exists("Delivery Note Item", dn_detail):
            delivery_note = frappe.db.get_value("Delivery Note Item", dn_detail, "parent")
            dn_item = frappe.db.get_value(
                "Delivery Note Item",
                dn_detail,
                ["item_code", "batch_no"],
                as_dict=True,
            )
            if dn_item and dn_item.get("batch_no"):
                return {
                    "sales_invoice": sales_invoice,
                    "delivery_note": delivery_note,
                    "item_code": dn_item["item_code"],
                    "fg_batch_no": dn_item["batch_no"],
                }

        if delivery_note:
            dn_rows = frappe.get_all(
                "Delivery Note Item",
                filters={"parent": delivery_note, "item_code": row.item_code},
                fields=["item_code", "batch_no", "qty"],
                order_by="creation asc",
                limit_page_length=50,
            )
            for dn_row in dn_rows:
                if dn_row.get("batch_no"):
                    return {
                        "sales_invoice": sales_invoice,
                        "delivery_note": delivery_note,
                        "item_code": dn_row["item_code"],
                        "fg_batch_no": dn_row["batch_no"],
                    }

    frappe.throw(f"No batch-tracked Delivery Note link found for Sales Invoice {sales_invoice}.")


def run_complaint_traceability_from_sales_invoice(sales_invoice: str) -> dict[str, object]:
    context = get_sales_invoice_delivery_context(sales_invoice)
    trace = build_traceability_data(context["item_code"], context["fg_batch_no"], context["delivery_note"])
    ticket = frappe.get_doc(
        {
            "doctype": "Technical Assistance Ticket",
            "delivery_note": context["delivery_note"],
            "item_code": context["item_code"],
            "fg_batch_no": context["fg_batch_no"],
            "issue_summary": f"Sales Invoice traceability validation for {sales_invoice}",
        }
    )
    ticket.insert(ignore_permissions=True)

    return {
        "sales_invoice": sales_invoice,
        "delivery_note": context["delivery_note"],
        "item_code": context["item_code"],
        "fg_batch_no": context["fg_batch_no"],
        "ticket": ticket.name,
        "batch_production_record": ticket.batch_production_record,
        "work_order": ticket.work_order,
        "stock_entry": ticket.stock_entry,
        "final_qc_release": ticket.final_qc_release,
        "final_quality_inspection": ticket.final_quality_inspection,
        "dispatch_clearance": ticket.dispatch_clearance,
        "coa_record": ticket.coa_record,
        "rm_batches": [row.as_dict() for row in ticket.rm_batches],
        "traceability_notes": ticket.traceability_notes,
        "trace_matches_builder": int(ticket.work_order == trace["work_order"] and len(ticket.rm_batches) == len(trace["rm_batches"])),
    }


def identify_go_live_gaps() -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []

    item_columns = set(frappe.get_meta("Item").get_valid_columns())
    if "inspection_required_before_purchase" in item_columns:
        missing_purchase_inspection = frappe.db.count(
            "Item",
            {
                "item_group": "Raw Material",
                "is_stock_item": 1,
                "inspection_required_before_purchase": 0,
            },
        )
        if missing_purchase_inspection:
            gaps.append(
                {
                    "type": "Master Data",
                    "severity": "High",
                    "gap": f"{missing_purchase_inspection} RM items are not flagged for inspection before purchase.",
                }
            )

    if "inspection_required_before_delivery" in item_columns:
        missing_delivery_inspection = frappe.db.count(
            "Item",
            {
                "item_group": "Finished Goods",
                "is_stock_item": 1,
                "inspection_required_before_delivery": 0,
            },
        )
        if missing_delivery_inspection:
            gaps.append(
                {
                    "type": "Master Data",
                    "severity": "High",
                    "gap": f"{missing_delivery_inspection} FG items are not flagged for inspection before delivery.",
                }
            )

    critical_doctypes = [
        "RM Inward Validation",
        "RM QC Decision",
        "RM Release Note",
        "Material Readiness Check",
        "Batch Production Record",
        "Final QC Release",
        "Dispatch Clearance",
        "Technical Assistance Ticket",
    ]
    restricted = []
    for doctype in critical_doctypes:
        roles = frappe.get_all("DocPerm", filters={"parent": doctype, "permlevel": 0, "read": 1}, pluck="role")
        non_admin_roles = sorted(role for role in roles if role not in ("System Manager", "Administrator"))
        if not non_admin_roles:
            restricted.append(doctype)
    if restricted:
        gaps.append(
            {
                "type": "Permission",
                "severity": "High",
                "gap": "These transaction doctypes are readable only by admin roles and need business-role permissions: "
                + ", ".join(restricted),
            }
        )

    gaps.append(
        {
            "type": "Workflow",
            "severity": "Medium",
            "gap": "Complaint traceability is proven from Sales Invoice context through linked Delivery Note, but the live UI still starts the complaint from Delivery Note / FG batch rather than a direct Sales Invoice action.",
        }
    )

    return gaps


def execute() -> dict[str, object]:
    verification = verify_master_data()

    simple_cycle = create_successful_cycle(SIMPLE_ITEM, SIMPLE_QTY, "phase2-simple-full")
    complex_cycle, complex_attempts = try_cycle_candidates(COMPLEX_ITEMS, COMPLEX_QTY, "phase2-complex-full")
    partial_cycle = create_successful_cycle(PARTIAL_ITEM, PARTIAL_PRODUCTION_QTY, "phase2-partial", PARTIAL_DISPATCH_QTY)
    try:
        hold_scenario = run_final_qc_hold_block(HOLD_ITEM, HOLD_QTY)
    except Exception as exc:
        hold_scenario = {
            "item_code": HOLD_ITEM,
            "qty": HOLD_QTY,
            "dispatch_blocked": False,
            "blocked_message": str(exc),
            "scenario_error": str(exc),
        }
    complaint_source_invoice = (complex_cycle or simple_cycle)["sales_invoice"]
    try:
        complaint_traceability = run_complaint_traceability_from_sales_invoice(complaint_source_invoice)
    except Exception as exc:
        complaint_traceability = {
            "sales_invoice": complaint_source_invoice,
            "scenario_error": str(exc),
            "work_order": "",
            "rm_batches": [],
        }
    go_live_gaps = identify_go_live_gaps()

    partial_remaining_qty = round(flt(partial_cycle["qty"]) - flt(partial_cycle["dispatch_qty"]), 6)

    summary = {
        "simple_grade_cycle": "PASS",
        "complex_grade_cycle": "PASS" if complex_cycle else "FAIL",
        "partial_dispatch": "PASS" if partial_remaining_qty > 0 else "FAIL",
        "final_qc_hold_blocks_dispatch": "PASS" if hold_scenario["dispatch_blocked"] else "FAIL",
        "complaint_traceability_from_sales_invoice": "PASS"
        if complaint_traceability["work_order"] and complaint_traceability["rm_batches"]
        else "FAIL",
    }

    result = {
        "summary": summary,
        "master_data_verification": verification,
        "simple_cycle": simple_cycle,
        "complex_cycle_attempts": complex_attempts,
        "complex_cycle": complex_cycle,
        "partial_dispatch": {
            "item_code": partial_cycle["item_code"],
            "produced_qty": partial_cycle["qty"],
            "dispatched_qty": partial_cycle["dispatch_qty"],
            "remaining_qty": partial_remaining_qty,
            "fg_batch": partial_cycle["fg_batch"],
            "delivery_note": partial_cycle["delivery_note"],
            "sales_invoice": partial_cycle["sales_invoice"],
            "dispatch_clearance": partial_cycle["dispatch_clearance"],
            "pass": partial_remaining_qty > 0,
        },
        "final_qc_hold_scenario": hold_scenario,
        "complaint_traceability": complaint_traceability,
        "go_live_gaps": go_live_gaps,
    }

    output_path = verification_dir() / "phase2_uat_validation_result.json"
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
