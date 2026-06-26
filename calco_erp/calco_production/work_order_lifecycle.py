from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


STAGE_MATERIAL_TRANSFER_PENDING = "Material Transfer Pending"
STAGE_MATERIAL_TRANSFERRED = "Material Transferred"
STAGE_GRADE_CHANGE_CHECKLIST = "Grade Change Checklist"
STAGE_PREMIX_PREPARATION = "Premix Preparation"
STAGE_RM_LOADING = "RM Loading"
STAGE_COMPOUNDING = "Compounding"
STAGE_PELLETIZING = "Pelletizing"
STAGE_INITIAL_QC_PENDING = "Initial QC Pending"
STAGE_INITIAL_QC_FAILED = "Initial QC Failed / Correction Required"
STAGE_INITIAL_QC_PASSED = "Initial QC Passed"
STAGE_PRODUCTION_RUNNING = "Production Running"
STAGE_FINAL_QC_PENDING = "Final QC Pending"
STAGE_COMPLETED = "Completed"

INITIAL_QC_PENDING = "Pending"
INITIAL_QC_PASSED = "Passed"
INITIAL_QC_FAILED = "Failed"
INITIAL_QC_RETEST_REQUIRED = "Retest Required"
FINAL_QC_PENDING = "Pending"
FINAL_QC_PASSED = "Passed"
FINAL_QC_FAILED = "Failed"

QI_STAGE_INITIAL = "Initial QC"
QI_STAGE_RETEST = "Initial QC Retest"
QI_STAGE_FINAL = "Final QC"

WORK_ORDER_STAGE_FIELD = "custom_production_stage"
WORK_ORDER_LINE_FIELD = "custom_production_line"
WORK_ORDER_GRADE_CHANGE_FIELD = "custom_grade_change_required"
WORK_ORDER_INITIAL_QC_STATUS_FIELD = "custom_initial_qc_status"
WORK_ORDER_FINAL_QC_STATUS_FIELD = "custom_final_qc_status"
WORK_ORDER_QC_REMARKS_FIELD = "custom_qc_correction_remarks"
WORK_ORDER_INITIAL_QI_FIELD = "custom_initial_quality_inspection"
WORK_ORDER_FINAL_QI_FIELD = "custom_final_quality_inspection"
WORK_ORDER_RETEST_REQUIRED_FIELD = "custom_qc_retest_required"
WORK_ORDER_RETEST_QI_FIELD = "custom_qc_retest_quality_inspection"
QI_WORK_ORDER_FIELD = "custom_work_order"
QI_STAGE_FIELD = "custom_work_order_qc_stage"

PRODUCTION_STAGES = [
    STAGE_MATERIAL_TRANSFER_PENDING,
    STAGE_MATERIAL_TRANSFERRED,
    STAGE_GRADE_CHANGE_CHECKLIST,
    STAGE_PREMIX_PREPARATION,
    STAGE_RM_LOADING,
    STAGE_COMPOUNDING,
    STAGE_PELLETIZING,
    STAGE_INITIAL_QC_PENDING,
    STAGE_INITIAL_QC_FAILED,
    STAGE_INITIAL_QC_PASSED,
    STAGE_PRODUCTION_RUNNING,
    STAGE_FINAL_QC_PENDING,
    STAGE_COMPLETED,
]


def options(values: list[str]) -> str:
    return "\n" + "\n".join(values)


def ensure_work_order_lifecycle_setup():
    ensure_custom_fields()
    frappe.clear_cache()


