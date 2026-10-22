#!/usr/bin/env python3
"""Render figure SVGs to PNG so layout collisions can be seen, not guessed.

    python3 tools/render_figures.py content/ch06/figures

Writes PNGs into a scratch directory and prints where they went.
"""

from __future__ import annotations

import sys
from pathlib import Path

OUTDIR = Path("/tmp/figpng")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    from playwright.sync_api import sync_playwright

    svgs: list[Path] = []
    for arg in argv:
        p = Path(arg)
        svgs.extend(sorted(p.glob("*.svg")) if p.is_dir() else [p])
    if not svgs:
        print("no svg found")
        return 1

    OUTDIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720},
                                device_scale_factor=1)
        for svg in svgs:
            page.goto(svg.resolve().as_uri())
            out = OUTDIR / (svg.stem + ".png")
            page.screenshot(path=str(out))
            print("rendered", out)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
