frappe.provide("calco_erp.master_data_governance");
window.calco_erp = window.calco_erp || {};
window.calco_erp.master_data_governance = window.calco_erp.master_data_governance || {};

(function () {
  const HTML_FIELD = "journey_tracker_html";
  const STYLE_ID = "calco-governance-journey-style";
  const MAX_RENDER_RETRIES = 4;
  const FALLBACK_CLASS = "calco-governance-journey-mount";
  const HOST_CLASS = "calco-governance-journey-host";

  const PURCHASE_REVIEW_LABEL_OVERRIDES = {
    commercial_feasibility_decision: __("Commercial Feasibility"),
    purchase_target_rate: __("Target Rate"),
    purchase_lead_time_days: __("Expected Lead Time"),
    purchase_moq: __("Expected MOQ"),
    purchase_pack_size: __("Purchase Pack Size"),
    commercial_remarks: __("Commercial Remarks"),
    purchase_decision: __("Purchase Decision"),
  };

  const CONFIG = {
    "New RM Request": {
      title: __("New RM Request Tracker"),
      subtitle: __("Approval and ERP creation journey for raw material onboarding"),
      method: "calco_erp.calco_purchase.master_data_governance_journey.get_new_rm_request_tracker",
      titleField: "rm_code",
      sectionField: "journey_section",
      anchorField: "requester_section",
      summarySections: [
        {
          title: __("Request Summary"),
          fields: ["rm_code", "rm_name", "category", "description", "stock_uom", "preferred_supplier"],
        },
        {
          title: __("Planning Defaults"),
          fields: [
            "current_season",
            "manual_lead_time_days",
            "safety_days",
            "review_period_days",
            "minimum_order_qty",
            "purchase_pack_size",
          ],
        },
      ],
      requestFields: [
        "rm_code",
        "rm_name",
        "category",
        "description",
        "stock_uom",
        "preferred_supplier",
        "current_season",
        "manual_lead_time_days",
        "safety_days",
        "review_period_days",
        "minimum_order_qty",
        "purchase_pack_size",
        "commercial_feasibility_decision",
        "purchase_target_rate",
        "purchase_lead_time_days",
        "purchase_moq",
        "purchase_pack_size",
        "commercial_remarks",
        "supplier_request",
        "purchase_decision",
      ],
      hiddenFields: [
        "technical_review_section",
        "technical_review_remarks",
        "existing_alternative_available",
        "recommended_material_type",
        "application_suitability",
        "technical_approval_attachment",
        "technical_decision",
        "document_readiness_section",
        "tds_attachment",
        "msds_attachment",
        "tc_coa_attachment",
        "sample_available",
        "sample_required",
        "sample_quantity_kg",
        "sample_received_by_quality",
        "sample_received_date",
        "document_readiness_remarks",
        "document_readiness_decision",
        "quality_review_section",
        "msds_available",
        "tds_available",
        "coa_available",
        "required_incoming_tests",
        "quality_review_remarks",
        "quality_approval_attachment",
        "quality_decision",
        "purchase_review_section",
        "commercial_feasibility_decision",
        "purchase_target_rate",
        "purchase_lead_time_days",
        "purchase_moq",
        "purchase_pack_size",
        "supplier_request",
        "commercial_remarks",
        "purchase_decision",
      ],
      stageFields: {
        "Technical Review": [
          "technical_review_remarks",
          "existing_alternative_available",
          "recommended_material_type",
          "application_suitability",
          "technical_approval_attachment",
          "technical_decision",
        ],
        "Document & Sample Readiness": [
          "tds_attachment",
          "msds_attachment",
          "tc_coa_attachment",
          "sample_available",
          "sample_required",
          "sample_quantity_kg",
          "sample_received_by_quality",
          "sample_received_date",
          "document_readiness_remarks",
          "document_readiness_decision",
        ],
        "Quality Review": [
          "msds_available",
          "tds_available",
          "coa_available",
          "required_incoming_tests",
          "quality_review_remarks",
          "quality_approval_attachment",
          "quality_decision",
        ],
        "Purchase Review": [
          "commercial_feasibility_decision",
          "purchase_target_rate",
          "purchase_lead_time_days",
          "purchase_moq",
          "purchase_pack_size",
          "commercial_remarks",
          "purchase_decision",
        ],
      },
      readOnlySections: {
        "Quality Review": [
          {
            title: __("Document Readiness"),
            fields: [
              "tds_attachment",
              "msds_attachment",
              "tc_coa_attachment",
              "document_readiness_remarks",
              "document_readiness_decision",
            ],
          },
          {
            title: __("Sample Readiness"),
            fields: [
              "sample_available",
              "sample_required",
              "sample_quantity_kg",
              "sample_received_by_quality",
              "sample_received_date",
            ],
          },
        ],
      },
      reviewStages: {
        technical_review: {
          stageStatus: "Technical Review",
          approveAction: "Technical Approve",
          approveLabel: __("Approve Technical Review"),
        },
        document_sample_readiness: {
          stageStatus: "Document & Sample Readiness",
          approveAction: "Document Readiness Complete",
          approveLabel: __("Mark Complete"),
        },
        quality_review: {
          stageStatus: "Quality Review",
          approveAction: "Quality Approve",
          approveLabel: __("Approve Quality Review"),
        },
        purchase_review: {
          stageStatus: "Purchase Review",
          approveAction: "Purchase Approve",
          approveLabel: __("Approve Purchase Review"),
        },
      },
      erpFields: ["created_item", "created_planning_parameter", "created_supplier_matrix", "creation_log"],
      erpStageKeys: ["erp_item_creation", "rm_planning_parameter", "supplier_approval_matrix", "completed"],
    },
    "New Supplier Request": {
      title: __("New Supplier Request Tracker"),
      subtitle: __("Approval and ERP creation journey for supplier onboarding"),
      method: "calco_erp.calco_purchase.master_data_governance_journey.get_new_supplier_request_tracker",
      titleField: "supplier_name",
      sectionField: "journey_section",
      anchorField: "supplier_section",
      summarySections: [
        {
          title: __("Request Summary"),
          fields: [
            "supplier_name",
            "source_rm_request",
            "source_rm_code",
            "source_rm_name",
            "source_category",
            "source_stock_uom",
            "supplier_type",
            "reason_for_supplier_onboarding",
            "payment_terms",
            "lead_time_days",
            "currency_type",
            "effective_date",
            "expiry_date",
          ],
        },
        {
          title: __("Requested RM Coverage"),
          fields: ["supplier_request_items"],
        },
      ],
      requestFields: [
        "supplier_name",
        "supplier_type",
        "reason_for_supplier_onboarding",
        "payment_terms",
        "lead_time_days",
        "currency_type",
        "effective_date",
        "expiry_date",
        "supplier_request_items",
      ],
      hiddenFields: [
        "quality_review_section",
        "certificates_checked",
        "quality_audit_required",
        "supplier_quality_remarks",
        "supplier_quality_decision",
        "purchase_review_section",
        "supplier_purchase_lead_time",
        "supplier_purchase_moq",
        "supplier_purchase_payment_terms",
        "commercial_terms",
        "supplier_purchase_remarks",
        "supplier_purchase_decision",
        "management_review_section",
        "strategic_supplier",
        "risk_remarks",
        "final_approval_decision",
      ],
      stageFields: {
        "Quality Review": [
          "certificates_checked",
          "quality_audit_required",
          "supplier_quality_remarks",
          "supplier_quality_decision",
        ],
        "Purchase Review": [
          "supplier_purchase_lead_time",
          "supplier_purchase_moq",
          "supplier_purchase_payment_terms",
          "commercial_terms",
          "supplier_purchase_remarks",
          "supplier_purchase_decision",
        ],
        "Management Review": [
          "strategic_supplier",
          "risk_remarks",
          "final_approval_decision",
        ],
      },
      reviewStages: {
        quality_review: {
          stageStatus: "Quality Review",
          approveAction: "Quality Approve",
          approveLabel: __("Approve Quality Review"),
        },
        purchase_review: {
          stageStatus: "Purchase Review",
          approveAction: "Purchase Approve",
          approveLabel: __("Approve Purchase Review"),
        },
        management_review: {
          stageStatus: "Management Review",
          approveAction: "Management Approve",
          approveLabel: __("Approve Management Review"),
        },
      },
      erpFields: ["created_supplier", "created_matrix_rows", "created_planning_parameters", "creation_log"],
      erpStageKeys: ["supplier_master_creation", "supplier_approval_matrix", "rm_planning_link", "completed"],
    },
  };

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .calco-governance-journey {
        padding: 16px;
        border: 1px solid var(--border-color);
        border-radius: 18px;
        background:
          radial-gradient(circle at top right, rgba(21, 101, 192, 0.08), transparent 30%),
          linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(255, 255, 255, 1));
      }
      .calco-governance-journey__header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 14px;
      }
      .calco-governance-journey__title {
        font-size: 16px;
        font-weight: 700;
      }
      .calco-governance-journey__subtitle {
        font-size: 12px;
        color: var(--text-muted);
      }
      .calco-governance-journey__tag {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.05);
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 700;
      }
      .calco-governance-journey__flow {
        display: flex;
        align-items: stretch;
        gap: 12px;
        overflow-x: auto;
        padding-bottom: 4px;
      }
      .calco-governance-journey__stage {
        position: relative;
        min-width: 210px;
        border: 1px solid var(--border-color);
        border-radius: 14px;
        background: var(--fg-color);
        padding: 14px 16px;
        text-align: left;
        transition: border-color 0.2s ease, transform 0.2s ease;
        box-shadow: inset 0 4px 0 var(--stage-color, #94a3b8);
      }
      .calco-governance-journey__stage:hover {
        border-color: var(--stage-color, var(--primary));
        transform: translateY(-1px);
      }
      .calco-governance-journey__stage-label {
        font-size: 13px;
        font-weight: 700;
        margin-bottom: 8px;
      }
      .calco-governance-journey__stage-status {
        display: inline-flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        margin-bottom: 8px;
        background: var(--stage-bg, rgba(148, 163, 184, 0.18));
        color: var(--stage-text, #334155);
      }
      .calco-governance-journey__stage-role {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--text-muted);
        margin-bottom: 8px;
      }
      .calco-governance-journey__stage-summary {
        font-size: 12px;
        line-height: 1.45;
        color: var(--text-muted);
        min-height: 52px;
      }
      .calco-governance-journey__stage-docs {
        font-size: 11px;
        color: var(--text-muted);
        margin-top: 10px;
        margin-bottom: 10px;
      }
      .calco-governance-journey__stage-actions {
        display: flex;
        gap: 8px;
        margin-top: 8px;
      }
      .calco-governance-journey__stage-button {
        border: 1px solid rgba(21, 101, 192, 0.16);
        background: rgba(21, 101, 192, 0.08);
        color: #0f4c91;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
      }
      .calco-governance-journey__stage-button--ghost {
        border-color: var(--border-color);
        background: rgba(148, 163, 184, 0.08);
        color: #475569;
      }
      .calco-governance-journey__connector {
        flex: 0 0 28px;
        align-self: center;
        height: 2px;
        border-radius: 999px;
        background: linear-gradient(90deg, rgba(148, 163, 184, 0.6), rgba(148, 163, 184, 0.18));
      }
      .calco-governance-journey__placeholder,
      .calco-governance-journey__empty {
        padding: 18px 4px;
        color: var(--text-muted);
        font-size: 13px;
      }
      .calco-governance-journey__stage[data-color="grey"] {
        --stage-color: #94a3b8;
        --stage-bg: rgba(148, 163, 184, 0.16);
        --stage-text: #475569;
      }
      .calco-governance-journey__stage[data-color="blue"] {
        --stage-color: #1565c0;
        --stage-bg: rgba(21, 101, 192, 0.12);
        --stage-text: #0f4c91;
      }
      .calco-governance-journey__stage[data-color="green"] {
        --stage-color: #2e7d32;
        --stage-bg: rgba(46, 125, 50, 0.12);
        --stage-text: #1f5b24;
      }
      .calco-governance-journey__stage[data-color="red"] {
        --stage-color: #c62828;
        --stage-bg: rgba(198, 40, 40, 0.12);
        --stage-text: #8f1d1d;
      }
      .calco-governance-journey__stage[data-color="orange"] {
        --stage-color: #dd6b20;
        --stage-bg: rgba(221, 107, 32, 0.12);
        --stage-text: #9c4221;
      }
      .calco-governance-review__summary {
        display: grid;
        gap: 14px;
        margin-bottom: 16px;
      }
      .calco-governance-review__summary-card,
      .calco-governance-review__audit,
      .calco-governance-review__erp {
        border: 1px solid var(--border-color);
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.03);
        padding: 14px;
      }
      .calco-governance-review__summary-title,
      .calco-governance-review__audit-title,
      .calco-governance-review__erp-title {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--text-muted);
        margin-bottom: 10px;
      }
      .calco-governance-review__summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px 14px;
      }
      .calco-governance-review__summary-item-label {
        font-size: 11px;
        color: var(--text-muted);
        margin-bottom: 4px;
      }
      .calco-governance-review__summary-item-value {
        font-size: 13px;
        line-height: 1.45;
        font-weight: 600;
        white-space: pre-wrap;
      }
      .calco-governance-review__table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .calco-governance-review__table th,
      .calco-governance-review__table td {
        border-bottom: 1px solid var(--border-color);
        padding: 8px 10px;
        text-align: left;
        vertical-align: top;
      }
      .calco-governance-review__audit-list,
      .calco-governance-review__erp-list {
        display: grid;
        gap: 8px;
      }
      .calco-governance-review__audit-label,
      .calco-governance-review__erp-label {
        color: var(--text-muted);
        margin-right: 6px;
      }
      .calco-governance-review__section-focus {
        animation: calcoGovernanceSectionPulse 1.8s ease;
      }
      @keyframes calcoGovernanceSectionPulse {
        0% {
          box-shadow: 0 0 0 0 rgba(21, 101, 192, 0.28);
        }
        100% {
          box-shadow: 0 0 0 14px rgba(21, 101, 192, 0);
        }
      }
      @media (max-width: 767px) {
        .calco-governance-journey {
          padding: 14px;
        }
        .calco-governance-journey__stage {
          min-width: 176px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function getConfig(doctype) {
    return CONFIG[doctype];
  }

  function cleanupDuplicateTrackerContainers(frm) {
    const root = $(frm.wrapper || document.body);
    const officialWrapper = frm.fields_dict && frm.fields_dict[HTML_FIELD] && frm.fields_dict[HTML_FIELD].$wrapper;

    root.find(`.${HOST_CLASS}`).remove();
    if (officialWrapper && officialWrapper.length) {
      root.find(`.${FALLBACK_CLASS}`).not(officialWrapper).remove();
      return;
    }

    const mounts = root.find(`.${FALLBACK_CLASS}`);
    if (mounts.length <= 1) {
      return;
    }
    mounts.slice(1).remove();
  }

  function applySupplierRequestCurrencyDefaults(frm) {
    if (!(frm.fields_dict && frm.fields_dict.currency_type)) {
      return;
    }

    const supplierType = (frm.doc.supplier_type || "").trim().toLowerCase();
    const defaultCurrency = supplierType === "local" ? "INR" : supplierType === "overseas" ? "USD" : "";
    if (!defaultCurrency) {
      return;
    }

    const currentCurrency = (frm.doc.currency_type || "").trim();
    if (!currentCurrency) {
      frm.set_value("currency_type", defaultCurrency);
    }
  }

  function getWrapper(frm) {
    const config = getConfig(frm.doctype);
    cleanupDuplicateTrackerContainers(frm);

    const htmlWrapper = frm.fields_dict && frm.fields_dict[HTML_FIELD] && frm.fields_dict[HTML_FIELD].$wrapper;
    if (htmlWrapper && htmlWrapper.length) {
      return htmlWrapper;
    }

    const sectionWrapper = config && config.sectionField && frm.fields_dict[config.sectionField] && frm.fields_dict[config.sectionField].$wrapper
      ? $(frm.fields_dict[config.sectionField].$wrapper)
      : null;
    const anchorWrapper = config && config.anchorField && frm.fields_dict[config.anchorField] && frm.fields_dict[config.anchorField].$wrapper
      ? $(frm.fields_dict[config.anchorField].$wrapper)
      : null;

    let wrapper = null;
    if (anchorWrapper && anchorWrapper.length) {
      wrapper = anchorWrapper.prev(`.${FALLBACK_CLASS}`);
      if (!wrapper.length) {
        wrapper = $(`<div class="${FALLBACK_CLASS}" data-doctype="${frappe.utils.escape_html(frm.doctype)}"></div>`);
        wrapper.insertBefore(anchorWrapper);
      }
      return wrapper;
    }

    if (sectionWrapper && sectionWrapper.length) {
      wrapper = sectionWrapper.siblings(`.${FALLBACK_CLASS}`);
      if (!wrapper.length) {
        wrapper = $(`<div class="${FALLBACK_CLASS}" data-doctype="${frappe.utils.escape_html(frm.doctype)}"></div>`);
        wrapper.insertAfter(sectionWrapper);
      }
      return wrapper;
    }

    return htmlWrapper || null;
  }

  function escapeHtml(value) {
    return frappe.utils.escape_html(String(value || ""));
  }

  function getFieldDefinition(frm, fieldname) {
    return (frm.fields_dict[fieldname] && frm.fields_dict[fieldname].df)
      || frappe.meta.get_docfield(frm.doctype, fieldname, frm.doc.name)
      || null;
  }

  function getFieldLabel(frm, fieldname) {
    const df = getFieldDefinition(frm, fieldname);
    const override = PURCHASE_REVIEW_LABEL_OVERRIDES[fieldname];
    return override || (df && df.label) || fieldname;
  }

  function formatValue(frm, fieldname, value) {
    if (value === null || value === undefined || value === "") {
      return __("Not set");
    }

    if (fieldname === "supplier_request_items") {
      const rows = Array.isArray(value) ? value : [];
      if (!rows.length) {
        return __("No requested RM rows.");
      }
      const body = rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.item_code || "-")}</td>
          <td>${escapeHtml(row.approval_status || "Approved")}</td>
          <td>${escapeHtml(row.lead_time || "-")}</td>
          <td>${escapeHtml(row.payment_terms || "-")}</td>
        </tr>
      `).join("");
      return `
        <table class="calco-governance-review__table">
          <thead>
            <tr>
              <th>${__("Item Code")}</th>
              <th>${__("Approval Status")}</th>
              <th>${__("Lead Time")}</th>
              <th>${__("Payment Terms")}</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      `;
    }

    const df = getFieldDefinition(frm, fieldname);
    if (df && df.fieldtype === "Attach" && value) {
      const href = escapeHtml(value);
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${href}</a>`;
    }
    if (df && df.fieldtype === "Date" && value) {
      return escapeHtml(frappe.datetime.str_to_user(value));
    }

    if (df && ["Small Text", "Text", "Long Text"].includes(df.fieldtype)) {
      return escapeHtml(value).replace(/\n/g, "<br>");
    }

    return escapeHtml(value);
  }

  function getPurchaseReviewFieldFilters(doctype, stageStatus) {
    if (doctype === "New RM Request" && stageStatus === "Purchase Review") {
      return [
        "commercial_feasibility_decision",
        "purchase_target_rate",
        "purchase_lead_time_days",
        "purchase_moq",
        "purchase_pack_size",
        "commercial_remarks",
        "purchase_decision",
      ];
    }
    return null;
  }

  function getHiddenSummaryFields(doctype, stageStatus) {
    if (doctype === "New RM Request" && stageStatus === "Purchase Review") {
      return ["preferred_supplier"];
    }
    return [];
  }

  function renderSummaryHtml(frm, stageStatus) {
    const config = getConfig(frm.doctype);
    const hiddenFields = getHiddenSummaryFields(frm.doctype, stageStatus);
    return (config.summarySections || []).map((section) => {
      const sectionFields = (section.fields || []).filter((fieldname) => !hiddenFields.includes(fieldname));
      if (!sectionFields.length) {
        return "";
      }
      const content = sectionFields.map((fieldname) => `
        <div>
          <div class="calco-governance-review__summary-item-label">${escapeHtml(getFieldLabel(frm, fieldname))}</div>
          <div class="calco-governance-review__summary-item-value">${formatValue(frm, fieldname, frm.doc[fieldname])}</div>
        </div>
      `).join("");

      return `
        <div class="calco-governance-review__summary-card">
          <div class="calco-governance-review__summary-title">${escapeHtml(section.title)}</div>
          <div class="calco-governance-review__summary-grid">${content}</div>
        </div>
      `;
    }).join("");
  }

  function renderReadOnlySectionsHtml(frm, stageStatus) {
    const config = getConfig(frm.doctype);
    const sections = ((config.readOnlySections || {})[stageStatus]) || [];
    return sections.map((section) => {
      const content = (section.fields || []).map((fieldname) => `
        <div>
          <div class="calco-governance-review__summary-item-label">${escapeHtml(getFieldLabel(frm, fieldname))}</div>
          <div class="calco-governance-review__summary-item-value">${formatValue(frm, fieldname, frm.doc[fieldname])}</div>
        </div>
      `).join("");

      return `
        <div class="calco-governance-review__summary-card">
          <div class="calco-governance-review__summary-title">${escapeHtml(section.title)}</div>
          <div class="calco-governance-review__summary-grid">${content}</div>
        </div>
      `;
    }).join("");
  }

  function renderAuditHtml(stage) {
    const audit = stage.audit || {};
    const items = audit.items || [];
    if (!audit.reviewed_by && !audit.reviewed_on && !audit.decision && !items.length) {
      return "";
    }

    const metaItems = [
      audit.reviewed_by ? `<div><span class="calco-governance-review__audit-label">${__("Reviewed By")}:</span>${escapeHtml(audit.reviewed_by)}</div>` : "",
      audit.reviewed_on ? `<div><span class="calco-governance-review__audit-label">${__("Reviewed On")}:</span>${escapeHtml(audit.reviewed_on)}</div>` : "",
      audit.decision ? `<div><span class="calco-governance-review__audit-label">${__("Decision")}:</span>${escapeHtml(audit.decision)}</div>` : "",
    ].filter(Boolean).join("");

    const checklist = items.map((item) => `
      <div><span class="calco-governance-review__audit-label">${escapeHtml(item.label)}:</span>${escapeHtml(item.value)}</div>
    `).join("");

    return `
      <div class="calco-governance-review__audit">
        <div class="calco-governance-review__audit-title">${__("Review Audit")}</div>
        <div class="calco-governance-review__audit-list">
          ${metaItems}
          ${checklist}
        </div>
      </div>
    `;
  }

  function renderErpHtml(frm, stage) {
    const config = getConfig(frm.doctype);
    const rows = (config.erpFields || []).map((fieldname) => {
      const value = frm.doc[fieldname];
      return `
        <div>
          <span class="calco-governance-review__erp-label">${escapeHtml(getFieldLabel(frm, fieldname))}:</span>
          ${formatValue(frm, fieldname, value)}
        </div>
      `;
    }).join("");

    const documents = (stage.documents || []).map((doc) => `
      <div>
        <span class="calco-governance-review__erp-label">${escapeHtml(doc.doctype)}:</span>
        <a href="#" class="calco-governance-doc-link" data-doctype="${escapeHtml(doc.doctype)}" data-name="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}</a>
      </div>
    `).join("");

    return `
      <div class="calco-governance-review__erp">
        <div class="calco-governance-review__erp-title">${escapeHtml(stage.label)}</div>
        <div class="calco-governance-review__erp-list">
          ${rows}
          ${documents || `<div>${__("No linked records available yet.")}</div>`}
        </div>
      </div>
    `;
  }

  function renderState(frm, message) {
    const wrapper = getWrapper(frm);
    const config = getConfig(frm.doctype);
    if (!wrapper || !config) {
      return;
    }

    wrapper.html(`
      <section class="calco-governance-journey">
        <div class="calco-governance-journey__header">
          <div>
            <div class="calco-governance-journey__title">${escapeHtml(config.title)}</div>
            <div class="calco-governance-journey__subtitle">${escapeHtml(config.subtitle)}</div>
          </div>
          <div class="calco-governance-journey__tag">${__("Focused reviews")}</div>
        </div>
        <div class="calco-governance-journey__placeholder">${escapeHtml(message)}</div>
      </section>
    `);
  }

  function renderVisibleTrackerError(frm, message, detail) {
    const wrapper = getWrapper(frm);
    const config = getConfig(frm.doctype);
    if (!wrapper || !config) {
      return;
    }

    wrapper.html(`
      <section class="calco-governance-journey">
        <div class="calco-governance-journey__header">
          <div>
            <div class="calco-governance-journey__title">${escapeHtml(config.title)}</div>
            <div class="calco-governance-journey__subtitle">${escapeHtml(config.subtitle)}</div>
          </div>
          <div class="calco-governance-journey__tag">${__("Focused reviews")}</div>
        </div>
        <div class="calco-governance-journey__stage" data-color="orange">
          <div class="calco-governance-journey__stage-label">${__("Tracker Error")}</div>
          <div class="calco-governance-journey__stage-status">${__("Attention Needed")}</div>
          <div class="calco-governance-journey__stage-summary">${escapeHtml(message)}</div>
          <div class="calco-governance-journey__stage-docs">${escapeHtml(detail || __("No additional detail available."))}</div>
        </div>
      </section>
    `);
  }

  function getActionLabel(stage, frm) {
    const config = getConfig(frm.doctype);
    if ((config.erpStageKeys || []).includes(stage.key)) {
      return __("Open");
    }
    if ((config.reviewStages || {})[stage.key]) {
      return stage.status === "In Progress" ? __("Review") : __("Open");
    }
    return __("Details");
  }

  function normalizeStage(stage, index) {
    const row = stage || {};
    return {
      key: row.key || `stage_${index + 1}`,
      label: row.label || __("Unnamed Stage"),
      status: row.status || __("Unknown"),
      owner_role: row.owner_role || __("Owner not set"),
      summary: row.summary || "",
      color: row.color || "grey",
      documents: Array.isArray(row.documents) ? row.documents : [],
      audit: row.audit || {},
      message: row.message || "",
    };
  }

  function buildStageHtml(frm, stage, index, stageCount) {
    try {
      const connector = index < stageCount - 1 ? `<div class="calco-governance-journey__connector"></div>` : "";
      const docCount = (stage.documents || []).length;
      return `
        <div
          class="calco-governance-journey__stage"
          data-stage-key="${escapeHtml(stage.key)}"
          data-color="${escapeHtml(stage.color || "grey")}"
        >
          <div class="calco-governance-journey__stage-label">${escapeHtml(stage.label)}</div>
          <div class="calco-governance-journey__stage-status">${escapeHtml(stage.status)}</div>
          <div class="calco-governance-journey__stage-role">${escapeHtml(stage.owner_role || __("Owner not set"))}</div>
          <div class="calco-governance-journey__stage-summary">${escapeHtml(stage.summary || "")}</div>
          <div class="calco-governance-journey__stage-docs">
            ${docCount ? __("{0} linked record(s)", [docCount]) : __("No linked records yet")}
          </div>
          <div class="calco-governance-journey__stage-actions">
            <button
              type="button"
              class="calco-governance-journey__stage-button"
              data-action-stage-key="${escapeHtml(stage.key)}"
            >
              ${escapeHtml(getActionLabel(stage, frm))}
            </button>
            <button
              type="button"
              class="calco-governance-journey__stage-button calco-governance-journey__stage-button--ghost"
              data-detail-stage-key="${escapeHtml(stage.key)}"
            >
              ${__("Details")}
            </button>
          </div>
        </div>
        ${connector}
      `;
    } catch (error) {
      console.error("Governance tracker stage render failed", { stage, error });
      return `
        <div class="calco-governance-journey__stage" data-color="orange">
          <div class="calco-governance-journey__stage-label">${escapeHtml(stage.label || __("Stage Render Error"))}</div>
          <div class="calco-governance-journey__stage-status">${__("Error")}</div>
          <div class="calco-governance-journey__stage-summary">${escapeHtml(error.message || __("Unable to render this stage."))}</div>
        </div>
      `;
    }
  }

  function buildFlowHtml(frm, stages) {
    if (!Array.isArray(stages) || !stages.length) {
      return `<div class="calco-governance-journey__empty">${__("No stages available.")}</div>`;
    }

    return stages
      .map((stage, index) => buildStageHtml(frm, normalizeStage(stage, index), index, stages.length))
      .join("");
  }

  function getStage(frm, stageKey) {
    return ((frm.__governance_journey_data || {}).stages || []).find((row) => row.key === stageKey);
  }

  function toggleFieldList(frm, fields, show) {
    (fields || []).forEach((fieldname) => {
      if (frm.fields_dict[fieldname]) {
        frm.toggle_display(fieldname, show);
      }
    });
  }

  function syncMainFormState(frm) {
    const config = getConfig(frm.doctype);
    if (!config) {
      return;
    }

    const isDraft = (frm.doc.status || "Draft") === "Draft";
    (config.requestFields || []).forEach((fieldname) => {
      if (frm.fields_dict[fieldname]) {
        frm.set_df_property(fieldname, "read_only", isDraft ? 0 : 1);
      }
    });

    Object.entries(config.stageFields || {}).forEach(([stageStatus, fieldnames]) => {
      const isActiveStage = (frm.doc.status || "") === stageStatus;
      fieldnames.forEach((fieldname) => {
        if (frm.fields_dict[fieldname]) {
          frm.set_df_property(fieldname, "read_only", isActiveStage ? 0 : 1);
          frm.set_df_property(fieldname, "reqd", 0);
        }
      });
    });

    toggleFieldList(frm, config.hiddenFields, false);
  }

  function getDialogTitle(frm, stage) {
    const config = getConfig(frm.doctype);
    const keyValue = frm.doc[(config && config.titleField) || "name"] || frm.doc.name;
    return `${stage.label} - ${keyValue}`;
  }

  function buildDialogField(frm, fieldname, readOnly) {
    const df = getFieldDefinition(frm, fieldname);
    return {
      fieldtype: (df && df.fieldtype) || "Data",
      fieldname,
      label: getFieldLabel(frm, fieldname),
      options: df && df.options,
      precision: df && df.precision,
      read_only: readOnly ? 1 : 0,
      reqd: 0,
    };
  }

  function collectDialogValues(dialog, fieldnames) {
    const values = {};
    (fieldnames || []).forEach((fieldname) => {
      values[fieldname] = dialog.get_value(fieldname);
    });
    return values;
  }

  async function submitStageReview(frm, dialog, stage, action) {
    const config = getConfig(frm.doctype);
    const stageConfig = (config.reviewStages || {})[stage.key];
    const explicitStageFields = getPurchaseReviewFieldFilters(frm.doctype, stageConfig.stageStatus);
    const fieldnames = explicitStageFields || (config.stageFields || {})[stageConfig.stageStatus] || [];
    const values = collectDialogValues(dialog, fieldnames);

    await frappe.call({
      method: "calco_erp.calco_purchase.master_data_governance_journey.save_stage_review",
      args: {
        doctype: frm.doctype,
        name: frm.doc.name,
        values,
        action: action || "",
      },
      freeze: true,
      freeze_message: action ? __("Applying review action...") : __("Saving review..."),
    });

    dialog.hide();
    await frm.reload_doc();
    frappe.show_alert({
      message: action ? __("Review updated and workflow action applied.") : __("Review saved."),
      indicator: "green",
    });
  }

  function addDialogButtons(frm, dialog, stage) {
    const config = getConfig(frm.doctype);
    const stageConfig = (config.reviewStages || {})[stage.key];
    const readOnly = stage.status !== "In Progress";

    dialog.set_primary_action(readOnly ? __("Close") : __("Save Review"), async () => {
      if (readOnly) {
        dialog.hide();
        return;
      }
      await submitStageReview(frm, dialog, stage, "");
    });

    if (readOnly) {
      return;
    }

    const footer = dialog.$wrapper.find(".modal-footer");
    if (frm.doctype === "New RM Request" && stage.key === "purchase_review") {
      const supplierRequestButton = $(
        `<button type="button" class="btn btn-secondary btn-sm">${escapeHtml(
          frm.doc.supplier_request ? __("Open Supplier Request") : __("Create Supplier Request"),
        )}</button>`,
      );
      footer.append(supplierRequestButton);
      supplierRequestButton.on("click", () => {
        openSupplierRequestFromRm(frm);
      });
    }

    const approveButton = $(`<button type="button" class="btn btn-primary btn-sm">${escapeHtml(stageConfig.approveLabel)}</button>`);
    const rejectButton = $(`<button type="button" class="btn btn-danger btn-sm">${__("Reject")}</button>`);

    footer.prepend(rejectButton);
    footer.prepend(approveButton);

    approveButton.on("click", async () => {
      await submitStageReview(frm, dialog, stage, stageConfig.approveAction);
    });
    rejectButton.on("click", async () => {
      await submitStageReview(frm, dialog, stage, "Reject");
    });
  }

  function openReviewDialog(frm, stageKey) {
    const stage = getStage(frm, stageKey);
    const config = getConfig(frm.doctype);
    const stageConfig = stage && (config.reviewStages || {})[stage.key];
    if (!stage || !stageConfig) {
      return;
    }

    const readOnly = stage.status !== "In Progress";
    const explicitStageFields = getPurchaseReviewFieldFilters(frm.doctype, stageConfig.stageStatus);
    const stageFields = explicitStageFields || (config.stageFields || {})[stageConfig.stageStatus] || [];
    const isPurchaseReview =
      frm.doctype === "New RM Request" && stageConfig.stageStatus === "Purchase Review";
    const dialog = new frappe.ui.Dialog({
      title: getDialogTitle(frm, stage),
      fields: [
        { fieldtype: "HTML", fieldname: "summary_html" },
        ...stageFields.map((fieldname) => buildDialogField(frm, fieldname, readOnly)),
        { fieldtype: "HTML", fieldname: "audit_html" },
      ],
      size: "large",
    });

    dialog.show();
    dialog.fields_dict.summary_html.$wrapper.html(renderSummaryHtml(frm, stageConfig.stageStatus));
    dialog.fields_dict.summary_html.$wrapper.append(renderReadOnlySectionsHtml(frm, stageConfig.stageStatus));
    dialog.fields_dict.audit_html.$wrapper.html(renderAuditHtml(stage));

    stageFields.forEach((fieldname) => {
      dialog.set_value(fieldname, frm.doc[fieldname]);
    });

    addDialogButtons(frm, dialog, stage);
  }

  function openErpDialog(frm, stageKey) {
    const stage = getStage(frm, stageKey);
    if (!stage) {
      return;
    }

    const dialog = new frappe.ui.Dialog({
      title: getDialogTitle(frm, stage),
      fields: [{ fieldtype: "HTML", fieldname: "content" }],
      size: "large",
    });
    dialog.show();
    dialog.fields_dict.content.$wrapper.html(`
      ${renderSummaryHtml(frm)}
      ${renderErpHtml(frm, stage)}
    `);
    dialog.$wrapper.on("click", ".calco-governance-doc-link", (event) => {
      event.preventDefault();
      const target = event.currentTarget;
      frappe.set_route("Form", target.dataset.doctype, target.dataset.name);
      dialog.hide();
    });
  }

  function buildDocumentsHtml(documents) {
    if (!documents.length) {
      return `<div class="calco-governance-journey__empty">${__("No linked documents found.")}</div>`;
    }

    return documents.map((doc) => `
      <div class="calco-governance-review__summary-card">
        <div class="calco-governance-review__summary-grid">
          <div>
            <div class="calco-governance-review__summary-item-label">${escapeHtml(doc.doctype)}</div>
            <div class="calco-governance-review__summary-item-value">
              <a href="#" class="calco-governance-doc-link" data-doctype="${escapeHtml(doc.doctype)}" data-name="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}</a>
            </div>
          </div>
          <div>
            <div class="calco-governance-review__summary-item-label">${__("Status")}</div>
            <div class="calco-governance-review__summary-item-value">${escapeHtml(doc.status || __("Open"))}</div>
          </div>
          <div>
            <div class="calco-governance-review__summary-item-label">${__("Detail")}</div>
            <div class="calco-governance-review__summary-item-value">${escapeHtml(doc.detail || __("No extra details"))}</div>
          </div>
        </div>
      </div>
    `).join("");
  }

  function openStageDialog(frm, stageKey) {
    const stage = getStage(frm, stageKey);
    if (!stage) {
      return;
    }

    const dialog = new frappe.ui.Dialog({
      title: getDialogTitle(frm, stage),
      fields: [{ fieldtype: "HTML", fieldname: "content" }],
      size: "large",
    });
    dialog.show();

    dialog.fields_dict.content.$wrapper.html(`
      ${renderSummaryHtml(frm)}
      ${renderAuditHtml(stage)}
      ${buildDocumentsHtml(stage.documents || [])}
    `);

    dialog.$wrapper.on("click", ".calco-governance-doc-link", (event) => {
      event.preventDefault();
      const target = event.currentTarget;
      frappe.set_route("Form", target.dataset.doctype, target.dataset.name);
      dialog.hide();
    });
  }

  function showBlockedStageMessage(stage) {
    const message = stage.status === "Stopped"
      ? __("Request rejected. No further action allowed.")
      : __("This stage will open after the previous review is approved.");
    frappe.msgprint(message);
  }

  function openStageFromDetails(frm, stageKey) {
    const stage = getStage(frm, stageKey);
    const config = getConfig(frm.doctype);
    if (!stage || !config) {
      return;
    }

    if (["Not Started", "Stopped"].includes(stage.status)) {
      showBlockedStageMessage(stage);
      return;
    }

    if ((config.reviewStages || {})[stage.key]) {
      if (stage.status === "Completed" || stage.status === "Rejected") {
        openStageDialog(frm, stageKey);
        return;
      }
      openReviewDialog(frm, stageKey);
      return;
    }

    if ((config.erpStageKeys || []).includes(stage.key)) {
      openErpDialog(frm, stageKey);
      return;
    }

    openStageDialog(frm, stageKey);
  }

  function executeStageAction(frm, stageKey) {
    const stage = getStage(frm, stageKey);
    const config = getConfig(frm.doctype);
    if (!stage || !config) {
      return;
    }

    if ((config.reviewStages || {})[stage.key]) {
      if (["Not Started", "Stopped"].includes(stage.status)) {
        showBlockedStageMessage(stage);
        return;
      }
      openReviewDialog(frm, stageKey);
      return;
    }

    if ((config.erpStageKeys || []).includes(stage.key)) {
      if (["Not Started", "Stopped"].includes(stage.status)) {
        showBlockedStageMessage(stage);
        return;
      }
      openErpDialog(frm, stageKey);
      return;
    }

    openStageDialog(frm, stageKey);
  }

  function getSupplierRequestPrefillPayload(frm) {
    return {
      __create_from_rm_request: 1,
      source_rm_request: frm.doc.name,
      source_rm_code: frm.doc.rm_code || "",
      source_rm_name: frm.doc.rm_name || "",
      source_category: frm.doc.category || "",
      source_stock_uom: frm.doc.stock_uom || "",
      expected_purchase_rate: frm.doc.purchase_target_rate || 0,
      expected_lead_time_days: frm.doc.purchase_lead_time_days || 0,
      expected_moq: frm.doc.purchase_moq || 0,
      expected_purchase_pack_size: frm.doc.purchase_pack_size || 0,
      commercial_remarks: frm.doc.commercial_remarks || "",
      supplier_request_items: JSON.stringify([
        {
          item_code: frm.doc.rm_code || "",
          approval_status: "Approved",
          lead_time: frm.doc.purchase_lead_time_days || 0,
          payment_terms: "",
          supplier_rating: 0,
          effective_date: "",
          expiry_date: "",
        },
      ]),
    };
  }

  function openSupplierRequestFromRm(frm) {
    if (frm.doc.supplier_request) {
      frappe.set_route("Form", "New Supplier Request", frm.doc.supplier_request);
      return;
    }

    const payload = getSupplierRequestPrefillPayload(frm);
    if (!payload.source_rm_code) {
      frappe.msgprint({
        title: __("Create Supplier Request"),
        message: __("RM Code is required before creating a Supplier Request."),
        indicator: "orange",
      });
      return;
    }

    frappe.route_options = payload;
    frappe.new_doc("New Supplier Request");
  }

  function normalizeSupplierRequestItemsOption(itemsOption) {
    if (!itemsOption) {
      return [];
    }
    if (Array.isArray(itemsOption)) {
      return itemsOption;
    }
    if (typeof itemsOption === "string") {
      try {
        const parsed = frappe.utils.parse_json(itemsOption);
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        console.warn("Unable to parse supplier request route items", {
          route_items: itemsOption,
          error,
        });
      }
    }
    return [];
  }

  function populateSupplierRequestFromRoute(frm) {
    const options = frappe.route_options;
    if (!options || !options.__create_from_rm_request || !frm.is_new()) {
      return;
    }

    const fields = [
      ["source_rm_request", options.source_rm_request],
      ["source_rm_code", options.source_rm_code],
      ["source_rm_name", options.source_rm_name],
      ["source_category", options.source_category],
      ["source_stock_uom", options.source_stock_uom],
      ["expected_purchase_rate", options.expected_purchase_rate || 0],
      ["expected_lead_time_days", options.expected_lead_time_days || 0],
      ["expected_moq", options.expected_moq || 0],
      ["expected_purchase_pack_size", options.expected_purchase_pack_size || 0],
      ["commercial_remarks", options.commercial_remarks],
    ];

    fields.forEach(([fieldname, value]) => {
      if (frm.fields_dict[fieldname]) {
        frm.set_value(fieldname, value || "");
      }
    });

    const rows = normalizeSupplierRequestItemsOption(options.supplier_request_items);
    if (rows.length && frm.fields_dict.supplier_request_items && !frm.doc.supplier_request_items?.length) {
      rows.forEach((row) => {
        if (!row || !row.item_code) {
          return;
        }
        frm.add_child("supplier_request_items", {
          item_code: row.item_code || "",
          approval_status: row.approval_status || "Approved",
          supplier_rating: row.supplier_rating || 0,
          lead_time: row.lead_time || 0,
          payment_terms: row.payment_terms || "",
          effective_date: row.effective_date || "",
          expiry_date: row.expiry_date || "",
        });
      });
      frm.refresh_field("supplier_request_items");
    }

    frappe.route_options = {};
  }

  function renderTracker(frm, data) {
    const wrapper = getWrapper(frm);
    const config = getConfig(frm.doctype);
    if (!wrapper || !config) {
      return;
    }

    wrapper.html(`
      <section class="calco-governance-journey">
        <div class="calco-governance-journey__header">
          <div>
            <div class="calco-governance-journey__title">${escapeHtml(config.title)}</div>
            <div class="calco-governance-journey__subtitle">${escapeHtml(config.subtitle)}</div>
          </div>
          <div class="calco-governance-journey__tag">${__("Focused reviews")}</div>
        </div>
        <div class="calco-governance-journey__flow">${buildFlowHtml(frm, data.stages || [])}</div>
      </section>
    `);

    wrapper.find("[data-action-stage-key]").on("click", (event) => {
      event.stopPropagation();
      executeStageAction(frm, event.currentTarget.dataset.actionStageKey);
    });
    wrapper.find("[data-detail-stage-key]").on("click", (event) => {
      event.stopPropagation();
      openStageFromDetails(frm, event.currentTarget.dataset.detailStageKey);
    });
    wrapper.find("[data-stage-key]").on("click", (event) => {
      const target = event.target;
      if (target.closest("[data-action-stage-key]") || target.closest("[data-detail-stage-key]")) {
        return;
      }
      executeStageAction(frm, event.currentTarget.dataset.stageKey);
    });
  }

  function scheduleTrackerRetry(frm) {
    frm.__governance_tracker_retry_count = (frm.__governance_tracker_retry_count || 0) + 1;
    if (frm.__governance_tracker_retry_count > MAX_RENDER_RETRIES) {
      console.error("Governance tracker wrapper was not available after retries", {
        doctype: frm.doctype,
        name: frm.doc.name,
      });
      frappe.show_alert({
        message: __("Journey tracker could not mount on the form. Please refresh the page."),
        indicator: "orange",
      });
      return;
    }

    setTimeout(() => loadTracker(frm), 250);
  }

  async function loadTracker(frm) {
    ensureStyle();
    syncMainFormState(frm);
    const config = getConfig(frm.doctype);

    if (frm.__governance_tracker_loading) {
      return;
    }

    frm.__governance_tracker_loading = true;
    const wrapper = getWrapper(frm);
    if (!config) {
      frm.__governance_tracker_loading = false;
      return;
    }
    if (!wrapper) {
      scheduleTrackerRetry(frm);
      frm.__governance_tracker_loading = false;
      return;
    }

    frm.__governance_tracker_retry_count = 0;

    if (frm.is_new()) {
      renderState(frm, __("Save the document to load the request journey tracker."));
      frm.__governance_tracker_loading = false;
      return;
    }

    renderState(frm, __("Loading governance journey..."));

    try {
      const response = await frappe.call({
        method: config.method,
        args: { name: frm.doc.name },
        freeze: false,
      });
      frm.__governance_journey_data = response.message || {};
      if (!Array.isArray(frm.__governance_journey_data.stages)) {
        renderVisibleTrackerError(
          frm,
          __("The journey payload did not include a valid stages list."),
          JSON.stringify({
            status: frm.__governance_journey_data.overall_status || "",
            keys: Object.keys(frm.__governance_journey_data || {}),
          }),
        );
        frm.__governance_tracker_loading = false;
        return;
      }
      renderTracker(frm, frm.__governance_journey_data);
    } catch (error) {
      console.error("Governance tracker load failed", error);
      renderVisibleTrackerError(
        frm,
        error.message || __("Unable to load the governance journey right now."),
        error.exc_type || error.name || "",
      );
    } finally {
      frm.__governance_tracker_loading = false;
    }
  }

  window.calco_erp.master_data_governance.loadTracker = loadTracker;
  window.calco_erp.master_data_governance.syncMainFormState = syncMainFormState;
  window.renderMasterDataJourney = async function renderMasterDataJourney(frm, payload) {
    ensureStyle();
    syncMainFormState(frm);
    if (payload) {
      frm.__governance_journey_data = payload;
      renderTracker(frm, payload);
      return payload;
    }
    await loadTracker(frm);
    return frm.__governance_journey_data || {};
  };
  window.syncMasterDataJourneyState = syncMainFormState;

  frappe.ui.form.on("New RM Request", {
    refresh(frm) {
      loadTracker(frm);
    },
    onload_post_render(frm) {
      loadTracker(frm);
    },
    status(frm) {
      syncMainFormState(frm);
    },
  });

  frappe.ui.form.on("New Supplier Request", {
    supplier_type(frm) {
      applySupplierRequestCurrencyDefaults(frm);
    },
    refresh(frm) {
      loadTracker(frm);
      applySupplierRequestCurrencyDefaults(frm);
    },
    onload_post_render(frm) {
      populateSupplierRequestFromRoute(frm);
      applySupplierRequestCurrencyDefaults(frm);
      loadTracker(frm);
    },
    status(frm) {
      syncMainFormState(frm);
    },
  });
})();
