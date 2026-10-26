"""Local page of the session log. The Temporal monitor is unchanged.

The panel button Session log opens http://localhost:8244. Nothing opens
the browser on its own. The page reads the sanitized log and refreshes itself.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from houdini_wizard.userlog import PAGE_PORT, read_events

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Houdini wizard · Your cards</title>
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
    --ink: #f3eadc;
    --muted: #b7aa96;
    --bg: #14110e;
    --panel: #1c1814;
    --line: #3a3128;
    --amber: #e0a45a;
    --work: #e4def8; --work-bg: #2a2838;
    --ok: #c8efd4; --ok-bg: #1c3326;
    --back: #d4e6fa; --back-bg: #1c2c40;
    --off: #f3e0b8; --off-bg: #3a3224;
    --bad: #f6d0c8; --bad-bg: #3c2222;
    --here: #e7dcc8; --here-bg: #2c2824;
    --glow: rgba(224,164,90,0.16);
  }
  html[data-theme="light"] {
    --ink: #2c261f;
    --muted: #6d6256;
    --bg: #f6f1e8;
    --panel: #fffdf8;
    --line: #e4d9cb;
    --amber: #8a5a22;
    --work: #34315f; --work-bg: #e6e4f2;
    --ok: #1d5c32; --ok-bg: #dcecde;
    --back: #1a4578; --back-bg: #d9e6f5;
    --off: #7a5410; --off-bg: #f3e6cf;
    --bad: #8a2e24; --bad-bg: #f6dcd6;
    --here: #5c4a32; --here-bg: #efe6d8;
    --glow: rgba(138,90,34,0.12);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    color: var(--ink);
    background:
      radial-gradient(1200px 500px at 10% -10%, var(--glow), transparent 55%),
      var(--bg);
    font-family: "Palatino Linotype", Palatino, "Iowan Old Style", Georgia, serif;
  }
  main { max-width: 760px; margin: 0 auto; padding: 48px 28px 80px; }
  header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }
  h1 { font-weight: 500; font-size: 42px; letter-spacing: -0.03em; margin: 0; }
  .lede { color: var(--muted); margin: 8px 0 0; font-size: 18px; max-width: 36rem; }
  .tools { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
  .theme {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 6px 12px;
    cursor: pointer;
  }
  .theme:hover { border-color: var(--amber); color: var(--amber); }
  .dev {
    color: var(--amber);
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    letter-spacing: 0.04em;
    text-decoration: none;
    border-bottom: 1px solid color-mix(in srgb, var(--amber) 45%, transparent);
    padding-bottom: 2px;
    white-space: nowrap;
  }
  ol { list-style: none; margin: 36px 0 0; padding: 0; }
  li {
    display: grid;
    grid-template-columns: 92px 16px 1fr;
    gap: 0 14px;
  }
  time {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    color: var(--muted);
    padding-top: 14px;
    text-align: right;
  }
  .rail { position: relative; }
  .rail::before {
    content: "";
    position: absolute;
    left: 6px; top: 0; bottom: 0;
    width: 2px;
    background: linear-gradient(var(--amber), rgba(224,164,90,0.15));
  }
  .dot {
    position: absolute;
    left: 1px; top: 18px;
    width: 12px; height: 12px;
    border-radius: 50%;
    background: var(--amber);
    box-shadow: 0 0 0 4px var(--bg);
  }
  article {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px 16px 16px;
    margin: 0 0 14px;
  }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pill {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 4px 8px;
    border-radius: 999px;
  }
  .working { color: var(--work); background: var(--work-bg); }
  .online { color: var(--ok); background: var(--ok-bg); }
  .restored { color: var(--back); background: var(--back-bg); }
  .offline { color: var(--off); background: var(--off-bg); }
  .error { color: var(--bad); background: var(--bad-bg); }
  .local { color: var(--here); background: var(--here-bg); }
  h2 { font-size: 22px; font-weight: 600; margin: 10px 0 0; letter-spacing: -0.02em; }
  .path, p { color: var(--muted); margin: 4px 0 0; font-size: 16px; }
  dl {
    display: grid;
    grid-template-columns: 108px 1fr;
    gap: 6px 14px;
    margin: 14px 0 0;
  }
  dt {
    color: var(--muted);
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding-top: 3px;
  }
  dd { margin: 0; color: var(--ink); font-size: 16px; }
  blockquote {
    margin: 14px 0 0;
    padding: 2px 0 2px 12px;
    border-left: 2px solid var(--amber);
    color: var(--ink);
    font-size: 17px;
  }
  .cook {
    margin-top: 12px;
    background: var(--bad-bg);
    color: var(--bad);
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 15px;
  }
  .file { color: var(--muted); font-size: 14px; }
  .mark {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-right: 6px;
  }
  .empty {
    margin-top: 48px;
    color: var(--muted);
    font-size: 20px;
  }
  .menu { display: flex; gap: 8px; }
  .theme[aria-pressed="true"] { border-color: var(--amber); color: var(--amber); }
  body.view-model main { max-width: 920px; }
  .band { font-size: 22px; font-weight: 600; margin: 32px 0 0; letter-spacing: -0.02em; }
  .stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin-top: 14px;
  }
  .stat {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 14px 14px;
  }
  .stat b {
    display: block;
    font-size: 28px;
    font-weight: 560;
    letter-spacing: -0.03em;
  }
  .stat b.compact { font-size: 18px; line-height: 1.25; }
  .stat span {
    display: block;
    margin-top: 4px;
    color: var(--muted);
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .note { color: var(--muted); font-size: 15px; margin: 14px 0 0; max-width: 40rem; }
  #jobs { margin-top: 22px; display: grid; gap: 14px; }
  #jobs article { margin: 0; }
  @media (max-width: 720px) {
    .stats { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 640px) {
    li { grid-template-columns: 16px 1fr; }
    time { grid-column: 2; text-align: left; padding-top: 0; }
    .rail { grid-row: 1 / span 2; }
  }
  @media (prefers-reduced-motion: reduce) {
    * { scroll-behavior: auto; }
  }
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Your cards</h1>
      <p class="lede" id="lede">Each node you open, one card. The parameter, the heading, the quote, and any error, warning, or message are on that card.</p>
    </div>
    <div class="tools">
      <div class="menu" role="tablist" aria-label="Session">
        <button type="button" id="view-cards" class="theme" role="tab">Cards</button>
        <button type="button" id="view-model" class="theme" role="tab">Model</button>
      </div>
      <button type="button" id="theme" class="theme">Light</button>
      <a class="dev" href="http://localhost:8233">Developer monitor</a>
      <a class="dev" href="https://entire.com/gh/AbisoyeOnanuga/houdini-wizard/session/e96d75ea-ea02-4990-b94a-81678a4c1465">Read more about the agent session behind this code</a>
    </div>
  </header>
  <p class="empty" id="empty">Open the tool on a node. Saved cards show up here.</p>
  <section id="summary" hidden></section>
  <ol id="flow"></ol>
  <div id="jobs" hidden></div>
</main>
<script>
const flow = document.getElementById("flow");
const jobs = document.getElementById("jobs");
const summary = document.getElementById("summary");
const empty = document.getElementById("empty");
const lede = document.getElementById("lede");
const themeButton = document.getElementById("theme");
const cardsButton = document.getElementById("view-cards");
const modelButton = document.getElementById("view-model");
let view = "cards";
try { view = localStorage.getItem("houdini-wizard-session-view") || "cards"; } catch (err) {}
if (view !== "model") view = "cards";
let lastBody = "";
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
function markMenu() {
  const model = view === "model";
  document.body.classList.toggle("view-model", model);
  document.querySelector("h1").textContent = model ? "Model" : "Your cards";
  cardsButton.setAttribute("aria-pressed", model ? "false" : "true");
  modelButton.setAttribute("aria-pressed", model ? "true" : "false");
  lede.textContent = model
    ? "Every time Gemma runs, and every time a heading is quoted without asking. Tokens, time, and the loaded model are on this page. The developer monitor stays the workflow list."
    : "Each node you open, one card. The parameter, the heading, the quote, and any error, warning, or message are on that card.";
}
function choose(next) {
  view = next === "model" ? "model" : "cards";
  try { localStorage.setItem("houdini-wizard-session-view", view); } catch (err) {}
  lastBody = "";
  markMenu();
  refresh(true);
}
cardsButton.addEventListener("click", function () { choose("cards"); });
modelButton.addEventListener("click", function () { choose("model"); });
markMenu();
function clock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
function pill(className, text) {
  const span = document.createElement("span");
  span.className = "pill " + className;
  span.textContent = text;
  return span;
}
function duration(ms) {
  if (ms >= 1000) {
    const seconds = ms / 1000;
    return (Math.round(seconds * 10) / 10).toString().replace(/\\.0$/, "") + " s";
  }
  return ms + " ms";
}
function modelFacts(list, usage) {
  if (!usage || typeof usage !== "object") return;
  if (usage.pending) {
    fact(list, "Model", usage.reason || "Gemma is choosing a heading.");
    return;
  }
  if (usage.used === false) {
    fact(list, "Model", usage.reason || "Gemma was not asked.");
    if (typeof usage.save_ms === "number") fact(list, "Round trip", duration(usage.save_ms));
    return;
  }
  if (usage.used !== true) return;
  const who = [usage.model, usage.task].filter(Boolean).join(" · ");
  fact(list, "Model", usage.reason || who || "Gemma");
  if (usage.reason && usage.model) fact(list, "Ran", usage.model);
  if (usage.skill) fact(list, "Skill", usage.skill);
  if (typeof usage.prompt_tokens !== "number" && typeof usage.answer_tokens !== "number") {
    fact(list, "Tokens", "Ollama did not report token counts.");
  }
  tokenLine(list, "In", usage.prompt_tokens, usage.prompt_ms);
  tokenLine(list, "Out", usage.answer_tokens, usage.answer_ms);
  if (typeof usage.total_ms === "number") fact(list, "Model time", duration(usage.total_ms));
  if (usage.load_ms) fact(list, "Model load", duration(usage.load_ms));
  const memory = memoryLine(usage);
  if (memory) fact(list, "Memory", memory);
  if (typeof usage.attempt === "number") fact(list, "Attempt", String(usage.attempt));
  if (typeof usage.save_ms === "number") fact(list, "Round trip", duration(usage.save_ms));
}
function fact(list, label, text) {
  if (!text) return;
  const term = document.createElement("dt");
  term.textContent = label;
  const value = document.createElement("dd");
  value.textContent = text;
  list.append(term, value);
}
function entry(item) {
  const li = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = item.time || "";
  time.textContent = clock(item.time);
  const rail = document.createElement("div");
  rail.className = "rail";
  const dot = document.createElement("div");
  dot.className = "dot";
  rail.appendChild(dot);
  const card = document.createElement("article");
  const row = document.createElement("div");
  row.className = "row";
  row.appendChild(pill(item.state || "working", item.title || ""));
  if (item.source) row.appendChild(pill("local", item.source));
  const name = document.createElement("h2");
  name.textContent = item.node_label || "This session";
  const path = document.createElement("div");
  path.className = "path";
  path.textContent = item.node || "";
  card.append(row, name, path);
  const facts = document.createElement("dl");
  fact(facts, "Parameter", item.parameter || "");
  fact(facts, "Heading", item.heading || "");
  fact(facts, "Situation", item.situation || "");
  modelFacts(facts, item.usage || {});
  if (facts.childNodes.length) card.appendChild(facts);
  if (item.quote) {
    const quote = document.createElement("blockquote");
    quote.textContent = item.quote;
    card.appendChild(quote);
  }
  if (item.error) {
    const cook = document.createElement("p");
    cook.className = "cook";
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = item.status_label || "On this node";
    cook.append(mark, document.createTextNode(item.error));
    card.appendChild(cook);
  }
  const names = Array.isArray(item.headings) ? item.headings.filter(Boolean) : [];
  if (names.length) {
    const file = document.createElement("p");
    file.className = "file";
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = "In this file";
    file.append(mark, document.createTextNode(names.join(", ")));
    card.appendChild(file);
  }
  if (item.detail) {
    const detail = document.createElement("p");
    detail.textContent = item.detail;
    card.appendChild(detail);
  }
  li.append(time, rail, card);
  return li;
}
function speed(tokens, ms) {
  if (typeof tokens !== "number" || typeof ms !== "number" || ms <= 0) return "";
  const rate = tokens / (ms / 1000);
  if (!isFinite(rate)) return "";
  return Math.round(rate) + " tok/s";
}
function mem(bytes) {
  if (typeof bytes !== "number") return "";
  if (bytes >= 1e9) return (Math.round(bytes / 1e8) / 10).toString().replace(/\\.0$/, "") + " GB";
  if (bytes >= 1e6) return Math.round(bytes / 1e6) + " MB";
  return bytes + " B";
}
function memoryLine(usage) {
  const parts = [];
  if (typeof usage.model_bytes === "number") parts.push(mem(usage.model_bytes) + " loaded");
  if (typeof usage.vram_bytes === "number") parts.push(mem(usage.vram_bytes) + " in video memory");
  return parts.join(", ");
}
function tokenLine(list, label, tokens, ms) {
  if (typeof tokens !== "number" && typeof ms !== "number") return;
  const parts = [];
  if (typeof tokens === "number") parts.push(tokens + " tokens");
  if (typeof ms === "number") parts.push(duration(ms));
  const rate = speed(typeof tokens === "number" ? tokens : null, typeof ms === "number" ? ms : null);
  if (rate) parts.push(rate);
  fact(list, label, parts.join(" · "));
}
function wasReplay(item) {
  return !!(item.usage && (item.usage.replayed || item.title === "Restored"));
}
function fresh(item) {
  return item.usage && item.usage.used === true && !wasReplay(item);
}
function total(rows, key, onlyFresh) {
  let sum = 0;
  let any = false;
  rows.forEach(function (item) {
    const usage = item.usage || {};
    if (onlyFresh && !fresh(item)) return;
    if (!onlyFresh && wasReplay(item) && key !== "save_ms") return;
    const number = usage[key];
    if (typeof number !== "number") return;
    sum += number;
    any = true;
  });
  return any ? sum : null;
}
function peak(rows, key) {
  let best = null;
  rows.forEach(function (item) {
    const number = item.usage && item.usage[key];
    if (typeof number === "number" && (best === null || number > best)) best = number;
  });
  return best;
}
function addStat(grid, value, label) {
  const tile = document.createElement("div");
  tile.className = "stat";
  const strong = document.createElement("b");
  strong.textContent = value;
  if (String(value).length > 14) strong.className = "compact";
  const span = document.createElement("span");
  span.textContent = label;
  tile.append(strong, span);
  grid.appendChild(tile);
}
function finished(reason) {
  if (reason === "stop") return "Finished";
  if (reason === "length") return "Stopped at the length limit";
  return reason || "";
}
function jobState(item) {
  const usage = item.usage || {};
  if (usage.pending) return "working";
  if (wasReplay(item)) return "restored";
  if (usage.used === true) return "online";
  if (/did not answer/i.test(usage.reason || "")) return "error";
  return "local";
}
function jobTitle(item) {
  const usage = item.usage || {};
  if (usage.pending) return "Choosing";
  if (wasReplay(item)) return "Opened again";
  if (usage.used === true) return "Ran";
  if (/did not answer/i.test(usage.reason || "")) return "No answer";
  return "Not asked";
}
function houdiniSide(item) {
  const parts = [];
  if (item.parameter) parts.push(item.parameter);
  if (item.situation) parts.push(item.situation);
  if (item.status_label) parts.push(item.status_label);
  return parts.join(" · ");
}
function job(item) {
  const usage = item.usage || {};
  const card = document.createElement("article");
  const row = document.createElement("div");
  row.className = "row";
  row.appendChild(pill(jobState(item), jobTitle(item)));
  if (item.source) row.appendChild(pill("local", item.source));
  const name = document.createElement("h2");
  name.textContent = item.node_label || usage.task || "This session";
  const path = document.createElement("div");
  path.className = "path";
  path.textContent = item.node || "";
  card.append(row, name, path);
  const facts = document.createElement("dl");
  fact(facts, "Action", usage.task || "");
  fact(facts, "Skill", usage.skill || "");
  fact(facts, "Model", usage.model || "");
  fact(facts, "What happened", usage.reason || item.detail || "");
  fact(facts, "Houdini", houdiniSide(item));
  tokenLine(facts, "In", usage.prompt_tokens, usage.prompt_ms);
  tokenLine(facts, "Out", usage.answer_tokens, usage.answer_ms);
  if (usage.load_ms) fact(facts, "Model load", duration(usage.load_ms));
  if (typeof usage.total_ms === "number") fact(facts, "Model time", duration(usage.total_ms));
  if (typeof usage.save_ms === "number") fact(facts, "Houdini round trip", duration(usage.save_ms));
  if (typeof usage.attempt === "number") fact(facts, "Attempt", String(usage.attempt));
  const memory = memoryLine(usage);
  if (memory) fact(facts, "Memory", memory);
  if (usage.done_reason) fact(facts, "Stop", finished(usage.done_reason));
  if (wasReplay(item)) fact(facts, "Counted", "Tokens stay on the first save. This open did not ask Gemma again.");
  if (facts.childNodes.length) card.appendChild(facts);
  const when = document.createElement("p");
  when.className = "file";
  when.textContent = clock(item.time);
  card.appendChild(when);
  return card;
}
function renderSummary(rows) {
  summary.replaceChildren();
  const title = document.createElement("h2");
  title.className = "band";
  title.textContent = "This session";
  const grid = document.createElement("div");
  grid.className = "stats";
  const calls = rows.filter(fresh);
  addStat(grid, String(calls.length), "Model calls");
  const inn = total(rows, "prompt_tokens", true);
  const out = total(rows, "answer_tokens", true);
  if (inn !== null) addStat(grid, String(inn), "Tokens in");
  if (out !== null) addStat(grid, String(out), "Tokens out");
  const modelMs = total(rows, "total_ms", true);
  if (modelMs !== null) addStat(grid, duration(modelMs), "Model time");
  const inSpeed = speed(inn, total(rows, "prompt_ms", true));
  const outSpeed = speed(out, total(rows, "answer_ms", true));
  if (inSpeed) addStat(grid, inSpeed, "Reading the prompt");
  if (outSpeed) addStat(grid, outSpeed, "Writing the answer");
  const trip = total(rows, "save_ms", false);
  if (trip !== null) addStat(grid, duration(trip), "Houdini round trip");
  const ram = peak(rows, "model_bytes");
  const vram = peak(rows, "vram_bytes");
  if (ram !== null || vram !== null) {
    const text = [ram !== null ? mem(ram) + " loaded" : "", vram !== null ? mem(vram) + " video" : ""].filter(Boolean).join(" · ");
    addStat(grid, text, "Model memory");
  }
  const skipped = rows.filter(function (item) {
    return item.usage && item.usage.used === false && !wasReplay(item);
  }).length;
  const again = rows.filter(wasReplay).length;
  const failed = rows.filter(function (item) {
    return item.usage && item.usage.used === false && !wasReplay(item) && /did not answer/i.test(item.usage.reason || "");
  }).length;
  if (skipped) addStat(grid, String(skipped), "Gemma not asked");
  if (again) addStat(grid, String(again), "Opened again");
  if (failed) addStat(grid, String(failed), "No answer");
  const note = document.createElement("p");
  note.className = "note";
  const tasks = {};
  calls.forEach(function (item) {
    const name = item.usage.task || "model call";
    tasks[name] = (tasks[name] || 0) + 1;
  });
  const breakdown = Object.keys(tasks).map(function (name) { return tasks[name] + " " + name; }).join(", ");
  note.textContent = (breakdown ? breakdown + ". " : "") + "Memory is the model Ollama has loaded. This page does not sample CPU, and it does not put a price on a token.";
  summary.append(title, grid, note);
}
function renderCards(rows) {
  summary.hidden = true;
  jobs.hidden = true;
  flow.hidden = false;
  const cards = rows.filter(function (item) { return item.title !== "Model"; }).slice().reverse();
  empty.hidden = cards.length > 0;
  empty.textContent = "Open the tool on a node. Saved cards show up here.";
  flow.replaceChildren(...cards.map(entry));
}
function renderModel(rows) {
  flow.hidden = true;
  const tracked = rows.filter(function (item) { return item.usage; });
  empty.hidden = tracked.length > 0;
  empty.textContent = "Open a node. Model calls, and quotes that skip Gemma, show up here.";
  summary.hidden = tracked.length === 0;
  jobs.hidden = tracked.length === 0;
  if (!tracked.length) {
    summary.replaceChildren();
    jobs.replaceChildren();
    return;
  }
  renderSummary(rows);
  const ordered = tracked.slice().reverse();
  jobs.replaceChildren(...ordered.map(job));
}
async function refresh(reset) {
  let text = "";
  try {
    const response = await fetch("/events", { cache: "no-store" });
    text = await response.text();
  } catch (err) {
    return;
  }
  if (!reset && text === lastBody) return;
  lastBody = text;
  let rows = [];
  try { rows = JSON.parse(text); } catch (err) { return; }
  if (!Array.isArray(rows)) return;
  const y = reset ? 0 : window.scrollY;
  if (view === "model") renderModel(rows);
  else renderCards(rows);
  markMenu();
  window.scrollTo(0, y);
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/events":
            body = json.dumps(read_events()).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path in {"/", "/index.html"}:
            self._send(200, "text/html; charset=utf-8", _PAGE.encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PAGE_PORT), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
