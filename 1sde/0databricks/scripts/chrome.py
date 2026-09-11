"""Drive the user's own Chrome over the DevTools protocol (debug port 9222).

This is the fallback path for the `chrome` skill when no DevTools MCP server is
connected to the session: the MCP wraps this same protocol, so anything it can
do, this can. It attaches to the user's real browser profile — real cookies,
real logins — which is the entire point and the entire risk. See the skill's
rules before using it.

    python scripts/chrome.py tabs
    python scripts/chrome.py find <substring>
    python scripts/chrome.py goto <tab-id-prefix> <url>
    python scripts/chrome.py eval <tab-id-prefix> <javascript>
    python scripts/chrome.py click <tab-id-prefix> <visible-text>  # real mouse event
    python scripts/chrome.py text <tab-id-prefix>           # innerText of the page
    python scripts/chrome.py shot <tab-id-prefix> <out.png>
    python scripts/chrome.py new <url>
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.request

import websocket

PORT = 9222
BASE = f"http://localhost:{PORT}"


def _tabs() -> list[dict]:
    with urllib.request.urlopen(f"{BASE}/json", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def _find(prefix: str) -> dict:
    tabs = _tabs()
    matches = [
        t
        for t in tabs
        if t["id"].lower().startswith(prefix.lower())
        or prefix.lower() in (t.get("title") or "").lower()
        or prefix.lower() in (t.get("url") or "").lower()
    ]
    if not matches:
        sys.exit(f"no tab matches {prefix!r}. Run `tabs` to list them.")
    if len(matches) > 1:
        for t in matches:
            print(f"  {t['id'][:8]} | {(t.get('title') or '')[:60]}", file=sys.stderr)
        sys.exit(f"{len(matches)} tabs match {prefix!r} - be more specific.")
    return matches[0]


class CDP:
    def __init__(self, tab: dict) -> None:
        # suppress_origin: Chrome 111+ rejects CDP websockets that carry an
        # Origin header unless launched with --remote-allow-origins. Omitting
        # the header entirely is accepted and needs no launch-flag change.
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=30, suppress_origin=True
        )
        self._id = 0

    def call(self, method: str, **params) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    sys.exit(f"CDP error from {method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expression: str) -> object:
        r = self.call(
            "Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True
        )
        if r.get("exceptionDetails"):
            sys.exit(f"JS exception: {r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "tabs":
        for t in _tabs():
            print(f"{t['id'][:8]}  {(t.get('title') or '')[:55]:55}  {(t.get('url') or '')[:80]}")
        return

    if cmd == "find":
        t = _find(sys.argv[2])
        print(f"{t['id'][:8]}  {t.get('title')}  {t.get('url')}")
        return

    if cmd == "new":
        req = urllib.request.Request(
            f"{BASE}/json/new?{urllib.parse.urlencode({'': sys.argv[2]})[1:]}", method="PUT"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            t = json.load(r)
        print(f"opened {t['id'][:8]}")
        return

    tab = _find(sys.argv[2])
    cdp = CDP(tab)

    if cmd == "goto":
        cdp.call("Page.navigate", url=sys.argv[3])
        print(f"navigated {tab['id'][:8]} -> {sys.argv[3]}")
    elif cmd == "eval":
        print(json.dumps(cdp.eval(sys.argv[3]), indent=2, default=str))
    elif cmd == "text":
        print(cdp.eval("document.body ? document.body.innerText.slice(0, 8000) : '(no body)'"))
    elif cmd == "click":
        # A real mouse event, not element.click(). Google's account chooser (and
        # most OAuth/consent UIs) ignore synthetic clicks: the handlers check
        # isTrusted, which only CDP-dispatched input sets. `eval` reported
        # "clicked" and nothing happened, which is the failure this exists for.
        #
        # Takes a text substring rather than coordinates so the caller does not
        # have to convert screenshot pixels to CSS pixels through the device
        # pixel ratio -- that conversion is where blind clicking goes wrong.
        needle = sys.argv[3]
        # "css:<selector>" for controls with no text of their own (comboboxes,
        # icon buttons); a bare string matches the innermost element containing
        # that text.
        if needle.startswith("css:"):
            finder = "document.querySelector(%s)" % json.dumps(needle[4:])
        else:
            finder = """[...document.querySelectorAll('*')].filter(e => {
                if (!e.innerText || !e.innerText.includes(%s)) return false;
                return ![...e.children].some(c => c.innerText && c.innerText.includes(%s));
              })[0]""" % (json.dumps(needle), json.dumps(needle))
        box = cdp.eval(
            """
            (() => {
              const hit = %s;
              if (!hit) return null;
              // Measure AFTER scrolling. Long dropdowns and virtualized lists
              // report rects far outside the viewport, and dispatching a mouse
              // event at those coordinates clicks whatever really sits there --
              // silently, on the wrong row.
              hit.scrollIntoView({block: 'center', inline: 'center'});
              const r = hit.getBoundingClientRect();
              if (!r.width || !r.height) return null;
              if (r.bottom < 0 || r.top > innerHeight) return null;
              return {x: r.left + r.width / 2, y: r.top + r.height / 2};
            })()
            """
            % finder
        )
        if not box:
            sys.exit(f"no visible element containing {needle!r}")
        for kind in ("mousePressed", "mouseReleased"):
            cdp.call(
                "Input.dispatchMouseEvent",
                type=kind,
                x=box["x"],
                y=box["y"],
                button="left",
                clickCount=1,
            )
        print(f"clicked {needle!r} at ({box['x']:.0f}, {box['y']:.0f})")
    elif cmd == "type":
        # Input.insertText, not `el.value = ...`. React (which the Databricks UI
        # uses) tracks the previous value on the DOM node and ignores a direct
        # assignment, so the field looks filled and the component's state stays
        # empty -- the submit button then stays disabled with no visible reason.
        cdp.call("Input.insertText", text=sys.argv[3])
        print(f"typed {len(sys.argv[3])} chars into the focused element")
    elif cmd == "shot":
        data = cdp.call("Page.captureScreenshot", format="png")["data"]
        out = sys.argv[3]
        with open(out, "wb") as f:
            f.write(base64.b64decode(data))
        print(f"screenshot -> {out}")
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used by `new`)

    main()
