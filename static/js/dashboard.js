window.addEventListener("load", async () => {
  await ImpactQuant.initDataPage(async (filters) => {
    const query = new URLSearchParams(filters).toString();
    const [dataPayload, analysisPayload, insightsPayload] = await Promise.all([
      ImpactQuant.fetchJson(`/get-data?${query}`),
      ImpactQuant.fetchJson(`/analysis?${query}`),
      ImpactQuant.fetchJson(`/insights?${query}`),
    ]);

    const kpis = analysisPayload.kpis;
    ImpactQuant.$("dash-avg-change").textContent = ImpactQuant.formatPercent(kpis.avg_change);
    ImpactQuant.$("dash-max-drop").textContent = ImpactQuant.formatPercent(kpis.max_drop);
    ImpactQuant.$("dash-recovery").textContent = ImpactQuant.formatNumber(kpis.recovery_days, 1);
    ImpactQuant.$("dash-volatility").textContent = ImpactQuant.formatNumber(kpis.volatility, 2);
    ImpactQuant.$("dash-impact-score").textContent = ImpactQuant.formatNumber(kpis.sector_impact_score, 2);
    ImpactQuant.$("dash-resilience-score").textContent = ImpactQuant.formatNumber(kpis.sector_resilience_score, 2);

    ImpactQuant.renderPlot("dashboard-line", analysisPayload.figures.line);
    ImpactQuant.renderPlot("dashboard-bar", analysisPayload.figures.bar);
    ImpactQuant.renderPlot("dashboard-sector", analysisPayload.figures.sector);
    ImpactQuant.renderPlot("dashboard-frequency", analysisPayload.figures.frequency);
    ImpactQuant.renderPlot("dashboard-location", analysisPayload.figures.location);

    const summaryCards = [
      {
        title: "Current Market Reading",
        description: `Average change is ${ImpactQuant.formatPercent(kpis.avg_change)} with volatility at ${ImpactQuant.formatNumber(kpis.volatility, 2)}.`,
      },
      {
        title: "Recovery Window",
        description: `Estimated recovery time is ${ImpactQuant.formatNumber(kpis.recovery_days, 1)} days while the sharpest drop reaches ${ImpactQuant.formatPercent(kpis.max_drop)}.`,
      },
      {
        title: "Sector Lens",
        description: `The filtered average impact score is ${ImpactQuant.formatNumber(kpis.sector_impact_score, 2)} and resilience score is ${ImpactQuant.formatNumber(kpis.sector_resilience_score, 2)}.`,
      },
    ];
    ImpactQuant.$("dashboard-summary").innerHTML = summaryCards
      .map((item) => `
        <div class="stack-item">
          <h4>${ImpactQuant.escapeHtml(item.title)}</h4>
          <p>${ImpactQuant.escapeHtml(item.description)}</p>
        </div>
      `)
      .join("");

    ImpactQuant.renderTable("dashboard-sector-table", analysisPayload.sector_summary.slice(0, 8));
    ImpactQuant.renderInsights("dashboard-insights", insightsPayload.insights);
    ImpactQuant.renderRipple("dashboard-ripple", insightsPayload.ripple_effects);
    ImpactQuant.$("dashboard-insight-count").textContent = `${insightsPayload.insights.length}`;

    const powerBi = analysisPayload.power_bi;
    const meta = ImpactQuant.$("powerbi-meta");
    meta.innerHTML = Object.entries(powerBi.selected_filters || {})
      .map(([label, value]) => `<div class="pill">${ImpactQuant.escapeHtml(label)}: ${ImpactQuant.escapeHtml(value || "All")}</div>`)
      .join("");
    const frame = ImpactQuant.$("powerbi-frame");
    const empty = ImpactQuant.$("powerbi-empty");
    if (powerBi.enabled && powerBi.embed_url) {
      frame.src = powerBi.embed_url;
      frame.classList.add("active");
      empty.style.display = "none";
    } else {
      frame.classList.remove("active");
      frame.removeAttribute("src");
      empty.style.display = "grid";
    }

    ImpactQuant.renderTable("dashboard-table", dataPayload.rows.slice(0, 12));
    ImpactQuant.$("dashboard-table-count").textContent = `${dataPayload.summary.records} rows`;
    ImpactQuant.setFilterMeta(
      `${dataPayload.summary.records} records - ${dataPayload.summary.companies} companies - ${dataPayload.summary.disasters} disasters`,
    );
  });
});
