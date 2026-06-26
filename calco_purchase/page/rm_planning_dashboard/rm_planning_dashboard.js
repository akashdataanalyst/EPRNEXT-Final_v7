frappe.pages["rm-planning-dashboard"].on_page_load = function (wrapper) {
  new CalcoRMPlanningDashboard(wrapper);
};

class CalcoRMPlanningDashboard {
  constructor(wrapper) {
    this.wrapper = $(wrapper);
    this.rows = [];
    this.data = {};
    this.searchTimer = null;
    this.searchSuggestions = [];
    this.filters = {
      item_code: "",
      inventory_health: "All",
      only_items_requiring_purchase: 0,
    };
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
        <div class="calco-rm-planning__filter-card">
          <div class="calco-rm-planning__filter-row">
            <div class="calco-rm-planning__filter-field calco-rm-planning__filter-field--search">
              <label class="calco-rm-planning__filter-label">${__("Search Item")}</label>
              <div class="calco-rm-planning__search-wrap">
                <input type="text" class="form-control calco-rm-planning__search-input" placeholder="${__("Search by Item Code or Item Name")}" autocomplete="off" />
                <div class="calco-rm-planning__search-suggestions"></div>
              </div>
            </div>
            <div class="calco-rm-planning__filter-field calco-rm-planning__filter-field--health">
              <label class="calco-rm-planning__filter-label">${__("Inventory Health")}</label>
              <div class="calco-rm-planning__health-pills">
                <button type="button" class="calco-rm-planning__health-pill is-active" data-health="All">${__("All")}</button>
                <button type="button" class="calco-rm-planning__health-pill" data-health="Critical">${__("Critical")}</button>
                <button type="button" class="calco-rm-planning__health-pill" data-health="Low">${__("Low")}</button>
                <button type="button" class="calco-rm-planning__health-pill" data-health="Healthy">${__("Healthy")}</button>
                <button type="button" class="calco-rm-planning__health-pill" data-health="Overstock">${__("Overstock")}</button>
              </div>
            </div>
            <div class="calco-rm-planning__filter-field calco-rm-planning__filter-field--toggle">
              <label class="calco-rm-planning__filter-label">${__("Quick Option")}</label>
              <label class="calco-rm-planning__checkline">
                <input type="checkbox" class="calco-rm-planning__purchase-only" />
                <span>${__("Only Requiring Purchase")}</span>
              </label>
            </div>
            <div class="calco-rm-planning__filter-actions">
              <button class="btn btn-sm btn-primary calco-rm-planning__apply-filters">${__("Apply Filters")}</button>
              <button class="btn btn-sm btn-default calco-rm-planning__clear-filters">${__("Clear Filters")}</button>
            </div>
          </div>
        </div>
        <div class="calco-rm-planning__table-wrap">
          <table class="calco-rm-planning__table">
            <thead></thead>
            <tbody></tbody>
          </table>
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
        .calco-rm-planning__card.is-clickable {
          cursor: pointer;
          transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .calco-rm-planning__card.is-clickable:hover {
          transform: translateY(-1px);
          box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
        }
        .calco-rm-planning__card.is-selected {
          box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18), 0 12px 24px rgba(15, 23, 42, 0.08);
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
          font-size: 12px;
        }
        .calco-rm-planning__filter-card {
          margin-bottom: 12px;
          padding: 14px 16px;
          border: 1px solid var(--border-color);
          border-radius: 14px;
          background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .calco-rm-planning__filter-row {
          display: grid;
          grid-template-columns: minmax(260px, 1.8fr) minmax(360px, 1.6fr) minmax(220px, 1fr) auto;
          align-items: end;
          gap: 12px;
          width: 100%;
        }
        .calco-rm-planning__filter-field {
          min-width: 0;
        }
        .calco-rm-planning__filter-label {
          display: block;
          margin-bottom: 6px;
          font-size: 12px;
          font-weight: 700;
          color: #475467;
        }
        .calco-rm-planning__search-input {
          min-height: 38px;
          width: 100%;
          border-radius: 10px;
          border: 1px solid #c3d2e6;
          background: #fff;
        }
        .calco-rm-planning__search-wrap {
          position: relative;
        }
        .calco-rm-planning__search-suggestions {
          position: absolute;
          top: calc(100% + 6px);
          left: 0;
          right: 0;
          z-index: 20;
          display: none;
          max-height: 260px;
          overflow: auto;
          border: 1px solid #d0d9e5;
          border-radius: 12px;
          background: #fff;
          box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
        }
        .calco-rm-planning__search-suggestions.is-open {
          display: block;
        }
        .calco-rm-planning__search-suggestion {
          display: block;
          width: 100%;
          padding: 10px 12px;
          border: 0;
          border-bottom: 1px solid #eef2f6;
          background: #fff;
          text-align: left;
        }
        .calco-rm-planning__search-suggestion:last-child {
          border-bottom: 0;
        }
        .calco-rm-planning__search-suggestion:hover {
          background: #f8fbff;
        }
        .calco-rm-planning__search-suggestion-code {
          font-size: 12px;
          font-weight: 700;
          color: #0f172a;
        }
        .calco-rm-planning__search-suggestion-name {
          font-size: 11px;
          color: #475467;
          margin-top: 2px;
        }
        .calco-rm-planning__health-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          min-height: 38px;
          align-items: center;
        }
        .calco-rm-planning__health-pill {
          border: 1px solid #cbd5e1;
          background: #fff;
          color: #344054;
          border-radius: 999px;
          padding: 7px 12px;
          font-size: 12px;
          font-weight: 700;
          line-height: 1;
          transition: all 0.15s ease;
        }
        .calco-rm-planning__health-pill:hover {
          border-color: #94a3b8;
          background: #f8fafc;
        }
        .calco-rm-planning__health-pill.is-active {
          border-color: #2563eb;
          background: #dbeafe;
          color: #1d4ed8;
        }
        .calco-rm-planning__checkline {
          display: flex;
          align-items: center;
          gap: 10px;
          min-height: 38px;
          margin: 0;
          font-size: 13px;
          font-weight: 600;
          color: #344054;
        }
        .calco-rm-planning__checkline input {
          width: 16px;
          height: 16px;
          margin: 0;
        }
        .calco-rm-planning__filter-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 8px;
          white-space: nowrap;
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
          min-width: 1080px;
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
        .calco-rm-planning__coverage {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 78px;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 700;
          background: #eef2ff;
          color: #3730a3;
        }
        .calco-rm-planning__coverage--critical {
          background: #fee4e2;
          color: #b42318;
        }
        .calco-rm-planning__coverage--low {
          background: #fef0c7;
          color: #b54708;
        }
        .calco-rm-planning__coverage--healthy {
          background: #dcfce7;
          color: #15803d;
        }
        .calco-rm-planning__coverage--overstock {
          background: #ede9fe;
          color: #6d28d9;
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
        @media (max-width: 1400px) {
          .calco-rm-planning__cards {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
          .calco-rm-planning__filter-row {
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          }
          .calco-rm-planning__filter-actions {
            justify-content: flex-start;
          }
        }
        @media (max-width: 768px) {
          .calco-rm-planning__cards {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .calco-rm-planning__filter-row {
            grid-template-columns: 1fr;
          }
          .calco-rm-planning__toolbar {
            flex-direction: column;
            align-items: flex-start;
          }
          .calco-rm-planning__filter-actions {
            justify-content: stretch;
            flex-wrap: wrap;
          }
        }
      `;
      document.head.appendChild(style);
    }

    this.bind_filter_toolbar();
  }

  build_args() {
    return {
      item_code: (this.filters.item_code || "").trim(),
      inventory_health: this.filters.inventory_health === "All" ? "" : this.filters.inventory_health,
      only_items_requiring_purchase: this.filters.only_items_requiring_purchase ? 1 : 0,
    };
  }

  refresh() {
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
      this.sync_filter_toolbar();
      this.render_filter_summary();
      this.page.main.find(".calco-rm-planning__warehouse").text(`Warehouse: ${this.data.warehouse || ""}`);
    });
  }

  render_cards() {
    const rows = this.rows || [];
    const cards = [
      { label: "Total RM Items", value: rows.length, accent: "#64748b", soft: "#f5f8fc", health: "" },
      { label: "Critical - Buy Now", value: rows.filter((row) => row.inventory_health === "Critical").length, accent: "#d92d20", soft: "#fff1f1", health: "Critical" },
      { label: "Low - Plan Order", value: rows.filter((row) => row.inventory_health === "Low").length, accent: "#dc6803", soft: "#fffaeb", health: "Low" },
      { label: "Healthy", value: rows.filter((row) => row.inventory_health === "Healthy").length, accent: "#16a34a", soft: "#effcf4", health: "Healthy" },
      { label: "Overstock", value: rows.filter((row) => row.inventory_health === "Overstock").length, accent: "#7c3aed", soft: "#f6f0ff", health: "Overstock" },
      {
        label: "Total Purchase Requirement",
        value: this.formatNumber(rows.reduce((total, row) => total + Number(row.suggested_order_qty || 0), 0), 3),
        accent: "#2563eb",
        soft: "#eff6ff",
        health: "",
      },
    ];
    this.page.main.find(".calco-rm-planning__cards").html(
      cards.map((card) => `
        <div class="calco-rm-planning__card ${card.health ? "is-clickable" : ""} ${card.health && this.filters.inventory_health === card.health ? "is-selected" : ""}" data-health="${frappe.utils.escape_html(card.health || "")}" style="--card-accent:${card.accent}; --card-soft:${card.soft};">
          <div class="calco-rm-planning__card-label">${frappe.utils.escape_html(card.label || "")}</div>
          <div class="calco-rm-planning__card-value">${frappe.utils.escape_html(String(card.value ?? ""))}</div>
        </div>
      `).join("")
    );
    this.bind_card_actions();
  }

  render_table() {
    const columns = [
      { label: "Item Code", fieldname: "item_code" },
      { label: "Item Name", fieldname: "item_name" },
      { label: "Current Stock", fieldname: "current_rm_store_stock" },
      { label: "Open PO / In Transit", fieldname: "open_po_in_transit_qty" },
      { label: "Open MR Qty", fieldname: "open_material_request_qty" },
      { label: "Maximum Inventory Level", fieldname: "maximum_level" },
      { label: "Days of Stock", fieldname: "coverage_days" },
      { label: "Inventory Health", fieldname: "inventory_health" },
      { label: "Purchase Requirement", fieldname: "suggested_order_qty" },
      { label: "Required By", fieldname: "required_by_date" },
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
          <td>${frappe.format(row.current_rm_store_stock, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.open_po_in_transit_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.open_material_request_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.format(row.maximum_level, { fieldtype: "Float", precision: 3 })}</td>
          <td>${this.render_coverage(row)}</td>
          <td>${this.render_health(row)}</td>
          <td class="${Number(row.suggested_order_qty || 0) > 0 ? "calco-rm-planning__ows-qty--active" : ""}">${frappe.format(row.suggested_order_qty, { fieldtype: "Float", precision: 3 })}</td>
          <td>${frappe.utils.escape_html(row.required_by_date || "")}</td>
          <td>${this.render_actions(row)}</td>
        </tr>
      `).join("")
    );

    this.bind_row_actions();
  }

  render_filter_summary() {
    const active = [];
    if (this.filters.item_code) {
      active.push(`Search: ${this.filters.item_code}`);
    }
    if (this.filters.inventory_health && this.filters.inventory_health !== "All") {
      active.push(`Health: ${this.filters.inventory_health}`);
    }
    if (this.filters.only_items_requiring_purchase) {
      active.push("Only Requiring Purchase");
    }
    this.page.main.find(".calco-rm-planning__summary").text(
      `${__("Rows")}: ${this.rows.length}${active.length ? ` | ${active.join(" | ")}` : ""}`
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

  render_coverage(row) {
    if (row.coverage_days === null || row.coverage_days === undefined) {
      return `<span class="calco-rm-planning__coverage">${__("No Use")}</span>`;
    }
    const health = (row.inventory_health || "healthy").toLowerCase();
    const value = frappe.format(row.coverage_days, { fieldtype: "Float", precision: 1 });
    return `<span class="calco-rm-planning__coverage calco-rm-planning__coverage--${health}">${value}</span>`;
  }

  getRowClass(row) {
    const health = (row.inventory_health || "").toLowerCase();
    return health ? `calco-rm-planning__row--${health}` : "";
  }

  render_actions(row) {
    if (row.suggested_order_qty > 0) {
      return `<div class="calco-rm-planning__actions"><button class="btn btn-xs btn-primary calco-rm-planning__create-mr">${__("Create Material Request")}</button></div>`;
    }
    return `<div class="calco-rm-planning__actions"><span class="calco-rm-planning__action-empty">-</span></div>`;
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

  bind_filter_toolbar() {
    const $main = this.page.main;
    $main.find(".calco-rm-planning__apply-filters").on("click", () => {
      this.capture_filter_state();
      this.refresh();
    });
    $main.find(".calco-rm-planning__clear-filters").on("click", () => this.clear_filters());
    $main.find(".calco-rm-planning__search-input").on("input", (event) => {
      const term = ($(event.currentTarget).val() || "").toString().trim();
      this.filters.item_code = term;
      this.queue_search_suggestions(term);
    });
    $main.find(".calco-rm-planning__search-input").on("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        this.hide_search_suggestions();
        this.capture_filter_state();
        this.refresh();
      }
    });
    $main.find(".calco-rm-planning__search-input").on("blur", () => {
      setTimeout(() => this.hide_search_suggestions(), 180);
    });
    $main.find(".calco-rm-planning__health-pill").on("click", (event) => {
      event.preventDefault();
      $main.find(".calco-rm-planning__health-pill").removeClass("is-active");
      $(event.currentTarget).addClass("is-active");
    });
    $main.find(".calco-rm-planning__search-suggestions").on("mousedown", ".calco-rm-planning__search-suggestion", (event) => {
      event.preventDefault();
      const itemCode = ($(event.currentTarget).attr("data-item-code") || "").trim();
      if (!itemCode) {
        return;
      }
      this.filters.item_code = itemCode;
      this.sync_filter_toolbar();
      this.hide_search_suggestions();
      this.refresh();
    });
  }

  bind_card_actions() {
    this.page.main.find(".calco-rm-planning__card.is-clickable").on("click", (event) => {
      const health = ($(event.currentTarget).attr("data-health") || "").trim();
      if (!health) {
        return;
      }
      this.filters.inventory_health = health;
      this.sync_filter_toolbar();
      this.refresh();
    });
  }

  capture_filter_state() {
    const $main = this.page.main;
    this.filters.item_code = ($main.find(".calco-rm-planning__search-input").val() || "").toString().trim();
    this.filters.inventory_health = ($main.find(".calco-rm-planning__health-pill.is-active").attr("data-health") || "All").trim();
    this.filters.only_items_requiring_purchase = $main.find(".calco-rm-planning__purchase-only").is(":checked") ? 1 : 0;
  }

  sync_filter_toolbar() {
    const $main = this.page.main;
    $main.find(".calco-rm-planning__search-input").val(this.filters.item_code || "");
    $main.find(".calco-rm-planning__purchase-only").prop("checked", !!this.filters.only_items_requiring_purchase);
    $main.find(".calco-rm-planning__health-pill").removeClass("is-active");
    $main.find(`.calco-rm-planning__health-pill[data-health="${this.filters.inventory_health || "All"}"]`).addClass("is-active");
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
    this.filters = {
      item_code: "",
      inventory_health: "All",
      only_items_requiring_purchase: 0,
    };
    this.sync_filter_toolbar();
    this.hide_search_suggestions();
    this.refresh();
  }

  queue_search_suggestions(term) {
    clearTimeout(this.searchTimer);
    if (!term) {
      this.hide_search_suggestions();
      return;
    }
    this.searchTimer = setTimeout(() => this.fetch_search_suggestions(term), 180);
  }

  fetch_search_suggestions(term) {
    frappe.call({
      method: "calco_erp.calco_purchase.page.rm_planning_dashboard.rm_planning_dashboard.search_rm_items",
      args: { term, limit: 12 },
      quiet: true,
    }).then((r) => {
      this.searchSuggestions = r.message || [];
      this.render_search_suggestions();
    });
  }

  render_search_suggestions() {
    const $box = this.page.main.find(".calco-rm-planning__search-suggestions");
    if (!this.searchSuggestions.length) {
      this.hide_search_suggestions();
      return;
    }
    $box.html(
      this.searchSuggestions.map((row) => `
        <button type="button" class="calco-rm-planning__search-suggestion" data-item-code="${frappe.utils.escape_html(row.item_code || "")}">
          <div class="calco-rm-planning__search-suggestion-code">${frappe.utils.escape_html(row.item_code || "")}</div>
          <div class="calco-rm-planning__search-suggestion-name">${frappe.utils.escape_html(row.item_name || "")}</div>
        </button>
      `).join("")
    );
    $box.addClass("is-open");
  }

  hide_search_suggestions() {
    this.page.main.find(".calco-rm-planning__search-suggestions").removeClass("is-open").empty();
  }

  formatNumber(value, precision = 2) {
    return Number(Number(value || 0).toFixed(precision)).toString();
  }

  export_rows() {
    const columns = [
      "item_code", "item_name", "current_rm_store_stock", "open_po_in_transit_qty", "maximum_level",
      "coverage_days", "inventory_health", "suggested_order_qty", "required_by_date",
      "current_season", "selected_daily_consumption", "lead_time_days", "safety_days",
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

  show_row_details(row) {
    const detailRows = [
      [__("Daily Avg Low"), frappe.format(row.daily_avg_consumption_low, { fieldtype: "Float", precision: 3 })],
      [__("Daily Avg Normal"), frappe.format(row.daily_avg_consumption_normal, { fieldtype: "Float", precision: 3 })],
      [__("Daily Avg Peak"), frappe.format(row.daily_avg_consumption_peak, { fieldtype: "Float", precision: 3 })],
      [__("Current Season"), frappe.utils.escape_html(row.current_season || "-")],
      [__("Selected Daily Consumption"), frappe.format(row.selected_daily_consumption, { fieldtype: "Float", precision: 3 })],
      [__("Lead Time"), frappe.format(row.lead_time_days, { fieldtype: "Float", precision: 2 })],
      [__("Safety Days"), frappe.format(row.safety_days, { fieldtype: "Float", precision: 2 })],
      [__("Safety Stock"), frappe.format(row.safety_stock, { fieldtype: "Float", precision: 3 })],
      [__("Reorder Level"), frappe.format(row.reorder_level, { fieldtype: "Float", precision: 3 })],
      [__("Production Requirement"), frappe.format(row.production_requirement, { fieldtype: "Float", precision: 3 })],
    ];

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
