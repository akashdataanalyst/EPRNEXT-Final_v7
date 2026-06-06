from __future__ import annotations

import json
import re
from pathlib import Path

import frappe
from frappe.utils import flt, now_datetime, nowtime, today
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

from calco_erp.calco_quality.rm_purchase_flow_setup import ensure_rm_purchase_flow_setup
from calco_erp.calco_quality.rm_warehouse_flow import get_batch_balance, get_rm_flow_warehouses
from calco_erp.data_foundation.manufacturing_test_cycle import (
    COMPANY,
    RM_WAREHOUSE,
    STANDARD_BUYING,
    SUPPLIER,
    ensure_batch,
    ensure_supplier,
)


ITEM_CODE = "JE25 OG"
QTY = 100.0
QC_TEMPLATE = "Calco Incoming RM QC"


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


def ensure_item_ready_for_rm_qc(item_code: str) -> None:
    if meta_has_field("Item", "inspection_required_before_purchase"):
        frappe.db.set_value(
            "Item",
            item_code,
            "inspection_required_before_purchase",
            1,
            update_modified=False,
        )
    if meta_has_field("Item", "custom_enable_rm_qc"):
        frappe.db.set_value(
            "Item",
            item_code,
            "custom_enable_rm_qc",
            1,
            update_modified=False,
        )
    if meta_has_field("Item", "quality_inspection_template"):
        frappe.db.set_value(
            "Item",
            item_code,
            "quality_inspection_template",
            QC_TEMPLATE,
            update_modified=False,
        )


def create_purchase_order(item_code: str, qty: float, suffix: str) -> str:
    item_row = {
        "item_code": item_code,
        "item_name": frappe.db.get_value("Item", item_code, "item_name"),
        "qty": qty,
        "uom": "Kg",
        "stock_uom": "Kg",
        "conversion_factor": 1,
        "rate": 1,
        "warehouse": RM_WAREHOUSE,
        "schedule_date": today(),
    }
    po = frappe.get_doc(
        {
            "doctype": "Purchase Order",
            "supplier": ensure_supplier(),
            "transaction_date": today(),
            "schedule_date": today(),
            "company": COMPANY,
            "currency": "INR",
            "conversion_rate": 1,
            "buying_price_list": STANDARD_BUYING,
            "price_list_currency": "INR",
            "plc_conversion_rate": 1,
            "supplier_quotation": f"CALCO-RM-QC-{suffix}",
            "items": [item_row],
        }
    )
    po.insert(ignore_permissions=True)
    po.submit()
    return po.name


def create_purchase_receipt_without_qi(purchase_order: str, batch_no: str, qty: float) -> str:
    pr = make_purchase_receipt(purchase_order)
    pr.posting_date = today()
    pr.posting_time = nowtime()
    pr.company = COMPANY

    for row in pr.items:
        row.warehouse = RM_WAREHOUSE
        row.batch_no = batch_no
        row.qty = qty
        row.received_qty = qty
        row.stock_qty = qty
        row.rejected_qty = 0
        row.uom = "Kg"
        row.stock_uom = "Kg"
        row.conversion_factor = 1
        row.rate = row.rate or 1
        row.base_rate = row.base_rate or 1
        row.quality_inspection = ""

    pr.insert(ignore_permissions=True)
    pr.submit()
    return pr.name


def get_inward_validation(purchase_receipt: str) -> dict[str, object] | None:
    rows = frappe.get_all(
        "RM Inward Validation",
        filters={"purchase_receipt": purchase_receipt},
        fields=["name", "item_code", "batch_no", "received_qty", "warehouse", "status"],
        limit_page_length=1,
    )
    return rows[0] if rows else None


