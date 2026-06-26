frappe.pages["material-traceability"].on_page_load = function (wrapper) {
  new CalcoMaterialTraceabilityPage(wrapper);
};

class CalcoMaterialTraceabilityPage {
  constructor(wrapper) {
    this.wrapper = $(wrapper);
    this.page = frappe.ui.make_app_page({
      parent: wrapper,
      title: __("Material Traceability"),
      single_column: true,
    });
    this.searchOptions = ["Any", "Batch No", "PO", "PR", "MR", "Supplier", "Item Code"];
    this.buildLayout();
    this.bindEvents();
    this.loadFromRoute();
  }

  buildLayout() {
    this.page.main.html(`
      <section class="calco-material-traceability">
        <style>
          .calco-material-traceability {
            padding: 18px;
            border-radius: 18px;
            background:
              radial-gradient(circle at top left, rgba(2, 136, 209, 0.08), transparent 26%),
              linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(255, 255, 255, 1));
          }
          .calco-material-traceability__toolbar {
            display: grid;
            grid-template-columns: minmax(180px, 220px) minmax(240px, 1fr) auto;
            gap: 12px;
            align-items: end;
            margin-bottom: 16px;
          }
          .calco-material-traceability__label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-muted);
            margin-bottom: 6px;
          }
          .calco-material-traceability__results {
            display: grid;
            gap: 12px;
          }
          .calco-material-traceability__result {
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 14px 16px;
            background: var(--fg-color);
          }
          .calco-material-traceability__top {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 10px;
          }
          .calco-material-traceability__name {
            font-size: 16px;
            font-weight: 700;
          }
          .calco-material-traceability__status {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 9px;
            background: rgba(46, 125, 50, 0.12);
            color: #1f5b24;
            font-size: 11px;
            font-weight: 700;
          }
          .calco-material-traceability__meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 12px;
          }
          .calco-material-traceability__metric {
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 10px 12px;
            background: rgba(15, 23, 42, 0.02);
          }
          .calco-material-traceability__metric-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-muted);
            margin-bottom: 4px;
          }
          .calco-material-traceability__metric-value {
            font-size: 14px;
            font-weight: 700;
          }
          .calco-material-traceability__links {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
          }
          .calco-material-traceability__link {
            border: 1px solid var(--border-color);
            border-radius: 999px;
            padding: 6px 10px;
            background: rgba(21, 101, 192, 0.06);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
          }
          .calco-material-traceability__empty {
            padding: 24px 0;
            color: var(--text-muted);
          }
          @media (max-width: 768px) {
            .calco-material-traceability__toolbar {
              grid-template-columns: 1fr;
            }
          }
        </style>
        <div class="calco-material-traceability__toolbar">
          <div>
            <div class="calco-material-traceability__label">${__("Search By")}</div>
            <select class="form-control calco-material-traceability__search-by"></select>
          </div>
          <div>
            <div class="calco-material-traceability__label">${__("Search Query")}</div>
            <input class="form-control calco-material-traceability__query" placeholder="${__("Batch No, PO, PR, MR, Supplier, Item Code")}" />
          </div>
          <button type="button" class="btn btn-primary calco-material-traceability__run">${__("Search")}</button>
        </div>
        <div class="calco-material-traceability__performance text-muted small"></div>
        <div class="calco-material-traceability__results"></div>
      </section>
    `);

    this.$searchBy = this.page.main.find(".calco-material-traceability__search-by");
    this.$query = this.page.main.find(".calco-material-traceability__query");
    this.$results = this.page.main.find(".calco-material-traceability__results");
    this.$performance = this.page.main.find(".calco-material-traceability__performance");

    this.$searchBy.html(this.searchOptions.map((option) => `<option value="${frappe.utils.escape_html(option)}">${frappe.utils.escape_html(option)}</option>`).join(""));
  }