def ensure_custom_fields():
    if not frappe.db.exists("DocType", "Work Order"):
        return

    create_custom_fields(
        {
            "Work Order": [
                {
                    "fieldname": "custom_work_order_lifecycle_section",
                    "label": "Production Lifecycle",
                    "fieldtype": "Section Break",
                    "insert_after": "custom_fg_batch_no",
                },
                {
                    "fieldname": WORK_ORDER_STAGE_FIELD,
                    "label": "Production Stage",
                    "fieldtype": "Select",
                    "options": options(PRODUCTION_STAGES),
                    "default": STAGE_MATERIAL_TRANSFER_PENDING,
                    "insert_after": "custom_work_order_lifecycle_section",
                    "in_list_view": 1,
                    "search_index": 1,
                },
                {
                    "fieldname": WORK_ORDER_LINE_FIELD,
                    "label": "Production Line",
                    "fieldtype": "Link",
                    "options": "Workstation",
                    "insert_after": WORK_ORDER_STAGE_FIELD,
                    "in_list_view": 1,
                    "search_index": 1,
                },
                {
                    "fieldname": WORK_ORDER_GRADE_CHANGE_FIELD,
                    "label": "Grade Change Required",
                    "fieldtype": "Check",
                    "insert_after": WORK_ORDER_LINE_FIELD,
                },
                {
                    "fieldname": "custom_work_order_qc_section",
                    "label": "Production QC Gates",
                    "fieldtype": "Section Break",
                    "insert_after": WORK_ORDER_GRADE_CHANGE_FIELD,
                },
                {
                    "fieldname": WORK_ORDER_INITIAL_QC_STATUS_FIELD,
                    "label": "Initial QC Status",
                    "fieldtype": "Select",
                    "options": options([INITIAL_QC_PENDING, INITIAL_QC_PASSED, INITIAL_QC_FAILED, INITIAL_QC_RETEST_REQUIRED]),
                    "default": INITIAL_QC_PENDING,
                    "insert_after": "custom_work_order_qc_section",
                    "in_list_view": 1,
                },
                {
                    "fieldname": WORK_ORDER_FINAL_QC_STATUS_FIELD,
                    "label": "Final QC Status",
                    "fieldtype": "Select",
                    "options": options([FINAL_QC_PENDING, FINAL_QC_PASSED, FINAL_QC_FAILED]),
                    "default": FINAL_QC_PENDING,
                    "insert_after": WORK_ORDER_INITIAL_QC_STATUS_FIELD,
                    "in_list_view": 1,
                },
                {
                    "fieldname": WORK_ORDER_QC_REMARKS_FIELD,
                    "label": "QC Correction Remarks",
                    "fieldtype": "Small Text",
                    "insert_after": WORK_ORDER_FINAL_QC_STATUS_FIELD,
                },
                {
                    "fieldname": WORK_ORDER_INITIAL_QI_FIELD,
                    "label": "Initial Quality Inspection",
                    "fieldtype": "Link",
                    "options": "Quality Inspection",
                    "insert_after": WORK_ORDER_QC_REMARKS_FIELD,
                    "read_only": 1,
                },
                {
                    "fieldname": WORK_ORDER_FINAL_QI_FIELD,
                    "label": "Final Quality Inspection",
                    "fieldtype": "Link",
                    "options": "Quality Inspection",
                    "insert_after": WORK_ORDER_INITIAL_QI_FIELD,
                    "read_only": 1,
                },
                {
                    "fieldname": WORK_ORDER_RETEST_REQUIRED_FIELD,
                    "label": "QC Retest Required",
                    "fieldtype": "Check",
                    "insert_after": WORK_ORDER_FINAL_QI_FIELD,
                    "read_only": 1,
                },
                {
                    "fieldname": WORK_ORDER_RETEST_QI_FIELD,
                    "label": "QC Retest Quality Inspection",
                    "fieldtype": "Link",
                    "options": "Quality Inspection",
                    "insert_after": WORK_ORDER_RETEST_REQUIRED_FIELD,
                    "read_only": 1,
                },
            ],
            "Quality Inspection": [
                {
                    "fieldname": QI_WORK_ORDER_FIELD,
                    "label": "Work Order",
                    "fieldtype": "Link",
                    "options": "Work Order",
                    "insert_after": "reference_name",
                    "in_list_view": 1,
                    "search_index": 1,
                },
                {
                    "fieldname": QI_STAGE_FIELD,
                    "label": "Work Order QC Stage",
                    "fieldtype": "Select",
                    "options": options([QI_STAGE_INITIAL, QI_STAGE_RETEST, QI_STAGE_FINAL]),
                    "insert_after": QI_WORK_ORDER_FIELD,
                    "in_list_view": 1,
                },
            ],
        },
        update=True,
    )


