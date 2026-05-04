(function attachImpactQuant() {
  const STORAGE_KEY = "impactquant-global-filters";
  const PLOT_CONFIG = { responsive: true, displayModeBar: false };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toTitle(value) {
    return String(value ?? "")
      .split(" ")
      .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
      .join(" ");
  }

  function formatNumber(value, digits = 2) {
    return Number(value ?? 0).toFixed(digits);
  }

  function formatPercent(value, digits = 2) {
    return `${Number(value ?? 0).toFixed(digits)}%`;
  }

  function formatSignedPercent(value, digits = 2) {
    const numeric = Number(value ?? 0);
    const prefix = numeric > 0 ? "+" : "";
    return `${prefix}${numeric.toFixed(digits)}%`;
  }

  function severityClass(name) {
    const lowered = String(name ?? "").toLowerCase();
    if (lowered === "high") {
      return "severity-high";
    }
    if (lowered === "medium") {
      return "severity-medium";
    }
    return "severity-low";
  }

  function readStoredFilters() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (error) {
      return {};
    }
  }

  function writeStoredFilters(filters) {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  }

  function readQueryFilters() {
    const params = new URLSearchParams(window.location.search);
    return {
      company: params.get("company") || undefined,
      sector: params.get("sector") || undefined,
      disaster_category: params.get("disaster_category") || undefined,
      event_type: params.get("event_type") || undefined,
      location: params.get("location") || undefined,
      event: params.get("event") || undefined,
      start_date: params.get("start_date") || undefined,
      end_date: params.get("end_date") || undefined,
    };
  }

  function buildQuery(filters) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "" && value !== "All" && value !== "Both") {
        params.set(key, value);
      }
      if ((key === "company" || key === "sector" || key === "location") && value === "All") {
        params.set(key, value);
      }
      if (key === "disaster_category" && value === "Both") {
        params.set(key, value);
      }
    });
    return params.toString();
  }

  function defaultFilters(options) {
    return {
      company: "All",
      sector: "All",
      disaster_category: "Both",
      event_type: "All",
      location: "All",
      event: "",
      start_date: options.date_range.start,
      end_date: options.date_range.end,
    };
  }

  function validateFilters(rawFilters, options) {
    const defaults = defaultFilters(options);
    const next = { ...defaults, ...rawFilters };
    if (!options.companies.includes(next.company)) {
      next.company = defaults.company;
    }
    if (!options.sectors.includes(next.sector)) {
      next.sector = defaults.sector;
    }
    if (!options.disaster_categories.includes(next.disaster_category)) {
      next.disaster_category = defaults.disaster_category;
    }
    if (!options.event_types.includes(next.event_type)) {
      next.event_type = defaults.event_type;
    }
    if (!options.locations.includes(next.location)) {
      next.location = defaults.location;
    }
    if (!next.start_date) {
      next.start_date = defaults.start_date;
    }
    if (!next.end_date) {
      next.end_date = defaults.end_date;
    }
    if (next.start_date > next.end_date) {
      next.start_date = defaults.start_date;
      next.end_date = defaults.end_date;
    }
    return next;
  }

  function populateSelect(elementId, values, selectedValue, formatter) {
    const select = $(elementId);
    if (!select) {
      return;
    }
    select.innerHTML = values
      .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(formatter ? formatter(value) : value)}</option>`)
      .join("");
    select.value = values.includes(selectedValue) ? selectedValue : values[0];
  }

  function setFilterInputs(filters, options) {
    populateSelect("filter-company", options.companies, filters.company);
    populateSelect("filter-sector", options.sectors, filters.sector);
    populateSelect("filter-category", options.disaster_categories, filters.disaster_category);
    populateSelect("filter-type", options.event_types, filters.event_type, (value) => (value === "All" ? value : toTitle(value)));
    populateSelect("filter-location", options.locations, filters.location);
    if ($("filter-event")) {
      $("filter-event").value = filters.event || "";
    }
    if ($("filter-start")) {
      $("filter-start").min = options.date_range.start;
      $("filter-start").max = options.date_range.end;
      $("filter-start").value = filters.start_date;
    }
    if ($("filter-end")) {
      $("filter-end").min = options.date_range.start;
      $("filter-end").max = options.date_range.end;
      $("filter-end").value = filters.end_date;
    }
  }

  function collectFiltersFromInputs(options) {
    return validateFilters(
      {
        company: $("filter-company")?.value || "All",
        sector: $("filter-sector")?.value || "All",
        disaster_category: $("filter-category")?.value || "Both",
        event_type: $("filter-type")?.value || "All",
        location: $("filter-location")?.value || "All",
        event: $("filter-event")?.value.trim() || "",
        start_date: $("filter-start")?.value || options.date_range.start,
        end_date: $("filter-end")?.value || options.date_range.end,
      },
      options,
    );
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch (error) {
        // Ignore parse errors for non-JSON responses.
      }
      throw new Error(message);
    }
    return response.json();
  }

  function setStatus(message, error = false) {
    const status = $("status-msg");
    if (!status) {
      return;
    }
    status.textContent = message;
    status.style.color = error ? "#ffb5c4" : "";
    status.style.borderColor = error ? "rgba(255,77,109,0.22)" : "";
    status.style.background = error ? "rgba(255,77,109,0.08)" : "";
  }

  function setFilterMeta(text) {
    const meta = $("filter-meta");
    if (meta) {
      meta.textContent = text;
    }
  }

  function syncNavLinks(filters) {
    const query = buildQuery(filters);
    document.querySelectorAll("[data-nav-target]").forEach((link) => {
      const target = link.getAttribute("data-nav-target");
      if (!target || target === "home" || target === "about") {
        return;
      }
      const path = link.getAttribute("href").split("?")[0];
      link.setAttribute("href", query ? `${path}?${query}` : path);
    });
  }

  function renderPlot(targetId, figure) {
    Plotly.react(targetId, figure.data, figure.layout, PLOT_CONFIG);
  }

  function renderTable(tableId, rows) {
    const table = $(tableId);
    if (!table) {
      return;
    }
    const head = table.querySelector("thead");
    const body = table.querySelector("tbody");
    if (!rows || !rows.length) {
      head.innerHTML = "";
      body.innerHTML = "<tr><td>No rows available for the current view.</td></tr>";
      return;
    }
    const headers = Object.keys(rows[0]);
    head.innerHTML = `<tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>`;
    body.innerHTML = rows
      .map((row) => `<tr>${headers.map((header) => `<td>${escapeHtml(row[header])}</td>`).join("")}</tr>`)
      .join("");
  }

  function renderInsights(containerId, insights) {
    const container = $(containerId);
    if (!container) {
      return;
    }
    if (!insights.length) {
      container.innerHTML = `<div class="stack-item"><h4>No insights yet</h4><p>Apply broader filters to generate insight cards.</p></div>`;
      return;
    }
    container.innerHTML = insights
      .map((item) => `
        <div class="stack-item">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.description)}</p>
          <div class="severity-pill ${severityClass(item.severity)}">${escapeHtml((item.severity || "low").toUpperCase())}</div>
        </div>
      `)
      .join("");
  }

  function renderRipple(containerId, rippleEffects) {
    const container = $(containerId);
    if (!container) {
      return;
    }
    if (!rippleEffects.length) {
      container.innerHTML = `<div class="ripple-item"><h4>No ripple chain available</h4><p>Try broadening the filters to compare sector spillovers.</p></div>`;
      return;
    }
    container.innerHTML = rippleEffects
      .map((item) => `
        <div class="ripple-item">
          <h4>${escapeHtml(item.type)}</h4>
          <p>${escapeHtml(item.chain)}</p>
        </div>
      `)
      .join("");
  }

  function hideLoader() {
    const loader = $("loader");
    if (!loader) {
      return;
    }
    window.setTimeout(() => {
      loader.style.opacity = "0";
      window.setTimeout(() => {
        loader.style.display = "none";
      }, 420);
    }, 350);
  }

  function initShell() {
    hideLoader();
  }

  async function initDataPage(loadPageData) {
    initShell();
    const optionsPayload = await fetchJson("/get-data");
    const options = optionsPayload.options;
    const mergedFilters = {
      ...readStoredFilters(),
      ...readQueryFilters(),
    };
    const filters = validateFilters(mergedFilters, options);
    setFilterInputs(filters, options);
    syncNavLinks(filters);
    writeStoredFilters(filters);

    async function run(activeFilters) {
      const validated = validateFilters(activeFilters, options);
      setFilterInputs(validated, options);
      writeStoredFilters(validated);
      syncNavLinks(validated);
      history.replaceState({}, "", `${window.location.pathname}?${buildQuery(validated)}`);
      setStatus("LOADING...");
      await loadPageData(validated, options);
      setStatus("READY");
    }

    $("apply-filters-btn")?.addEventListener("click", async () => {
      try {
        await run(collectFiltersFromInputs(options));
      } catch (error) {
        console.error(error);
        setStatus("ERROR", true);
      }
    });

    $("reset-filters-btn")?.addEventListener("click", async () => {
      try {
        const resetFilters = defaultFilters(options);
        await run(resetFilters);
      } catch (error) {
        console.error(error);
        setStatus("ERROR", true);
      }
    });

    await run(filters);
    return { options, filters };
  }

  window.ImpactQuant = {
    $,
    fetchJson,
    renderPlot,
    renderTable,
    renderInsights,
    renderRipple,
    initShell,
    initDataPage,
    setFilterMeta,
    setStatus,
    escapeHtml,
    toTitle,
    formatNumber,
    formatPercent,
    formatSignedPercent,
    severityClass,
    syncNavLinks,
  };

  window.addEventListener("load", () => {
    hideLoader();
  });
})();
