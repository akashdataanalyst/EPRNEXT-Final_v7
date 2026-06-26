frappe.provide("calco_erp.production_execution");

(function () {
  const HTML_FIELD = "journey_tracker_html";
  const STYLE_ID = "calco-production-execution-style";
  const SUPPORTED_DOCTYPES = ["Production Requirement", "Production Job Card"];

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .calco-production-journey {
        padding: 16px;
        border: 1px solid var(--border-color);
        border-radius: 18px;
        background:
          radial-gradient(circle at top right, rgba(198, 40, 40, 0.08), transparent 32%),
          linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(255, 255, 255, 1));
      }
      .calco-production-journey__header {
        display:flex;
        justify-content:space-between;
        align-items:flex-start;
        gap:12px;
        margin-bottom:14px;
      }
      .calco-production-journey__title {
        font-size:16px;
        font-weight:700;
      }
      .calco-production-journey__subtitle {
        font-size:12px;
        color:var(--text-muted);
      }
      .calco-production-journey__summary {
        display:grid;
        grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));
        gap:10px;
        margin-bottom:14px;
      }
      .calco-production-journey__metric {
        border:1px solid var(--border-color);
        border-radius:14px;
        padding:10px 12px;
        background:rgba(255,255,255,0.78);
      }
      .calco-production-journey__metric-label {
        font-size:11px;
        text-transform:uppercase;
        letter-spacing:0.04em;
        color:var(--text-muted);
        margin-bottom:4px;
      }
      .calco-production-journey__metric-value {
        font-size:17px;
        font-weight:700;
      }
      .calco-production-journey__flow {
        display:flex;
        gap:10px;
        overflow-x:auto;
        padding-bottom:4px;
      }
      .calco-production-journey__stage {
        min-width:190px;
        border:1px solid var(--border-color);
        border-radius:14px;
        background:var(--fg-color);
        padding:14px;
        box-shadow: inset 0 4px 0 var(--stage-color, #94a3b8);
        cursor:pointer;
      }
      .calco-production-journey__stage-label {
        font-size:13px;
        font-weight:700;
        margin-bottom:8px;
      }
      .calco-production-journey__stage-status {
        display:inline-flex;
        border-radius:999px;
        padding:4px 8px;
        font-size:11px;
        font-weight:700;
        margin-bottom:8px;
        background:rgba(15, 23, 42, 0.06);
      }
      .calco-production-journey__stage-summary {
        font-size:12px;
        color:var(--text-muted);
        line-height:1.45;
      }
      .calco-production-journey__connector {
        flex:0 0 24px;
        align-self:center;
        height:2px;
        background:linear-gradient(90deg, rgba(148,163,184,0.7), rgba(148,163,184,0.18));
      }
      .calco-production-journey__state {
        font-size:13px;
        color:var(--text-muted);
        padding:12px 2px;
      }
      .calco-production-journey__stage[data-color="grey"] { --stage-color:#94a3b8; }
      .calco-production-journey__stage[data-color="blue"] { --stage-color:#1565c0; }
      .calco-production-journey__stage[data-color="green"] { --stage-color:#2e7d32; }
      .calco-production-journey__stage[data-color="orange"] { --stage-color:#ef6c00; }
      .calco-production-journey__stage[data-color="red"] { --stage-color:#c62828; }
      .calco-production-journey-dialog__summary {
        padding:12px 14px;
        border-radius:12px;
        background:rgba(15, 23, 42, 0.04);
        margin-bottom:12px;
        font-size:13px;
      }
    `;
    document.head.appendChild(style);
  }

  function getWrapper(frm) {
    return frm.fields_dict[HTML_FIELD] && frm.fields_dict[HTML_FIELD].$wrapper;
  }

  function renderState(wrapper, message) {
    wrapper.html(`
      <section class="calco-production-journey">
        <div class="calco-production-journey__header">
          <div>
            <div class="calco-production-journey__title">${__("Production Execution Journey")}</div>
            <div class="calco-production-journey__subtitle">${__("Production execution stops at FG Quarantine in Phase 3A")}</div>
          </div>
        </div>
        <div class="calco-production-journey__state">${frappe.utils.escape_html(message || "")}</div>
      </section>
    `);
  }

  function buildMetrics(summary) {
    return [
      ["Requirement", summary.requirement || "-"],
      ["Job Card", summary.job_card || "-"],
      ["FG Batch", summary.fg_batch_no || "-"],
      ["Grade", summary.grade_code || "-"],
      ["Planned Qty", `${summary.planned_qty || 0} Kg`],
      ["Actual Qty", `${summary.actual_qty || 0} Kg`],
    ].map(([label, value]) => `
      <div class="calco-production-journey__metric">
        <div class="calco-production-journey__metric-label">${frappe.utils.escape_html(label)}</div>
        <div class="calco-production-journey__metric-value">${frappe.utils.escape_html(value)}</div>
      </div>
    `).join("");
  }

  function buildFlow(stages) {
    return (stages || []).map((stage, index) => `
      <button type="button" class="calco-production-journey__stage" data-color="${frappe.utils.escape_html(stage.color)}" data-stage-key="${frappe.utils.escape_html(stage.key)}">
        <div class="calco-production-journey__stage-label">${frappe.utils.escape_html(stage.label)}</div>
        <div class="calco-production-journey__stage-status">${frappe.utils.escape_html(stage.status)}</div>
        <div class="calco-production-journey__stage-summary">${frappe.utils.escape_html(stage.summary || "")}</div>
      </button>
      ${index < stages.length - 1 ? '<div class="calco-production-journey__connector"></div>' : ""}
    `).join("");
  }

  function openStageDialog(stage) {
    const dialog = new frappe.ui.Dialog({
      title: `${stage.label} - ${stage.status}`,
      fields: [{ fieldtype: "HTML", fieldname: "content" }],
      size: "large",
    });
    dialog.show();
    const routeHtml = stage.route
      ? `<div style="margin-top:10px;"><a href="#" class="calco-production-open-doc">${__("Open linked document")}</a></div>`
      : "";
    dialog.fields_dict.content.$wrapper.html(`
      <div class="calco-production-journey-dialog__summary">${frappe.utils.escape_html(stage.summary || "")}</div>
      ${routeHtml}
    `);
    dialog.$wrapper.on("click", ".calco-production-open-doc", (event) => {
      event.preventDefault();
      if (stage.route) {
        frappe.set_route(...stage.route);
      }
      dialog.hide();
    });
  }

  function renderTracker(frm, payload) {
    const wrapper = getWrapper(frm);
    if (!wrapper) {
      return;
    }
    wrapper.html(`
      <section class="calco-production-journey">
        <div class="calco-production-journey__header">
          <div>
            <div class="calco-production-journey__title">${__("Production Execution Journey")}</div>
            <div class="calco-production-journey__subtitle">${__("Weekly planning to FG Quarantine only")}</div>
          </div>
        </div>
        <div class="calco-production-journey__summary">${buildMetrics(payload.summary || {})}</div>
        <div class="calco-production-journey__flow">${buildFlow(payload.stages || [])}</div>
      </section>
    `);
    wrapper.find(".calco-production-journey__stage").on("click", (event) => {
      const stageKey = event.currentTarget.dataset.stageKey;
      const stage = (payload.stages || []).find((row) => row.key === stageKey);
      if (stage) {
        openStageDialog(stage);
      }
    });
  }

  async function loadTracker(frm) {
    ensureStyle();
    const wrapper = getWrapper(frm);
    if (!wrapper) {
      return;
    }
    if (frm.is_new()) {
      renderState(wrapper, __("Save this document to load the Production Execution Journey."));
      return;
    }
    renderState(wrapper, __("Loading Production Execution Journey..."));
    try {
      const response = await frappe.call({
        method: "calco_erp.calco_production.production_execution_journey.get_tracker",
        args: {
          doctype: frm.doctype,
          docname: frm.doc.name,
        },
        freeze: false,
      });
      renderTracker(frm, response.message || {});
    } catch (error) {
      renderState(wrapper, error.message || __("Unable to load Production Execution Journey."));
    }
  }

  function register(doctype) {
    frappe.ui.form.on(doctype, {
      refresh(frm) {
        loadTracker(frm);
      },
    });
  }

  SUPPORTED_DOCTYPES.forEach(register);
})();