def validate_work_order_lifecycle(doc, method=None):
    if not doc.get(WORK_ORDER_STAGE_FIELD):
        doc.set(WORK_ORDER_STAGE_FIELD, STAGE_MATERIAL_TRANSFER_PENDING)
    if not doc.get(WORK_ORDER_INITIAL_QC_STATUS_FIELD):
        doc.set(WORK_ORDER_INITIAL_QC_STATUS_FIELD, INITIAL_QC_PENDING)
    if not doc.get(WORK_ORDER_FINAL_QC_STATUS_FIELD):
        doc.set(WORK_ORDER_FINAL_QC_STATUS_FIELD, FINAL_QC_PENDING)

    initial_status = doc.get(WORK_ORDER_INITIAL_QC_STATUS_FIELD)
    stage = doc.get(WORK_ORDER_STAGE_FIELD)
    if initial_status == INITIAL_QC_FAILED or stage == STAGE_INITIAL_QC_FAILED:
        if not (doc.get(WORK_ORDER_QC_REMARKS_FIELD) or "").strip():
            frappe.throw(_("QC Correction Remarks are mandatory when Initial QC fails."))
        doc.set(WORK_ORDER_STAGE_FIELD, STAGE_INITIAL_QC_FAILED)

    if stage == STAGE_COMPLETED and doc.get(WORK_ORDER_FINAL_QC_STATUS_FIELD) != FINAL_QC_PASSED:
        frappe.throw(_("Final QC must be Passed before Production Stage can be Completed."))


def validate_stock_entry_lifecycle(doc, method=None):
    if get_stock_entry_purpose(doc) != "Manufacture" or not doc.get("work_order"):
        return

    work_order = frappe.db.get_value(
        "Work Order",
        doc.work_order,
        [
            WORK_ORDER_STAGE_FIELD,
            WORK_ORDER_INITIAL_QC_STATUS_FIELD,
            WORK_ORDER_QC_REMARKS_FIELD,
        ],
        as_dict=True,
    )
    if not work_order:
        return

    stage = work_order.get(WORK_ORDER_STAGE_FIELD)
    initial_status = work_order.get(WORK_ORDER_INITIAL_QC_STATUS_FIELD)
    remarks = (work_order.get(WORK_ORDER_QC_REMARKS_FIELD) or "").strip()

    if stage == STAGE_INITIAL_QC_FAILED or initial_status == INITIAL_QC_FAILED:
        if not remarks:
            frappe.throw(_("QC Correction Remarks are mandatory before correction processing can continue."))
        frappe.throw(_("Manufacture Stock Entry is blocked because Initial QC failed and correction/retest is required."))

    if initial_status != INITIAL_QC_PASSED:
        frappe.throw(_("Initial QC must be Passed before Manufacture Stock Entry can be submitted."))


def sync_stock_entry_lifecycle_on_submit(doc, method=None):
    if not doc.get("work_order"):
        return

    purpose = get_stock_entry_purpose(doc)
    if purpose == "Material Transfer for Manufacture":
        set_work_order_values_if_not_cancelled(
            doc.work_order,
            {
                WORK_ORDER_STAGE_FIELD: STAGE_MATERIAL_TRANSFERRED,
            },
            only_if_stage_before=STAGE_MATERIAL_TRANSFERRED,
        )
    elif purpose == "Manufacture":
        set_work_order_values_if_not_cancelled(
            doc.work_order,
            {
                WORK_ORDER_STAGE_FIELD: STAGE_FINAL_QC_PENDING,
            },
            only_if_not_completed=True,
        )


