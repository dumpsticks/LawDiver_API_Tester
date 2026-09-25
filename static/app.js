/* LawDiver API Tester — client UI */

const state = {
  functions: [],
  selected: null,
  keyConfigured: false,
  baseUrl: "",
  reference: { states: [], circuits: [] },
  formValues: {},
  lastMachine: null,
  lastSendAt: 0,
  rateLimitUntil: 0,
  rateTimer: null,
  pacing: true,
};

const MIN_GAP_MS = 1000;

const el = {
  nav: document.getElementById("fnNav"),
  title: document.getElementById("fnTitle"),
  desc: document.getElementById("fnDesc"),
  form: document.getElementById("runForm"),
  runBtn: document.getElementById("runBtn"),
  busy: document.getElementById("busyHint"),
  rateBanner: document.getElementById("rateLimitBanner"),
  softSpacing: document.getElementById("softSpacing"),
  resultsPanel: document.getElementById("resultsPanel"),
  resultsMeta: document.getElementById("resultsMeta"),
  resultsBody: document.getElementById("resultsBody"),
  machineBody: document.getElementById("machineBody"),
  copyMachineBtn: document.getElementById("copyMachineBtn"),
  status: document.getElementById("statusPill"),
  historyBtn: document.getElementById("historyBtn"),
  historyDialog: document.getElementById("historyDialog"),
  historyList: document.getElementById("historyList"),
  closeHistory: document.getElementById("closeHistory"),
};

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toneClass(tone) {
  if (tone === "ok") return "tone-ok";
  if (tone === "warn") return "tone-warn";
  if (tone === "danger") return "tone-danger";
  return "tone-muted";
}

function chip(text, tone) {
  return `<span class="chip ${tone || ""}">${esc(text)}</span>`;
}

function optionList(field) {
  if (field.optionsSource && state.reference[field.optionsSource]) {
    return state.reference[field.optionsSource];
  }
  return (field.options || []).map((o) =>
    typeof o === "string" ? { value: o, label: o } : o
  );
}

function fieldVisible(field, values) {
  if (!field.showWhen) return true;
  return Object.entries(field.showWhen).every(([key, allowed]) => {
    const current = values[key] ?? "";
    return (allowed || []).includes(current);
  });
}

function visibleFields(fn, values) {
  return (fn.fields || []).filter((f) => fieldVisible(f, values));
}

function snapshotFormValues() {
  const values = { ...state.formValues };
  if (!state.selected) return values;
  for (const field of state.selected.fields || []) {
    const input = el.form.querySelector(`[name="${field.name}"]`);
    if (!input) continue;
    if (field.type === "checkbox") values[field.name] = !!input.checked;
    else if (field.type !== "file") values[field.name] = input.value;
  }
  state.formValues = values;
  return values;
}

function groupFunctions(fns) {
  const map = new Map();
  for (const f of fns) {
    if (!map.has(f.group)) map.set(f.group, []);
    map.get(f.group).push(f);
  }
  return map;
}

function renderNav() {
  const groups = groupFunctions(state.functions);
  let html = "";
  for (const [group, items] of groups) {
    html += `<div class="fn-group"><h3>${esc(group)}</h3>`;
    for (const f of items) {
      const active = state.selected?.id === f.id ? "active" : "";
      html += `<button type="button" class="fn-btn ${active}" data-id="${esc(f.id)}">${esc(f.label)}</button>`;
    }
    html += `</div>`;
  }
  el.nav.innerHTML = html;
  el.nav.querySelectorAll(".fn-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectFunction(btn.dataset.id));
  });
}

