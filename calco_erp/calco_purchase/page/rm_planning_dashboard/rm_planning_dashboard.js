frappe.pages["rm-planning-dashboard"].on_page_load = function (wrapper) {
  new CalcoRMPlanningDashboard(wrapper);
};

class CalcoRMPlanningDashboard {
  constructor(wrapper) {
    this.wrapper = $(wrapper);
    this.rows = [];
    this.suppress_refresh = false;
    this.make_page();
    this.make_layout();
    this.refresh();
  }

  make_page() {
    this.page = frappe.ui.make_app_page({
      parent: this.wrapper,
      title: "RM Planning Dashboard",
      single_column: true,
    });

    this.fields = {
      item_code: this.page.add_field({
        label: "Item Code",
        fieldname: "item_code",
        fieldtype: "Link",
        options: "Item",
        change: () => this.refresh(),
      }),
      category: this.page.add_field({
        label: "Category",
        fieldname: "category",
        fieldtype: "Link",
        options: "Item Group",
        change: () => this.refresh(),
      }),
      inventory_health: this.page.add_field({
        label: "Inventory Health",
        fieldname: "inventory_health",
        fieldtype: "Select",
        options: "\nCritical\nLow\nHealthy\nOverstock",
        change: () => this.refresh(),
      }),
      current_season: this.page.add_field({
        label: "Current Season",
        fieldname: "current_season",
        fieldtype: "Select",
        options: "\nLow\nNormal\nPeak",
        change: () => this.refresh(),
      }),
      only_items_requiring_purchase: this.page.add_field({
        label: "Only Requiring Purchase",
        fieldname: "only_items_requiring_purchase",
        fieldtype: "Check",
        change: () => this.refresh(),
      }),
      supplier: this.page.add_field({
        label: "Supplier",
        fieldname: "supplier",
        fieldtype: "Link",
        options: "Supplier",
        change: () => this.refresh(),
      }),
      supplier_type: this.page.add_field({
        label: "Supplier Type",
        fieldname: "supplier_type",
        fieldtype: "Select",
        options: "\nLocal\nOverseas\nTrader\nManufacturer",
        change: () => this.refresh(),
      }),
    };

    this.page.set_primary_action("Refresh Calculations", () => this.refresh(), "refresh");
    this.page.add_action_item("Export to Excel", () => this.export_rows());
    this.page.add_action_item("Bulk Create Material Requests for All Red Items", () => this.create_red_material_requests());
  }

