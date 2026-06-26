function calcoIsRmQualityInspection(frm) {
  return (frm.doc.quality_inspection_template || "").startsWith("Calco RM QC -");
}

function calcoIsRmIncomingPurchaseQc(doc) {
  return doc.inspection_type === "Incoming" && doc.reference_type === "Purchase Receipt";
}

function calcoNormalizeRmText(value) {
  return (value || "").toString().replace(/\s+/g, " ").trim().toLowerCase();
}

function calcoGetRmStandardContext(standardMap, specification) {
  const exactKey = (specification || "").toString().replace(/\s+/g, " ").trim();
  if (!exactKey) {
    return null;
  }

  return standardMap[exactKey] || standardMap[calcoNormalizeRmText(exactKey)] || null;
}

function calcoSetRmReadingGridBehavior(frm) {
  const grid = frm.fields_dict.readings && frm.fields_dict.readings.grid;
  if (!grid) {
    return;
  }

  const isRmContext = calcoIsRmIncomingPurchaseQc(frm.doc) || calcoIsRmQualityInspection(frm);
  const isFgContext =
    !isRmContext &&
    Boolean(frm.doc.item_code) &&
    Boolean(frm.__calco_fg_control_plan_active || frm.doc.quality_inspection_template || (frm.doc.readings || []).length);
  const lockedContext = isRmContext || isFgContext;

  frm.set_df_property("status", "read_only", lockedContext ? 1 : 0);
  const readOnlyFields = {
    specification: lockedContext ? 1 : 0,
    numeric: lockedContext ? 1 : 0,
    min_value: 1,
    max_value: 1,
    value: isRmContext ? 1 : 0,
    acceptance_formula: lockedContext ? 1 : 0,
    formula_based_criteria: lockedContext ? 1 : 0,
    status: lockedContext ? 1 : 0,
    manual_inspection: lockedContext ? 1 : 0,
    custom_rm_testing_standard: 1,
    custom_unit: 1,
    custom_test_standard: 1,
    custom_cppl_method: 1,
    custom_test_condition: 1,
    custom_approval_rule: 1,
    custom_critical_test: 1,
    custom_result_label: 1,
    custom_sample_size: 1,
    custom_frequency: 1,
    custom_target_value: 1,
  };

  Object.entries(readOnlyFields).forEach(([fieldname, readOnly]) => {
    grid.update_docfield_property(fieldname, "read_only", readOnly);
  });

  grid.cannot_add_rows = lockedContext;
  grid.cannot_delete_rows = lockedContext;
  if (grid.wrapper) {
    grid.wrapper.find(".grid-add-row, .grid-remove-rows").toggle(!lockedContext);
  }
}

function calcoIsRmIncomingWrongSource(doc) {
  return doc.inspection_type === "Incoming" && doc.reference_type === "Purchase Invoice";
}

function calcoRowHasMeasurement(row) {
  if ((row.reading_value || "").toString().trim()) {
    return true;
  }

  for (let index = 1; index <= 10; index += 1) {
    if ((row[`reading_${index}`] || "").toString().trim()) {
      return true;
    }
  }

  return false;
}