function fieldHtml(field, values) {
  const id = `f_${field.name}`;
  const current = values[field.name];
  const req = field.required ? "required" : "";
  const hint = field.hint ? `<div class="hint">${esc(field.hint)}</div>` : "";

  if (field.type === "checkbox") {
    const checked =
      current === true || current === "true" || (current == null && field.default === true)
        ? "checked"
        : "";
    return `<div class="field" data-field="${esc(field.name)}">
      <div class="check-row">
        <input type="checkbox" id="${id}" name="${esc(field.name)}" ${checked} />
        <label for="${id}">${esc(field.label)}</label>
      </div>
      ${hint}
    </div>`;
  }

  if (field.type === "select") {
    const opts = optionList(field);
    const selectedVal =
      current != null && current !== "" ? String(current) : String(field.default ?? "");
    const optionsHtml = opts
      .map((o) => {
        const sel = String(o.value) === selectedVal ? "selected" : "";
        return `<option value="${esc(o.value)}" ${sel}>${esc(o.label)}</option>`;
      })
      .join("");
    return `<div class="field" data-field="${esc(field.name)}">
      <label for="${id}">${esc(field.label)}</label>
      <select id="${id}" name="${esc(field.name)}" ${req}>${optionsHtml}</select>
      ${hint}
    </div>`;
  }

  if (field.type === "textarea") {
    const val = current != null ? String(current) : "";
    return `<div class="field" data-field="${esc(field.name)}">
      <label for="${id}">${esc(field.label)}</label>
      <textarea id="${id}" name="${esc(field.name)}" rows="${field.rows || 5}" placeholder="${esc(field.placeholder || "")}" ${req}>${esc(val)}</textarea>
      ${hint}
    </div>`;
  }

  if (field.type === "file") {
    return `<div class="field" data-field="${esc(field.name)}">
      <label for="${id}">${esc(field.label)}</label>
      <input type="file" id="${id}" name="${esc(field.name)}" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" ${req} />
      ${hint}
    </div>`;
  }

  const type = field.type === "number" ? "number" : "text";
  const min = field.min != null ? `min="${field.min}"` : "";
  const max = field.max != null ? `max="${field.max}"` : "";
  const val =
    current != null && current !== ""
      ? `value="${esc(current)}"`
      : field.default != null
        ? `value="${esc(field.default)}"`
        : "";
  return `<div class="field" data-field="${esc(field.name)}">
    <label for="${id}">${esc(field.label)}</label>
    <input type="${type}" id="${id}" name="${esc(field.name)}" placeholder="${esc(field.placeholder || "")}" ${val} ${min} ${max} ${req} />
    ${hint}
  </div>`;
}

function defaultFormValues(fn) {
  const values = {};
  for (const field of fn.fields || []) {
    if (field.type === "checkbox") values[field.name] = field.default === true;
    else if (field.default != null) values[field.name] = field.default;
    else values[field.name] = "";
  }
  return values;
}

function renderForm() {
  if (!state.selected) return;
  const values = state.formValues;
  const fields = visibleFields(state.selected, values);
  el.form.innerHTML =
    fields.map((f) => fieldHtml(f, values)).join("") ||
    `<p class="empty">No inputs needed — click Run.</p>`;

  for (const field of state.selected.fields || []) {
    if (!field.drivesVisibility) continue;
    const input = el.form.querySelector(`[name="${field.name}"]`);
    if (!input) continue;
    input.addEventListener("change", () => {
      snapshotFormValues();
      renderForm();
    });
  }
}

function selectFunction(id) {
  state.selected = state.functions.find((f) => f.id === id) || null;
  renderNav();
  if (!state.selected) return;

  el.title.textContent = state.selected.label;
  el.desc.textContent = state.selected.description;
  state.formValues = defaultFormValues(state.selected);
  renderForm();
  el.runBtn.disabled = false;
  el.resultsPanel.hidden = true;
}

function collectInputs() {
  const values = snapshotFormValues();
  const data = {};
  for (const field of visibleFields(state.selected, values)) {
    if (field.type === "file") {
      const input = el.form.querySelector(`[name="${field.name}"]`);
      data[field.name] = input?.files?.[0] || null;
    } else {
      data[field.name] = values[field.name];
    }
  }
  return data;
}

function renderMeta(view, ok, requestId) {
  const chips = [];
  chips.push(chip(ok ? "Success" : "Failed", ok ? "ok" : "danger"));
  if (requestId) chips.push(chip(`requestId: ${requestId}`));
  const usage = view?.meta?.usage;
  if (usage?.lines?.length) chips.push(chip(usage.lines.join(" · ")));
  if (usage?.replayed) chips.push(chip("Replayed (idempotent)", "warn"));
  el.resultsMeta.innerHTML = chips.join("");
}

function pretty(value) {
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value);
  }
}

