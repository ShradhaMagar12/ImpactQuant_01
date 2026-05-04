window.addEventListener("load", async () => {
  let latestOptions = null;
  let latestContext = null;

  function populatePredictionInputs(options, filters) {
    latestOptions = options;
    const companies = options.companies.filter((item) => item !== "All");
    const sectors = options.sectors.filter((item) => item !== "All");
    const types = options.event_types.filter((item) => item !== "All");
    const locations = options.locations.filter((item) => item !== "All");

    const setSelect = (id, values, preferred, formatter) => {
      const select = ImpactQuant.$(id);
      select.innerHTML = values
        .map((value) => `<option value="${ImpactQuant.escapeHtml(value)}">${ImpactQuant.escapeHtml(formatter ? formatter(value) : value)}</option>`)
        .join("");
      select.value = values.includes(preferred) ? preferred : values[0];
    };

    setSelect("pred-company", companies, filters.company !== "All" ? filters.company : companies[0]);
    setSelect("pred-sector", sectors, filters.sector !== "All" ? filters.sector : sectors[0]);
    setSelect("pred-type", types, filters.event_type !== "All" ? filters.event_type : types[0], (value) => ImpactQuant.toTitle(value));
    setSelect("pred-location", locations, filters.location !== "All" ? filters.location : locations[0]);
    ImpactQuant.$("pred-year").value = Number(options.date_range.end.slice(0, 4)) + 1;
  }

  function inferCategory(eventType) {
    const natural = ["earthquake", "tsunami", "cyclone", "hurricane", "typhoon", "flood", "heatwave", "landslide"];
    return natural.some((keyword) => String(eventType || "").toLowerCase().includes(keyword)) ? "Natural" : "Man-made";
  }

  function renderProbabilities(probabilities) {
    const chart = {
      data: [
        {
          type: "bar",
          x: probabilities.map((item) => item.label),
          y: probabilities.map((item) => item.value),
          marker: {
            color: probabilities.map((item) => {
              if (item.label === "High") return "#ff4d6d";
              if (item.label === "Medium") return "#ffb830";
              return "#7fff6e";
            }),
          },
        },
      ],
      layout: {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 42, r: 18, t: 18, b: 40 },
        font: { family: "Outfit, sans-serif", color: "#d6dff5" },
        xaxis: { gridcolor: "rgba(255,255,255,0.06)" },
        yaxis: { title: "Probability (%)", gridcolor: "rgba(255,255,255,0.06)" },
      },
    };
    Plotly.react("prediction-probabilities", chart.data, chart.layout, { responsive: true, displayModeBar: false });
  }

  function renderGuidance(prediction) {
    const items = [
      {
        title: "Impact Outlook",
        description: `Predicted impact level is ${prediction.impact} with an expected change of ${ImpactQuant.formatSignedPercent(prediction.change_pct)}.`,
      },
      {
        title: "Recovery Lens",
        description: `The model estimates around ${prediction.recovery_days} trading days for recovery under this scenario.`,
      },
      {
        title: "Scenario Use",
        description: "Use this forecast as a directional decision-support signal, then compare it with the EDA and dashboard context.",
      },
    ];
    ImpactQuant.$("prediction-guidance").innerHTML = items
      .map((item) => `
        <div class="stack-item">
          <h4>${ImpactQuant.escapeHtml(item.title)}</h4>
          <p>${ImpactQuant.escapeHtml(item.description)}</p>
        </div>
      `)
      .join("");
  }

  ImpactQuant.$("run-predict-btn")?.addEventListener("click", async () => {
    if (!latestOptions) {
      return;
    }
    const payload = {
      company: ImpactQuant.$("pred-company").value,
      sector: ImpactQuant.$("pred-sector").value,
      type: ImpactQuant.$("pred-type").value,
      location: ImpactQuant.$("pred-location").value,
      year: Number(ImpactQuant.$("pred-year").value),
      before_price: Number(ImpactQuant.$("pred-price").value),
      disaster_category: inferCategory(ImpactQuant.$("pred-type").value),
    };
    const message = ImpactQuant.$("prediction-message");
    message.className = "message-box";
    message.textContent = "Running future prediction...";
    try {
      const response = await ImpactQuant.fetchJson("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      ImpactQuant.$("pred-impact").textContent = response.prediction.impact;
      ImpactQuant.$("pred-change").textContent = ImpactQuant.formatSignedPercent(response.prediction.change_pct);
      ImpactQuant.$("pred-after").textContent = ImpactQuant.formatNumber(response.prediction.after_price, 2);
      ImpactQuant.$("pred-recovery").textContent = `${response.prediction.recovery_days}d`;

      const severity = ImpactQuant.severityClass(response.prediction.impact);
      message.className = `message-box ${severity.replace("severity-", "")}`;
      message.textContent =
        severity === "severity-high"
          ? `High-risk scenario. Expected drop is around ${Math.abs(response.prediction.change_pct).toFixed(2)}%.`
          : severity === "severity-medium"
            ? "Moderate scenario. Monitor resilience and downside spread before acting."
            : "Lower-risk scenario. The forecast suggests comparatively better resilience.";
      renderProbabilities(response.probabilities);
      renderGuidance(response.prediction);
    } catch (error) {
      console.error(error);
      message.className = "message-box high";
      message.textContent = error.message;
    }
  });

  await ImpactQuant.initDataPage(async (filters, options) => {
    populatePredictionInputs(options, filters);
    const query = new URLSearchParams(filters).toString();
    const [analysisPayload, insightsPayload, dataPayload] = await Promise.all([
      ImpactQuant.fetchJson(`/analysis?${query}`),
      ImpactQuant.fetchJson(`/insights?${query}`),
      ImpactQuant.fetchJson(`/get-data?${query}`),
    ]);
    latestContext = analysisPayload;
    ImpactQuant.renderPlot("prediction-context-sector", analysisPayload.figures.sector);
    ImpactQuant.renderInsights("prediction-insights", insightsPayload.insights);
    ImpactQuant.$("prediction-insight-count").textContent = `${insightsPayload.insights.length}`;
    ImpactQuant.renderTable("prediction-history-table", dataPayload.rows.slice(0, 10));
    ImpactQuant.$("prediction-guidance").innerHTML = `
      <div class="stack-item">
        <h4>Historical Context</h4>
        <p>Use the table on the left as a baseline before launching a future scenario prediction.</p>
      </div>
      <div class="stack-item">
        <h4>Current Filter State</h4>
        <p>${analysisPayload.kpis.records} contextual rows and ${analysisPayload.kpis.disaster_frequency} disasters are active in the current filter view.</p>
      </div>
    `;
    ImpactQuant.setFilterMeta(
      `${analysisPayload.kpis.records} contextual rows - ${analysisPayload.kpis.disaster_frequency} disasters in current view`,
    );
  });
});
