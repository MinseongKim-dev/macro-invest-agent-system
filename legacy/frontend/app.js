const snapshotBody = document.getElementById("snapshot-body");
const snapshotTrust = document.getElementById("snapshot-trust");
const compareBody = document.getElementById("compare-body");
const compareTrust = document.getElementById("compare-trust");
const signalsBody = document.getElementById("signals-body");
const signalsTrust = document.getElementById("signals-trust");
const explanationTrust = document.getElementById("explanation-trust");
const explanationSummary = document.getElementById("explanation-summary");
const explanationPoints = document.getElementById("explanation-points");
const regimeLatestStatus = document.getElementById("regime-latest-status");
const regimeLatestGrid = document.getElementById("regime-latest-grid");
const regimeCompareStatus = document.getElementById("regime-compare-status");
const regimeCompareGrid = document.getElementById("regime-compare-grid");

let latestSnapshot = null;
let latestSignals = null;

function formatTrust(trust) {
  if (!trust) {
    return "No trust metadata";
  }
  const sources = (trust.sources || [])
    .map((source) => source.source_label || source.source_id)
    .join(", ");
  return `freshness=${trust.freshness_status} | availability=${trust.availability} | degraded=${trust.is_degraded} | sources=${sources || "n/a"}`;
}

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toFixed(3);
}

function renderKvGrid(element, pairs) {
  element.innerHTML = pairs
    .map(
      (pair) => `
      <div class="kv-item">
        <span class="kv-key">${pair.key}</span>
        <span class="kv-value">${pair.value ?? "-"}</span>
      </div>
    `,
    )
    .join("");
}

async function getJson(path, options = undefined) {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }
  return response.json();
}

function renderSnapshot(snapshot) {
  snapshotTrust.textContent = formatTrust(snapshot.trust);
  const features = snapshot.features || [];
  if (features.length === 0) {
    snapshotBody.innerHTML = '<tr><td colspan="4">No observations available</td></tr>';
    return;
  }
  snapshotBody.innerHTML = features
    .map(
      (feature) => `
      <tr>
        <td>${feature.indicator_label}</td>
        <td>${formatNumber(feature.value)}</td>
        <td>${feature.source_id}</td>
        <td>${feature.observed_at}</td>
      </tr>
    `,
    )
    .join("");
}

function renderCompare(compare) {
  compareTrust.textContent = formatTrust(compare.trust);
  const deltas = compare.deltas || [];
  if (deltas.length === 0) {
    compareBody.innerHTML = '<tr><td colspan="5">No comparison data available</td></tr>';
    return;
  }
  compareBody.innerHTML = deltas
    .map(
      (delta) => `
      <tr>
        <td>${delta.indicator_label}</td>
        <td>${formatNumber(delta.current_value)}</td>
        <td>${formatNumber(delta.prior_value)}</td>
        <td>${formatNumber(delta.delta)}</td>
        <td>${delta.direction}</td>
      </tr>
    `,
    )
    .join("");
}

function renderSignals(signals) {
  signalsTrust.textContent = formatTrust(signals.trust);
  signalsBody.innerHTML = signals.signals
    .map(
      (signal) => `
      <tr>
        <td>${signal.signal_id}</td>
        <td>${signal.signal_type}</td>
        <td>${signal.strength}</td>
        <td>${formatNumber(signal.score)}</td>
        <td>${signal.trend}</td>
      </tr>
    `,
    )
    .join("");
}

function renderExplanation(explanation) {
  explanationTrust.textContent = formatTrust(explanation.trust);
  explanationSummary.textContent = explanation.summary;
  explanationPoints.innerHTML = (explanation.rationale_points || [])
    .map((point) => `<li>${point}</li>`)
    .join("");
}

async function loadSnapshot() {
  latestSnapshot = await getJson("/api/snapshots/latest?country=US");
  renderSnapshot(latestSnapshot);
}

async function loadCompare() {
  if (!latestSnapshot) {
    await loadSnapshot();
  }
  const priorFeatures = latestSnapshot.features.map((feature) => ({
    indicator_type: feature.indicator_type,
    value: Number(feature.value) * 0.98,
  }));

  const compare = await getJson("/api/snapshots/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country: "US",
      prior_snapshot_label: "synthetic-prior",
      prior_features: priorFeatures,
    }),
  });
  renderCompare(compare);
}

