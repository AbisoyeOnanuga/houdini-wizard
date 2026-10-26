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
<style>
  :root {
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
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    color: var(--ink);
    background:
      radial-gradient(1200px 500px at 10% -10%, rgba(224,164,90,0.16), transparent 55%),
      var(--bg);
    font-family: "Palatino Linotype", Palatino, "Iowan Old Style", Georgia, serif;
  }
  main { max-width: 760px; margin: 0 auto; padding: 48px 28px 80px; }
  header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }
  h1 { font-weight: 500; font-size: 42px; letter-spacing: -0.03em; margin: 0; }
  .lede { color: var(--muted); margin: 8px 0 0; font-size: 18px; max-width: 36rem; }
  .dev {
    color: var(--amber);
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    letter-spacing: 0.04em;
    text-decoration: none;
    border-bottom: 1px solid rgba(224,164,90,0.45);
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
      <p class="lede">Each node you open with the tool, in the order you opened it.</p>
    </div>
    <a class="dev" href="http://localhost:8233">Developer monitor</a>
  </header>
  <p class="empty" id="empty">Open the tool on a node. Saved cards show up here.</p>
  <ol id="flow"></ol>
</main>
<script>
const flow = document.getElementById("flow");
const empty = document.getElementById("empty");
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
  const label = item.node_label || "This session";
  name.textContent = item.heading ? label + " · " + item.heading : label;
  const path = document.createElement("div");
  path.className = "path";
  path.textContent = item.node || "";
  const detail = document.createElement("p");
  detail.textContent = item.detail || "";
  card.append(row, name, path, detail);
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