  make_layout() {
    this.page.main.html(`
      <div class="calco-rm-planning">
        <div class="calco-rm-planning__cards"></div>
        <div class="calco-rm-planning__toolbar">
          <div class="calco-rm-planning__warehouse"></div>
          <div class="calco-rm-planning__summary"></div>
        </div>
        <div class="calco-rm-planning__filters">
          <div class="calco-rm-planning__filters-header">
            <div class="calco-rm-planning__filters-title">Filters</div>
            <div class="calco-rm-planning__filters-summary"></div>
          </div>
          <div class="calco-rm-planning__filter-controls"></div>
          <div class="calco-rm-planning__filter-actions">
            <button class="btn btn-sm btn-primary calco-rm-planning__apply-filters">Apply Filters</button>
            <button class="btn btn-sm btn-default calco-rm-planning__clear-filters">Clear Filters</button>
          </div>
        </div>
        <div class="calco-rm-planning__table-wrap">
          <table class="calco-rm-planning__table">
            <thead></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="calco-rm-planning__analytics">
          <h4>Supplier Lead Time Analytics</h4>
          <div class="calco-rm-planning__analytics-table"></div>
        </div>
      </div>
    `);

    if (!document.getElementById("calco-rm-planning-style")) {
      const style = document.createElement("style");
      style.id = "calco-rm-planning-style";
      style.textContent = `
        .calco-rm-planning__cards {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 16px;
        }
        .calco-rm-planning__card {
          border: 1px solid var(--border-color);
          border-left: 6px solid var(--card-accent, #90a4ae);
          border-radius: 14px;
          padding: 14px 16px;
          background: linear-gradient(180deg, var(--card-soft, #fff) 0%, var(--fg-color) 100%);
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .calco-rm-planning__card-label {
          color: var(--text-muted);
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 8px;
        }
        .calco-rm-planning__card-value {
          font-size: 28px;
          font-weight: 700;
          line-height: 1.1;
        }
        .calco-rm-planning__toolbar {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 12px;
          color: var(--text-muted);
        }
        .calco-rm-planning__filters {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-bottom: 12px;
          padding: 14px;
          border: 1px solid var(--border-color);
          border-radius: 14px;
          background: linear-gradient(180deg, #fafcff 0%, var(--fg-color) 100%);
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .calco-rm-planning__filters-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          width: 100%;
        }
        .calco-rm-planning__filters-title {
          font-weight: 700;
          font-size: 16px;
        }
        .calco-rm-planning__filters-summary {
          color: var(--text-muted);
          font-size: 12px;
          text-align: right;
        }
        .calco-rm-planning__filter-controls {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 10px 12px;
          width: 100%;
        }
        .calco-rm-planning__filter-controls .form-group {
          margin-bottom: 0;
        }
        .calco-rm-planning__filter-controls .control-label {
          font-size: 12px;
          color: #475467;
          margin-bottom: 6px;
          font-weight: 600;
          display: block;
        }
        .calco-rm-planning__filter-controls .control-input,
        .calco-rm-planning__filter-controls .select-input,
        .calco-rm-planning__filter-controls .link-field .form-control,
        .calco-rm-planning__filter-controls input,
        .calco-rm-planning__filter-controls select {
          min-height: 34px;
          width: 100%;
          border-radius: 10px;
          border: 1px solid #cbd5e1;
          background: #fff;
        }
        .calco-rm-planning__filter-controls .checkbox {
          margin-top: 8px;
        }
        .calco-rm-planning__filter-actions {
          display: flex;
          justify-content: flex-end;
          gap: 8px;
          width: 100%;
        }
        .calco-rm-planning__table-wrap {
          overflow: auto;
          border: 1px solid var(--border-color);
          border-radius: 14px;
          background: var(--fg-color);
          max-height: calc(100vh - 310px);
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .calco-rm-planning__table {
          width: 100%;
          border-collapse: collapse;
          min-width: 1500px;
        }
        .calco-rm-planning__table th,
        .calco-rm-planning__table td {
          padding: 10px 12px;
          border-bottom: 1px solid var(--border-color);
          vertical-align: top;
          font-size: 12px;
        }
        .calco-rm-planning__table th {
          position: sticky;
          top: 0;
          background: white;
          z-index: 5;
          box-shadow: 0 1px 0 var(--border-color);
          text-align: left;
          white-space: nowrap;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          color: #475467;
        }
        .calco-rm-planning__table tbody tr {
          cursor: pointer;
        }
        .calco-rm-planning__table tbody tr:hover {
          background: #f8fafc;
        }
        .calco-rm-planning__health {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-weight: 600;
        }
        .calco-rm-planning__health-dot {
          width: 10px;
          height: 10px;
          border-radius: 999px;
          display: inline-block;
        }
        .calco-rm-planning__health-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 700;
          white-space: nowrap;
        }
        .calco-rm-planning__row--critical {
          background: #fff5f5;
        }
        .calco-rm-planning__row--low {
          background: #fffdf4;
        }
        .calco-rm-planning__row--healthy {
          background: #f6fff9;
        }
        .calco-rm-planning__row--overstock {
          background: #fbf7ff;
        }
        .calco-rm-planning__ows-qty--active {
          font-weight: 700;
          color: #b42318;
        }
        .calco-rm-planning__actions {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
        }
        .calco-rm-planning__action-empty {
          color: var(--text-muted);
          font-weight: 600;
        }
        .calco-rm-planning__issue {
          display: inline-block;
          margin: 2px 4px 0 0;
          padding: 2px 6px;
          border-radius: 999px;
          background: var(--subtle-fg);
          font-size: 11px;
        }
        .calco-rm-planning__analytics {
          margin-top: 20px;
          border: 1px solid var(--border-color);
          border-radius: 14px;
          background: var(--fg-color);
          padding: 16px;
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .calco-rm-planning__analytics-table table {
          width: 100%;
          border-collapse: collapse;
        }
        .calco-rm-planning__analytics-table th,
        .calco-rm-planning__analytics-table td {
          padding: 8px 10px;
          border-bottom: 1px solid var(--border-color);
          font-size: 12px;
          text-align: left;
        }
        @media (max-width: 1400px) {
          .calco-rm-planning__cards {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
        @media (max-width: 768px) {
          .calco-rm-planning__cards {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .calco-rm-planning__filters-header,
          .calco-rm-planning__toolbar {
            flex-direction: column;
            align-items: flex-start;
          }
        }
      `;
      document.head.appendChild(style);
    }

    const $controls = this.page.main.find(".calco-rm-planning__filter-controls");
    Object.values(this.fields).forEach((field) => {
      if (field.$wrapper) {
        $controls.append(field.$wrapper);
      }
    });
    this.page.main.find(".calco-rm-planning__apply-filters").on("click", () => this.refresh());
    this.page.main.find(".calco-rm-planning__clear-filters").on("click", () => this.clear_filters());
  }

