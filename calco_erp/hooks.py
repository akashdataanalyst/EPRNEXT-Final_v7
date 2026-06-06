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
    "calco_erp.calco_purchase.purchase_journey.ensure_purchase_journey_setup",
    "calco_erp.calco_purchase.supplier_approval_matrix.ensure_supplier_approval_setup",
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
            "calco_erp.calco_quality.purchase_receipt_qc.validate_rejected_qty_purchase_return",
            "calco_erp.calco_purchase.import_shipment.validate_purchase_receipt_import_shipment_gate",
        ],
        "before_submit": [
            "calco_erp.calco_quality.purchase_receipt_qc.validate_supplier_documents_and_rm_storage",
        ],
        "on_submit": "calco_erp.thermal_label_setup.handle_purchase_receipt_submit",
    },
    "Purchase Invoice": {
        "validate": "calco_erp.utils.dependencies.validate_purchase_invoice_chain",
    },
    "Request for Quotation": {
        "validate": "calco_erp.calco_purchase.supplier_approval_matrix.validate_request_for_quotation_supplier_matrix",
    },
    "Supplier Quotation": {
        "validate": "calco_erp.calco_purchase.supplier_approval_matrix.validate_supplier_quotation_supplier_matrix",
    },
    "Work Order": {
        "validate": "calco_erp.machine_setup.validate_work_order_machine",
        "before_submit": "calco_erp.utils.dependencies.validate_work_order_material_readiness",
    },
    "Stock Entry": {
        "validate": "calco_erp.machine_setup.validate_stock_entry_machine",
        "before_save": "calco_erp.fg_batch_setup.normalize_rm_batch_consumption_rows",
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
        "on_update_after_submit": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
        "on_submit": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
        "on_cancel": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_quality_inspection",
    },
    "RM Deviation Approval": {
        "on_submit": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_rm_deviation",
        "on_cancel": "calco_erp.calco_quality.purchase_receipt_qc.sync_purchase_receipt_qc_status_from_rm_deviation",
    },
}

doctype_js = {
    "Sales Order": "public/js/sales_order_journey_tracker.js",
    "Request for Quotation": "public/js/request_for_quotation.js",
    "Purchase Receipt": "public/js/barcode_transaction.js",
    "Stock Entry": "public/js/barcode_transaction.js",
    "Delivery Note": "public/js/barcode_transaction.js",
    "Quality Inspection": "public/js/quality_inspection.js",
    "RM QC Decision": "public/js/rm_qc_decision.js",
    "RM Release Note": "public/js/rm_release_note.js",
    "RM Deviation Approval": "public/js/rm_deviation_approval.js",
}

override_whitelisted_methods = {
    "erpnext.stock.doctype.material_request.material_request.make_request_for_quotation": "calco_erp.calco_purchase.supplier_approval_matrix.make_request_for_quotation_with_supplier_matrix",
}