function renderMachine(machine) {
  state.lastMachine = machine || null;
  if (!el.machineBody) return;

  if (!machine) {
    el.machineBody.innerHTML = `<p class="empty">No machine payload yet.</p>`;
    if (el.copyMachineBtn) el.copyMachineBtn.hidden = true;
    return;
  }

  const req = machine.request;
  const method = req?.method || "?";
  const url = req?.url || req?.path || "";
  let html = "";

  html += `<div class="machine-block">
    <h4>Sent to API</h4>
    <div class="wire-line"><strong>${esc(method)}</strong> ${esc(url)}</div>
    <pre class="machine-json">${esc(pretty(req))}</pre>
  </div>`;

  html += `<div class="machine-block">
    <h4>Returned from API</h4>
    ${machine.error ? `<div class="wire-line tone-danger">${esc(typeof machine.error === "string" ? machine.error : pretty(machine.error))}</div>` : ""}
    <pre class="machine-json">${esc(pretty(machine.response))}</pre>
  </div>`;

  el.machineBody.innerHTML = html;
  if (el.copyMachineBtn) el.copyMachineBtn.hidden = false;
}

function goodLawHtml(gl) {
  if (!gl) return "";
  return `<div class="${toneClass(gl.tone)}">${esc(gl.label)}${gl.basis ? ` — ${esc(gl.basis)}` : ""}</div>`;
}