  build_args() {
    return Object.fromEntries(
      Object.entries(this.fields).map(([key, field]) => [key, field.get_value() || ""])
    );
  }

  refresh() {
    if (this.suppress_refresh) {
      return;
    }
    frappe.call({
      method: "calco_erp.calco_purchase.page.rm_planning_dashboard.rm_planning_dashboard.get_dashboard_data",
      args: this.build_args(),
      freeze: true,
      freeze_message: "Loading RM planning dashboard...",
    }).then((r) => {
      this.data = r.message || {};
      this.rows = this.data.rows || [];
      this.render_cards();
      this.render_table();
      this.render_analytics();
      this.render_filter_summary();
      this.page.main.find(".calco-rm-planning__warehouse").text(`Warehouse: ${this.data.warehouse || ""}`);
      this.page.main.find(".calco-rm-planning__summary").text(`Rows: ${this.rows.length}`);
    });
  }

  render_cards() {
    const rows = this.rows || [];
    const cards = [
      { label: "Total RM Items", value: rows.length, accent: "#64748b", soft: "#f5f8fc" },
      { label: "Critical - Buy Now", value: rows.filter((row) => row.inventory_health === "Critical").length, accent: "#d92d20", soft: "#fff1f1" },
      { label: "Low - Plan Order", value: rows.filter((row) => row.inventory_health === "Low").length, accent: "#dc6803", soft: "#fffaeb" },
      { label: "Healthy", value: rows.filter((row) => row.inventory_health === "Healthy").length, accent: "#16a34a", soft: "#effcf4" },
      { label: "Overstock", value: rows.filter((row) => row.inventory_health === "Overstock").length, accent: "#7c3aed", soft: "#f6f0ff" },
      {
        label: "Total OWS Qty",
        value: this.formatNumber(rows.reduce((total, row) => total + Number(row.suggested_order_qty || 0), 0), 3),
        accent: "#2563eb",
        soft: "#eff6ff",
      },
    ];
    this.page.main.find(".calco-rm-planning__cards").html(
      cards.map((card) => `
        <div class="calco-rm-planning__card" style="--card-accent:${card.accent}; --card-soft:${card.soft};">
          <div class="calco-rm-planning__card-label">${frappe.utils.escape_html(card.label || "")}</div>
          <div class="calco-rm-planning__card-value">${frappe.utils.escape_html(String(card.value ?? ""))}</div>
        </div>
      `).join("")
    );
  }

