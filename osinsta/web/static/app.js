async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
  return data;
}

const el = (id) => document.getElementById(id);
const tooltip = el("tooltip");
let commands = [];
let selected = new Set();
let profileMode = "public";
let lastReport = null;

function setStatus(ok, text) {
  const s = el("status");
  s.textContent = text;
  s.className = "pill " + (ok ? "ok" : "bad");
}

function applyBalance(bal) {
  if (!bal || bal.error) {
    el("req-left").textContent = bal?.error ? "error" : "—";
    el("req-amount").textContent = "";
    return;
  }
  el("req-left").textContent = bal.requests ?? "—";
  el("req-amount").textContent = bal.amount != null
    ? `(${bal.amount}${bal.currency ? " " + bal.currency : ""})`
    : "";
}

async function refreshHealth() {
  try {
    const h = await api("/api/health");
    el("token-masked").textContent = h.token_masked || "not set";
    applyBalance(h.balance);
    setStatus(h.has_token, h.has_token ? "connected" : "key needed");
  } catch {
    setStatus(false, "offline");
  }
}

function visibleCommands() {
  const q = el("filter").value.trim().toLowerCase();
  return commands.filter((c) => {
    if (profileMode === "private" && !(c.access === "private_ok" || c.access === "no_target")) return false;
    if (!q) return true;
    const hay = `${c.label || ""} ${c.name} ${c.description} ${c.group_label || c.group}`.toLowerCase();
    return hay.includes(q);
  });
}

function chipText(access) {
  if (access === "private_ok") return "Private ok";
  if (access === "public_only") return "Public";
  return "No target";
}

function renderCommands() {
  const board = el("commands");
  board.innerHTML = "";
  const list = visibleCommands();
  const groups = {};
  list.forEach((c) => {
    const g = c.group_label || c.group;
    (groups[g] ||= []).push(c);
  });

  Object.entries(groups).forEach(([group, items]) => {
    const block = document.createElement("section");
    block.className = "group-block";
    block.innerHTML = `<h3 class="group-title">${group}</h3>`;
    const grid = document.createElement("div");
    grid.className = "lookup-grid";

    items.forEach((c) => {
      const card = document.createElement("article");
      card.className = `lookup-card access-${c.access}` + (selected.has(c.name) ? " selected" : "");
      card.innerHTML = `
        <span class="chip">${chipText(c.access)}</span>
        <h4 class="title">${c.label || c.name}</h4>
        <p class="blurb">${c.description}</p>
        <span class="check-dot" aria-hidden="true"></span>
      `;
      card.addEventListener("click", () => {
        if (selected.has(c.name)) selected.delete(c.name);
        else selected.add(c.name);
        card.classList.toggle("selected", selected.has(c.name));
        updateSelectionUI();
      });
      card.addEventListener("mouseenter", (ev) => showTip(ev, `${c.label || c.name} — ${c.description}`));
      card.addEventListener("mousemove", moveTip);
      card.addEventListener("mouseleave", hideTip);
      grid.appendChild(card);
    });

    block.appendChild(grid);
    board.appendChild(block);
  });
  updateSelectionUI();
}

function showTip(ev, text) {
  tooltip.hidden = false;
  tooltip.textContent = text;
  moveTip(ev);
}
function moveTip(ev) {
  const pad = 14;
  let x = ev.clientX + pad;
  let y = ev.clientY + pad;
  const rect = tooltip.getBoundingClientRect();
  if (x + rect.width > window.innerWidth - 8) x = ev.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - 8) y = ev.clientY - rect.height - pad;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}
function hideTip() { tooltip.hidden = true; }

function updateSelectionUI() {
  const vis = new Set(visibleCommands().map((c) => c.name));
  [...selected].forEach((n) => { if (!vis.has(n)) selected.delete(n); });
  el("sel-count").textContent = selected.size ? `· ${selected.size} selected` : "";
  el("btn-run").disabled = selected.size === 0;
}

function labelFor(name) {
  return commands.find((x) => x.name === name)?.label || name;
}

function niceKey(key) {
  return String(key).replace(/_/g, " ");
}

