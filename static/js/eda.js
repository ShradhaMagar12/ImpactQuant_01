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
    const hypothesis = edaPayload?.hypothesis_test ?? {};
    ImpactQuant.$("eda-hypothesis").innerHTML = `
      <div class="stack-item">
        <h4> Objective</h4>
        <p>To analyze whether <b>high-impact disasters</b> significantly affect stock price changes.</p>
      </div>

      <div class="stack-item">
        <h4> Hypotheses</h4>
        <p><b>H₀:</b> ${hypothesis.null_hypothesis ?? "μ₁ = μ₂ (No difference in means)"}</p>
        <p><b>H₁:</b> ${hypothesis.alternative_hypothesis ?? "μ₁ ≠ μ₂ (Significant difference exists)"}</p>
      </div>

      <div class="stack-item">
        <h4> Test Details</h4>
        <p><b>Test:</b> ${hypothesis.test_type ?? "Independent Two-Sample T-Test (Welch’s)"}</p>
        <p><b>Significance Level (α):</b> ${hypothesis.significance_level ?? 0.05}</p>
      </div>

      <div class="stack-item">
        <h4> Sample Summary</h4>
        <p><b>High Impact Samples:</b> ${hypothesis.high_samples ?? "N/A"}</p>
        <p><b>Other Samples:</b> ${hypothesis.other_samples ?? "N/A"}</p>
        <p><b>Mean (High Impact):</b> ${hypothesis.high_mean ?? "N/A"}%</p>
        <p><b>Mean (Others):</b> ${hypothesis.other_mean ?? "N/A"}%</p>
      </div>

      <div class="stack-item">
        <h4> Test Results</h4>
        <p><b>T-Statistic:</b> ${hypothesis.t_statistic ?? "N/A"}</p>
        <p><b>P-Value:</b> ${hypothesis.p_value ?? "N/A"}</p>
      </div>

      <div class="stack-item">
        <h4> Decision & Justification</h4>
        ${
          hypothesis.p_value !== undefined && hypothesis.p_value < 0.05
            ? `<p style="color: green;"><b>Reject H₀</b><br>
              Since p-value (${hypothesis.p_value}) < α (0.05), there is a statistically significant difference.</p>`
            : `<p style="color: orange;"><b>Fail to Reject H₀</b><br>
              Since p-value (${hypothesis.p_value ?? "N/A"}) ≥ α (0.05), no statistically significant difference is observed.</p>`
        }
      </div>

      <div class="stack-item">
        <h4> Interpretation</h4>
        <p>${hypothesis.interpretation ?? "No interpretation available."}</p>
      </div>
    `;
    ImpactQuant.setFilterMeta(
      `${dataPayload.summary.records} rows analysed - ${dataPayload.summary.sectors} sectors - ${dataPayload.summary.date_range.start || "N/A"} to ${dataPayload.summary.date_range.end || "N/A"}`,
    );
  });
});