def get_quality_inspection(purchase_receipt: str, batch_no: str) -> str:
    quality_inspection = frappe.db.get_value(
        "Quality Inspection",
        {
            "reference_type": "Purchase Receipt",
            "reference_name": purchase_receipt,
            "item_code": ITEM_CODE,
            "batch_no": batch_no,
        },
        "name",
    )
    if not quality_inspection:
        from calco_erp.calco_quality.purchase_receipt_qc import (
            ensure_purchase_receipt_quality_inspection,
            get_item_qc_config,
        )

        purchase_receipt_doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
        for row in purchase_receipt_doc.items:
            if row.item_code == ITEM_CODE and (row.batch_no or "") == (batch_no or ""):
                created = ensure_purchase_receipt_quality_inspection(
                    purchase_receipt_doc,
                    row,
                    get_item_qc_config(row.item_code),
                )
                quality_inspection = created.name if created else None
                break

    if not quality_inspection:
        quality_inspection = frappe.db.get_value(
            "Quality Inspection",
            {
                "reference_type": "Purchase Receipt",
                "reference_name": purchase_receipt,
                "item_code": ITEM_CODE,
                "batch_no": batch_no,
            },
            "name",
        )
    if not quality_inspection:
        frappe.throw(f"No Quality Inspection found for {purchase_receipt} / {batch_no}.")
    return quality_inspection


def submit_rm_quality_inspection(quality_inspection: str, status: str, overall_result: str) -> None:
    qi = frappe.get_doc("Quality Inspection", quality_inspection)
    qi.report_date = today()
    qi.inspected_by = "Administrator"
    qi.manual_inspection = 1
    qi.status = status
    qi.custom_overall_result = overall_result
    qi.save(ignore_permissions=True)
    qi.submit()


def create_rm_qc_decision(
    inward_validation: str | None, quality_inspection: str, decision: str, sample_qty: float
) -> str:
    payload = {
        "doctype": "RM QC Decision",
        "quality_inspection": quality_inspection,
        "decision": decision,
        "sample_qty": sample_qty,
    }
    if inward_validation:
        payload["inward_validation"] = inward_validation

    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def create_rm_release_note(rm_qc_decision: str, release_qty: float) -> str:
    release_doc = frappe.get_doc(
        {
            "doctype": "RM Release Note",
            "rm_qc_decision": rm_qc_decision,
            "release_qty": release_qty,
            "status": "Released",
        }
    )
    release_doc.insert(ignore_permissions=True)
    release_doc.submit()
    return release_doc.name


def attempt_rm_consumption(batch_no: str, source_warehouse: str) -> dict[str, object]:
    blocked = False
    stock_entry_name = ""
    message = ""
    savepoint = f"rm_qc_gate_{batch_no.replace('-', '_')}"
    purpose = "Material Consumption for Manufacture"
    frappe.db.sql(f"SAVEPOINT {savepoint}")
    try:
        se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": purpose,
                "stock_entry_type": purpose,
                "company": COMPANY,
                "posting_date": today(),
                "posting_time": nowtime(),
                "items": [
                    {
                        "item_code": ITEM_CODE,
                        "qty": 1,
                        "uom": "Kg",
                        "stock_uom": "Kg",
                        "conversion_factor": 1,
                        "s_warehouse": source_warehouse,
                        "batch_no": batch_no,
                    }
                ],
            }
        )
        se.insert(ignore_permissions=True)
        se.submit()
        stock_entry_name = se.name
    except Exception:
        blocked = True
        message = frappe.get_traceback()
    finally:
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")

    return {"blocked": blocked, "stock_entry": stock_entry_name, "message": message}


def get_stock_ledger_entries(voucher_type: str, voucher_no: str) -> list[dict[str, object]]:
    return frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "item_code": ITEM_CODE},
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
        order_by="posting_datetime asc, creation asc",
        limit_page_length=50,
    )


def get_auto_transfer_stock_entries(reference_name: str) -> list[dict[str, object]]:
    stock_entries = frappe.get_all(
        "Stock Entry",
        filters={"remarks": ("like", f"%{reference_name}%")},
        fields=["name", "purpose", "stock_entry_type", "remarks"],
        order_by="creation asc",
        limit_page_length=10,
    )
    for row in stock_entries:
        row["stock_ledger"] = get_stock_ledger_entries("Stock Entry", row["name"])
    return stock_entries