  render_table() {
    const columns = [
      { label: "Item Code", fieldname: "item_code" },
      { label: "Item Name", fieldname: "item_name" },
      { label: "Season", fieldname: "current_season" },
      { label: "Daily Use", fieldname: "selected_daily_consumption" },
      { label: "Lead Time", fieldname: "lead_time_days" },
      { label: "Safety Days", fieldname: "safety_days" },
      { label: "Current Stock", fieldname: "current_rm_store_stock" },
      { label: "Open PO / In Transit", fieldname: "open_po_in_transit_qty" },
      { label: "Projected Qty", fieldname: "projected_available_qty" },
      { label: "Coverage Days", fieldname: "coverage_days" },
      { label: "Inventory Health", fieldname: "inventory_health" },
      { label: "OWS Qty", fieldname: "suggested_order_qty" },
      { label: "Required By", fieldname: "required_by_date" },
      { label: "Preferred Supplier", fieldname: "preferred_supplier" },
      { label: "Action", fieldname: "_actions" },
    ];

    this.page.main.find(".calco-rm-planning__table thead").html(
      `<tr>${columns.map((col) => `<th>${frappe.utils.escape_html(col.label)}</th>`).join("")}</tr>`
    );
    this.page.main.find(".calco-rm-planning__table tbody").html(
      this.rows.map((row, index) => `
        <tr data-row-index="${index}" class="${this.getRowClass(row)}">
          <td><a href="${row.item_route}" class="calco-rm-planning__item-link">${frappe.utils.escape_html(row.item_code)}</a></td>
          <td>${frappe.utils.escape_html(row.item_name || "")}</td>
          <td>${frappe.utils.escape_html(row.current_season || "")}</td>
          <td>${frappe.format(row.selected_daily_consumption, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.lead_time_days, { fieldtype: "Float", precision: 2 })}</td>
          <td>${frappe.format(row.safety_days, { fieldtype: "Float", precision: 2 })}</td>
          <td>${frappe.format(row.current_rm_store_stock, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.open_po_in_transit_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.projected_available_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${row.coverage_days === null ? __("No Consumption") : frappe.format(row.coverage_days, { fieldtype: "Float", precision: 2 })}</td>
          <td>${this.render_health(row)}</td>
          <td class="${Number(row.suggested_order_qty || 0) > 0 ? "calco-rm-planning__ows-qty--active" : ""}">${frappe.format(row.suggested_order_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.utils.escape_html(row.required_by_date || "")}</td>
          <td>${frappe.utils.escape_html(row.preferred_supplier || "")}</td>
          <td>${this.render_actions(row)}</td>
        </tr>
      `).join("")
    );

    this.bind_row_actions();
  }

  render_filter_summary() {
    const active = Object.entries(this.build_args())
      .filter(([, value]) => !!value)
      .map(([key, value]) => `${frappe.model.unscrub(key)}: ${value}`);
    this.page.main.find(".calco-rm-planning__filters-summary").text(
      active.length ? active.join(" | ") : "No active filters"
    );
  }

  render_health(row) {
    const colorMap = {
      red: { dot: "#d92d20", bg: "#fee4e2", text: "#b42318" },
      yellow: { dot: "#dc6803", bg: "#fef0c7", text: "#b54708" },
      green: { dot: "#16a34a", bg: "#dcfce7", text: "#15803d" },
      purple: { dot: "#7c3aed", bg: "#ede9fe", text: "#6d28d9" },
    };
    const palette = colorMap[row.inventory_health_color] || { dot: "#90a4ae", bg: "#f1f5f9", text: "#475569" };
    return `
      <span class="calco-rm-planning__health-badge" style="background:${palette.bg}; color:${palette.text};">
        <span class="calco-rm-planning__health-dot" style="background:${palette.dot}"></span>
        ${frappe.utils.escape_html(row.inventory_health || "")}
      </span>
    `;
  }

  getRowClass(row) {
    const health = (row.inventory_health || "").toLowerCase();
    return health ? `calco-rm-planning__row--${health}` : "";
  }

  render_actions(row) {
    if (row.suggested_order_qty > 0) {
      return `<div class="calco-rm-planning__actions"><button class="btn btn-xs btn-primary calco-rm-planning__create-mr">${__("Create MR")}</button></div>`;
    }
    return `<div class="calco-rm-planning__actions"><span class="calco-rm-planning__action-empty">${__("No Action")}</span></div>`;
  }