function renderView(view) {
  if (!view) {
    el.resultsBody.innerHTML = `<p class="empty">No result.</p>`;
    return;
  }

  let body = `<h2>${esc(view.headline || "Result")}</h2>`;
  if (view.subtitle) body += `<p class="sub">${esc(view.subtitle)}</p>`;

  switch (view.kind) {
    case "error":
      body += `<div class="result-card">
        <p class="tone-danger">${esc(view.message)}</p>
        ${(view.details || []).map((d) => `<div class="meta-line">${esc(d)}</div>`).join("")}
      </div>`;
      break;

    case "discovery":
      body += `<div class="table-wrap"><table class="data">
        <thead><tr><th>Method</th><th>Path</th><th>Summary</th></tr></thead>
        <tbody>${(view.endpoints || [])
          .map((e) => `<tr><td>${esc(e.method)}</td><td>${esc(e.path)}</td><td>${esc(e.summary)}</td></tr>`)
          .join("") || `<tr><td colspan="3">Surface keys: ${esc((view.rawKeys || []).join(", "))}</td></tr>`}
        </tbody></table></div>`;
      if (view.pricing) {
        body += `<div class="result-card" style="margin-top:0.75rem"><h3>Pricing policy</h3>
          <pre class="body-text">${esc(JSON.stringify(view.pricing, null, 2))}</pre></div>`;
      }
      break;

    case "jurisdictions":
      body += `<div class="result-card"><h3>Types</h3>
        ${(view.types || []).map((t) => `<div class="meta-line"><strong>${esc(t.type)}</strong> — ${esc(t.label)}</div>`).join("") || "<div class='empty'>No types listed.</div>"}
      </div>`;
      if ((view.circuits || []).length) {
        body += `<div class="result-card"><h3>Circuits</h3><div>${esc(view.circuits.join(", "))}</div></div>`;
      }
      if ((view.states || []).length) {
        body += `<div class="result-card"><h3>States</h3>
          <div class="table-wrap"><table class="data"><thead><tr><th>Code</th><th>Name</th></tr></thead>
          <tbody>${view.states.slice(0, 60).map((s) => `<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td></tr>`).join("")}
          </tbody></table></div>
          ${view.states.length > 60 ? `<div class="hint">Showing first 60 of ${view.states.length}.</div>` : ""}
        </div>`;
      }
      break;

    case "search":
      if (!(view.results || []).length) {
        body += `<p class="empty">No cases matched.</p>`;
        break;
      }
      body += view.results
        .map((r) => {
          const holdings = (r.holdings || [])
            .map((h) => `<li>${esc(h.holding || h.issue || JSON.stringify(h))}</li>`)
            .join("");
          return `<article class="result-card">
            <h3>${esc(r.caseName)}</h3>
            <div class="cite">${esc(r.citation)}</div>
            <div class="meta-line">${esc([r.court, r.dateFiled, r.caseId ? `ID ${r.caseId}` : ""].filter(Boolean).join(" · "))}</div>
            ${goodLawHtml(r.goodLaw)}
            ${r.snippet ? `<blockquote class="snippet">${esc(r.snippet)}</blockquote>` : ""}
            ${r.summaryAi ? `<p>${esc(r.summaryAi)}</p>` : ""}
            ${holdings ? `<ul>${holdings}</ul>` : ""}
            ${r.opinionText ? `<details><summary>Opinion text</summary><pre class="body-text">${esc(typeof r.opinionText === "string" ? r.opinionText : JSON.stringify(r.opinionText, null, 2))}</pre></details>` : ""}
          </article>`;
        })
        .join("");
      break;

    case "cite_check":
      body += `<div class="counts">${Object.entries(view.counts || {})
        .map(([k, v]) => chip(`${k}: ${v}`, k === "valid" ? "ok" : k.includes("mismatch") || k === "implausible" || k === "error" ? "danger" : "warn"))
        .join("")}</div>`;
      body += (view.rows || [])
        .map((r) => `<article class="result-card">
          <div class="meta-line">Input #${esc(r.inputIndex)}${r.unitIndex != null ? ` · unit ${esc(r.unitIndex)}` : ""}</div>
          <h3 class="${toneClass(r.tone)}">${esc(r.verdictLabel)}</h3>
          <div class="cite">${esc(r.asSent)}</div>
          <p class="sub">${esc(r.meaning)}</p>
          ${r.corrected ? `<div><strong>Corrected:</strong> ${esc(r.corrected)}</div>` : ""}
          ${goodLawHtml(r.goodLaw)}
          ${r.message ? `<div class="meta-line">${esc(r.message)}</div>` : ""}
          ${(r.candidates || []).length ? `<div class="meta-line">Candidates: ${(r.candidates || []).map((c) => esc(c.caseName || c.citation || c.caseId)).join("; ")}</div>` : ""}
        </article>`)
        .join("") || `<p class="empty">No citation rows.</p>`;
      break;

    case "resolve":
    case "batch":
    case "cited_by": {
      const items = view.candidates || view.cases || view.items || [];
      body += items
        .map((c) => `<article class="result-card">
          <h3>${esc(c.caseName || "Untitled")}</h3>
          <div class="cite">${esc(c.citation || "")}</div>
          <div class="meta-line">${esc([c.court, c.dateFiled || c.year, c.caseId ? `ID ${c.caseId}` : "", c.treatment].filter(Boolean).join(" · "))}</div>
        </article>`)
        .join("") || `<p class="empty">No matches.</p>`;
      if ((view.notFound || []).length) {
        body += `<div class="result-card"><h3>Not found</h3><div>${esc(view.notFound.join(", "))}</div></div>`;
      }
      break;
    }

    case "retrieve":
      if ((view.candidates || []).length) {
        body += `<p class="sub">Pick a candidate to retrieve it by case ID.</p>`;
        body += view.candidates
          .map((c) => `<article class="result-card">
            <h3>${esc(c.caseName || "Candidate")}</h3>
            <div class="cite">${esc(c.citation || "")}</div>
            <div class="meta-line">${esc([c.court, c.caseId ? `ID ${c.caseId}` : ""].filter(Boolean).join(" · "))}</div>
            ${c.caseId ? `<button type="button" class="ghost-btn tiny-btn follow-retrieve" data-case-id="${esc(c.caseId)}" data-query="${esc(view.case?.caseName || c.caseName || "")}">Retrieve this case</button>` : ""}
          </article>`)
          .join("");
      }
      if (view.case) {
        body += `<article class="result-card">
          <h3>${esc(view.case.caseName || "Case")}</h3>
          <div class="cite">${esc(view.case.citation || "")}</div>
          <div class="meta-line">${esc([view.case.court, view.case.dateFiled, view.case.caseId ? `ID ${view.case.caseId}` : ""].filter(Boolean).join(" · "))}</div>
          ${goodLawHtml(view.case.goodLaw)}
          ${view.case.summary ? `<p>${esc(view.case.summary)}</p>` : ""}
        </article>`;
      }
      break;

    case "statute":
      body += `<article class="result-card">
        <div class="cite">${esc(view.citation || "")}</div>
        ${view.title ? `<h3>${esc(view.title)}</h3>` : ""}
        <div class="meta-line">${esc([view.authorityKey, view.year ? `Year ${view.year}` : "", `Status: ${view.status}`].filter(Boolean).join(" · "))}</div>
        ${view.body ? `<pre class="body-text">${esc(view.body)}</pre>` : `<p class="empty">No body text returned.</p>`}
      </article>`;
      break;

    case "case_meta":
      body += `<article class="result-card">
        ${goodLawHtml(view.goodLaw)}
        <dl class="kv">${(view.fields || []).map((f) => `<dt>${esc(f.label)}</dt><dd>${esc(f.value)}</dd>`).join("")}</dl>
        ${(view.parallels || []).length ? `<div class="meta-line" style="margin-top:0.6rem">Parallel cites: ${esc(view.parallels.join("; "))}</div>` : ""}
      </article>`;
      break;

    case "good_law":
      body += `<article class="result-card">${goodLawHtml(view.goodLaw)}</article>`;
      body += (view.negativeCitations || [])
        .map((n) => `<article class="result-card">
          <h3>${esc(n.caseName || "Citing case")}</h3>
          <div class="cite">${esc(n.citation || "")}</div>
          <div class="meta-line">${esc([n.treatment, n.caseId ? `ID ${n.caseId}` : ""].filter(Boolean).join(" · "))}</div>
        </article>`)
        .join("") || (view.goodLaw?.tone === "ok" ? "" : `<p class="empty">No negative citations listed.</p>`);
      break;

    case "usage":
      body += `<article class="result-card"><h3>Account</h3>
        <pre class="body-text">${esc(JSON.stringify(view.consumer || {}, null, 2))}</pre></article>`;
      body += `<div class="table-wrap"><table class="data">
        <thead><tr><th>Operation</th><th>Calls</th><th>Units</th><th>Cost ¢</th></tr></thead>
        <tbody>${(view.byOperation || [])
          .map((r) => `<tr><td>${esc(r.operation)}</td><td>${esc(r.calls)}</td><td>${esc(r.units)}</td><td>${esc(r.costCents)}</td></tr>`)
          .join("") || `<tr><td colspan="4">No usage rows in this window.</td></tr>`}
        </tbody></table></div>`;
      if (view.pricing || view.rateLimit) {
        body += `<div class="result-card" style="margin-top:0.75rem"><h3>Limits / pricing</h3>
          <pre class="body-text">${esc(JSON.stringify({ pricing: view.pricing, rateLimit: view.rateLimit }, null, 2))}</pre></div>`;
      }
      break;

    case "document_job":
      body += `<article class="result-card">
        <dl class="kv">
          <dt>Job ID</dt><dd>${esc(view.jobId)}</dd>
          <dt>Status</dt><dd class="${toneClass(view.status === "completed" ? "ok" : view.status === "failed" ? "danger" : "warn")}">${esc(view.status)}</dd>
          ${view.resultsUrl ? `<dt>Results page</dt><dd><a href="${esc(view.resultsUrl)}" target="_blank" rel="noreferrer">Open results</a></dd>` : ""}
          ${view.emails ? `<dt>Emails</dt><dd>${esc(Array.isArray(view.emails) ? view.emails.join(", ") : view.emails)}</dd>` : ""}
          ${view.counts ? `<dt>Counts</dt><dd>${esc(JSON.stringify(view.counts))}</dd>` : ""}
          ${view.error ? `<dt>Error</dt><dd class="tone-danger">${esc(typeof view.error === "string" ? view.error : JSON.stringify(view.error))}</dd>` : ""}
        </dl>
      </article>`;
      if (view.reportDownload) {
        body += `<p><a class="primary-btn" style="display:inline-block" href="${esc(view.reportDownload.url)}" download>Download PDF report</a></p>`;
      }
      body += (view.citations || [])
        .map((c) => `<article class="result-card">
          <h3 class="${toneClass(c.tone)}">${esc(c.verdictLabel)}</h3>
          <div class="cite">${esc(c.asSent)}</div>
          ${c.page != null ? `<div class="meta-line">Page ${esc(c.page)}</div>` : ""}
          ${c.corrected ? `<div><strong>Corrected:</strong> ${esc(c.corrected)}</div>` : ""}
        </article>`)
        .join("");
      break;

    case "download":
      body += `<article class="result-card">
        <p>${esc(view.subtitle || "")}</p>
        <p><a class="primary-btn" style="display:inline-block" href="${esc(view.url)}" download>Open ${esc(view.filename)}</a></p>
      </article>`;
      break;

    default:
      body += `<pre class="body-text">${esc(JSON.stringify(view, null, 2))}</pre>`;
  }

  el.resultsBody.innerHTML = body;
  el.resultsBody.querySelectorAll(".follow-retrieve").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!state.selected || state.selected.id !== "retrieve") {
        selectFunction("retrieve");
      }
      state.formValues = {
        ...defaultFormValues(state.selected),
        query: btn.dataset.query || state.formValues.query || "",
        caseId: btn.dataset.caseId || "",
      };
      renderForm();
      el.runBtn.click();
    });
  });
}

