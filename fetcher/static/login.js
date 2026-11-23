// The remote browser, through noVNC. Text from the server is only ever shown with textContent.
import RFB from "/novnc/core/rfb.js";

const $ = (id) => document.getElementById(id);
const account = new URLSearchParams(location.search).get("account") || "";
let rfb = null;
// True once THIS page has seen the session run. The service remembers how the last session ended, so a page opened later
// finds an old result: that is not news and must not send anyone to the expense app (which would visit the bank).
let watched = false;
let remaining = 0;
let ticking = null;

function note(text, kind) { $("note").textContent = text; $("note").className = kind || ""; }

async function api(method, path) {
  const r = await fetch(path, { method, headers: method === "GET" ? {} : { "Content-Type": "application/json" }, body: method === "GET" ? undefined : "{}" });
  if (r.status === 401) { location.reload(); throw new Error("signed out"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || body.detail || `failed (HTTP ${r.status})`);
  return body;
}

function clock() {
  const m = Math.floor(remaining / 60), s = remaining % 60;
  $("timer").textContent = remaining > 0 ? `${m}:${String(s).padStart(2, "0")} left` : "";
}
function startClock(seconds) {
  remaining = seconds; clock();
  clearInterval(ticking);
  ticking = setInterval(() => { remaining = Math.max(0, remaining - 1); clock(); }, 1000);
}

function show(running) {
  $("intro").style.display = running ? "none" : "";
  $("screen").classList.toggle("on", running);
  $("bar").classList.toggle("on", running);
}

function finished(st) {
  clearInterval(ticking); remaining = 0; clock();
  if (rfb) { try { rfb.disconnect(); } catch (_) {} rfb = null; }
  show(false);
  // Done (or closing Chrome yourself) means you have just logged in: go and fetch that account in the expense app, which
  // does it with your login there and shows the result. A timeout means you walked away: nothing to fetch.
  const fetchable = (st.fetch_institutions || []).includes(account.split("-")[0]);
  if ((st.result === "finished" || st.result === "closed") && st.expense_url && account && fetchable) {
    note("Chrome was closed so it keeps your login. Opening the expense app to fetch…", "ok");
    $("start").textContent = "Start the browser";
    setTimeout(() => location.assign(`${st.expense_url}/?refresh=${encodeURIComponent(account)}`), 800);
    return;
  }
  const msg = { finished: "Done. Chrome was closed so it keeps what it saved.", closed: "The browser was closed.", timed_out: "Time ran out, so the browser was closed." }[st.result];
  note(msg || "", st.result === "finished" ? "ok" : "");
  $("start").textContent = "Start the browser";
}

async function connect() {
  const { password } = await api("GET", "/api/login/session");
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/vnc";
  rfb = new RFB($("screen"), url, { credentials: { password }, shared: true, wsProtocols: ["binary"] });
  rfb.scaleViewport = true;
  rfb.resizeSession = false;
  rfb.background = "#000";
  rfb.addEventListener("connect", () => note("Connected. Tap the page to click; drag to scroll."));
  rfb.addEventListener("credentialsrequired", () => rfb && rfb.sendCredentials({ password }));
  rfb.addEventListener("disconnect", () => { rfb = null; poll(); });
}

async function poll() {
  try {
    const st = await api("GET", "/api/login");
    if (st.state === "running" && st.account === account) {
      watched = true;
      show(true); startClock(st.remaining);
      if (!rfb) await connect();
    } else if (st.state === "running") {
      show(false); note(`Another login (${st.account}) is running. Stop it first.`, "err");
    } else if (st.result && watched) finished(st);
  } catch (e) { note(e.message, "err"); }
}

$("start").addEventListener("click", async () => {
  $("start").disabled = true; note("Starting the browser…");
  try {
    const st = await api("POST", `/api/login/${encodeURIComponent(account)}/start`);
    watched = true;
    show(true); startClock(st.remaining); await connect();
  } catch (e) { note(e.message, "err"); show(false); }
  finally { $("start").disabled = false; }
});

$("stop").addEventListener("click", async () => {
  $("stop").disabled = true;
  try { finished(await api("POST", "/api/login/stop")); } catch (e) { note(e.message, "err"); }
  finally { $("stop").disabled = false; }
});

// Typing on a phone: noVNC has no soft keyboard of its own, so a hidden input collects what the keyboard types and the
// difference from what was there before is sent as key presses (this also copes with autocorrect and composition).
const kb = $("kb");
let before = "";
const keysym = (ch) => { const c = ch.codePointAt(0); return c < 0x100 ? c : 0x01000000 + c; };
function typeChars(text) { if (rfb) for (const ch of text) rfb.sendKey(keysym(ch), null); }
const BACKSPACE = 0xff08, ENTER = 0xff0d, TAB = 0xff09;
kb.addEventListener("input", () => {
  const now = kb.value;
  let i = 0;
  while (i < before.length && i < now.length && before[i] === now[i]) i++;
  if (rfb) {
    for (let n = before.length; n > i; n--) rfb.sendKey(BACKSPACE, null);
    typeChars(now.slice(i));
  }
  before = now;
  if (now.length > 200) { kb.value = ""; before = ""; }
});
kb.addEventListener("keydown", (e) => {
  const special = { Enter: ENTER, Tab: TAB, Backspace: before.length ? null : BACKSPACE };
  if (e.key in special && special[e.key] !== null) { e.preventDefault(); if (rfb) rfb.sendKey(special[e.key], null); }
});
$("keyboard").addEventListener("click", () => { kb.value = ""; before = ""; kb.focus(); });

$("pastebtn").addEventListener("click", () => { $("paste").classList.add("on"); $("pastetext").focus(); });
$("pasteclose").addEventListener("click", () => { $("pastetext").value = ""; $("paste").classList.remove("on"); });
$("typeit").addEventListener("click", () => {
  typeChars($("pastetext").value);
  $("pastetext").value = ""; $("paste").classList.remove("on");
});

$("title").textContent = account ? `Log in: ${account}` : "Log in by hand";
$("what").textContent = account ? `You will sign in to ${account}.` : "No account chosen.";
if (!account) { $("start").disabled = true; }
poll();
setInterval(() => { if (!rfb) poll(); }, 5000);
