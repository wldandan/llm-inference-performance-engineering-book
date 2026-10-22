"""Shared SVG primitives for the book's figures.

The visual contract is the one fixed for chapter 1 (see
``strategy/reviews/ch01/storyboard.md``): 1280x720, a kicker/heading/sub header
block, a dark conclusion bar at the bottom, PingFang SC font stack, minimum
14px type, arrows via ``marker-end``, and no "Key Takeaway" wording.

Every figure is generated, never hand-edited. To change a layout, change the
chapter's ``build_figures.py`` and re-run it.
"""

from __future__ import annotations

from html import escape

W, H = 1280, 720
PAD = 56
BODY_TOP = 150
BODY_BOTTOM = 624

INK = "#0F172A"
MUTED = "#64748B"
LINE = "#CBD5E1"
WASH = "#F1F5F9"
PAGE = "#F8FAFC"
GOOD = "#0F766E"
WARN = "#B45309"
BAD = "#B91C1C"
COOL = "#1D4ED8"

STYLE = """
    text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
    .k{font-size:14px;font-weight:700;letter-spacing:2px;fill:#64748B}
    .t{font-size:30px;font-weight:750}
    .sub{font-size:16px;fill:#64748B}
    .card{fill:#FFFFFF;stroke:#CBD5E1;stroke-width:1.8}
    .soft{fill:#F1F5F9;stroke:#CBD5E1;stroke-width:1.3}
    .dark{fill:#0F172A}
    .h{font-size:20px;font-weight:750}
    .hw{font-size:20px;font-weight:750;fill:#FFFFFF}
    .s{font-size:15px;fill:#64748B}
    .sw{font-size:15px;fill:#CBD5E1}
    .b{font-size:17px;font-weight:700}
    .m{font-size:15px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
    .mb{font-size:17px;font-weight:700;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
    .flow{fill:none;stroke:#334155;stroke-width:2.5;marker-end:url(#arrow)}
    .flowb{fill:none;stroke:#1D4ED8;stroke-width:2.5;marker-end:url(#arrowb)}
    .feedback{fill:none;stroke:#0F766E;stroke-width:2.2;stroke-dasharray:7 5;marker-end:url(#arrowg)}
    .bracket{fill:none;stroke:#64748B;stroke-width:2}
    .divider{stroke:#E2E8F0;stroke-width:1.5}
    .rule{stroke:#94A3B8;stroke-width:1.6;stroke-dasharray:6 5}
    .take{fill:#0F172A}
    .tl{font-size:14px;font-weight:700;letter-spacing:1px;fill:#CBD5E1}
    .tv{font-size:18px;font-weight:650;fill:#FFFFFF}
    .good{fill:#0F766E}
    .warn{fill:#B45309}
    .bad{fill:#B91C1C}
    .cool{fill:#1D4ED8}
    .goodfill{fill:#ECFDF5;stroke:#0F766E;stroke-width:1.6}
    .warnfill{fill:#FFFBEB;stroke:#B45309;stroke-width:1.6}
    .badfill{fill:#FEF2F2;stroke:#B91C1C;stroke-width:1.6}
    .coolfill{fill:#EFF6FF;stroke:#1D4ED8;stroke-width:1.6}
"""

DEFS = """<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L10 5L0 10Z" fill="#334155"/></marker>
    <marker id="arrowb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L10 5L0 10Z" fill="#1D4ED8"/></marker>
    <marker id="arrowg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L10 5L0 10Z" fill="#0F766E"/></marker>
    <style>{style}</style>
  </defs>"""


