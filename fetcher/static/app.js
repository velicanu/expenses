"use strict";
// Plain DOM calls with textContent only: nothing from the server is ever parsed as HTML.
const list = document.getElementById("list");
const who = document.getElementById("who");

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const k of kids) e.append(k);
  return e;
}

function chip(text, ok) { return el("span", { class: "chip" + (ok ? " ok" : ""), text }); }

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function field(id, label, type, hint, extra = {}) {
  const input = el("input", { id, type, autocomplete: "off", autocapitalize: "off", autocorrect: "off", spellcheck: "false", ...extra });
  const row = el("div", { class: "field" }, input);
  if (type === "password") {
    const show = el("button", { type: "button", text: "Show", "aria-label": "Show or hide " + label });
    show.addEventListener("click", () => {
      input.type = input.type === "password" ? "text" : "password";
      show.textContent = input.type === "password" ? "Show" : "Hide";
    });
    row.append(show);
  }
  const wrap = el("div", {}, el("label", { for: id, text: label }), row);
  if (hint) wrap.append(el("div", { class: "hint", text: hint }));
  return { wrap, input };
}

function card(a) {
  const name = a.key;
  const status = el("div", { class: "chips" });
  if (a.error) status.append(chip("status unavailable", false));
  else {
    status.append(chip(a.stored ? "credentials stored" + (a.saved_at ? " · " + when(a.saved_at) : "") : "no credentials", a.stored));
    status.append(chip(a.totp ? "authenticator stored" : "no authenticator", a.totp));
  }
  const open = el("button", { type: "button", text: a.stored ? "Replace credentials" : "Set credentials" });
  const remove = el("button", { type: "button", class: "quiet", text: "Remove" });
  remove.addEventListener("click", async () => {
    if (!confirm(`Remove ${a.label} from the list? Stored credentials stay in the vault and are used again if you re-add it.`)) return;
    const r = await fetch(`/api/accounts/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (r.status === 401) { location.reload(); return; }
    const body = await r.json().catch(() => ({}));
    await load(r.ok ? `Removed ${a.label}.` : body.error || `Could not remove (HTTP ${r.status})`);
  });
  const user = field(`u-${name}`, "Username or email", "text", null, { inputmode: "email" });
  const pass = field(`p-${name}`, "Password", "password");
  const seed = field(`s-${name}`, "Authenticator seed (optional)", "password", "The base32 secret or the otpauth:// link shown when you set up an authenticator app. Leave empty if the bank only texts you codes.");
  const msg = el("div", { class: "msg", role: "status" });
  const save = el("button", { type: "submit", class: "primary", text: "Save" });
  const cancel = el("button", { type: "button", text: "Cancel" });
  const form = el("form", { autocomplete: "off" }, user.wrap, pass.wrap, seed.wrap, el("div", { class: "hint", text: "Saved straight to the vault. It is never shown again; to change it, enter everything again." }), el("div", { class: "actions" }, save, cancel), msg);

  const close = () => { form.classList.remove("open"); open.hidden = false; };
  open.addEventListener("click", () => { form.classList.add("open"); open.hidden = true; msg.textContent = ""; user.input.focus(); });
  cancel.addEventListener("click", () => { form.reset(); close(); });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    save.disabled = true; msg.className = "msg"; msg.textContent = "Saving…";
    try {
      const r = await fetch(`/api/accounts/${encodeURIComponent(name)}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user.input.value, password: pass.input.value, totp_seed: seed.input.value || null }),
      });
      if (r.status === 401) { location.reload(); return; }
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || `failed (HTTP ${r.status})`);
      form.reset(); close();
      await load(`Saved ${a.label}.`);
    } catch (e) {
      msg.className = "msg err"; msg.textContent = e.message;
    } finally { save.disabled = false; }
  });

  return el("div", { class: "card", id: `card-${name}` },
    el("div", { class: "row" }, el("div", {}, el("div", { class: "name", text: a.label }), status), el("div", { class: "btns" }, open, remove)),
    a.error ? el("div", { class: "msg err", text: a.error }) : "",
    form);
}

function addCard(institutions) {
  const pick = el("select", { id: "add-institution", "aria-label": "Institution" });
  for (const i of institutions) pick.append(el("option", { value: i.id, text: i.label }));
  const owner = el("input", { id: "add-owner", type: "text", autocomplete: "off", autocapitalize: "none", autocorrect: "off", spellcheck: "false", placeholder: "dragos, viral… (optional)", "aria-label": "Owner" });
  const add = el("button", { type: "submit", class: "primary", text: "Add account" });
  const msg = el("div", { class: "msg", role: "status" });
  const form = el("form", { class: "open", autocomplete: "off" }, el("label", { for: "add-institution", text: "Add another account" }), pick, el("label", { for: "add-owner", text: "Owner" }), owner,
    el("div", { class: "hint", text: "Two accounts at the same bank are told apart by owner: venmo-dragos, venmo-viral." }), el("div", { class: "actions" }, add), msg);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    add.disabled = true; msg.className = "msg"; msg.textContent = "Adding…";
    try {
      const r = await fetch("/api/accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ institution: pick.value, owner: owner.value }) });
      if (r.status === 401) { location.reload(); return; }
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || `failed (HTTP ${r.status})`);
      await load(`Added ${body.account.label}.`);
    } catch (e) { msg.className = "msg err"; msg.textContent = e.message; } finally { add.disabled = false; }
  });
  return el("div", { class: "card" }, form);
}

async function load(note) {
  const r = await fetch("/api/accounts");
  if (r.status === 401) { location.reload(); return; }
  if (!r.ok) { who.textContent = `Cannot load (HTTP ${r.status})`; return; }
  const body = await r.json();
  who.textContent = "Signed in as " + body.email + (note ? " · " + note : "");
  list.replaceChildren(...body.accounts.map(card), addCard(body.institutions));
}
load();