async function runSelected(event) {
  event.preventDefault();
  if (!state.selected) return;
  if (state.rateLimitUntil > Date.now()) {
    updateRateBanner();
    return;
  }

  // Soft spacing: wait out the min gap before sending
  if (state.pacing && state.lastSendAt) {
    const wait = MIN_GAP_MS - (Date.now() - state.lastSendAt);
    if (wait > 0) {
      el.runBtn.disabled = true;
      el.busy.hidden = false;
      const end = Date.now() + wait;
      while (Date.now() < end) {
        const left = Math.ceil((end - Date.now()) / 1000);
        el.busy.textContent = `Pacing… ${left}s`;
        await new Promise((r) => setTimeout(r, 100));
      }
      el.busy.textContent = "Calling LawDiver…";
    }
  }

  const inputs = collectInputs();
  el.runBtn.disabled = true;
  el.busy.hidden = false;
  el.busy.textContent = "Calling LawDiver…";
  el.resultsPanel.hidden = false;
  el.resultsBody.innerHTML = `<p class="empty">Working…</p>`;
  if (el.machineBody) el.machineBody.innerHTML = `<p class="empty">Waiting for API response…</p>`;
  if (el.copyMachineBtn) el.copyMachineBtn.hidden = true;
  el.resultsMeta.innerHTML = "";
  state.lastSendAt = Date.now();

  try {
    let res;
    if (state.selected.id === "document_cite_check") {
      if (!inputs.file) throw new Error("Choose a PDF or Word file.");
      const fd = new FormData();
      fd.append("file", inputs.file);
      fd.append("emails", inputs.emails || "");
      fd.append("downloadReport", inputs.downloadReport ? "true" : "false");
      res = await fetch("/api/run/document", { method: "POST", body: fd });
    } else {
      const payload = { ...inputs };
      delete payload.file;
      res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ functionId: state.selected.id, inputs: payload }),
      });
    }
    const data = await res.json();
    if (!res.ok && !data.view) {
      throw new Error(data.detail || `HTTP ${res.status}`);
    }
    renderMeta(data.view, !!data.ok, data.requestId);
    renderView(data.view);
    renderMachine(data.machine);
    maybeStartRateLimit(data.view);
    if (data.download && data.view?.kind !== "download" && data.view?.kind !== "document_job") {
      el.resultsBody.insertAdjacentHTML(
        "beforeend",
        `<p><a href="${esc(data.download.url)}" download>Download ${esc(data.download.filename)}</a></p>`
      );
    }
  } catch (err) {
    renderMeta({ meta: {} }, false, null);
    renderView({
      kind: "error",
      headline: "Request failed",
      message: err.message || String(err),
      details: [],
    });
    renderMachine({
      request: null,
      response: null,
      error: { message: err.message || String(err) },
    });
  } finally {
    if (state.rateLimitUntil <= Date.now()) {
      el.runBtn.disabled = false;
    }
    el.busy.hidden = true;
    el.busy.textContent = "Calling LawDiver…";
  }
}

