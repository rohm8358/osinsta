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

async function refresh() {
  const h = await api("/api/health");
  el("token-masked").textContent = h.token_masked || "not set";
  applyBalance(h.balance);
}

async function submit(save) {
  const msg = el("token-msg");
  msg.textContent = "Checking…";
  msg.className = "msg";
  try {
    const data = await api("/api/token", {
      method: "POST",
      body: JSON.stringify({
        token: el("token").value,
        save: save ? el("save-token").checked : false,
      }),
    });
    msg.textContent = save ? "Key verified and updated." : "Key verified (not saved).";
    msg.className = "msg ok";
    el("token").value = "";
    el("token-masked").textContent = data.token_masked || "set";
    applyBalance(data.balance);
  } catch (e) {
    msg.textContent = String(e.message || e);
    msg.className = "msg err";
  }
}

el("btn-verify").addEventListener("click", () => submit(false));
el("btn-save").addEventListener("click", () => submit(true));
refresh().catch((e) => {
  el("token-msg").textContent = String(e.message || e);
  el("token-msg").className = "msg err";
});
