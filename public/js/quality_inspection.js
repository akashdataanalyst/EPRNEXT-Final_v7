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
  const isFgControlPlanContext = Boolean(frm.__calco_fg_control_plan_active);
  const lockedContext = isRmContext || isFgContext;

  frm.set_df_property("status", "read_only", lockedContext ? 1 : 0);
  const readOnlyFields = {
    specification: lockedContext ? 1 : 0,
    numeric: lockedContext ? 1 : 0,
    min_value: 1,
    max_value: 1,
    value: isRmContext || isFgControlPlanContext ? 1 : 0,
    reading_value: isFgControlPlanContext ? 1 : 0,
    reading_1: isFgControlPlanContext ? 1 : 0,
    reading_2: isFgControlPlanContext ? 1 : 0,
    reading_3: isFgControlPlanContext ? 1 : 0,
    reading_4: isFgControlPlanContext ? 1 : 0,
    reading_5: isFgControlPlanContext ? 1 : 0,
    reading_6: isFgControlPlanContext ? 1 : 0,
    reading_7: isFgControlPlanContext ? 1 : 0,
    reading_8: isFgControlPlanContext ? 1 : 0,
    reading_9: isFgControlPlanContext ? 1 : 0,
    reading_10: isFgControlPlanContext ? 1 : 0,
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
    custom_required_tests: 1,
    custom_test_sequence: 1,
    custom_target_value: 1,
    custom_parameter_result: 1,
    custom_parameter_key: 1,
  };

  Object.entries(readOnlyFields).forEach(([fieldname, readOnly]) => {
    grid.update_docfield_property(fieldname, "read_only", readOnly);
  });

  grid.cannot_add_rows = lockedContext;
  grid.cannot_delete_rows = lockedContext;
  if (grid.wrapper) {
    grid.wrapper.find(".grid-add-row, .grid-remove-rows").toggle(!lockedContext);
  }

  calcoSetFgSampleGridBehavior(frm, isFgControlPlanContext);
}

