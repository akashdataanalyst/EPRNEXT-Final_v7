import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import frappe


GENERATED_DIR = Path(__file__).resolve().parent / "generated"
VERIFICATION_DIR = GENERATED_DIR / "verification"
ROUND_TOLERANCE = Decimal("0.000001")
TOTAL_TOLERANCE = Decimal("0.01")


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def decimalize(value):
    return Decimal(str(value or 0))


def source_bom_name(item_code):
    headers = read_csv(GENERATED_DIR / "bom_header.csv")
    for row in headers:
        if row["item"].strip() == item_code:
            return row["name"].strip()
    return None


def live_bom_name(item_code):
    return frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "docstatus": 1}, "name")


def load_expected_rows(item_code):
    expected_parent = source_bom_name(item_code)
    if not expected_parent:
        return []
    rows = []
    for row in read_csv(GENERATED_DIR / "bom_items.csv"):
        if row["parent"].strip() == expected_parent:
            rows.append(
                {
                    "item_code": row["item_code"].strip(),
                    "qty": decimalize(row["qty"]),
                }
            )
    return rows


def load_live_rows(item_code):
    bom_name = live_bom_name(item_code)
    if not bom_name:
        return None, []
    rows = frappe.get_all(
        "BOM Item",
        filters={"parent": bom_name},
        fields=["name", "item_code", "qty", "idx"],
        order_by="idx asc",
        limit_page_length=500,
    )
    normalized = [
        {
            "name": row.name,
            "item_code": row.item_code,
            "qty": decimalize(row.qty),
            "idx": row.idx,
        }
        for row in rows
    ]
    return bom_name, normalized


def aggregate(rows):
    totals = defaultdict(Decimal)
    counts = Counter()
    for row in rows:
        totals[row["item_code"]] += row["qty"]
        counts[row["item_code"]] += 1
    return totals, counts


def classify(item_code, mismatch_rows):
    expected_rows = load_expected_rows(item_code)
    live_bom, live_rows = load_live_rows(item_code)
    expected_totals, expected_counts = aggregate(expected_rows)
    live_totals, live_counts = aggregate(live_rows)
    all_components = sorted(set(expected_totals) | set(live_totals))
    component_deltas = []
    for component in all_components:
        expected_qty = expected_totals.get(component, Decimal("0"))
        live_qty = live_totals.get(component, Decimal("0"))
        if abs(expected_qty - live_qty) > ROUND_TOLERANCE:
            component_deltas.append(
                {
                    "component": component,
                    "expected_qty": float(expected_qty),
                    "live_qty": float(live_qty),
                    "expected_rows": expected_counts.get(component, 0),
                    "live_rows": live_counts.get(component, 0),
                }
            )

    expected_total = sum(expected_totals.values(), Decimal("0"))
    live_total = sum(live_totals.values(), Decimal("0"))

    root_cause = "Needs Review"
    clear_fix = False
    notes = []

    if not component_deltas and abs(expected_total - live_total) <= TOTAL_TOLERANCE:
        root_cause = "Rounding Issue"
        clear_fix = False
        notes.append("Total difference is within tolerance after aggregation.")
    elif not component_deltas:
        root_cause = "Incorrect Total Basis"
        clear_fix = False
        notes.append("Component totals match, but full BOM total differs from 100%.")
    elif len(component_deltas) == 1:
        delta = component_deltas[0]
        if delta["expected_rows"] != delta["live_rows"]:
            root_cause = "Duplicate Component Row Handling"
            clear_fix = True
            notes.append("Same component appears with different row counts between source and ERP.")
        else:
            root_cause = "Wrong Component Quantity"
            clear_fix = True
            notes.append("Single component total differs while source is otherwise consistent.")
    else:
        repeated_source = [d for d in component_deltas if d["expected_rows"] > 1 or d["live_rows"] > 1]
        if repeated_source:
            root_cause = "Duplicate Component Row Handling"
            clear_fix = True
            notes.append("Multiple repeated component rows were imported inconsistently.")
        elif abs(expected_total - Decimal("100")) > TOTAL_TOLERANCE:
            root_cause = "Source Data Issue"
            clear_fix = False
            notes.append("Source-derived expected total is not 100%.")
        else:
            root_cause = "Wrong Component Quantity"
            clear_fix = True
            notes.append("ERP BOM deviates from normalized source totals.")

    return {
        "item_code": item_code,
        "live_bom": live_bom,
        "expected_source_bom": source_bom_name(item_code),
        "expected_total": float(expected_total),
        "live_total": float(live_total),
        "mismatch_rows": mismatch_rows,
        "component_deltas": component_deltas,
        "root_cause": root_cause,
        "clear_fix": clear_fix,
        "notes": notes,
    }


def replace_bom_items(bom_name, expected_rows):
    bom = frappe.get_doc("BOM", bom_name)
    if bom.docstatus == 1:
        bom.cancel()
        bom.reload()

    bom.items = []
    for row in expected_rows:
        bom.append(
            "items",
            {
                "item_code": row["item_code"],
                "qty": float(row["qty"]),
                "uom": "Kg",
                "stock_uom": "Kg",
                "stock_qty": float(row["qty"]),
                "include_item_in_manufacturing": 1,
            },
        )
    bom.is_active = 1
    bom.is_default = 1
    bom.save(ignore_permissions=True)
    bom.submit()


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def execute(apply_fixes=True):
    mismatch_rows = read_csv(VERIFICATION_DIR / "bom_quantity_mismatches.csv")
    by_item = defaultdict(list)
    for row in mismatch_rows:
        by_item[row["item_code"].strip()].append(row)

    analyses = []
    fixed_items = []
    exception_rows = []

    for item_code in sorted(by_item):
        analysis = classify(item_code, by_item[item_code])
        analyses.append(analysis)
        if apply_fixes and analysis["clear_fix"]:
            replace_bom_items(analysis["live_bom"], load_expected_rows(item_code))
            fixed_items.append(
                {
                    "item_code": item_code,
                    "bom": analysis["live_bom"],
                    "root_cause": analysis["root_cause"],
                }
            )
        else:
            exception_rows.append(
                {
                    "item_code": item_code,
                    "bom": analysis["live_bom"],
                    "root_cause": analysis["root_cause"],
                    "expected_total": analysis["expected_total"],
                    "live_total": analysis["live_total"],
                    "notes": " | ".join(analysis["notes"]),
                }
            )

    # Regenerate mismatch summary after any fixes.
    from calco_erp.data_foundation.manufacturing_test_cycle import verify_master_data

    verification = verify_master_data()

    report = {
        "before_mismatch_count": len(mismatch_rows),
        "after_mismatch_count": verification["bom_quantity_mismatches"],
        "analyses": analyses,
        "fixed_items": fixed_items,
        "exceptions": exception_rows,
    }

    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    (VERIFICATION_DIR / "bom_mismatch_resolution_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv(
        VERIFICATION_DIR / "bom_mismatch_exceptions.csv",
        exception_rows,
        ["item_code", "bom", "root_cause", "expected_total", "live_total", "notes"],
    )
    frappe.db.commit()
    return report


def analyze():
    return execute(apply_fixes=False)


def apply():
    return execute(apply_fixes=True)


def main():
    frappe.init(site="frontend", sites_path="/home/frappe/frappe-bench/sites")
    frappe.connect()
    try:
        print(json.dumps(execute(), indent=2))
    finally:
        frappe.destroy()