  bind_row_actions() {
    this.page.main.find(".calco-rm-planning__table tbody tr").on("click", (event) => {
      if ($(event.target).closest("button, a, input").length) {
        return;
      }
      const row = this.get_row_from_event(event);
      if (!row) {
        return;
      }
      this.show_row_details(row);
    });
    this.page.main.find(".calco-rm-planning__create-mr").on("click", (event) => {
      event.stopPropagation();
      const row = this.get_row_from_event(event);
      if (!row) {
        return;
      }
      this.create_material_request(row);
    });
  }

  get_row_from_event(event) {
    const $tr = $(event.currentTarget).closest("tr");
    const index = Number($tr.attr("data-row-index"));
    return this.rows[index];
  }

  create_material_request(row) {
    frappe.call({
      method: "calco_erp.calco_purchase.page.rm_planning_dashboard.rm_planning_dashboard.create_material_request",
      args: {
        item_code: row.item_code,
        qty: row.suggested_order_qty,
        required_by: row.required_by_date,
        warehouse: row.warehouse,
      },
      freeze: true,
      freeze_message: "Creating Material Request...",
    }).then((r) => {
      const message = r.message || {};
      if (message.route) {
        frappe.set_route(message.route);
      }
    });
  }

  create_red_material_requests() {
    const rows = this.rows.filter((row) => row.inventory_health === "Critical" && row.suggested_order_qty > 0);
    if (!rows.length) {
      frappe.msgprint(__("There are no Critical items with a positive Suggested Order Qty in the current view."));
      return;
    }
    this.create_bulk_material_request(rows);
  }

  create_bulk_material_request(rows) {
    frappe.call({
      method: "calco_erp.calco_purchase.page.rm_planning_dashboard.rm_planning_dashboard.create_bulk_material_requests",
      args: { rows_json: JSON.stringify(rows) },
      freeze: true,
      freeze_message: "Creating Material Request...",
    }).then((r) => {
      const message = r.message || {};
      if (message.route) {
        frappe.set_route(message.route);
      }
    });
  }

  clear_filters() {
    this.suppress_refresh = true;
    Object.values(this.fields).forEach((field) => field.set_value(field.df.fieldtype === "Check" ? 0 : ""));
    this.suppress_refresh = false;
    this.refresh();
  }

  formatNumber(value, precision = 2) {
    return Number(Number(value || 0).toFixed(precision)).toString();
  }