  bindEvents() {
    this.page.main.on("click", ".calco-material-traceability__run", () => this.runSearch());
    this.page.main.on("keydown", ".calco-material-traceability__query", (event) => {
      if (event.key === "Enter") {
        this.runSearch();
      }
    });
    this.page.main.on("click", ".calco-material-traceability__link", (event) => {
      const target = event.currentTarget.dataset;
      if (target.doctype && target.name) {
        frappe.set_route("Form", target.doctype, target.name);
      }
    });
  }

  loadFromRoute() {
    const routeOptions = frappe.route_options || {};
    if (routeOptions.search_by) {
      this.$searchBy.val(routeOptions.search_by);
    }
    if (routeOptions.query) {
      this.$query.val(routeOptions.query);
      this.runSearch();
      return;
    }
    this.runSearch();
  }

  async runSearch() {
    try {
      const response = await frappe.call({
        method: "calco_erp.calco_purchase.purchase_journey.search_material_traceability",
        args: {
          query: this.$query.val(),
          search_by: this.$searchBy.val(),
          limit: 20,
        },
        freeze: false,
      });
      this.renderResults(response.message || {});
    } catch (error) {
      this.$results.html(`<div class="calco-material-traceability__empty">${frappe.utils.escape_html(error.message || __("Unable to load traceability results."))}</div>`);
    }
  }

  renderResults(data) {
    const results = data.results || [];
    this.$performance.text(__("Loaded in {0} ms", [data.performance_ms || 0]));

    if (!results.length) {
      this.$results.html(`<div class="calco-material-traceability__empty">${__("No matching Material Request journeys found.")}</div>`);
      return;
    }

    this.$results.html(results.map((row) => `
      <div class="calco-material-traceability__result">
        <div class="calco-material-traceability__top">
          <div class="calco-material-traceability__name">${frappe.utils.escape_html(row.material_request)}</div>
          <div class="calco-material-traceability__status">${frappe.utils.escape_html(row.status || __("Unknown"))}</div>
        </div>
        <div class="calco-material-traceability__meta">
          ${this.renderMetric("Supplier", row.supplier || "-")}
          ${this.renderMetric("Requested", row.requested_qty)}
          ${this.renderMetric("Ordered", row.ordered_qty)}
          ${this.renderMetric("Received", row.received_qty)}
          ${this.renderMetric("Accepted", row.accepted_qty)}
          ${this.renderMetric("Rejected", row.rejected_qty)}
          ${this.renderMetric("Returned", row.returned_qty)}
          ${this.renderMetric("Items", (row.item_codes || []).join(", ") || "-")}
          ${this.renderMetric("Batches", (row.batches || []).join(", ") || "-")}
        </div>
        <div class="calco-material-traceability__links">
          <button type="button" class="calco-material-traceability__link" data-doctype="Material Request" data-name="${frappe.utils.escape_html(row.material_request)}">${__("Open MR")}</button>
          ${(row.purchase_orders || []).map((name) => `<button type="button" class="calco-material-traceability__link" data-doctype="Purchase Order" data-name="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</button>`).join("")}
          ${(row.purchase_receipts || []).map((name) => `<button type="button" class="calco-material-traceability__link" data-doctype="Purchase Receipt" data-name="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</button>`).join("")}
          ${(row.deviations || []).map((name) => `<button type="button" class="calco-material-traceability__link" data-doctype="RM Deviation Approval" data-name="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</button>`).join("")}
          ${(row.supplier_capa_requests || []).map((name) => `<button type="button" class="calco-material-traceability__link" data-doctype="Supplier CAPA Request" data-name="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</button>`).join("")}
        </div>
      </div>
    `).join(""));
  }

  renderMetric(label, value) {
    return `
      <div class="calco-material-traceability__metric">
        <div class="calco-material-traceability__metric-label">${frappe.utils.escape_html(label)}</div>
        <div class="calco-material-traceability__metric-value">${frappe.utils.escape_html(value)}</div>
      </div>
    `;
  }
}
