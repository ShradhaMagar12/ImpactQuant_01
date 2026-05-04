window.addEventListener("load", async () => {
  await ImpactQuant.initDataPage(async (filters) => {
    const query = new URLSearchParams(filters).toString();
    const modelPayload = await ImpactQuant.fetchJson(`/model-data?${query}`);
    const metrics = modelPayload.metrics;

    ImpactQuant.$("model-accuracy").textContent = `${(Number(metrics.classifier_accuracy) * 100).toFixed(1)}%`;
    ImpactQuant.$("model-rmse").textContent = ImpactQuant.formatNumber(metrics.regression_rmse, 3);
    ImpactQuant.$("model-mae").textContent = ImpactQuant.formatNumber(metrics.regression_mae, 3);
    ImpactQuant.$("model-r2").textContent = ImpactQuant.formatNumber(metrics.regression_r2, 3);

    ImpactQuant.renderPlot("model-confusion", modelPayload.figures.confusion_matrix);
    ImpactQuant.renderPlot("model-class-balance", modelPayload.figures.class_balance);
    ImpactQuant.renderPlot("model-classifier-importance", modelPayload.figures.classifier_importance);
    ImpactQuant.renderPlot("model-regressor-importance", modelPayload.figures.regressor_importance);
    ImpactQuant.renderPlot("model-actual-predicted", modelPayload.figures.actual_vs_predicted);
    ImpactQuant.renderPlot("model-residuals", modelPayload.figures.residuals);

    ImpactQuant.renderTable("model-classifier-table", modelPayload.top_classifier_features.slice(0, 10));
    ImpactQuant.renderTable("model-regressor-table", modelPayload.top_regressor_features.slice(0, 10));
    ImpactQuant.setFilterMeta(
      `${metrics.training_records} training rows · ${metrics.filtered_records} filtered rows · Random Forest classifier + regressor`,
    );
  });
});