function formatValue(value) {
  if (value == null || value === "") return document.createTextNode("—");
  if (typeof value === "boolean") return document.createTextNode(value ? "yes" : "no");
  if (typeof value === "number") return document.createTextNode(String(value));
  if (typeof value === "string") {
    if (/^https?:\/\//i.test(value)) {
      const a = document.createElement("a");
      a.href = value; a.target = "_blank"; a.rel = "noreferrer"; a.textContent = value;
      return a;
    }
    return document.createTextNode(value);
  }
  if (Array.isArray(value)) {
    if (!value.length) return document.createTextNode("(none)");
    if (value.every((x) => typeof x !== "object" || x == null)) {
      const ul = document.createElement("ul");
      ul.style.margin = "0";
      ul.style.paddingLeft = "1.1rem";
      value.slice(0, 50).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = String(item);
        ul.appendChild(li);
      });
      if (value.length > 50) {
        const li = document.createElement("li");
        li.textContent = `… +${value.length - 50} more`;
        ul.appendChild(li);
      }
      return ul;
    }
    const wrap = document.createElement("div");
    wrap.className = "nested";
    value.slice(0, 25).forEach((item, i) => {
      const block = document.createElement("div");
      block.style.marginBottom = "0.45rem";
      const title = document.createElement("div");
      title.className = "k";
      title.textContent = `Item ${i + 1}`;
      block.append(title, renderObject(item));
      wrap.appendChild(block);
    });
    if (value.length > 25) {
      const more = document.createElement("div");
      more.className = "k";
      more.textContent = `… +${value.length - 25} more`;
      wrap.appendChild(more);
    }
    return wrap;
  }
  if (typeof value === "object") return renderObject(value);
  return document.createTextNode(String(value));
}

function renderObject(obj) {
  if (obj == null || typeof obj !== "object" || Array.isArray(obj)) return formatValue(obj);
  const kv = document.createElement("div");
  kv.className = "kv";
  Object.entries(obj).forEach(([k, v]) => {
    if (k === "previews" && Array.isArray(v)) {
      const kk = document.createElement("div"); kk.className = "k"; kk.textContent = niceKey(k);
      const vv = document.createElement("div"); vv.className = "v"; vv.textContent = `${v.length} media items`;
      kv.append(kk, vv);
      return;
    }
    const kk = document.createElement("div"); kk.className = "k"; kk.textContent = niceKey(k);
    const vv = document.createElement("div"); vv.className = "v"; vv.appendChild(formatValue(v));
    kv.append(kk, vv);
  });
  return kv;
}

function buildReport(data) {
  const target = data.target || el("target").value.trim().replace(/^@/, "") || "unknown";
  const when = new Date().toISOString();
  const report = {
    title: `Osinsta report · @${target}`,
    target,
    profile_mode: data.profile_mode || profileMode,
    generated_at: when,
    total_api_calls: data.total_api_calls,
    balance: data.balance || null,
    sections: (data.results || []).map((item) => ({
      command: item.command,
      label: labelFor(item.command),
      ok: item.ok !== false,
      api_calls: item.api_calls || 0,
      error: item.error || null,
      result: item.result,
    })),
  };
  lastReport = report;
  return report;
}

