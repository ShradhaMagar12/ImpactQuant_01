window.addEventListener("load", async () => {
  await ImpactQuant.initDataPage(async (filters) => {
    const query = new URLSearchParams(filters).toString();
    const [dataPayload, edaPayload] = await Promise.all([
      ImpactQuant.fetchJson(`/get-data?${query}`),
      ImpactQuant.fetchJson(`/eda-data?${query}`),
    ]);

    ImpactQuant.$("eda-records").textContent = dataPayload.summary.records ?? 0;
    ImpactQuant.$("eda-companies").textContent = dataPayload.summary.companies ?? 0;
    ImpactQuant.$("eda-disasters").textContent = dataPayload.summary.disasters ?? 0;
    ImpactQuant.$("eda-change").textContent = ImpactQuant.formatPercent(edaPayload.kpis.avg_change);

    ImpactQuant.renderPlot("eda-histogram", edaPayload.figures.histogram);
    ImpactQuant.renderPlot("eda-impact-pie", edaPayload.figures.impact_pie);
    ImpactQuant.renderPlot("eda-box-plot", edaPayload.figures.box_plot);
    ImpactQuant.renderPlot("eda-sector-bar", edaPayload.figures.sector_bar);
    ImpactQuant.renderPlot("eda-type-bar", edaPayload.figures.type_bar);
    ImpactQuant.renderPlot("eda-correlation", edaPayload.figures.correlation);
    ImpactQuant.renderPlot("eda-year-heatmap", edaPayload.figures.year_heatmap);
    ImpactQuant.renderPlot("eda-sector-bubble", edaPayload.figures.sector_bubble);
    ImpactQuant.renderPlot("eda-multivariate", edaPayload.figures.multivariate_scatter);
    ImpactQuant.renderPlot("eda-outliers", edaPayload.figures.outlier_scatter);
    ImpactQuant.renderPlot("eda-price-scatter", edaPayload.figures.price_scatter);
    ImpactQuant.renderPlot("eda-hypothesis-chart", edaPayload.figures.hypothesis_compare);

    ImpactQuant.renderTable("eda-stats-table", edaPayload.summary_stats);
    ImpactQuant.renderTable("eda-sample-table", edaPayload.sample_rows);
    ImpactQuant.renderTable("eda-sector-table", edaPayload.sector_summary.slice(0, 10));

    const normality = edaPayload.normality_test;
    ImpactQuant.$("eda-normality").innerHTML = `
      <div class="stack-item">
        <h4>Sample Size</h4>
        <p>${normality.sample_size}</p>
      </div>
      <div class="stack-item">
        <h4>Shapiro Statistic</h4>
        <p>${normality.statistic ?? "N/A"}</p>
      </div>
      <div class="stack-item">
        <h4>P-Value</h4>
        <p>${normality.p_value ?? "N/A"}</p>
      </div>
      <div class="stack-item">
        <h4>Conclusion</h4>
        <p>${ImpactQuant.escapeHtml(normality.conclusion)}</p>
      </div>
    `;

    const hypothesis = edaPayload.hypothesis_test;
    ImpactQuant.$("eda-hypothesis").innerHTML = `
      <div class="stack-item">
        <h4>Objective</h4>
        <p>Check whether high-impact disasters affect stock-price change differently from other events.</p>
      </div>
      <div class="stack-item">
        <h4>Samples</h4>
        <p>High impact: ${hypothesis.high_samples} | Others: ${hypothesis.other_samples}</p>
      </div>
      <div class="stack-item">
        <h4>Means</h4>
        <p>High impact mean: ${hypothesis.high_mean ?? "N/A"}% | Others: ${hypothesis.other_mean ?? "N/A"}%</p>
      </div>
      <div class="stack-item">
        <h4>T-Test</h4>
        <p>T-statistic: ${hypothesis.t_statistic ?? "N/A"} | P-value: ${hypothesis.p_value ?? "N/A"}</p>
      </div>
      <div class="stack-item">
        <h4>Decision</h4>
        <p>${ImpactQuant.escapeHtml(hypothesis.decision)}</p>
        <div class="severity-pill ${hypothesis.decision === "Reject H0" ? "severity-high" : "severity-low"}">${ImpactQuant.escapeHtml(hypothesis.interpretation)}</div>
      </div>
    `;

    ImpactQuant.setFilterMeta(
      `${dataPayload.summary.records} rows analysed - ${dataPayload.summary.sectors} sectors - ${dataPayload.summary.date_range.start || "N/A"} to ${dataPayload.summary.date_range.end || "N/A"}`,
    );
  });
});