function parseRetrySeconds(view) {
  if (view?.retryAfterSeconds != null) return Number(view.retryAfterSeconds);
  const msg = view?.message || "";
  const m = msg.match(/[Rr]etry in (\d+)\s*s/);
  if (m) return Number(m[1]);
  if (view?.code === "rate_limited" || view?.status === 429 || /rate.?limit/i.test(view?.headline || "")) {
    return 20;
  }
  return null;
}

function updateRateBanner() {
  if (!el.rateBanner) return;
  const leftMs = state.rateLimitUntil - Date.now();
  if (leftMs <= 0) {
    el.rateBanner.hidden = true;
    el.rateBanner.textContent = "";
    el.runBtn.disabled = !state.selected;
    if (state.rateTimer) {
      clearInterval(state.rateTimer);
      state.rateTimer = null;
    }
    return;
  }
  const sec = Math.ceil(leftMs / 1000);
  el.rateBanner.hidden = false;
  el.rateBanner.textContent = `Rate limited — retry in ${sec}s`;
  el.runBtn.disabled = true;
}

function maybeStartRateLimit(view) {
  if (!view) return;
  const isRate =
    view.code === "rate_limited" ||
    view.status === 429 ||
    /rate.?limit/i.test(view.headline || "") ||
    /rate.?limit/i.test(view.message || "");
  if (!isRate) return;
  const sec = parseRetrySeconds(view) || 20;
  state.rateLimitUntil = Date.now() + sec * 1000;
  updateRateBanner();
  if (state.rateTimer) clearInterval(state.rateTimer);
  state.rateTimer = setInterval(updateRateBanner, 250);
}