def sync_quality_inspection_lifecycle_on_submit(doc, method=None):
    work_order = doc.get(QI_WORK_ORDER_FIELD)
    qc_stage = doc.get(QI_STAGE_FIELD)
    if not work_order or not qc_stage:
        return

    status = (doc.get("status") or "").strip()
    passed = status == "Accepted"
    failed = status == "Rejected"
    if not (passed or failed):
        return

    updates: dict[str, object] = {}
    if qc_stage == QI_STAGE_INITIAL:
        updates[WORK_ORDER_INITIAL_QI_FIELD] = doc.name
        if passed:
            updates[WORK_ORDER_INITIAL_QC_STATUS_FIELD] = INITIAL_QC_PASSED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_INITIAL_QC_PASSED
            updates[WORK_ORDER_RETEST_REQUIRED_FIELD] = 0
        elif failed:
            updates[WORK_ORDER_INITIAL_QC_STATUS_FIELD] = INITIAL_QC_FAILED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_INITIAL_QC_FAILED
            updates[WORK_ORDER_RETEST_REQUIRED_FIELD] = 1
    elif qc_stage == QI_STAGE_RETEST:
        updates[WORK_ORDER_RETEST_QI_FIELD] = doc.name
        if passed:
            updates[WORK_ORDER_INITIAL_QC_STATUS_FIELD] = INITIAL_QC_PASSED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_INITIAL_QC_PASSED
            updates[WORK_ORDER_RETEST_REQUIRED_FIELD] = 0
        elif failed:
            updates[WORK_ORDER_INITIAL_QC_STATUS_FIELD] = INITIAL_QC_FAILED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_INITIAL_QC_FAILED
            updates[WORK_ORDER_RETEST_REQUIRED_FIELD] = 1
    elif qc_stage == QI_STAGE_FINAL:
        updates[WORK_ORDER_FINAL_QI_FIELD] = doc.name
        if passed:
            updates[WORK_ORDER_FINAL_QC_STATUS_FIELD] = FINAL_QC_PASSED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_COMPLETED
        elif failed:
            updates[WORK_ORDER_FINAL_QC_STATUS_FIELD] = FINAL_QC_FAILED
            updates[WORK_ORDER_STAGE_FIELD] = STAGE_FINAL_QC_PENDING

    if updates:
        set_work_order_values_if_not_cancelled(work_order, updates)


def mark_retest_required(work_order: str):
    if not work_order:
        frappe.throw(_("Work Order is required."))
    set_work_order_values_if_not_cancelled(
        work_order,
        {
            WORK_ORDER_INITIAL_QC_STATUS_FIELD: INITIAL_QC_RETEST_REQUIRED,
            WORK_ORDER_RETEST_REQUIRED_FIELD: 1,
            WORK_ORDER_STAGE_FIELD: STAGE_INITIAL_QC_FAILED,
        },
    )
    return frappe.get_doc("Work Order", work_order)


@frappe.whitelist()
def mark_retest_required_for_work_order(work_order: str):
    return mark_retest_required(work_order).as_dict()


@frappe.whitelist()
def make_work_order_quality_inspection(work_order: str, qc_stage: str):
    if qc_stage not in {QI_STAGE_INITIAL, QI_STAGE_RETEST, QI_STAGE_FINAL}:
        frappe.throw(_("Invalid Work Order QC Stage."))
    if not work_order or not frappe.db.exists("Work Order", work_order):
        frappe.throw(_("Valid Work Order is required."))

    wo = frappe.get_doc("Work Order", work_order)
    doc = frappe.new_doc("Quality Inspection")
    doc.inspection_type = "In Process" if qc_stage in {QI_STAGE_INITIAL, QI_STAGE_RETEST} else "Outgoing"
    doc.item_code = wo.production_item
    doc.batch_no = wo.get("custom_fg_batch_no") or ""
    doc.company = wo.company
    doc.set(QI_WORK_ORDER_FIELD, wo.name)
    doc.set(QI_STAGE_FIELD, qc_stage)
    return doc.as_dict()


def set_work_order_values_if_not_cancelled(
    work_order: str,
    values: dict[str, object],
    only_if_stage_before: str | None = None,
    only_if_not_completed: bool = False,
):
    if not work_order or not frappe.db.exists("Work Order", work_order):
        return
    current = frappe.db.get_value("Work Order", work_order, ["docstatus", WORK_ORDER_STAGE_FIELD], as_dict=True)
    if not current or current.get("docstatus") == 2:
        return
    if only_if_not_completed and current.get(WORK_ORDER_STAGE_FIELD) == STAGE_COMPLETED:
        return
    if only_if_stage_before and not should_advance_stage(current.get(WORK_ORDER_STAGE_FIELD), only_if_stage_before):
        return

    for fieldname, value in values.items():
        frappe.db.set_value("Work Order", work_order, fieldname, value, update_modified=True)
    frappe.clear_cache(doctype="Work Order")


def should_advance_stage(current_stage: str | None, next_stage: str) -> bool:
    if not current_stage:
        return True
    try:
        return PRODUCTION_STAGES.index(current_stage) <= PRODUCTION_STAGES.index(next_stage)
    except ValueError:
        return True


def get_stock_entry_purpose(doc) -> str:
    return (doc.get("stock_entry_type") or doc.get("purpose") or "").strip()