function calcoParseRmNumber(value) {
  const cleaned = (value || "").toString().replace(/,/g, "").trim();
  if (!cleaned) {
    return null;
  }

  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function calcoGetRmMeasurements(row) {
  const measurements = [];

  for (let index = 1; index <= 10; index += 1) {
    const rawValue = (row[`reading_${index}`] || "").toString().trim();
    if (!rawValue) {
      continue;
    }

    const parsedValue = calcoParseRmNumber(rawValue);
    if (parsedValue === null) {
      return null;
    }

    measurements.push(parsedValue);
  }

  if (measurements.length) {
    return measurements;
  }

  const primaryValue = (row.reading_value || "").toString().trim();
  if (!primaryValue) {
    return [];
  }

  const parsedPrimary = calcoParseRmNumber(primaryValue);
  if (parsedPrimary === null) {
    return null;
  }

  row.reading_1 = row.reading_1 || row.reading_value;
  return [parsedPrimary];
}

function calcoIsManualReviewRule(row) {
  return ["Manual Review", "Reference Only"].includes((row.custom_approval_rule || "").trim());
}

function calcoEvaluateRmInspectionState(frm) {
  if (!calcoIsRmIncomingPurchaseQc(frm.doc) && !calcoIsRmQualityInspection(frm)) {
    return;
  }

  let changed = false;
  let pendingMeasurementPresent = false;
  let pendingManualReview = false;
  let criticalFailPresent = false;
  let nonCriticalFailPresent = false;
  const rowStatuses = [];

  (frm.doc.readings || []).forEach((row) => {
    if (!calcoRowHasMeasurement(row)) {
      pendingMeasurementPresent = true;
      if (row.status !== "") {
        row.status = "";
        changed = true;
      }
      if (row.custom_result_label !== "") {
        row.custom_result_label = "";
        changed = true;
      }
      return;
    }

    if (calcoIsManualReviewRule(row)) {
      pendingManualReview = true;
      if (row.status !== "Review Required") {
        row.status = "Review Required";
        changed = true;
      }
      if (row.custom_result_label !== "REVIEW REQUIRED") {
        row.custom_result_label = "REVIEW REQUIRED";
        changed = true;
      }
      rowStatuses.push("Review Required");
      return;
    }

    const measurements = calcoGetRmMeasurements(row);
    const minValue = calcoParseRmNumber(row.min_value);
    const maxValue = calcoParseRmNumber(row.max_value);

    if (!measurements || !measurements.length || minValue === null || maxValue === null) {
      pendingManualReview = true;
      if (row.status !== "Review Required") {
        row.status = "Review Required";
        changed = true;
      }
      if (row.custom_result_label !== "REVIEW REQUIRED") {
        row.custom_result_label = "REVIEW REQUIRED";
        changed = true;
      }
      rowStatuses.push("Review Required");
      return;
    }

    const isAccepted = measurements.every((value) => value >= minValue && value <= maxValue);
    const nextStatus = isAccepted ? "Accepted" : "Rejected";
    const nextResult = isAccepted ? "PASS" : "FAIL";

    if (row.status !== nextStatus) {
      row.status = nextStatus;
      changed = true;
    }
    if (row.custom_result_label !== nextResult) {
      row.custom_result_label = nextResult;
      changed = true;
    }
    rowStatuses.push(nextStatus);

    if (!isAccepted) {
      if (Number(row.custom_critical_test || 0)) {
        criticalFailPresent = true;
      } else {
        nonCriticalFailPresent = true;
      }
    }
  });

  let nextParentStatus = "";
  if (rowStatuses.includes("Rejected")) {
    nextParentStatus = "Rejected";
  } else if (rowStatuses.includes("Review Required")) {
    nextParentStatus = "Review Required";
  } else if (rowStatuses.length && rowStatuses.every((status) => status === "Accepted")) {
    nextParentStatus = "Accepted";
  }

  if (frm.doc.status !== nextParentStatus && frm.doc.status !== "Cancelled") {
    frm.doc.status = nextParentStatus;
    changed = true;
  }

  if (pendingMeasurementPresent) {
    if (frm.doc.custom_overall_result !== "") {
      frm.doc.custom_overall_result = "";
      changed = true;
    }
  } else if (criticalFailPresent) {
    if (frm.doc.custom_overall_result !== "REJECTED") {
      frm.doc.custom_overall_result = "REJECTED";
      changed = true;
    }
    if (frm.doc.status !== "Rejected") {
      frm.doc.status = "Rejected";
      changed = true;
    }
  } else if (nonCriticalFailPresent || pendingManualReview) {
    if (frm.doc.custom_overall_result !== "REVIEW REQUIRED") {
      frm.doc.custom_overall_result = "REVIEW REQUIRED";
      changed = true;
    }
  } else {
    if (frm.doc.custom_overall_result !== "ACCEPTED") {
      frm.doc.custom_overall_result = "ACCEPTED";
      changed = true;
    }
  }

  if (changed) {
    frm.refresh_field("readings");
    frm.refresh_field("custom_overall_result");
    frm.refresh_field("status");
  }
}

function calcoEnforceRmReferenceSource(frm) {
  if (!frm.is_new() || frm.doc.docstatus !== 0 || frm.doc.inspection_type !== "Incoming") {
    return;
  }

  if (!frm.doc.reference_type) {
    frm.set_value("reference_type", "Purchase Receipt");
    return;
  }

  if (frm.doc.reference_type === "Purchase Invoice") {
    frappe.show_alert({
      message: __("Raw material incoming QC uses Purchase Receipt as the reference source."),
      indicator: "orange",
    });

    if (frm.doc.reference_name || frm.doc.item_code || frm.doc.batch_no || frm.doc.quality_inspection_template) {
      frm.set_value("reference_name", "");
      frm.set_value("item_code", "");
      frm.set_value("batch_no", "");
      frm.set_value("quality_inspection_template", "");
      frm.clear_table("readings");
      frm.refresh_field("readings");
    }

    frm.set_value("reference_type", "Purchase Receipt");
  }
}

function calcoUpdateRmReferenceFieldUx(frm) {
  const field = frm.get_field("reference_name");
  if (!field || !field.$input) {
    return;
  }

  field.$input.off(".calco_rm_reference");

  if (calcoIsRmIncomingPurchaseQc(frm.doc)) {
    frm.set_df_property(
      "reference_name",
      "description",
      __("Pending Purchase Receipts only. Click the field or type MAT-PRE, supplier, or item code. Newest pending receipts appear first.")
    );
    field.$input.attr(
      "placeholder",
      __("Search pending Purchase Receipt by receipt no, supplier, or item code")
    );

    const triggerSuggestions = () => {
      window.setTimeout(() => {
        if (!field.$input.val()) {
          field.$input.trigger("input");
          field.$input.trigger("keyup");
        }
      }, 0);
    };

    field.$input.on("focus.calco_rm_reference", triggerSuggestions);
    field.$input.on("click.calco_rm_reference", triggerSuggestions);
    return;
  }

  if (calcoIsRmIncomingWrongSource(frm.doc)) {
    frm.set_df_property(
      "reference_name",
      "description",
      __("Raw material incoming QC uses Purchase Receipt as the reference source.")
    );
  } else {
    frm.set_df_property("reference_name", "description", "");
  }

  field.$input.attr("placeholder", "");
}

function calcoAutoFetchRmBatch(frm) {
  if (
    !calcoIsRmIncomingPurchaseQc(frm.doc) ||
    !frm.doc.reference_name ||
    !frm.doc.item_code ||
    frm.doc.batch_no
  ) {
    return;
  }

  frappe.call({
    method: "calco_erp.calco_quality.quality_inspection_queries.get_single_pending_rm_batch",
    args: {
      reference_name: frm.doc.reference_name,
      item_code: frm.doc.item_code,
    },
  }).then((response) => {
    const batchNo = response.message;
    if (batchNo && !frm.doc.batch_no) {
      frm.set_value("batch_no", batchNo);
    }
  });
}

function calcoQueueRmReadingStandards(frm) {
  frappe.after_ajax(() => {
    window.setTimeout(() => calcoApplyRmReadingStandards(frm), 0);
  });
}

function calcoIsFgManagedInspection(frm) {
  return !calcoIsRmIncomingPurchaseQc(frm.doc) && !calcoIsRmQualityInspection(frm) && Boolean(frm.doc.item_code);
}

function calcoFgRowHasMeasurement(row) {
  if ((row.value || "").toString().trim()) {
    return true;
  }

  return calcoRowHasMeasurement(row);
}

function calcoGetFgMeasurements(row) {
  const measurements = calcoGetRmMeasurements(row);
  if (measurements && measurements.length) {
    return measurements;
  }

  const rawValue = (row.value || "").toString().trim();
  if (!rawValue) {
    return measurements;
  }

  const parsedValue = calcoParseRmNumber(rawValue);
  if (parsedValue === null) {
    return null;
  }

  return [parsedValue];
}

function calcoIsFgManualReviewRow(row) {
  const manualSpecs = new Set([
    "color variation (black spot free)",
    "finish (shine/dull)",
    "long cut",
    "metal contamination",
  ]);
  const minValue = calcoParseRmNumber(row.min_value);
  const maxValue = calcoParseRmNumber(row.max_value);

  return (
    manualSpecs.has(calcoNormalizeRmText(row.specification)) ||
    Number(row.manual_inspection || 0) === 1 ||
    (minValue === null && maxValue === null)
  );
}

function calcoEvaluateFgInspectionState(frm) {
  if (!calcoIsFgManagedInspection(frm)) {
    return;
  }

  let changed = false;
  let pendingMeasurementPresent = false;
  let rejectedPresent = false;
  let reviewRequiredPresent = false;
  const rowStatuses = [];

  (frm.doc.readings || []).forEach((row) => {
    if (!calcoFgRowHasMeasurement(row)) {
      pendingMeasurementPresent = true;
      if (row.status !== "") {
        row.status = "";
        changed = true;
      }
      if (row.custom_result_label !== "") {
        row.custom_result_label = "";
        changed = true;
      }
      return;
    }

    if (calcoIsFgManualReviewRow(row)) {
      if (row.status !== "Review Required") {
        row.status = "Review Required";
        changed = true;
      }
      if (row.custom_result_label !== "REVIEW REQUIRED") {
        row.custom_result_label = "REVIEW REQUIRED";
        changed = true;
      }
      rowStatuses.push("Review Required");
      reviewRequiredPresent = true;
      return;
    }

    const measurements = calcoGetFgMeasurements(row);
    const minValue = calcoParseRmNumber(row.min_value);
    const maxValue = calcoParseRmNumber(row.max_value);

    if (!measurements || !measurements.length || (minValue === null && maxValue === null)) {
      if (row.status !== "Review Required") {
        row.status = "Review Required";
        changed = true;
      }
      if (row.custom_result_label !== "REVIEW REQUIRED") {
        row.custom_result_label = "REVIEW REQUIRED";
        changed = true;
      }
      rowStatuses.push("Review Required");
      reviewRequiredPresent = true;
      return;
    }

    const isAccepted = measurements.every((value) => {
      if (minValue !== null && value < minValue) {
        return false;
      }
      if (maxValue !== null && value > maxValue) {
        return false;
      }
      return true;
    });
    const nextStatus = isAccepted ? "Accepted" : "Rejected";
    const nextResult = isAccepted ? "PASS" : "FAIL";

    if (row.status !== nextStatus) {
      row.status = nextStatus;
      changed = true;
    }
    if (row.custom_result_label !== nextResult) {
      row.custom_result_label = nextResult;
      changed = true;
    }
    rowStatuses.push(nextStatus);
    if (!isAccepted) {
      rejectedPresent = true;
    }
  });

  let nextParentStatus = "";
  if (rowStatuses.includes("Rejected")) {
    nextParentStatus = "Rejected";
  } else if (rowStatuses.includes("Review Required")) {
    nextParentStatus = "Review Required";
  } else if (
    rowStatuses.length &&
    rowStatuses.length === (frm.doc.readings || []).length &&
    rowStatuses.every((status) => status === "Accepted")
  ) {
    nextParentStatus = "Accepted";
  }

  if (frm.doc.status !== nextParentStatus && frm.doc.status !== "Cancelled") {
    frm.doc.status = nextParentStatus;
    changed = true;
  }

  let nextOverallResult = "";
  if (rejectedPresent) {
    nextOverallResult = "REJECTED";
  } else if (reviewRequiredPresent) {
    nextOverallResult = "REVIEW REQUIRED";
  } else if (pendingMeasurementPresent) {
    nextOverallResult = "";
  } else if (rowStatuses.length && rowStatuses.every((status) => status === "Accepted")) {
    nextOverallResult = "ACCEPTED";
  }

  if ((frm.doc.custom_overall_result || "") !== nextOverallResult) {
    frm.doc.custom_overall_result = nextOverallResult;
    changed = true;
  }

  if (changed) {
    frm.refresh_field("readings");
    frm.refresh_field("custom_overall_result");
    frm.refresh_field("status");
  }
}

function calcoEvaluateInspectionState(frm) {
  if (calcoIsRmIncomingPurchaseQc(frm.doc) || calcoIsRmQualityInspection(frm)) {
    calcoEvaluateRmInspectionState(frm);
    return;
  }

  calcoEvaluateFgInspectionState(frm);
}

function calcoFgRowHasUserInput(row) {
  if ((row.value || "").toString().trim()) {
    return true;
  }

  if ((row.reading_value || "").toString().trim()) {
    return true;
  }

  for (let index = 1; index <= 10; index += 1) {
    if ((row[`reading_${index}`] || "").toString().trim()) {
      return true;
    }
  }

  return false;
}

function calcoFgReadingsMatchPlan(currentRows, planRows) {
  if ((currentRows || []).length !== (planRows || []).length) {
    return false;
  }

  return (currentRows || []).every((row, index) => (
    calcoNormalizeRmText(row.specification) === calcoNormalizeRmText((planRows[index] || {}).specification)
  ));
}

function calcoBuildFgReading(existingRow, planRow) {
  const row = {
    specification: planRow.specification,
    numeric: planRow.numeric ? 1 : 0,
    manual_inspection: planRow.manual_inspection ? 1 : 0,
    min_value: planRow.min_value,
    max_value: planRow.max_value,
    custom_unit: planRow.custom_unit,
    custom_sample_size: planRow.custom_sample_size,
    custom_frequency: planRow.custom_frequency,
    custom_target_value: planRow.custom_target_value,
    custom_critical_test: planRow.custom_critical_test ? 1 : 0,
    acceptance_formula: "",
    formula_based_criteria: 0,
  };

  if (!existingRow) {
    return row;
  }

  [
    "value",
    "reading_value",
    "reading_1",
    "reading_2",
    "reading_3",
    "reading_4",
    "reading_5",
    "reading_6",
    "reading_7",
    "reading_8",
    "reading_9",
    "reading_10",
  ].forEach((fieldname) => {
    if (existingRow[fieldname] !== undefined && existingRow[fieldname] !== null && existingRow[fieldname] !== "") {
      row[fieldname] = existingRow[fieldname];
    }
  });

  return row;
}

function calcoQueueFgControlPlanSync(frm, forceReplace = false) {
  frappe.after_ajax(() => {
    window.setTimeout(() => calcoApplyFgControlPlan(frm, forceReplace), 0);
  });
}

function calcoLoadFgTemplateReadings(frm, forceReplace = false) {
  if (!frm.doc.quality_inspection_template) {
    return Promise.resolve();
  }

  const currentRows = frm.doc.readings || [];
  const hasExistingInput = currentRows.some(calcoFgRowHasUserInput);
  if (!forceReplace && (hasExistingInput || currentRows.length)) {
    return Promise.resolve();
  }

  return frm.call({
    method: "get_item_specification_details",
    doc: frm.doc,
  }).then(() => {
    frm.refresh_field("readings");
    calcoSetRmReadingGridBehavior(frm);
    calcoEvaluateInspectionState(frm);
  });
}

function calcoApplyFgControlPlan(frm, forceReplace = false) {
  if (!frm.doc.item_code || calcoIsRmIncomingPurchaseQc(frm.doc) || calcoIsRmQualityInspection(frm)) {
    frm.__calco_fg_control_plan_active = false;
    calcoSetRmReadingGridBehavior(frm);
    calcoEvaluateInspectionState(frm);
    return;
  }

  frappe.call({
    method: "calco_erp.calco_quality.fg_quality_setup.get_fg_inspection_context",
    args: {
      item_code: frm.doc.item_code,
    },
  }).then((response) => {
    const payload = response.message || {};
    const templateName = payload.quality_inspection_template || "";
    const planRows = payload.readings || [];
    const emptyMessage = payload.empty_message || __("No QC parameters defined for this grade.");
    const currentRows = frm.doc.readings || [];
    const hasExistingInput = currentRows.some(calcoFgRowHasUserInput);
    const rowsMatchPlan = calcoFgReadingsMatchPlan(currentRows, planRows);

    frm.__calco_fg_control_plan_active = Boolean(payload.use_control_plan);
    calcoSetRmReadingGridBehavior(frm);

    if (templateName && frm.doc.quality_inspection_template !== templateName) {
      return frm.set_value("quality_inspection_template", templateName);
    }

    if (!payload.use_control_plan) {
      return calcoLoadFgTemplateReadings(frm, forceReplace).then(() => calcoEvaluateInspectionState(frm));
    }

    if (!forceReplace && hasExistingInput) {
      return;
    }

    if (!forceReplace && rowsMatchPlan) {
      return;
    }

    const existingRowsBySpec = {};
    currentRows.forEach((row) => {
      const key = calcoNormalizeRmText(row.specification);
      if (!existingRowsBySpec[key]) {
        existingRowsBySpec[key] = [];
      }
      existingRowsBySpec[key].push(row);
    });

    frm.clear_table("readings");
    planRows.forEach((planRow) => {
      const key = calcoNormalizeRmText(planRow.specification);
      const existingRow = (existingRowsBySpec[key] || []).shift();
      frm.add_child("readings", calcoBuildFgReading(existingRow, planRow));
    });
    const sampleSizes = planRows
      .map((planRow) => Number(planRow.custom_sample_size || 0))
      .filter((value) => Number.isFinite(value) && value > 0);
    frm.doc.sample_size = sampleSizes.length ? Math.max(...sampleSizes) : "";
    frm.refresh_field("readings");
    frm.refresh_field("sample_size");
    calcoSetRmReadingGridBehavior(frm);
    calcoEvaluateInspectionState(frm);

    if (!planRows.length && forceReplace) {
      frappe.show_alert({
        message: emptyMessage,
        indicator: "orange",
      });
    }
  });
}

function calcoApplyRmReadingStandards(frm) {
  if (!frm.doc.item_code || !(frm.doc.readings || []).length) {
    return;
  }

  if (!calcoIsRmIncomingPurchaseQc(frm.doc) && !calcoIsRmQualityInspection(frm)) {
    return;
  }

  frappe.call({
    method: "calco_erp.calco_quality.rm_quality_setup.get_rm_reading_context",
    args: {
      item_code: frm.doc.item_code,
      specifications: (frm.doc.readings || []).map((row) => row.specification).filter(Boolean),
    },
  }).then((response) => {
    const standardMap = response.message || {};
    let changed = false;

    (frm.doc.readings || []).forEach((row) => {
      const standard = calcoGetRmStandardContext(standardMap, row.specification);
      const minValue =
        standard && standard.approval_rule === "Numeric Range" ? standard.min_value : null;
      const maxValue =
        standard && standard.approval_rule === "Numeric Range" ? standard.max_value : null;

      if (row.min_value !== minValue) {
        row.min_value = minValue;
        changed = true;
      }

      if (row.max_value !== maxValue) {
        row.max_value = maxValue;
        changed = true;
      }
    });

    if (changed) {
      frm.refresh_field("readings");
    }

    calcoEvaluateInspectionState(frm);
  });
}

function calcoSetRmPendingQueries(frm) {
  frm.set_query("reference_name", function (doc) {
    if (calcoIsRmIncomingPurchaseQc(doc)) {
      return {
        query: "calco_erp.calco_quality.quality_inspection_queries.pending_rm_reference_name_query",
        filters: {
          company: doc.company || "",
        },
      };
    }

    if (calcoIsRmIncomingWrongSource(doc)) {
      return {
        query: "calco_erp.calco_quality.quality_inspection_queries.unsupported_rm_reference_query",
      };
    }

    const filters = { docstatus: ["!=", 2] };
    if (doc.company) {
      filters.company = doc.company;
    }
    return { filters };
  });

  frm.set_query("item_code", function (doc) {
    if (calcoIsRmIncomingPurchaseQc(doc) && doc.reference_name) {
      return {
        query: "calco_erp.calco_quality.quality_inspection_queries.pending_rm_item_query",
        filters: {
          reference_name: doc.reference_name,
        },
      };
    }

    let from_doctype = doc.reference_type;
    if (doc.reference_type !== "Job Card") {
      from_doctype =
        doc.reference_type === "Stock Entry" ? "Stock Entry Detail" : `${doc.reference_type} Item`;
    }

    if (doc.reference_type && doc.reference_name) {
      const filters = {
        from: from_doctype,
        inspection_type: doc.inspection_type,
      };

      if (doc.reference_type === from_doctype) {
        filters.reference_name = doc.reference_name;
      } else {
        filters.parent = doc.reference_name;
      }

      return {
        query: "erpnext.stock.doctype.quality_inspection.quality_inspection.item_query",
        filters,
      };
    }
  });

  frm.set_query("batch_no", function (doc) {
    if (calcoIsRmIncomingPurchaseQc(doc) && doc.reference_name) {
      return {
        query: "calco_erp.calco_quality.quality_inspection_queries.pending_rm_batch_query",
        filters: {
          reference_name: doc.reference_name,
          item_code: doc.item_code || "",
        },
      };
    }

    return {
      filters: {
        item: doc.item_code,
      },
    };
  });
}

frappe.ui.form.on("Quality Inspection", {
  setup(frm) {
    frm.__calco_fg_control_plan_active = false;
    calcoSetRmPendingQueries(frm);
    calcoSetRmReadingGridBehavior(frm);
  },

  refresh(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoEnforceRmReferenceSource(frm);
    calcoSetRmPendingQueries(frm);
    calcoUpdateRmReferenceFieldUx(frm);
    calcoQueueRmReadingStandards(frm);
    calcoQueueFgControlPlanSync(frm, false);
    calcoEvaluateInspectionState(frm);
  },

  item_code(frm) {
    calcoSetRmReadingGridBehavior(frm);
    frappe.after_ajax(() => {
      calcoAutoFetchRmBatch(frm);
      calcoQueueRmReadingStandards(frm);
      calcoQueueFgControlPlanSync(frm, true);
      calcoEvaluateInspectionState(frm);
    });
  },

  quality_inspection_template(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoQueueRmReadingStandards(frm);
    calcoQueueFgControlPlanSync(frm, false);
    frappe.after_ajax(() => {
      calcoEvaluateInspectionState(frm);
    });
  },

  inspection_type(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoEnforceRmReferenceSource(frm);
    calcoSetRmPendingQueries(frm);
    calcoUpdateRmReferenceFieldUx(frm);
  },

  reference_type(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoEnforceRmReferenceSource(frm);
    calcoSetRmPendingQueries(frm);
    calcoUpdateRmReferenceFieldUx(frm);
  },

  reference_name(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoSetRmPendingQueries(frm);
    calcoAutoFetchRmBatch(frm);
    calcoQueueRmReadingStandards(frm);
    calcoUpdateRmReferenceFieldUx(frm);
  },

  company(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoSetRmPendingQueries(frm);
    calcoUpdateRmReferenceFieldUx(frm);
    calcoQueueRmReadingStandards(frm);
  },
});

const rmReadingHandlers = {};
[
  "reading_value",
  "reading_1",
  "reading_2",
  "reading_3",
  "reading_4",
  "reading_5",
  "reading_6",
  "reading_7",
  "reading_8",
  "reading_9",
  "reading_10",
].forEach((fieldname) => {
  rmReadingHandlers[fieldname] = function (frm) {
    calcoEvaluateInspectionState(frm);
  };
});

rmReadingHandlers.value = function (frm) {
  calcoEvaluateInspectionState(frm);
};

frappe.ui.form.on("Quality Inspection Reading", rmReadingHandlers);
