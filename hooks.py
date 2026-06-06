app_name = "calco_erp"
app_title = "Calco PolyTechnik Pvt Ltd ERP"
app_publisher = "Codex"
app_description = "Calco PolyTechnik Pvt Ltd manufacturing ERP on ERPNext"
app_email = "support@example.com"
app_license = "MIT"
app_include_css = "/assets/calco_erp/css/calco_branding.css"
web_include_css = "/assets/calco_erp/css/calco_branding.css"
app_include_js = "/assets/calco_erp/js/calco_branding.js"
web_include_js = "/assets/calco_erp/js/calco_branding.js"
app_logo_url = "/assets/calco_erp/images/calco-polytechnik-logo.svg"
brand_html = """<span class="calco-brand-inline"><img src="/assets/calco_erp/images/calco-polytechnik-logo.svg" alt="Calco PolyTechnik Pvt Ltd ERP"><span>Calco PolyTechnik Pvt Ltd ERP</span></span>"""

after_install = "calco_erp.workspace_setup.after_install_setup"

after_migrate = [
    "calco_erp.branding_setup.ensure_branding_setup",
    "calco_erp.workspace_setup.sync_workspace_ui",
    "calco_erp.calco_customer_approval.sales_order_journey.ensure_sales_order_journey_setup",
    "calco_erp.machine_setup.ensure_machine_tracking_setup",
    "calco_erp.calco_maintenance.machine_master_sync.sync_machine_master_after_migrate",
    "calco_erp.calco_maintenance.spare_mapping_sync.sync_machine_spare_mapping_after_migrate",
    "calco_erp.calco_maintenance.pm_schedule_sync.refresh_pm_schedule_tracking",
    "calco_erp.foundation_setup.ensure_foundation_records",
    "calco_erp.calco_quality.rm_quality_setup.ensure_rm_quality_setup",
    "calco_erp.calco_quality.rm_purchase_flow_setup.ensure_rm_purchase_flow_setup",
    "calco_erp.calco_quality.fg_quality_setup.ensure_fg_quality_setup",
    "calco_erp.hrms_setup.ensure_hrms_integration_records",
    "calco_erp.barcode_setup.ensure_barcode_setup",
    "calco_erp.coa_setup.ensure_coa_setup",
    "calco_erp.thermal_label_setup.ensure_thermal_label_setup",
]

scheduler_events = {
    "daily": [
        "calco_erp.calco_maintenance.automation.run_daily_maintenance_automation",
    ]
}

doc_events = {
    "Item": {
        "validate": "calco_erp.barcode_setup.ensure_item_barcode_on_validate",
    },
    "Batch": {
        "validate": "calco_erp.barcode_setup.ensure_batch_barcode_on_validate",
    },
    "Purchase Receipt": {
        "validate": [
            "calco_erp.rm_batch_setup.ensure_purchase_receipt_batch_numbers",
            "calco_erp.calco_quality.rm_warehouse_flow.apply_purchase_receipt_quarantine",
        ],
        "on_submit": "calco_erp.thermal_label_setup.handle_purchase_receipt_submit",
    },
    "Work Order": {
        "validate": "calco_erp.machine_setup.validate_work_order_machine",
        "before_submit": "calco_erp.utils.dependencies.validate_work_order_material_readiness",
    },
    "Stock Entry": {
        "validate": "calco_erp.machine_setup.validate_stock_entry_machine",
        "before_submit": "calco_erp.fg_batch_setup.prepare_manufacture_stock_entry",
        "on_submit": "calco_erp.thermal_label_setup.handle_stock_entry_submit",
    },
    "Delivery Note": {
        "before_submit": "calco_erp.utils.dependencies.validate_delivery_note_chain",
        "on_submit": "calco_erp.coa_setup.attach_coa_pdf_to_delivery_note",
    },
    "Maintenance Ticket": {
        "on_update": "calco_erp.calco_maintenance.automation.sync_pm_plan_completion_from_ticket",
    },
    "Quality Inspection": {
        "before_validate": [
            "calco_erp.calco_quality.rm_quality_setup.apply_rm_testing_context",
            "calco_erp.calco_quality.fg_quality_setup.apply_fg_control_plan",
        ],
        "validate": [
            "calco_erp.calco_quality.rm_quality_setup.apply_rm_testing_context",
            "calco_erp.calco_quality.fg_quality_setup.apply_fg_control_plan",
        ],
        "before_submit": "calco_erp.calco_quality.fg_quality_setup.validate_fg_submission",
        "on_update": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
        "on_submit": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
        "on_cancel": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
    },
}

doctype_js = {
    "Sales Order": "public/js/sales_order_journey_tracker.js",
    "Purchase Receipt": "public/js/barcode_transaction.js",
    "Stock Entry": "public/js/barcode_transaction.js",
    "Delivery Note": "public/js/barcode_transaction.js",
    "Quality Inspection": "public/js/quality_inspection.js",
    "RM QC Decision": "public/js/rm_qc_decision.js",
    "RM Release Note": "public/js/rm_release_note.js",
}
