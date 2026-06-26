__version__ = "0.0.1"


def _ensure_calco_module_map():
    try:
        import frappe

        if not getattr(frappe.local, "site", None):
            return

        module_map = getattr(frappe.local, "module_app", None) or {}
        if "calco_quality" in module_map and "calco_erp" in (getattr(frappe.local, "app_modules", {}) or {}):
            return

        frappe.setup_module_map(include_all_apps=True)
    except Exception:
        return


_ensure_calco_module_map()