function renderReport(report) {
  const box = el("results");
  box.innerHTML = "";
  const root = document.createElement("article");
  root.className = "report";
  root.id = "report-root";

  const cover = document.createElement("div");
  cover.className = "report-cover";
  cover.innerHTML = `
    <h3>${escapeHtml(report.title)}</h3>
    <p class="sub">Generated ${escapeHtml(report.generated_at)} · ${report.sections.length} section(s)</p>
    <div class="report-meta">
      <span>Mode: ${escapeHtml(report.profile_mode || "—")}</span>
      <span>API calls: ${report.total_api_calls ?? 0}</span>
      ${report.balance?.requests != null ? `<span>Requests left: ${report.balance.requests}</span>` : ""}
    </div>
  `;
  root.appendChild(cover);

  report.sections.forEach((sec, idx) => {
    const section = document.createElement("section");
    section.className = "report-section" + (sec.ok ? "" : " err");
    const status = document.createElement("span");
    status.className = "sec-status";
    status.textContent = sec.ok ? `${sec.api_calls} calls` : "failed";
    const h = document.createElement("h4");
    h.textContent = `${idx + 1}. ${sec.label}`;
    h.prepend(status);
    // status floated right - append instead
    h.textContent = `${idx + 1}. ${sec.label}`;
    section.appendChild(status);
    section.appendChild(h);
    if (!sec.ok) {
      const kv = document.createElement("div");
      kv.className = "kv";
      kv.innerHTML = `<div class="k">Error</div><div class="v">${escapeHtml(sec.error || "unknown")}</div>`;
      section.appendChild(kv);
    } else {
      section.appendChild(renderObject(sec.result));
    }
    root.appendChild(section);
  });

  box.appendChild(root);
  el("report-actions").hidden = false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function reportToHtml(report) {
  const rows = report.sections.map((sec, i) => {
    const body = sec.ok
      ? `<pre>${escapeHtml(JSON.stringify(sec.result, null, 2))}</pre>`
      : `<p style="color:#b91c1c"><strong>Error:</strong> ${escapeHtml(sec.error || "unknown")}</p>`;
    return `<section style="margin:1.2rem 0;padding:1rem;border:1px solid #dbe3f0;border-radius:12px">
      <h2 style="margin:0 0 .6rem;font-size:1.1rem">${i + 1}. ${escapeHtml(sec.label)}</h2>
      ${body}
    </section>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>${escapeHtml(report.title)}</title>
<style>
 body{font-family:Georgia,serif;background:#f7fafc;color:#0f172a;margin:0;padding:2rem}
 h1{font-size:1.8rem;margin:0}
 .sub{color:#64748b;margin:.4rem 0 1.2rem}
 pre{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#e2e8f0;padding:1rem;border-radius:10px;font-size:.82rem}
 .meta span{display:inline-block;margin:.2rem .35rem .2rem 0;padding:.2rem .55rem;border:1px solid #cbd5e1;border-radius:999px;font-size:.8rem;color:#334155}
</style></head><body>
<h1>${escapeHtml(report.title)}</h1>
<p class="sub">Generated ${escapeHtml(report.generated_at)}</p>
<div class="meta">
  <span>Mode: ${escapeHtml(report.profile_mode || "—")}</span>
  <span>API calls: ${report.total_api_calls ?? 0}</span>
</div>
${rows}
<p style="margin-top:2rem;color:#64748b;font-size:.85rem">Generated by Osinsta</p>
</body></html>`;
}

async function runSelected() {
  const target = el("target").value.trim().replace(/^@/, "");
  const needsTarget = [...selected].some((name) => commands.find((c) => c.name === name)?.needs_target);
  if (needsTarget && !target) {
    el("results").innerHTML = `<div class="empty-state"><strong>Add a target</strong><p>Enter a username above first.</p></div>`;
    el("report-actions").hidden = true;
    return;
  }
  el("btn-run").disabled = true;
  el("results").innerHTML = `<div class="empty-state"><strong>Building report…</strong><p>Running ${selected.size} lookup(s).</p></div>`;
  el("report-actions").hidden = true;
  el("meta").textContent = "";
  try {
    const data = await api("/api/run_batch", {
      method: "POST",
      body: JSON.stringify({
        commands: [...selected],
        target: target || null,
        profile_mode: profileMode,
        case_id: el("active-case").value || null,
        params: {},
      }),
    });
    el("meta").textContent = `${data.total_api_calls} API calls`;
    if (data.balance) applyBalance(data.balance);
    const report = buildReport(data);
    renderReport(report);
    refreshHealth();
  } catch (e) {
    el("results").innerHTML = `<div class="empty-state"><strong>Run failed</strong><p>${escapeHtml(e.message || e)}</p></div>`;
  } finally {
    updateSelectionUI();
  }
}

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    profileMode = btn.dataset.mode;
    el("mode-hint").textContent = profileMode === "private"
      ? "Private mode: only lookups that usually work without follow access."
      : "Public mode: full toolkit for open profiles.";
    renderCommands();
  });
});

el("filter").addEventListener("input", renderCommands);
el("btn-select-all").addEventListener("click", () => {
  visibleCommands().forEach((c) => selected.add(c.name));
  renderCommands();
});
el("btn-clear").addEventListener("click", () => {
  selected.clear();
  renderCommands();
});
el("btn-run").addEventListener("click", runSelected);
el("btn-refresh-bal").addEventListener("click", refreshHealth);

el("btn-download-html").addEventListener("click", () => {
  if (!lastReport) return;
  const html = reportToHtml(lastReport);
  downloadBlob(`osinsta_${lastReport.target || "report"}.html`, html, "text/html");
});
el("btn-download-json").addEventListener("click", () => {
  if (!lastReport) return;
  downloadBlob(`osinsta_${lastReport.target || "report"}.json`, JSON.stringify(lastReport, null, 2), "application/json");
});

async function refreshCases() {
  const list = await api("/api/cases");
  const select = el("active-case");
  const current = select.value;
  select.innerHTML = '<option value="">None</option>';
  list.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.title;
    select.appendChild(opt);
  });
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

(async function init() {
  await refreshHealth();
  commands = await api("/api/commands");
  renderCommands();
  try { await refreshCases(); } catch {}
})();