async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    el.historyList.innerHTML = `<p class="empty">No local history yet.</p>`;
    return;
  }
  el.historyList.innerHTML = items
    .map((h) => `<div class="history-item" data-id="${h.id}">
      <div class="when">${esc(h.createdAt)} · ${h.ok ? "OK" : "Error"}</div>
      <strong>${esc(h.functionLabel)}</strong>
      <div>${esc(h.summary || h.errorMessage || "")}</div>
      ${h.requestId ? `<div class="when">requestId: ${esc(h.requestId)}</div>` : ""}
      <div class="hist-actions">
        ${h.hasView || h.hasMachine ? `<button type="button" class="ghost-btn tiny-btn hist-open" data-id="${h.id}">Open I/O</button>` : `<span class="when">No stored I/O</span>`}
      </div>
    </div>`)
    .join("");

  el.historyList.querySelectorAll(".hist-open").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const detail = await fetch(`/api/history/${id}`).then((r) => r.json());
      el.historyDialog.close();
      el.resultsPanel.hidden = false;
      renderMeta(detail.view || {}, !!detail.ok, detail.requestId);
      if (detail.view) renderView(detail.view);
      else {
        el.resultsBody.innerHTML = `<p class="empty">${esc(detail.summary || detail.errorMessage || "No human view stored.")}</p>`;
      }
      renderMachine(detail.machine || { request: null, response: null, error: detail.errorMessage || null });
      if (detail.functionId) {
        // select matching function without wiping results
        const fn = state.functions.find((f) => f.id === detail.functionId);
        if (fn) {
          state.selected = fn;
          renderNav();
          el.title.textContent = fn.label;
          el.desc.textContent = `${fn.description} (restored from history #${detail.id})`;
        }
      }
    });
  });
}

async function boot() {
  const res = await fetch("/api/functions");
  const data = await res.json();
  state.functions = data.functions || [];
  state.keyConfigured = !!data.keyConfigured;
  state.baseUrl = data.baseUrl || "";
  state.reference = data.reference || { states: [], circuits: [] };
  el.status.textContent = state.keyConfigured
    ? `Key configured · ${state.baseUrl}`
    : "No API key in .env";
  el.status.className = `status-pill ${state.keyConfigured ? "ok" : "bad"}`;
  renderNav();
  const search = state.functions.find((f) => f.id === "search");
  selectFunction(search?.id || state.functions[0]?.id);
}

el.form.addEventListener("submit", runSelected);
if (el.softSpacing) {
  state.pacing = !!el.softSpacing.checked;
  el.softSpacing.addEventListener("change", () => {
    state.pacing = !!el.softSpacing.checked;
  });
}
el.historyBtn.addEventListener("click", async () => {
  await loadHistory();
  el.historyDialog.showModal();
});
el.closeHistory.addEventListener("click", () => el.historyDialog.close());
if (el.copyMachineBtn) {
  el.copyMachineBtn.addEventListener("click", async () => {
    if (!state.lastMachine) return;
    try {
      await navigator.clipboard.writeText(pretty(state.lastMachine));
      el.copyMachineBtn.textContent = "Copied";
      setTimeout(() => {
        el.copyMachineBtn.textContent = "Copy JSON";
      }, 1200);
    } catch {
      el.copyMachineBtn.textContent = "Copy failed";
    }
  });
}

boot().catch((err) => {
  el.status.textContent = `Failed to load: ${err.message}`;
  el.status.className = "status-pill bad";
});
