import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import frappe


COMPANY_NAME = "Calco PolyTechnik Pvt Ltd"
RAW_MATERIAL_GROUP = "Raw Material"
FINISHED_GOODS_GROUP = "Finished Goods"
STOCK_UOM = "Kg"


def generated_dir():
    return Path(__file__).resolve().parent / "generated"


def read_csv(filename):
    path = generated_dir() / filename
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_item_group(name):
    if frappe.db.exists("Item Group", name):
        return

    frappe.get_doc(
        {
            "doctype": "Item Group",
            "item_group_name": name,
            "parent_item_group": "All Item Groups",
            "is_group": 0,
        }
    ).insert(ignore_permissions=True)


def ensure_master_prerequisites():
    ensure_item_group(RAW_MATERIAL_GROUP)
    ensure_item_group(FINISHED_GOODS_GROUP)

    if not frappe.db.exists("UOM", STOCK_UOM):
        frappe.get_doc({"doctype": "UOM", "uom_name": STOCK_UOM}).insert(ignore_permissions=True)


def normalize_flag(value):
    return 1 if str(value).strip() in ("1", "True", "true") else 0


def upsert_item(row, item_group):
    item_code = row["item_code"].strip()
    quality_template = (row.get("quality_template") or "").strip()
    payload = {
        "item_code": item_code,
        "item_name": row["item_name"].strip() or item_code,
        "item_group": item_group,
        "stock_uom": STOCK_UOM,
        "is_stock_item": 1,
        "include_item_in_manufacturing": 1,
        "valuation_method": row.get("valuation_method") or ("Moving Average" if item_group == RAW_MATERIAL_GROUP else "FIFO"),
        "has_batch_no": 1,
        "create_new_batch": 1 if item_group == FINISHED_GOODS_GROUP else 0,
        "inspection_required_before_purchase": 1 if item_group == RAW_MATERIAL_GROUP else 0,
        "inspection_required_before_delivery": 1 if item_group == FINISHED_GOODS_GROUP else 0,
        "custom_enable_rm_qc": 1 if item_group == RAW_MATERIAL_GROUP else 0,
        "allow_alternative_item": 0,
        "disabled": 0,
        "description": "",
    }
    if quality_template:
        payload["quality_inspection_template"] = quality_template

    if frappe.db.exists("Item", item_code):
        item = frappe.get_doc("Item", item_code)
        created = False
    else:
        item = frappe.new_doc("Item")
        created = True

    for fieldname, value in payload.items():
        item.set(fieldname, value)

    if created:
        item.insert(ignore_permissions=True)
    else:
        item.save(ignore_permissions=True)

    return created


def validate_no_duplicate_items():
    duplicates = frappe.db.sql(
        """
        select item_code, count(*) as cnt
        from `tabItem`
        group by item_code
        having count(*) > 1
        """
    )
    if duplicates:
        raise frappe.ValidationError(f"Duplicate Item codes detected after import: {duplicates}")


def select_bom_headers():
    rows = read_csv("bom_header.csv")
    selected = {}
    for row in rows:
        item_code = row["item"].strip()
        if not item_code:
            continue
        if row.get("is_default") == "1":
            selected[item_code] = row
        elif item_code not in selected:
            selected[item_code] = row
    return selected


def build_bom_item_map():
    grouped = defaultdict(list)
    for row in read_csv("bom_items.csv"):
        grouped[row["parent"].strip()].append(row)
    return grouped


def ensure_components_exist(component_rows):
    missing = []
    for row in component_rows:
        if not frappe.db.exists("Item", row["item_code"].strip()):
            missing.append(row["item_code"].strip())
    if missing:
        raise frappe.ValidationError(f"BOM components missing in Item master: {sorted(set(missing))[:20]}")


def ensure_total_is_100(component_rows):
    total = sum(float(row["qty"]) for row in component_rows)
    if abs(total - 100.0) > 0.01:
        raise frappe.ValidationError(f"BOM total {total} does not equal 100%.")


def create_bom(header_row, component_rows):
    item_code = header_row["item"].strip()

    existing = frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "docstatus": ("!=", 2)}, "name")
    if existing:
        return False

    ensure_components_exist(component_rows)
    ensure_total_is_100(component_rows)

    bom = frappe.get_doc(
        {
            "doctype": "BOM",
            "item": item_code,
            "company": COMPANY_NAME,
            "quantity": float(header_row["quantity"]),
            "uom": STOCK_UOM,
            "is_active": 1,
            "is_default": 1,
            "allow_alternative_item": 0,
            "set_rate_of_sub_assembly_item_based_on_bom": 0,
            "rm_cost_as_per": "Valuation Rate",
            "with_operations": 0,
            "fg_based_operating_cost": 0,
        }
    )

    for row in component_rows:
        bom.append(
            "items",
            {
                "item_code": row["item_code"].strip(),
                "qty": float(row["qty"]),
                "uom": STOCK_UOM,
                "stock_uom": STOCK_UOM,
                "stock_qty": float(row["stock_qty"]),
                "include_item_in_manufacturing": normalize_flag(row["include_item_in_manufacturing"]),
            },
        )

    bom.insert(ignore_permissions=True)
    bom.submit()
    return True


def import_items():
    rm_rows = read_csv("items_rm.csv")
    fg_rows = read_csv("items_fg.csv")

    rm_created = sum(1 for row in rm_rows if upsert_item(row, RAW_MATERIAL_GROUP))
    fg_created = sum(1 for row in fg_rows if upsert_item(row, FINISHED_GOODS_GROUP))
    validate_no_duplicate_items()
    return rm_created, fg_created, len(rm_rows), len(fg_rows)


def import_boms():
    selected_headers = select_bom_headers()
    item_map = build_bom_item_map()
    created = 0
    validated = 0

    for item_code, header in selected_headers.items():
        component_rows = item_map.get(header["name"].strip(), [])
        ensure_components_exist(component_rows)
        ensure_total_is_100(component_rows)
        validated += 1
        if create_bom(header, component_rows):
            created += 1

    return created, validated


def execute():
    ensure_master_prerequisites()
    rm_created, fg_created, rm_total, fg_total = import_items()
    boms_created, boms_validated = import_boms()

    result = {
        "rm_items_created": rm_created,
        "fg_items_created": fg_created,
        "rm_items_total_in_source": rm_total,
        "fg_items_total_in_source": fg_total,
        "total_items_in_db": frappe.db.count("Item"),
        "boms_created": boms_created,
        "boms_validated": boms_validated,
        "total_boms_in_db": frappe.db.count("BOM"),
    }

    result_path = generated_dir() / "import_result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    frappe.db.commit()
    return result


def main():
    frappe.init(site="frontend", sites_path="/home/frappe/frappe-bench/sites")
    frappe.connect()
    try:
        execute()
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
