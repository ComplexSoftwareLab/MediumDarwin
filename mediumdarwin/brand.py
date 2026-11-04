"""MediumDarwin logo, motion banner, and startup ASCII art.

The mark and colors come from the Figma file "Logo, banner and motion".
The green square is the mutated terminal of the M. In the motion banner it
blinks with the Figma keyframes ``kf_5_5_opacity_0`` (2s, step-end, infinite).
HTML reports embed that animation. A terminal cannot run those keyframes, so
the ASCII banner uses a blinking green ``[-]`` for the same square.
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
BANNER_SVG = os.path.join(_ASSETS, "banner.svg")

# Block M from the logo. "[-]" is the green mutated terminal on the right stem.
_CAP = "[-]"
_MARK = (
    "████        [-] ",
    "████        ████",
    "██████    ██████",
    "███████  ███████",
    "████████████████",
    "████  ████  ████",
    "████   ██   ████",
    "████        ████",
    "████        ████",
    "████        ████",
)

_WORDMARK_ROW = 2
_TAGLINE_ROW = 3

_LICENSE = """
Copyright (c) 2014 2022 Ali Parsai
Copyright (c) 2025      MediumDarwin Contributors

This project builds upon the original work of Ali Parsai and the LittleDarwin mutation testing framework.
We gratefully acknowledge his foundational contributions, which made this extended version possible.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.
If not, see <https://www.gnu.org/licenses/>.

Original author:
Ali Parsai — https://www.parsai.net/
""".strip("\n")


def ascii_logo(*, blink: bool = True) -> Text:
    """ASCII M matching the logo, with the motion-banner wordmark beside it."""
    green = "blink #14A17E" if blink else "#14A17E"
    text = Text()
    for index, row in enumerate(_MARK):
        if index:
            text.append("\n")
        cursor = 0
        while cursor < len(row):
            if row.startswith(_CAP, cursor):
                text.append(_CAP, style=green)
                cursor += len(_CAP)
                continue
            cell = row[cursor]
            if cell == "█":
                text.append(cell, style="bold bright_white")
            else:
                text.append(cell)
            cursor += 1
        if index == _WORDMARK_ROW:
            text.append("   ")
            text.append("MediumDarwin", style="bold bright_white")
        elif index == _TAGLINE_ROW:
            text.append("   ")
            text.append("Mutation testing for Java", style="#14A17E")
    return text


def render_banner(console: Console, *, full: bool) -> None:
    """Print the tool banner. ``full`` is the interactive ASCII lockup."""
    if not full:
        console.print(
            "[bold]MediumDarwin[/bold]  [#14A17E]Mutation testing for Java[/]"
        )
        return
    console.print(
        Panel(
            ascii_logo(blink=True),
            style="on #182B2A",
            border_style="#182B2A",
            padding=(1, 3),
            expand=False,
        )
    )
    console.print(_LICENSE, style="dim")


def html_banner() -> str:
    """Motion banner markup for HTML reports. SVG is inlined so reports travel."""
    with open(BANNER_SVG, "r", encoding="utf-8") as handle:
        svg = handle.read()
    return (
        '<div class="md-banner" style="max-width:649px;margin:0 0 1.5em 0">'
        + svg.replace(
            'width="649" height="200"',
            'width="649" height="200" style="max-width:100%;height:auto;display:block"',
            1,
        )
        + "</div>"
    )


def insert_html_banner(html: str) -> str:
    """Place the motion banner at the start of an HTML report body."""
    return html.replace("<body>", "<body>" + html_banner(), 1)


def report_page_css(*, aggregate: bool = False) -> str:
    """Page CSS for HTML reports, using the Figma banner palette.

    Coverage pages are fully dark. Aggregate source listings keep a light
    panel so the per-operator highlight colors stay readable, framed by the
    same teal, green, and white.
    """
    css = """
        :root {
            --md-bg: #182B2A;
            --md-raised: #203734;
            --md-line: rgba(255, 255, 255, 0.08);
            --md-green: #14A17E;
            --md-green-bright: #3dceb0;
            --md-text: #f4f7f6;
            --md-muted: #b7c7c2;
            --md-survived: #e07a76;
        }
        body {
            background: var(--md-bg);
            color: var(--md-text);
            font-family: Manrope, "Segoe UI", Calibri, "Helvetica Neue", sans-serif;
            margin: 0;
            padding: 28px 36px 64px;
            line-height: 1.45;
        }
        h1 {
            font-weight: 700;
            letter-spacing: -0.03em;
            font-size: 1.7rem;
            margin: 0.15em 0 0.4em;
        }
        h2 {
            color: var(--md-green-bright);
            font-size: 0.95rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin: 1.7em 0 0.65em;
        }
        p { color: var(--md-muted); }
        table {
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            max-width: 1200px;
            background: var(--md-raised);
            border-radius: 12px;
            overflow: hidden;
            margin: 0 0 1.2em;
        }
        th, td {
            text-align: left;
            padding: 0.8em 1em;
            border-bottom: 1px solid var(--md-line);
            vertical-align: middle;
        }
        th {
            background: var(--md-green);
            color: #ffffff;
            font-weight: 600;
        }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: #2a4a46; }
        a:link, a:visited { color: var(--md-green-bright); text-decoration: none; }
        a:hover, a:active { color: #ffffff; }
        .coverage_bar {
            display: inline-block;
            border-radius: 999px;
            height: 1.15em;
            width: 9.5em;
            background: var(--md-survived);
            margin: 0 0 0 0.4em;
            vertical-align: middle;
            position: relative;
            overflow: hidden;
        }
        .coverage_complete {
            display: inline-block;
            height: 100%;
            background: var(--md-green);
            float: left;
        }
        .coverage_legend {
            position: absolute;
            height: 100%;
            width: 100%;
            left: 0;
            top: 0;
            text-align: center;
            color: #10211f;
            font-size: 0.78em;
            font-weight: 700;
            line-height: 1.15em;
        }
        footer { margin-top: 2.2em; }
        footer p { color: var(--md-muted); font-size: 0.85rem; }
    """
    if aggregate:
        css += """
        pre.code {
            background: #f7faf9;
            color: #182B2A;
            font-family: Consolas, "Courier New", monospace;
            font-size: 0.92rem;
            line-height: 1.55;
            border-radius: 12px;
            border: 1px solid rgba(20, 161, 126, 0.55);
            padding: 14px 16px;
            overflow: auto;
            max-width: 1200px;
        }
        .methodLine { background: #ffffff; }
        .outsideLine { background: #e7eeec; }
        .methodLine > i, .outsideLine > i {
            color: #0f6e56;
            font-style: normal;
            font-weight: 600;
            margin-right: 0.8em;
        }
        .tooltip { position: relative; display: inline-block; }
        .tooltip .tooltiptext {
            visibility: hidden;
            display: block;
            background-color: #182B2A;
            color: #f4f7f6;
            text-align: left;
            border: 1px solid #14A17E;
            border-radius: 0.45em;
            padding: 0.55em 0.7em;
            position: absolute;
            top: 125%;
            z-index: 200;
            min-width: 16em;
            white-space: pre-wrap;
        }
        .tooltip:hover .tooltiptext { visibility: visible; }
        """
    return css
