from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import cstr


RM_QI_TEMPLATE_PREFIX = "Calco RM QC - "
MANUAL_APPROVAL_RULES = {"Manual Review", "Reference Only"}


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", cstr(value or "")).strip()


def parse_decimal(value) -> Decimal | None:
    cleaned = normalize_text(value)
    if not cleaned:
        return None

    cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_float(value) -> float | None:
    parsed = parse_decimal(value)
    return float(parsed) if parsed is not None else None


def derive_target_value(acceptable_min=None, acceptable_max=None) -> str:
    min_value = normalize_text(acceptable_min)
    max_value = normalize_text(acceptable_max)

    if min_value and max_value and min_value == max_value:
        return min_value

    for candidate in (max_value, min_value):
        if candidate and parse_decimal(candidate) is None:
            return candidate

    return ""


def derive_approval_rule(acceptable_min=None, acceptable_max=None, target_value=None) -> str:
    min_value = normalize_text(acceptable_min)
    max_value = normalize_text(acceptable_max)
    target = normalize_text(target_value)

    numeric_min = parse_decimal(min_value) if min_value else None
    numeric_max = parse_decimal(max_value) if max_value else None

    if numeric_min is not None and numeric_max is not None:
        return "Numeric Range"

    reference_text = " ".join(filter(None, [min_value.lower(), max_value.lower(), target.lower()]))
    if "refer" in reference_text:
        return "Reference Only"

    if target or min_value or max_value:
        return "Manual Review"

    return "Manual Review"


def infer_result_type_from_rules(rules: list[str]) -> str:
    normalized = set(rules)
    if "Numeric Range" in normalized:
        return "Numeric"
    if normalized.intersection(MANUAL_APPROVAL_RULES):
        return "Manual Review"
    return "Qualitative"


def build_rm_template_name(item_code: str) -> str:
    cleaned = normalize_text(item_code) or "RM"
    return (RM_QI_TEMPLATE_PREFIX + cleaned)[:140]


def resolve_item_by_code_or_name(item_reference: str) -> str | None:
    cleaned = normalize_text(item_reference)
    if not cleaned:
        return None

    if frappe.db.exists("Item", cleaned):
        return cleaned

    for filters in ({"item_code": cleaned}, {"item_name": cleaned}):
        match = frappe.db.get_value("Item", filters, "name")
        if match:
            return match

    return None