async function loadSignals() {
  latestSignals = await getJson("/api/signals/latest?country=US");
  renderSignals(latestSignals);
}

async function loadRegimeLatest() {
  try {
    const regime = await getJson("/api/regimes/latest");
    regimeLatestStatus.textContent = `as_of=${regime.as_of_date} | freshness=${regime.freshness_status} | degraded=${regime.degraded_status}`;
    renderKvGrid(regimeLatestGrid, [
      { key: "Label", value: regime.regime_label },
      { key: "Family", value: regime.regime_family },
      { key: "Confidence", value: regime.confidence },
      { key: "Transition Type", value: regime.transition?.transition_type },
      { key: "Changed", value: String(regime.transition?.changed) },
      { key: "Missing Inputs", value: (regime.missing_inputs || []).join(", ") || "none" },
    ]);
  } catch (error) {
    regimeLatestStatus.textContent = "No persisted regime available yet";
    regimeLatestGrid.innerHTML = "";
  }
}

async function loadRegimeCompare() {
  try {
    const compare = await getJson("/api/regimes/compare");
    regimeCompareStatus.textContent = `as_of=${compare.as_of_date} | baseline_available=${compare.baseline_available}`;
    renderKvGrid(regimeCompareGrid, [
      { key: "Current Label", value: compare.current_regime_label },
      { key: "Prior Label", value: compare.prior_regime_label || "-" },
      { key: "Transition Type", value: compare.transition_type },
      { key: "Changed", value: String(compare.changed) },
      { key: "Current Confidence", value: compare.current_confidence },
      { key: "Prior Confidence", value: compare.prior_confidence || "-" },
    ]);
  } catch {
    regimeCompareStatus.textContent = "No regime comparison baseline available yet";
    regimeCompareGrid.innerHTML = "";
  }
}

async function loadExplanation() {
  if (!latestSignals) {
    await loadSignals();
  }
  const strongest = latestSignals.strongest_signal_id;
  const runId = latestSignals.run_id;
  if (!runId) {
    explanationTrust.textContent = "No experimental explanation available";
    explanationSummary.textContent = "";
    explanationPoints.innerHTML = "";
    return;
  }

  const explanationId = strongest ? `${runId}:${strongest}` : runId;
  try {
    const explanation = await getJson(`/api/explanations/${encodeURIComponent(explanationId)}`);
    renderExplanation(explanation);
  } catch {
    explanationTrust.textContent = "No experimental explanation found";
    explanationSummary.textContent = "";
    explanationPoints.innerHTML = "";
  }
}

async function loadAll() {
  await Promise.allSettled([
    loadSnapshot().then(() => loadCompare()).catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      snapshotTrust.textContent = `Load error: ${message}`;
      compareTrust.textContent = "Skipped — snapshot unavailable";
    }),
    loadRegimeLatest(),
    loadRegimeCompare(),
    loadSignals().then(() => loadExplanation()).catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      signalsTrust.textContent = `Load error: ${message}`;
      explanationTrust.textContent = "Skipped — signals unavailable";
    }),
  ]);
}

document.getElementById("refresh-snapshot").addEventListener("click", () => {
  loadSnapshot();
});

document.getElementById("run-compare").addEventListener("click", () => {
  loadCompare();
});

document.getElementById("refresh-signals").addEventListener("click", async () => {
  await loadSignals();
  await loadExplanation();
});

document.getElementById("refresh-regime").addEventListener("click", async () => {
  await loadRegimeLatest();
});

document.getElementById("refresh-regime-compare").addEventListener("click", async () => {
  await loadRegimeCompare();
});

// Set initial loading states so sections never look silently blank
snapshotTrust.textContent = "Loading…";
compareTrust.textContent = "Loading…";
regimeLatestStatus.textContent = "Loading…";
regimeCompareStatus.textContent = "Loading…";
signalsTrust.textContent = "Loading…";
explanationTrust.textContent = "Loading…";

loadAll();