def page(*, system: str, title: str, desc: str, kicker: str, heading: str,
         sub: str, body: str, takeaway: str) -> str:
    """Wrap a figure body in the standard skeleton."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="fig-title fig-desc" '
        f'data-figure-system="{system}" fill="{INK}">\n'
        f'  <title id="fig-title">{escape(title)}</title>'
        f'<desc id="fig-desc">{escape(desc)}</desc>\n'
        f'  {DEFS.format(style=STYLE)}\n'
        f'  <rect width="{W}" height="{H}" fill="{PAGE}"/>\n'
        f'  <text class="k" x="{PAD}" y="46">{escape(kicker)}</text>'
        f'<text class="t" x="{PAD}" y="86">{escape(heading)}</text>'
        f'<text class="sub" x="{PAD}" y="116">{escape(sub)}</text>\n'
        f'{body}\n'
        f'  <rect class="take" x="{PAD}" y="642" width="{W - 2 * PAD}" height="54" rx="14"/>'
        f'<text class="tl" x="80" y="675">关键结论</text>'
        f'<text class="tv" x="184" y="676">{escape(takeaway)}</text>\n'
        f'</svg>\n'
    )


# --- primitives -------------------------------------------------------------

def card(x, y, w, h, *, cls="card", rx=16) -> str:
    return f'  <rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def txt(x, y, s, *, cls="s", anchor="start") -> str:
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'  <text class="{cls}" x="{x}" y="{y}"{a}>{escape(str(s))}</text>'


def arrow(x1, y1, x2, y2, *, cls="flow") -> str:
    return f'  <path class="{cls}" d="M{x1} {y1}L{x2} {y2}"/>'


def hpath(x1, y, x2, *, cls="flow") -> str:
    return f'  <path class="{cls}" d="M{x1} {y}H{x2}"/>'


def vpath(x, y1, y2, *, cls="flow") -> str:
    return f'  <path class="{cls}" d="M{x} {y1}V{y2}"/>'


def curve(x1, y1, x2, y2, bend, *, cls="feedback") -> str:
    """A simple quadratic arc, bend is the control-point offset in y."""
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + bend
    return f'  <path class="{cls}" d="M{x1} {y1}Q{cx} {cy} {x2} {y2}"/>'


def dashed(x1, y1, x2, y2, *, cls="rule") -> str:
    return f'  <path class="{cls}" fill="none" d="M{x1} {y1}L{x2} {y2}"/>'


def bar(x, y, w, h, *, cls="coolfill", rx=6) -> str:
    return f'  <rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def table(x, y, w, *, header: list[str], rows: list[list[str]],
          col_w: list[int], row_h: int = 46, head_h: int = 42,
          row_cls: list[str] | None = None) -> str:
    """A light table: header strip plus striped rows. Text is left-aligned."""
    parts = [card(x, y, w, head_h + row_h * len(rows), cls="card", rx=14)]
    parts.append(f'  <path d="M{x} {y + head_h}H{x + w}" class="divider"/>')
    cx = x + 20
    for label, cw in zip(header, col_w):
        parts.append(txt(cx, y + 28, label, cls="b"))
        cx += cw
    for i, row in enumerate(rows):
        ry = y + head_h + row_h * i
        if i:
            parts.append(f'  <path d="M{x + 12} {ry}H{x + w - 12}" class="divider"/>')
        cls = (row_cls[i] if row_cls else None) or "s"
        cx = x + 20
        for j, (cell, cw) in enumerate(zip(row, col_w)):
            c = "b" if j == 0 else cls
            parts.append(txt(cx, ry + row_h / 2 + 6, cell, cls=c))
            cx += cw
    return "\n".join(parts)


def lane(x, y, w, h, label, *, cls="soft") -> str:
    return "\n".join([
        card(x, y, w, h, cls=cls, rx=14),
        txt(x + 18, y + 26, label, cls="b"),
    ])


def note(x, y, w, lines: list[str], *, cls="soft", h=None) -> str:
    h = h or (26 + 26 * len(lines))
    parts = [card(x, y, w, h, cls=cls, rx=14)]
    for i, line in enumerate(lines):
        parts.append(txt(x + 18, y + 30 + 26 * i, line, cls="s"))
    return "\n".join(parts)


def write(out_dir, name: str, svg: str) -> None:
    (out_dir / name).write_text(svg, encoding="utf-8")


def write_note(out_dir, stem: str, *, title: str, source: str, order: str,
               takeaway: str, boundary: str) -> None:
    text = (
        f"# {title}\n\n"
        f"- 来源段落：{source}\n"
        f"- 阅读顺序：{order}\n"
        f"- 关键结论：{takeaway}\n"
        f"- 表达边界：{boundary}\n"
    )
    (out_dir / f"{stem}.figure-note.md").write_text(text, encoding="utf-8")
