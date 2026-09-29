// Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
const state = {
  datasets: [],
  selectedId: "",
  filter: "",
};

const el = {
  modeValue: document.querySelector("#modeValue"),
  datasetCount: document.querySelector("#datasetCount"),
  registryStatus: document.querySelector("#registryStatus"),
  fusekiStatus: document.querySelector("#fusekiStatus"),
  searchInput: document.querySelector("#searchInput"),
  refreshButton: document.querySelector("#refreshButton"),
  datasetRows: document.querySelector("#datasetRows"),
  emptyState: document.querySelector("#emptyState"),
  detailEmpty: document.querySelector("#detailEmpty"),
  detailContent: document.querySelector("#detailContent"),
  detailTitle: document.querySelector("#detailTitle"),
  detailId: document.querySelector("#detailId"),
  detailProvider: document.querySelector("#detailProvider"),
  detailTypes: document.querySelector("#detailTypes"),
  rdfGraph: document.querySelector("#rdfGraph"),
};

const shortIri = (value) => {
  if (!value) return "-";
  const hash = value.lastIndexOf("#");
  const slash = value.lastIndexOf("/");
  const index = Math.max(hash, slash);
  return index >= 0 ? value.slice(index + 1) || value : value;
};

const text = (value) => (value || "").toString();

const escapeHtml = (value) =>
  text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const matchesFilter = (dataset) => {
  const query = state.filter.trim().toLowerCase();
  if (!query) return true;
  return [dataset.title, dataset.provider, dataset.type, dataset.dataset_id]
    .map(text)
    .some((value) => value.toLowerCase().includes(query));
};

const setStatusValue = (target, value) => {
  target.classList.remove("bad", "warn");
  if (value === false || value === "down") target.classList.add("bad");
  if (value === null || value === undefined) target.classList.add("warn");
  target.textContent = value === true ? "up" : value === false ? "down" : value ?? "-";
};

async function loadStatus() {
  const [statusResponse, readyResponse] = await Promise.all([
    fetch("/status"),
    fetch("/ready").catch(() => null),
  ]);
  const status = await statusResponse.json();
  const ready = readyResponse ? await readyResponse.json() : {};
  const dependencies = ready.dependencies || status.dependencies || {};

  el.modeValue.textContent = status.mode || "-";
  el.datasetCount.textContent = status.dataset_count ?? "-";
  setStatusValue(el.registryStatus, dependencies.registry);
  setStatusValue(el.fusekiStatus, dependencies.fuseki);
}

async function loadDatasets() {
  const response = await fetch("/datasets");
  state.datasets = await response.json();
  renderRows();
}

function renderRows() {
  const visible = state.datasets.filter(matchesFilter);
  el.datasetRows.innerHTML = "";
  el.emptyState.hidden = visible.length > 0;

  visible.forEach((dataset) => {
    const row = document.createElement("tr");
    row.className = dataset.dataset_id === state.selectedId ? "selected" : "";
    row.innerHTML = `
      <td><strong>${escapeHtml(dataset.title || shortIri(dataset.dataset_id))}</strong><br>
        <span class="mono">${escapeHtml(dataset.dataset_id)}</span></td>
      <td class="mono">${escapeHtml(dataset.provider || "-")}</td>
      <td>${escapeHtml(dataset.type || "-")}</td>
    `;
    row.addEventListener("click", () => selectDataset(dataset.dataset_id));
    el.datasetRows.appendChild(row);
  });
}

async function selectDataset(datasetId) {
  state.selectedId = datasetId;
  renderRows();
  const response = await fetch(`/datasets/detail?dataset_id=${encodeURIComponent(datasetId)}`);
  if (!response.ok) return;
  const detail = await response.json();
  el.detailEmpty.hidden = true;
  el.detailContent.hidden = false;
  el.detailTitle.textContent = detail.title || shortIri(detail.dataset_id);
  el.detailId.textContent = detail.dataset_id;
  el.detailProvider.textContent = detail.provider || "-";
  el.detailTypes.textContent = (detail.types || []).map(shortIri).join(", ") || detail.type || "-";
  renderGraph(detail.triples || []);
}

function renderGraph(triples) {
  if (!triples.length) {
    el.rdfGraph.innerHTML = '<p class="empty">No triples returned for this dataset.</p>';
    return;
  }

  const nodes = Array.from(new Set(triples.flatMap((triple) => [triple.subject, triple.object])));
  const width = 660;
  const height = 320;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.34;
  const positions = new Map(
    nodes.map((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
      return [
        node,
        {
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        },
      ];
    })
  );

  const edgeMarkup = triples
    .map((triple) => {
      const from = positions.get(triple.subject);
      const to = positions.get(triple.object);
      if (!from || !to) return "";
      const labelX = (from.x + to.x) / 2;
      const labelY = (from.y + to.y) / 2;
      return `
        <line class="graph-edge" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" />
        <text class="graph-label" x="${labelX}" y="${labelY}">${escapeHtml(shortIri(triple.predicate))}</text>
      `;
    })
    .join("");

  const nodeMarkup = nodes
    .map((node) => {
      const pos = positions.get(node);
      return `
        <circle class="graph-node" cx="${pos.x}" cy="${pos.y}" r="18" />
        <text class="graph-label" x="${pos.x + 22}" y="${pos.y + 4}">${escapeHtml(shortIri(node))}</text>
      `;
    })
    .join("");

  el.rdfGraph.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="RDF graph">
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

async function refresh() {
  await Promise.all([loadStatus(), loadDatasets()]);
  if (state.selectedId) await selectDataset(state.selectedId);
}

el.searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  renderRows();
});

el.refreshButton.addEventListener("click", refresh);

refresh().catch((error) => {
  el.emptyState.hidden = false;
  el.emptyState.textContent = `Failed to load discovery API: ${error.message}`;
});
