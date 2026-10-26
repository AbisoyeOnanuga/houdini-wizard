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
      <p class="lede">Each node you open, one card. The parameter, the heading, the quote, and any error, warning, or message are on that card.</p>
    </div>
    <div class="tools">
      <button type="button" id="theme" class="theme">Light</button>
      <a class="dev" href="http://localhost:8233">Developer monitor</a>
    </div>
  </header>
  <p class="empty" id="empty">Open the tool on a node. Saved cards show up here.</p>
  <ol id="flow"></ol>
</main>
<script>
const flow = document.getElementById("flow");
const empty = document.getElementById("empty");
const themeButton = document.getElementById("theme");
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
  if (typeof usage.prompt_tokens === "number" || typeof usage.answer_tokens === "number") {
    const parts = [];
    if (typeof usage.prompt_tokens === "number") parts.push(usage.prompt_tokens + " prompt");
    if (typeof usage.answer_tokens === "number") parts.push(usage.answer_tokens + " answer");
    fact(list, "Tokens", parts.join(", "));
  } else {
    fact(list, "Tokens", "Ollama did not report token counts.");
  }
  if (typeof usage.total_ms === "number") fact(list, "Model time", duration(usage.total_ms));
  if (usage.load_ms) fact(list, "Model load", duration(usage.load_ms));
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
async function refresh() {
  let rows = [];
  try {
    const response = await fetch("/events", { cache: "no-store" });
    rows = await response.json();
  } catch (err) {
    return;
  }
  empty.hidden = rows.length > 0;
  flow.replaceChildren(...rows.map(entry));
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
