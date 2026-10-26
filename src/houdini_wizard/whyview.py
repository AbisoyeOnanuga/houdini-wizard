"""Local page for searching why this tool exists.

The Houdini shelf does not open it. A reader starts it from the repository.
The look matches the session log so the two pages feel like one tool.
"""

from __future__ import annotations

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Houdini wizard · Why this code exists</title>
<script>
(function () {
  var theme = "dark";
  try { theme = localStorage.getItem("houdini-wizard-session-theme") || "dark"; } catch (err) {}
  if (theme !== "light") theme = "dark";
  document.documentElement.setAttribute("data-theme", theme);
})();
</script>
<style>
  :root, html[data-theme="dark"] {
    --ink: #f3eadc; --muted: #b7aa96; --bg: #14110e; --panel: #1c1814;
    --line: #3a3128; --amber: #e0a45a; --field: #100e0c;
    --ok: #c8efd4; --ok-bg: #1c3326; --here: #e7dcc8; --here-bg: #2c2824;
    --glow: rgba(224,164,90,0.16);
  }
  html[data-theme="light"] {
    --ink: #2c261f; --muted: #6d6256; --bg: #f6f1e8; --panel: #fffdf8;
    --line: #e4d9cb; --amber: #8a5a22; --field: #fff;
    --ok: #1d5c32; --ok-bg: #dcecde; --here: #5c4a32; --here-bg: #efe6d8;
    --glow: rgba(138,90,34,0.12);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; color: var(--ink);
    background: radial-gradient(1200px 500px at 10% -10%, var(--glow), transparent 55%), var(--bg);
    font-family: "Palatino Linotype", Palatino, "Iowan Old Style", Georgia, serif;
  }
  main { max-width: 760px; margin: 0 auto; padding: 48px 28px 80px; }
  header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }
  h1 { font-weight: 500; font-size: 42px; letter-spacing: -0.03em; margin: 0; }
  h2 { font-size: 22px; font-weight: 600; margin: 28px 0 0; letter-spacing: -0.02em; }
  .lede { color: var(--muted); margin: 8px 0 0; font-size: 18px; max-width: 36rem; }
  .tools { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
  .theme, button.ask, .chip {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px; letter-spacing: 0.04em;
    color: var(--ink); background: var(--panel);
    border: 1px solid var(--line); border-radius: 999px;
    padding: 6px 12px; cursor: pointer;
  }
  .theme { text-transform: uppercase; letter-spacing: 0.06em; }
  .theme:hover, button.ask:hover, .chip:hover { border-color: var(--amber); color: var(--amber); }
  a.dev {
    color: var(--amber); font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px; letter-spacing: 0.04em; text-decoration: none;
    border-bottom: 1px solid color-mix(in srgb, var(--amber) 45%, transparent); padding-bottom: 2px;
  }
  form { display: flex; gap: 8px; margin-top: 28px; }
  input[type="search"] {
    flex: 1; font: 18px/1.4 Georgia, serif; color: var(--ink);
    background: var(--field); border: 1px solid var(--line); border-radius: 12px;
    padding: 12px 14px;
  }
  input[type="search"]:focus { outline: 2px solid var(--amber); border-color: transparent; }
  button.ask { border-radius: 12px; padding: 0 16px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .chip { text-transform: none; letter-spacing: 0; font-family: Georgia, serif; font-size: 15px; }
  .note { color: var(--muted); font-size: 15px; margin-top: 14px; }
  article {
    background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
    padding: 14px 16px 16px; margin-top: 12px;
  }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pill {
    font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px;
    letter-spacing: 0.06em; text-transform: uppercase; padding: 4px 8px; border-radius: 999px;
  }
  .local { color: var(--here); background: var(--here-bg); }
  .online { color: var(--ok); background: var(--ok-bg); }
  .path, .file { color: var(--muted); margin: 4px 0 0; font-size: 15px; }
  dl { display: grid; grid-template-columns: 108px 1fr; gap: 6px 14px; margin: 14px 0 0; }
  dt {
    color: var(--muted); font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; padding-top: 3px;
  }
  dd { margin: 0; font-size: 16px; }
  .open {
    margin-top: 12px; background: transparent; color: var(--amber);
    border: 0; padding: 0; cursor: pointer;
    font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; letter-spacing: 0.04em;
  }
  .error { color: var(--amber); margin-top: 18px; font-size: 17px; }
  @media (max-width: 640px) {
    form { flex-direction: column; }
    button.ask { padding: 10px 16px; }
  }
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Why this code exists</h1>
      <p class="lede" id="lede">Search the agent session that built this shelf. The shelf does not open this page.</p>
    </div>
    <div class="tools">
      <button type="button" id="theme" class="theme">Light</button>
      <a class="dev" id="dash" href="https://entire.com">On entire.com</a>
    </div>
  </header>
  <form id="find">
    <input id="q" type="search" name="q" placeholder="Ask why a piece of this tool exists" aria-label="Question">
    <button class="ask" type="submit">Search</button>
  </form>
  <div class="chips" id="chips"></div>
  <p class="note" id="status"></p>
  <div id="out"></div>
</main>
<script>
const QUESTIONS = [
  "why a named heading skips Gemma",
  "why the help card is stored in Temporal",
  "why the window stays where the artist moved it"
];
const q = document.getElementById("q");
const out = document.getElementById("out");
const status = document.getElementById("status");
const themeButton = document.getElementById("theme");
const chips = document.getElementById("chips");
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const light = theme === "light";
  themeButton.textContent = light ? "Dark" : "Light";
  themeButton.setAttribute("aria-pressed", light ? "true" : "false");
  try { localStorage.setItem("houdini-wizard-session-theme", theme); } catch (err) {}
}
applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
themeButton.addEventListener("click", function () {
  const current = document.documentElement.getAttribute("data-theme");
  applyTheme(current === "light" ? "dark" : "light");
});
QUESTIONS.forEach(function (text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "chip";
  button.textContent = text;
  button.addEventListener("click", function () {
    q.value = text;
    search(text);
  });
  chips.appendChild(button);
});
function pill(className, text) {
  const span = document.createElement("span");
  span.className = "pill " + className;
  span.textContent = text;
  return span;
}
function fact(list, label, text) {
  if (!text) return;
  const term = document.createElement("dt");
  term.textContent = label;
  const value = document.createElement("dd");
  value.textContent = text;
  list.append(term, value);
}
function clock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
function article() {
  const card = document.createElement("article");
  out.appendChild(card);
  return card;
}
async function search(question) {
  status.textContent = "Searching the recorded session…";
  out.replaceChildren();
  let payload = {};
  try {
    const response = await fetch("/search?q=" + encodeURIComponent(question), { cache: "no-store" });
    payload = await response.json();
  } catch (err) {
    status.textContent = "This page could not reach the search on this computer.";
    return;
  }
  if (payload.dashboard) document.getElementById("dash").href = payload.dashboard;
  if (payload.error) {
    status.textContent = payload.error;
    return;
  }
  const hits = Array.isArray(payload.hits) ? payload.hits : [];
  const points = Array.isArray(payload.checkpoints) ? payload.checkpoints : [];
  status.textContent = points.length
    ? "These checkpoints are the recorded reasons. Open one to see the files and the agent tokens."
    : "No checkpoint matched that question.";
  points.forEach(function (item) { out.appendChild(pointCard(item)); });
  if (hits.length && !points.length) hits.forEach(function (item) { out.appendChild(hitCard(item)); });
}
function pointCard(item) {
  const card = document.createElement("article");
  const row = document.createElement("div");
  row.className = "row";
  row.appendChild(pill("online", "Checkpoint"));
  if (item.agent) row.appendChild(pill("local", item.agent));
  const name = document.createElement("h2");
  name.textContent = item.message || item.id;
  const path = document.createElement("div");
  path.className = "path";
  path.textContent = [item.id, clock(item.date)].filter(Boolean).join(" · ");
  card.append(row, name, path);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "open";
  button.textContent = "Read this checkpoint";
  button.addEventListener("click", function () { openPoint(item.id, card); });
  card.appendChild(button);
  return card;
}
function hitCard(item) {
  const card = document.createElement("article");
  const row = document.createElement("div");
  row.className = "row";
  row.appendChild(pill("local", item.type || "Hit"));
  const name = document.createElement("h2");
  name.textContent = item.title || item.id;
  const path = document.createElement("div");
  path.className = "path";
  path.textContent = [item.author, clock(item.date), item.branch].filter(Boolean).join(" · ");
  card.append(row, name, path);
  return card;
}
async function openPoint(id, card) {
  let payload = {};
  try {
    const response = await fetch("/checkpoint?id=" + encodeURIComponent(id), { cache: "no-store" });
    payload = await response.json();
  } catch (err) {
    return;
  }
  const prior = card.querySelector("dl");
  if (prior) prior.remove();
  if (payload.error) {
    const note = document.createElement("p");
    note.className = "file";
    note.textContent = payload.error;
    card.appendChild(note);
    return;
  }
  const facts = document.createElement("dl");
  fact(facts, "Branch", payload.branch || "");
  fact(facts, "Files", (payload.files || []).join(", "));
  const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  sessions.forEach(function (session) {
    const who = [session.agent, session.model].filter(Boolean).join(" · ");
    fact(facts, "Agent", who);
    const tokens = [];
    if (typeof session.input_tokens === "number") tokens.push(session.input_tokens + " in");
    if (typeof session.output_tokens === "number") tokens.push(session.output_tokens + " out");
    fact(facts, "Agent tokens", tokens.join(", "));
  });
  if (payload.commit_url) {
    const term = document.createElement("dt");
    term.textContent = "Commit";
    const value = document.createElement("dd");
    const link = document.createElement("a");
    link.className = "dev";
    link.href = payload.commit_url;
    link.textContent = "Open this checkpoint on entire.com";
    value.appendChild(link);
    facts.append(term, value);
  }
  card.appendChild(facts);
}
document.getElementById("find").addEventListener("submit", function (event) {
  event.preventDefault();
  search(q.value.trim());
});
fetch("/home", { cache: "no-store" }).then(function (response) { return response.json(); }).then(function (payload) {
  if (payload.dashboard) document.getElementById("dash").href = payload.dashboard;
}).catch(function () {});
</script>
</body>
</html>
"""
