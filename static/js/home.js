window.addEventListener("load", async () => {
  ImpactQuant.initShell();
  try {
    const [dataPayload, analysisPayload] = await Promise.all([
      ImpactQuant.fetchJson("/get-data"),
      ImpactQuant.fetchJson("/analysis"),
    ]);
    ImpactQuant.$("home-disasters").textContent = dataPayload.summary.disasters ?? 0;
    ImpactQuant.$("home-companies").textContent = dataPayload.summary.companies ?? 0;
    ImpactQuant.$("home-sectors").textContent = dataPayload.summary.sectors ?? 0;
    ImpactQuant.$("home-change").textContent = ImpactQuant.formatPercent(analysisPayload.kpis.avg_change);
  } catch (error) {
    console.error(error);
  }
});