def build_flow_case(decision: str) -> dict[str, object]:
    suffix = unique_suffix(f"{ITEM_CODE}-{decision}")
    batch_no = ensure_batch(f"RM-qc-flow-{suffix}", ITEM_CODE)
    purchase_order = create_purchase_order(ITEM_CODE, QTY, suffix)
    purchase_receipt = create_purchase_receipt_without_qi(purchase_order, batch_no, QTY)
    inward_validation = get_inward_validation(purchase_receipt)
    quality_inspection = get_quality_inspection(purchase_receipt, batch_no)

    warehouses = get_rm_flow_warehouses(COMPANY)
    before_release_block = attempt_rm_consumption(batch_no, warehouses["quarantine"])

    quality_status = "Accepted" if decision == "Accepted" else "Rejected"
    quality_result = "ACCEPTED" if decision == "Accepted" else "REJECTED"
    submit_rm_quality_inspection(quality_inspection, quality_status, quality_result)
    sample_qty = inward_validation["received_qty"] if inward_validation else QTY
    rm_qc_decision = create_rm_qc_decision(
        inward_validation["name"] if inward_validation else None,
        quality_inspection,
        decision,
        sample_qty,
    )

    release_note = ""
    after_release_attempt = {}
    if decision == "Accepted":
        release_note = create_rm_release_note(rm_qc_decision, sample_qty)
        after_release_attempt = attempt_rm_consumption(batch_no, warehouses["released"])
    else:
        blocked_source = warehouses["hold"] if decision == "Hold" else warehouses["rejected"]
        after_release_attempt = attempt_rm_consumption(batch_no, blocked_source)

    return {
        "decision": decision,
        "purchase_order": purchase_order,
        "purchase_receipt": purchase_receipt,
        "batch_no": batch_no,
        "inward_validation": inward_validation,
        "quality_inspection": quality_inspection,
        "rm_qc_decision": rm_qc_decision,
        "rm_release_note": release_note,
        "before_release_block": before_release_block,
        "after_decision_attempt": after_release_attempt,
        "purchase_receipt_stock_ledger": get_stock_ledger_entries("Purchase Receipt", purchase_receipt),
        "auto_transfer_stock_entries": get_auto_transfer_stock_entries(release_note or rm_qc_decision),
        "quality_inspection_status": frappe.db.get_value(
            "Quality Inspection",
            quality_inspection,
            ["status", "custom_overall_result", "docstatus"],
            as_dict=True,
        ),
        "decision_status": frappe.db.get_value(
            "RM QC Decision",
            rm_qc_decision,
            ["decision", "status", "docstatus"],
            as_dict=True,
        ),
        "release_status": frappe.db.get_value(
            "RM Release Note",
            release_note,
            ["status", "release_qty", "release_warehouse", "docstatus"],
            as_dict=True,
        )
        if release_note
        else {},
        "warehouse_balances": {
            name: get_batch_balance(ITEM_CODE, batch_no, warehouse)
            for name, warehouse in warehouses.items()
            if warehouse
        },
    }


def build_report() -> dict[str, object]:
    ensure_supplier()
    ensure_rm_purchase_flow_setup()
    ensure_item_ready_for_rm_qc(ITEM_CODE)

    warehouses = get_rm_flow_warehouses(COMPANY)
    accepted_case = build_flow_case("Accepted")
    hold_case = build_flow_case("Hold")
    rejected_case = build_flow_case("Rejected")

    report = {
        "summary": {
            "po_to_pr_without_qc": "PASS" if accepted_case["purchase_receipt"] else "FAIL",
            "purchase_receipt_into_quarantine": "PASS"
            if any(row["warehouse"] == warehouses["quarantine"] for row in accepted_case["purchase_receipt_stock_ledger"])
            else "FAIL",
            "production_blocked_before_release": "PASS"
            if accepted_case["before_release_block"]["blocked"]
            else "FAIL",
            "accepted_release_submitted": "PASS" if accepted_case["rm_release_note"] else "FAIL",
            "production_allowed_after_release": "PASS"
            if not accepted_case["after_decision_attempt"]["blocked"]
            else "FAIL",
            "hold_remains_blocked": "PASS" if hold_case["after_decision_attempt"]["blocked"] else "FAIL",
            "rejected_remains_blocked": "PASS" if rejected_case["after_decision_attempt"]["blocked"] else "FAIL",
        },
        "warehouses": warehouses,
        "accepted_case": accepted_case,
        "hold_case": hold_case,
        "rejected_case": rejected_case,
    }

    output_path = verification_dir() / "rm_purchase_qc_flow_uat_result.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run() -> dict[str, object]:
    report = build_report()
    frappe.db.commit()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