  export_rows() {
    const columns = [
      "item_code", "item_name", "current_season", "selected_daily_consumption", "lead_time_days",
      "safety_days", "current_rm_store_stock",
      "open_po_in_transit_qty", "projected_available_qty", "production_requirement", "coverage_days",
      "inventory_health", "suggested_order_qty", "required_by_date", "preferred_supplier", "supplier_type",
      "payment_terms", "daily_avg_consumption_low", "daily_avg_consumption_normal", "daily_avg_consumption_peak",
      "safety_stock", "reorder_level", "maximum_level", "issues"
    ];
    const lines = [
      columns.join(","),
      ...this.rows.map((row) => columns.map((col) => {
        const value = Array.isArray(row[col]) ? row[col].join(" | ") : row[col];
        return `"${String(value ?? "").replace(/"/g, '""')}"`;
      }).join(",")),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "rm_planning_dashboard.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  render_analytics() {
    const rows = this.data.lead_time_analytics || [];
    if (!rows.length) {
      this.page.main.find(".calco-rm-planning__analytics-table").html(`<div class="text-muted">${__("No supplier lead time history available.")}</div>`);
      return;
    }
    this.page.main.find(".calco-rm-planning__analytics-table").html(`
      <table>
        <thead>
          <tr>
            <th>${__("Supplier")}</th>
            <th>${__("Item Code")}</th>
            <th>${__("Average Lead Time")}</th>
            <th>${__("Min Lead Time")}</th>
            <th>${__("Max Lead Time")}</th>
            <th>${__("Last 3 receipt lead times")}</th>
            <th>${__("On-time %")}</th>
            <th>${__("Local / Overseas")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${frappe.utils.escape_html(row.supplier || "")}</td>
              <td>${frappe.utils.escape_html(row.item_code || "")}</td>
              <td>${frappe.format(row.average_lead_time, { fieldtype: "Float", precision: 2 })}</td>
              <td>${frappe.format(row.min_lead_time, { fieldtype: "Float", precision: 2 })}</td>
              <td>${frappe.format(row.max_lead_time, { fieldtype: "Float", precision: 2 })}</td>
              <td>${frappe.utils.escape_html((row.last_three_receipts || []).join(", "))}</td>
              <td>${frappe.format(row.on_time_percentage, { fieldtype: "Percent", precision: 2 })}</td>
              <td>${frappe.utils.escape_html(row.supplier_type || "")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `);
  }

  show_row_details(row) {
    const detailRows = [
      [__("Daily Avg Consumption Low"), frappe.format(row.daily_avg_consumption_low, { fieldtype: "Float", precision: 3 })],
      [__("Daily Avg Consumption Normal"), frappe.format(row.daily_avg_consumption_normal, { fieldtype: "Float", precision: 3 })],
      [__("Daily Avg Consumption Peak"), frappe.format(row.daily_avg_consumption_peak, { fieldtype: "Float", precision: 3 })],
      [__("Safety Stock"), frappe.format(row.safety_stock, { fieldtype: "Float", precision: 3 })],
      [__("Reorder Level"), frappe.format(row.reorder_level, { fieldtype: "Float", precision: 3 })],
      [__("Maximum Level"), frappe.format(row.maximum_level, { fieldtype: "Float", precision: 3 })],
      [__("Production Requirement"), frappe.format(row.production_requirement, { fieldtype: "Float", precision: 3 })],
      [__("Supplier Type"), frappe.utils.escape_html(row.supplier_type || "-")],
      [__("Payment Terms"), frappe.utils.escape_html(row.payment_terms || "-")],
      [__("Issues"), (row.issues || []).length ? row.issues.map((issue) => `<span class="calco-rm-planning__issue">${frappe.utils.escape_html(issue)}</span>`).join("") : __("None")],
    ];

    const leadTimes = (row.lead_time_stats?.last_three || []).length
      ? row.lead_time_stats.last_three.join(", ")
      : "-";

    const html = `
      <div class="calco-rm-planning__detail">
        <div style="margin-bottom: 12px;">
          <strong>${frappe.utils.escape_html(row.item_code || "")}</strong>
          <div class="text-muted">${frappe.utils.escape_html(row.item_name || "")}</div>
        </div>
        <table class="table table-bordered">
          <tbody>
            ${detailRows.map(([label, value]) => `
              <tr>
                <th style="width: 32%;">${label}</th>
                <td>${value}</td>
              </tr>
            `).join("")}
            <tr>
              <th>${__("Supplier Lead Time History")}</th>
              <td>${frappe.utils.escape_html(leadTimes)}</td>
            </tr>
          </tbody>
        </table>
        <div class="calco-rm-planning__actions" style="margin-top: 12px;">
          <button class="btn btn-xs btn-default calco-rm-planning__detail-stock-ledger">${__("View Stock Ledger")}</button>
          <button class="btn btn-xs btn-default calco-rm-planning__detail-open-po">${__("View Open PO")}</button>
          ${row.planning_parameter_route ? `<a class="btn btn-xs btn-default" href="${row.planning_parameter_route}">${__("Planning Param")}</a>` : ""}
        </div>
      </div>
    `;

    const dialog = new frappe.ui.Dialog({
      title: __("RM Planning Details"),
      size: "large",
      fields: [{ fieldtype: "HTML", fieldname: "details_html" }],
    });
    dialog.fields_dict.details_html.$wrapper.html(html);
    dialog.fields_dict.details_html.$wrapper.find(".calco-rm-planning__detail-stock-ledger").on("click", () => {
      frappe.route_options = { item_code: row.item_code, warehouse: row.warehouse };
      frappe.set_route("List", "Stock Ledger Entry");
      dialog.hide();
    });
    dialog.fields_dict.details_html.$wrapper.find(".calco-rm-planning__detail-open-po").on("click", () => {
      frappe.route_options = { supplier: row.preferred_supplier, docstatus: 1 };
      frappe.set_route("List", "Purchase Order");
      dialog.hide();
    });
    dialog.show();
  }
}
