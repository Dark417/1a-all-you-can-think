"""Real mouse/keyboard input for the debug Chrome, via CDP Input events.

`Element.click()` is not enough for component libraries like AWS Cloudscape:
their dropdowns listen for pointer/mouse sequences, so a synthetic click either
does nothing or lands on the wrong element. `Input.dispatchMouseEvent` produces
events indistinguishable from a real user's.

    python scripts/chrome_click.py <tab> click <x> <y>
    python scripts/chrome_click.py <tab> type <text>
    python scripts/chrome_click.py <tab> key <Enter|Escape|Tab|ArrowDown>
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__file__.rsplit("\\", 1)[0] if "\\" in __file__ else "."))

from chrome import CDP, _find  # noqa: E402

KEYS = {
    "Enter": (13, "Enter"),
    "Escape": (27, "Escape"),
    "Tab": (9, "Tab"),
    "ArrowDown": (40, "ArrowDown"),
    "ArrowUp": (38, "ArrowUp"),
}


def click(cdp: CDP, x: int, y: int) -> None:
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        params = {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1}
        if kind == "mouseMoved":
            params.pop("clickCount")
            params["button"] = "none"
        cdp.call("Input.dispatchMouseEvent", **params)


def main() -> None:
    tab = _find(sys.argv[1])
    cdp = CDP(tab)
    cmd = sys.argv[2]

    if cmd == "click":
        click(cdp, int(sys.argv[3]), int(sys.argv[4]))
        print(f"clicked ({sys.argv[3]}, {sys.argv[4]})")
    elif cmd == "type":
        for ch in sys.argv[3]:
            cdp.call("Input.dispatchKeyEvent", type="char", text=ch)
        print(f"typed {len(sys.argv[3])} chars")
    elif cmd == "key":
        code, key = KEYS[sys.argv[3]]
        cdp.call("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=code, key=key)
        cdp.call("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=code, key=key)
        print(f"pressed {sys.argv[3]}")
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
