const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const statusLine = document.querySelector("#status");
const resultList = document.querySelector("#results");
const filters = document.querySelector("#filters");
const stopButton = document.querySelector("#stop");
let apiToken = "";
let activeJob = "";
let currentFilter = "all";
let latest = [];

function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function makeLink(url, title) {
  const anchor = element("a");
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.append(element("h2", "", title || url));
  return anchor;
}

function displayResult(item) {
  const card = element("article", "result");
  if (item.source_type === "IMAGE") {
    card.classList.add("image-card");
    const image = document.createElement("img");
    image.src = item.thumbnail_url;
    image.alt = item.title;
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    const body = element("div");
    const link = element("a");
    link.href = item.file_page || item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.append(element("h2", "", item.title));
    body.append(link);
    const attribution = [item.artist, item.license].filter(Boolean).join(" · ");
    if (attribution) body.append(element("p", "attribution", attribution));
    if (item.license_url) {
      const licenseLink = element("a", "url", "License details");
      licenseLink.href = item.license_url;
      licenseLink.target = "_blank";
      licenseLink.rel = "noopener noreferrer";
      body.append(licenseLink);
    }
    if (item.excerpt) body.append(element("p", "excerpt", item.excerpt));
    card.append(image, body);
  } else {
    card.append(makeLink(item.url, item.title));
    card.append(element("div", "url", item.url));
    if (item.excerpt) card.append(element("p", "excerpt", item.excerpt));
    card.append(element("span", "source", item.source_provider.replaceAll("_", " ")));
  }
  return card;
}

function category(item) {
  if (item.source_type === "IMAGE") return "images";
  if (["DOCUMENT", "ARCHIVE", "DATASET", "REGISTRY"].includes(item.source_type)) return "research";
  return "web";
}

function render() {
  resultList.replaceChildren();
  const shown = latest.filter(item => currentFilter === "all" || category(item) === currentFilter);
  if (!shown.length && latest.length) {
    resultList.append(element("p", "empty", "No results in this category yet."));
    return;
  }
  for (const result of shown) resultList.append(displayResult(result));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "X-Tractor-Token": apiToken, "X-Requested-With": "TractorSearch", ...(options.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Search service returned ${response.status}`);
  return response.json();
}

async function poll(jobId) {
  while (activeJob === jobId) {
    try {
      const data = await api(`/api/jobs/${jobId}`);
      latest = data.results || [];
      render();
      filters.hidden = latest.length === 0;
      const progress = data.providers ? `${data.providers} providers · ` : "";
      statusLine.textContent = data.error || `${progress}${data.status === "running" ? "Tractor is searching recursively…" : data.stop_reason || `${latest.length} results`}`;
      if (data.status !== "running" && data.status !== "queued") {
        stopButton.hidden = true;
        return;
      }
    } catch (error) {
      statusLine.textContent = error.message;
      stopButton.hidden = true;
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 900));
  }
}

async function search(value) {
  const query = value.trim().slice(0, 500);
  if (!query) return;
  queryInput.value = query;
  document.querySelector("#page-title").textContent = query;
  resultList.replaceChildren();
  latest = [];
  currentFilter = "all";
  document.querySelectorAll(".filter").forEach(button => button.classList.toggle("selected", button.dataset.filter === "all"));
  filters.hidden = true;
  statusLine.textContent = "Starting recursive search…";
  stopButton.hidden = false;
  const data = await api("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  activeJob = data.id;
  await poll(activeJob);
}

form.addEventListener("submit", event => {
  event.preventDefault();
  search(queryInput.value).catch(error => { statusLine.textContent = error.message; stopButton.hidden = true; });
});
document.querySelectorAll(".filter").forEach(button => button.addEventListener("click", () => {
  currentFilter = button.dataset.filter;
  document.querySelectorAll(".filter").forEach(item => item.classList.toggle("selected", item === button));
  render();
}));
stopButton.addEventListener("click", async () => {
  if (!activeJob) return;
  try { await api(`/api/jobs/${activeJob}`, { method: "DELETE" }); } catch {}
  statusLine.textContent = "Stopping search and saving collected results…";
  stopButton.hidden = true;
});

(async () => {
  try {
    const response = await fetch("/api/bootstrap", { cache: "no-store" });
    if (!response.ok) throw new Error("Tractor service is not available.");
    apiToken = (await response.json()).token;
    const initial = new URLSearchParams(location.search).get("q") || "";
    queryInput.value = initial;
    if (initial) await search(initial);
    else { statusLine.textContent = "Search the web, images, archives, research and more."; queryInput.focus(); }
  } catch (error) { statusLine.textContent = error.message; }
})();