function calcoSetFgSampleGridBehavior(frm, isFgContext = null) {
  const field = frm.fields_dict.parameter_samples;
  if (!field || !field.grid) {
    return;
  }

  const fgContext = isFgContext !== null ? isFgContext : calcoIsFgManagedInspection(frm);
  const grid = field.grid;
  const readOnlyFields = {
    parameter: 1,
    sample_no: 1,
    result: 1,
    parameter_key: 1,
    reading: fgContext ? 0 : 1,
  };

  Object.entries(readOnlyFields).forEach(([fieldname, readOnly]) => {
    grid.update_docfield_property(fieldname, "read_only", readOnly);
  });

  grid.cannot_add_rows = fgContext;
  grid.cannot_delete_rows = fgContext;
  frm.toggle_display("parameter_samples", fgContext);
  if (grid.wrapper) {
    grid.wrapper.find(".grid-add-row, .grid-remove-rows").toggle(!fgContext);
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

function calcoGetFgParameterGroupKey(row, index) {
  return (
    (row.custom_parameter_key || "").toString().trim() ||
    (row.specification || "").toString().trim() ||
    `row-${index + 1}`
  );
}

function calcoGetFgParameterSampleMap(frm) {
  const sampleMap = {};

  (frm.doc.parameter_samples || [])
    .slice()
    .sort((left, right) => {
      const leftKey = calcoNormalizeRmText(left.parameter_key);
      const rightKey = calcoNormalizeRmText(right.parameter_key);
      if (leftKey !== rightKey) {
        return leftKey.localeCompare(rightKey);
      }
      return Number(left.sample_no || 0) - Number(right.sample_no || 0);
    })
    .forEach((row) => {
      const key = calcoNormalizeRmText(row.parameter_key);
      if (!sampleMap[key]) {
        sampleMap[key] = [];
      }
      sampleMap[key].push(row);
    });

  return sampleMap;
}

function calcoFgSampleHasInput(sampleRow) {
  return Boolean(((sampleRow.reading || "").toString().trim()) || ((sampleRow.result || "").toString().trim()));
}

function calcoFgSampleHasReading(sampleRow) {
  return Boolean((sampleRow.reading || "").toString().trim());
}

function calcoGetFgSampleExtent(sampleRows) {
  let lastNonEmptyIndex = 0;

  (sampleRows || []).forEach((row, index) => {
    if (calcoFgSampleHasInput(row)) {
      lastNonEmptyIndex = index + 1;
    }
  });

  return lastNonEmptyIndex;
}

function calcoGetFgRelevantSampleRows(row, sampleRows) {
  if (!(sampleRows || []).length) {
    return [];
  }

  const requiredTests = Number(row.custom_required_tests || 0);
  const sampleExtent = calcoGetFgSampleExtent(sampleRows);
  return sampleRows.slice(0, Math.max(requiredTests, sampleExtent));
}

function calcoSetFgParentResult(row, parameterResult) {
  row.status = parameterResult;
  row.custom_parameter_result = parameterResult;

  if (parameterResult === "Accepted") {
    row.custom_result_label = "PASS";
  } else if (parameterResult === "Rejected") {
    row.custom_result_label = "FAIL";
  } else if (parameterResult === "Review Required") {
    row.custom_result_label = "REVIEW REQUIRED";
  } else {
    row.custom_result_label = "";
  }
}

function calcoEvaluateFgNumericSampleResult(row, sampleRow) {
  const measurement = calcoParseRmNumber(sampleRow.reading);
  const minValue = calcoParseRmNumber(row.min_value);
  const maxValue = calcoParseRmNumber(row.max_value);

  if (measurement === null || (minValue === null && maxValue === null)) {
    return null;
  }
  if (minValue !== null && measurement < minValue) {
    return false;
  }
  if (maxValue !== null && measurement > maxValue) {
    return false;
  }
  return true;
}

function calcoEvaluateFgInspectionState(frm) {
  if (!calcoIsFgManagedInspection(frm)) {
    return;
  }

  let changed = false;
  let pendingMeasurementPresent = false;
  let criticalRejectedPresent = false;
  let nonCriticalRejectedPresent = false;
  let reviewRequiredPresent = false;
  const parameterResults = [];
  const sampleMap = calcoGetFgParameterSampleMap(frm);
  let manualRowPresent = false;

  (frm.doc.readings || []).forEach((row, index) => {
    const allSampleRows = sampleMap[calcoNormalizeRmText(calcoGetFgParameterGroupKey(row, index))] || [];
    const sampleRows = calcoGetFgRelevantSampleRows(row, allSampleRows);
    let groupHasReview = false;
    let groupHasRejected = false;
    let groupHasPending = false;
    const groupIsCritical = Number(row.custom_critical_test || 0) === 1;

    if (calcoIsFgManualReviewRow(row)) {
      manualRowPresent = true;
    }

    if (allSampleRows.length) {
      allSampleRows.forEach((sampleRow) => {
        if ((sampleRow.result || "") !== "") {
          sampleRow.result = "";
          changed = true;
        }
      });

      sampleRows.forEach((sampleRow) => {
        if (!calcoFgSampleHasReading(sampleRow)) {
          groupHasPending = true;
          pendingMeasurementPresent = true;
          return;
        }

        if (calcoIsFgManualReviewRow(row)) {
          if (sampleRow.result !== "Review Required") {
            sampleRow.result = "Review Required";
            changed = true;
          }
          groupHasReview = true;
          return;
        }

        const sampleResult = calcoEvaluateFgNumericSampleResult(row, sampleRow);
        if (sampleResult === null) {
          if (sampleRow.result !== "Review Required") {
            sampleRow.result = "Review Required";
            changed = true;
          }
          groupHasReview = true;
          return;
        }

        const nextSampleResult = sampleResult ? "Pass" : "Fail";
        if (sampleRow.result !== nextSampleResult) {
          sampleRow.result = nextSampleResult;
          changed = true;
        }
        if (!sampleResult) {
          groupHasRejected = true;
        }
      });
    } else if (!calcoFgRowHasMeasurement(row)) {
      groupHasPending = true;
      pendingMeasurementPresent = true;
    } else if (calcoIsFgManualReviewRow(row)) {
      groupHasReview = true;
    } else {
      const measurements = calcoGetFgMeasurements(row);
      const minValue = calcoParseRmNumber(row.min_value);
      const maxValue = calcoParseRmNumber(row.max_value);

      if (!measurements || !measurements.length || (minValue === null && maxValue === null)) {
        groupHasReview = true;
      } else {
        const isAccepted = measurements.every((value) => {
          if (minValue !== null && value < minValue) {
            return false;
          }
          if (maxValue !== null && value > maxValue) {
            return false;
          }
          return true;
        });
        if (!isAccepted) {
          groupHasRejected = true;
        }
      }
    }

    let parameterResult = "";
    if (groupHasRejected) {
      parameterResult = "Rejected";
    } else if (groupHasReview) {
      parameterResult = "Review Required";
    } else if (groupHasPending) {
      parameterResult = "";
    } else if (sampleRows.length || calcoFgRowHasMeasurement(row)) {
      parameterResult = "Accepted";
    }

    if (
      row.status !== parameterResult ||
      (row.custom_parameter_result || "") !== parameterResult ||
      (parameterResult === "Accepted" && row.custom_result_label !== "PASS") ||
      (parameterResult === "Rejected" && row.custom_result_label !== "FAIL") ||
      (parameterResult === "Review Required" && row.custom_result_label !== "REVIEW REQUIRED") ||
      (!parameterResult && row.custom_result_label !== "")
    ) {
      calcoSetFgParentResult(row, parameterResult);
      changed = true;
    }

    if (parameterResult) {
      parameterResults.push(parameterResult);
    }
    if (parameterResult === "Rejected") {
      if (groupIsCritical) {
        criticalRejectedPresent = true;
      } else {
        nonCriticalRejectedPresent = true;
      }
    } else if (parameterResult === "Review Required") {
      reviewRequiredPresent = true;
    }
  });

  const nextManualInspection = manualRowPresent ? 1 : 0;
  if (Number(frm.doc.manual_inspection || 0) !== nextManualInspection) {
    frm.doc.manual_inspection = nextManualInspection;
    changed = true;
  }

  let nextParentStatus = "";
  if (criticalRejectedPresent) {
    nextParentStatus = "Rejected";
  } else if (reviewRequiredPresent || nonCriticalRejectedPresent) {
    nextParentStatus = "Review Required";
  } else if (
    parameterResults.length &&
    parameterResults.length === (frm.doc.readings || []).length &&
    parameterResults.every((status) => status === "Accepted")
  ) {
    nextParentStatus = "Accepted";
  }

  if (frm.doc.status !== nextParentStatus && frm.doc.status !== "Cancelled") {
    frm.doc.status = nextParentStatus;
    changed = true;
  }

  let nextOverallResult = "";
  if (criticalRejectedPresent) {
    nextOverallResult = "REJECTED";
  } else if (reviewRequiredPresent || nonCriticalRejectedPresent) {
    nextOverallResult = "REVIEW REQUIRED";
  } else if (pendingMeasurementPresent) {
    nextOverallResult = "";
  } else if (parameterResults.length && parameterResults.every((status) => status === "Accepted")) {
    nextOverallResult = "ACCEPTED";
  }

  if ((frm.doc.custom_overall_result || "") !== nextOverallResult) {
    frm.doc.custom_overall_result = nextOverallResult;
    changed = true;
  }

  if (changed) {
    frm.refresh_field("readings");
    frm.refresh_field("parameter_samples");
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

function calcoFgSampleRowHasUserInput(row) {
  return Boolean(((row.reading || "").toString().trim()) || ((row.result || "").toString().trim()));
}

function calcoFgInspectionHasUserInput(frm) {
  return (
    (frm.doc.readings || []).some(calcoFgRowHasUserInput) ||
    (frm.doc.parameter_samples || []).some(calcoFgSampleRowHasUserInput)
  );
}

function calcoFgReadingsMatchPlan(currentRows, planRows) {
  if ((currentRows || []).length !== (planRows || []).length) {
    return false;
  }

  return (currentRows || []).every((row, index) => {
    const planRow = planRows[index] || {};
    return (
      calcoNormalizeRmText(row.specification) === calcoNormalizeRmText(planRow.specification) &&
      calcoNormalizeRmText(row.custom_parameter_key) === calcoNormalizeRmText(planRow.custom_parameter_key) &&
      Number(row.custom_required_tests || 0) === Number(planRow.custom_required_tests || 0)
    );
  });
}

function calcoFgSamplesMatchPlan(currentSampleRows, planSampleRows) {
  if ((currentSampleRows || []).length !== (planSampleRows || []).length) {
    return false;
  }

  return (currentSampleRows || []).every((row, index) => {
    const planRow = planSampleRows[index] || {};
    return (
      calcoNormalizeRmText(row.parameter_key) === calcoNormalizeRmText(planRow.parameter_key) &&
      calcoNormalizeRmText(row.parameter) === calcoNormalizeRmText(planRow.parameter) &&
      Number(row.sample_no || 0) === Number(planRow.sample_no || 0)
    );
  });
}

function calcoBuildFgReading(planRow) {
  return {
    specification: planRow.specification,
    numeric: planRow.numeric ? 1 : 0,
    manual_inspection: planRow.manual_inspection ? 1 : 0,
    min_value: planRow.min_value,
    max_value: planRow.max_value,
    custom_unit: planRow.custom_unit,
    custom_sample_size: planRow.custom_sample_size,
    custom_frequency: planRow.custom_frequency,
    custom_required_tests: planRow.custom_required_tests,
    custom_test_sequence: 0,
    custom_target_value: planRow.custom_target_value,
    custom_parameter_result: planRow.custom_parameter_result || "",
    custom_parameter_key: planRow.custom_parameter_key,
    custom_critical_test: planRow.custom_critical_test ? 1 : 0,
    acceptance_formula: "",
    formula_based_criteria: 0,
  };
}

function calcoCollectFgSampleEntries(sampleRows, planRowsByKey) {
  const entries = {};

  (sampleRows || [])
    .slice()
    .sort((left, right) => {
      const leftKey = calcoNormalizeRmText(left.parameter_key);
      const rightKey = calcoNormalizeRmText(right.parameter_key);
      if (leftKey !== rightKey) {
        return leftKey.localeCompare(rightKey);
      }
      return Number(left.sample_no || 0) - Number(right.sample_no || 0);
    })
    .forEach((row) => {
      const key = calcoNormalizeRmText(row.parameter_key);
      if (!key || !planRowsByKey[key]) {
        return;
      }

      if (!entries[key]) {
        entries[key] = [];
      }
      entries[key].push({
        reading: (row.reading || "").toString().trim(),
        result: (row.result || "").toString().trim(),
      });
    });

  return entries;
}

function calcoExtractLegacyFgSampleValues(row) {
  const readings = [];

  for (let index = 1; index <= 10; index += 1) {
    const value = (row[`reading_${index}`] || "").toString().trim();
    if (value) {
      readings.push(value);
    }
  }

  if (readings.length) {
    return readings;
  }

  const primaryValue = (row.reading_value || row.value || "").toString().trim();
  return primaryValue ? [primaryValue] : [];
}

function calcoCollectLegacyFgSampleEntries(currentRows, planRows, planRowsByKey, planRowsBySpec) {
  const entries = {};

  (currentRows || []).forEach((row) => {
    const parameterKey = calcoNormalizeRmText(row.custom_parameter_key);
    const specification = calcoNormalizeRmText(row.specification);
    const planRow = (parameterKey && planRowsByKey[parameterKey]) || planRowsBySpec[specification];
    if (!planRow) {
      return;
    }

    const key = calcoNormalizeRmText(planRow.custom_parameter_key);
    if (!entries[key]) {
      entries[key] = [];
    }
    calcoExtractLegacyFgSampleValues(row).forEach((reading) => {
      entries[key].push({ reading, result: "" });
    });
  });

  return entries;
}

function calcoGetFgPreservedSampleEntries(currentRows, currentSampleRows, planRows) {
  const planRowsByKey = {};
  const planRowsBySpec = {};

  (planRows || []).forEach((row) => {
    planRowsByKey[calcoNormalizeRmText(row.custom_parameter_key)] = row;
    planRowsBySpec[calcoNormalizeRmText(row.specification)] = row;
  });

  const sampleEntries = calcoCollectFgSampleEntries(currentSampleRows, planRowsByKey);
  if (calcoPreservedFgSampleEntriesHaveInput(sampleEntries)) {
    return sampleEntries;
  }

  return calcoCollectLegacyFgSampleEntries(currentRows, planRows, planRowsByKey, planRowsBySpec);
}

function calcoPreservedFgSampleEntriesHaveInput(sampleEntries) {
  return Object.values(sampleEntries || {}).some((rows) =>
    (rows || []).some((row) => ((row.reading || "").toString().trim()) || ((row.result || "").toString().trim()))
  );
}

function calcoGetFgPreservedSampleExtent(entries) {
  let lastNonEmptyIndex = 0;

  (entries || []).forEach((entry, index) => {
    if (((entry.reading || "").toString().trim()) || ((entry.result || "").toString().trim())) {
      lastNonEmptyIndex = index + 1;
    }
  });

  return lastNonEmptyIndex;
}

function calcoBuildFgParameterSamples(planRows, planSampleRows, preservedEntries) {
  const planSamplesByKey = {};
  const builtRows = [];

  (planSampleRows || []).forEach((row) => {
    const key = calcoNormalizeRmText(row.parameter_key);
    if (!planSamplesByKey[key]) {
      planSamplesByKey[key] = [];
    }
    planSamplesByKey[key].push(row);
  });

  (planRows || []).forEach((planRow) => {
    const key = calcoNormalizeRmText(planRow.custom_parameter_key);
    const baseRows = planSamplesByKey[key] || [];
    const sampleEntries = preservedEntries[key] || [];
    const sampleCount = Math.max(baseRows.length, calcoGetFgPreservedSampleExtent(sampleEntries));

    for (let sampleNo = 1; sampleNo <= sampleCount; sampleNo += 1) {
      const baseRow = baseRows[sampleNo - 1] || {};
      const preservedEntry = sampleEntries[sampleNo - 1] || {};
      builtRows.push({
        parameter_key: planRow.custom_parameter_key,
        parameter: planRow.specification,
        sample_no: sampleNo,
        reading: preservedEntry.reading || baseRow.reading || "",
        result: "",
      });
    }
  });

  return builtRows;
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
  const hasExistingInput = calcoFgInspectionHasUserInput(frm);
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
    frm.doc.custom_manufacturing_qty_mt = "";
    frm.doc.custom_quantity_multiplier = "";
    if (frm.doc.parameter_samples) {
      frm.clear_table("parameter_samples");
      frm.refresh_field("parameter_samples");
    }
    frm.refresh_field("custom_manufacturing_qty_mt");
    frm.refresh_field("custom_quantity_multiplier");
    calcoSetRmReadingGridBehavior(frm);
    calcoEvaluateInspectionState(frm);
    return;
  }

  frappe.call({
    method: "calco_erp.calco_quality.fg_quality_setup.get_fg_inspection_context",
    args: {
      item_code: frm.doc.item_code,
      reference_type: frm.doc.reference_type,
      reference_name: frm.doc.reference_name,
      batch_no: frm.doc.batch_no,
    },
  }).then((response) => {
    const payload = response.message || {};
    const templateName = payload.quality_inspection_template || "";
    const planRows = payload.readings || [];
    const planSampleRows = payload.parameter_samples || [];
    const emptyMessage = payload.empty_message || __("No QC parameters defined for this grade.");
    const currentRows = frm.doc.readings || [];
    const currentSampleRows = frm.doc.parameter_samples || [];
    const hasExistingInput = calcoFgInspectionHasUserInput(frm);
    const rowsMatchPlan = calcoFgReadingsMatchPlan(currentRows, planRows);
    const samplesMatchPlan = calcoFgSamplesMatchPlan(currentSampleRows, planSampleRows);

    frm.__calco_fg_control_plan_active = Boolean(payload.use_control_plan);
    frm.doc.custom_manufacturing_qty_mt =
      payload.manufacturing_qty_mt !== undefined && payload.manufacturing_qty_mt !== null
        ? payload.manufacturing_qty_mt
        : "";
    frm.doc.custom_quantity_multiplier = payload.quantity_multiplier || "";
    calcoSetRmReadingGridBehavior(frm);

    if (templateName && frm.doc.quality_inspection_template !== templateName) {
      return frm.set_value("quality_inspection_template", templateName);
    }

    if (!payload.use_control_plan) {
      frm.doc.custom_manufacturing_qty_mt = "";
      frm.doc.custom_quantity_multiplier = "";
      if (frm.doc.parameter_samples) {
        frm.clear_table("parameter_samples");
        frm.refresh_field("parameter_samples");
      }
      frm.refresh_field("custom_manufacturing_qty_mt");
      frm.refresh_field("custom_quantity_multiplier");
      return calcoLoadFgTemplateReadings(frm, forceReplace).then(() => calcoEvaluateInspectionState(frm));
    }

    if (!forceReplace && hasExistingInput) {
      return;
    }

    if (!forceReplace && rowsMatchPlan && samplesMatchPlan) {
      return;
    }

    const preservedSampleEntries = calcoGetFgPreservedSampleEntries(currentRows, currentSampleRows, planRows);
    const rebuiltSampleRows = calcoBuildFgParameterSamples(planRows, planSampleRows, preservedSampleEntries);

    frm.clear_table("readings");
    planRows.forEach((planRow) => {
      frm.add_child("readings", calcoBuildFgReading(planRow));
    });
    if (frm.doc.parameter_samples) {
      frm.clear_table("parameter_samples");
      rebuiltSampleRows.forEach((sampleRow) => {
        frm.add_child("parameter_samples", sampleRow);
      });
    });
    const requiredTests = planRows
      .map((planRow) => Number(planRow.custom_required_tests || 0))
      .filter((value) => Number.isFinite(value) && value > 0);
    frm.doc.sample_size = requiredTests.length ? Math.max(...requiredTests) : "";
    frm.refresh_field("readings");
    frm.refresh_field("parameter_samples");
    frm.refresh_field("sample_size");
    frm.refresh_field("custom_manufacturing_qty_mt");
    frm.refresh_field("custom_quantity_multiplier");
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
    calcoQueueFgControlPlanSync(frm, true);
  },

  reference_name(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoSetRmPendingQueries(frm);
    calcoAutoFetchRmBatch(frm);
    calcoQueueRmReadingStandards(frm);
    calcoUpdateRmReferenceFieldUx(frm);
    calcoQueueFgControlPlanSync(frm, true);
  },

  batch_no(frm) {
    calcoSetRmReadingGridBehavior(frm);
    calcoQueueFgControlPlanSync(frm, true);
    calcoEvaluateInspectionState(frm);
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

frappe.ui.form.on("FG Inspection Parameter Sample", {
  reading(frm) {
    calcoEvaluateInspectionState(frm);
  },
});
