#!/usr/bin/env python3
"""Generate a benchmark summary chart in the same house style as TexSoup."""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).with_name("competitor_summary.svg")

TOOLS = (
    {"name": "pymini", "color": "#1f7a5a"},
    {"name": "pyminifier", "color": "#6e7c91"},
    {"name": "python-minifier", "color": "#c06b3e"},
)

PACKAGES = (
    {
        "name": "TexSoup",
        "speed_ms": {"pymini": 124.9, "pyminifier": 52.2, "python-minifier": 117.2},
        "compression_x": {"pymini": 4.0, "pyminifier": 2.8, "python-minifier": 1.2},
    },
    {
        "name": "timefhuman",
        "speed_ms": {"pymini": 352.0, "pyminifier": 71.0, "python-minifier": 266.0},
        "compression_x": {"pymini": 1.9, "pyminifier": 1.2, "python-minifier": 1.6},
    },
    {
        "name": "rich",
        "speed_ms": {"pymini": 3286.6, "pyminifier": None, "python-minifier": 1838.7},
        "compression_x": {"pymini": 2.6, "pyminifier": None, "python-minifier": 1.6},
    },
)

WIDTH = 980
HEIGHT = 430
PADDING = 36
TITLE_Y = 32
SUBTITLE_Y = 54
LEGEND_Y = 77
PANEL_GAP = 28
PANEL_TOP = 102
PANEL_HEIGHT = 270
PANEL_WIDTH = (WIDTH - PADDING * 2 - PANEL_GAP) / 2
BAR_GAP = 6
BAR_WIDTH = 24
BG_COLOR = "var(--bg)"
PANEL_COLOR = "var(--panel)"
PANEL_STROKE = "var(--panel-stroke)"
AXIS_COLOR = "var(--axis)"
GRID_COLOR = "var(--grid)"
TEXT_COLOR = "var(--text)"
MUTED = "var(--muted)"
FAIL_FILL = "var(--fail-fill)"
FAIL_STROKE = "var(--fail-stroke)"
FAIL_TEXT = "var(--fail-text)"
FONT = "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"


def style_block():
    return """
<style>
  svg {
    color-scheme: light dark;
    --bg: rgba(15, 23, 42, 0.10);
    --panel: rgba(250, 251, 252, 0.92);
    --panel-stroke: #e4e7ec;
    --grid: #eceef2;
    --axis: #d5d8df;
    --text: #1c1f24;
    --muted: #5d6674;
    --fail-fill: rgba(255, 255, 255, 0.9);
    --fail-stroke: #c7cdd8;
    --fail-text: #b42318;
  }

  @media (prefers-color-scheme: dark) {
    svg {
      --bg: rgba(248, 250, 252, 0.08);
      --panel: rgba(21, 26, 35, 0.88);
      --panel-stroke: #2f3847;
      --grid: #2a3140;
      --axis: #3a4456;
      --text: #f3f5f8;
      --muted: #b7bfcb;
      --fail-fill: rgba(255, 255, 255, 0.06);
      --fail-stroke: #8f9bad;
      --fail-text: #f6c3be;
    }
  }
</style>""".strip()


def svg_text(x, y, text, size=14, weight="400", anchor="start", fill=TEXT_COLOR):
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">'
        f"{escape(text)}</text>"
    )


def svg_rect(x, y, width, height, fill, rx=8, stroke="none", dash=None, opacity=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}"{dash_attr}{opacity_attr} />'
    )


def panel_origin(index):
    return PADDING + index * (PANEL_WIDTH + PANEL_GAP), PANEL_TOP


def draw_panel_frame(elements, x, y, width, height, title, subtitle):
    elements.append(svg_rect(x, y, width, height, PANEL_COLOR, rx=14, stroke=PANEL_STROKE))
    elements.append(svg_text(x + 18, y + 28, title, size=16, weight="600"))
    elements.append(svg_text(x + 18, y + 48, subtitle, size=12, fill=MUTED))


def draw_legend(elements):
    x = PADDING
    for tool in TOOLS:
        elements.append(svg_rect(x, LEGEND_Y - 11, 14, 14, tool["color"], rx=4))
        elements.append(svg_text(x + 22, LEGEND_Y + 1, tool["name"], size=12, fill=MUTED))
        x += 148


def layout_groups(axis_left, axis_right, group_count):
    group_width = (axis_right - axis_left) / group_count
    cluster_width = len(TOOLS) * BAR_WIDTH + (len(TOOLS) - 1) * BAR_GAP
    return group_width, cluster_width


def group_center(axis_left, group_width, group_index):
    return axis_left + group_width * (group_index + 0.5)


def group_start_x(axis_left, group_width, group_index, cluster_width):
    return axis_left + group_width * group_index + (group_width - cluster_width) / 2


def draw_compression_panel(elements, x, y, width, height, title, subtitle, packages, max_value=4.0):
    draw_panel_frame(elements, x, y, width, height, title, subtitle)
    axis_left = x + 54
    axis_right = x + width - 16
    axis_top = y + 82
    axis_bottom = y + height - 52
    axis_height = axis_bottom - axis_top

    for tick in (0, 1, 2, 3, 4):
        tick_y = axis_bottom - axis_height * (tick / max_value)
        elements.append(f'<line x1="{axis_left}" y1="{tick_y}" x2="{axis_right}" y2="{tick_y}" stroke="{GRID_COLOR}" />')
        elements.append(svg_text(axis_left - 10, tick_y + 4, f"{tick}x", size=11, anchor="end", fill=MUTED))

    elements.append(f'<line x1="{axis_left}" y1="{axis_top}" x2="{axis_left}" y2="{axis_bottom}" stroke="{AXIS_COLOR}" />')
    elements.append(f'<line x1="{axis_left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="{AXIS_COLOR}" />')

    group_width, cluster_width = layout_groups(axis_left, axis_right, len(packages))

    for group_index, package in enumerate(packages):
        center = group_center(axis_left, group_width, group_index)
        start_x = group_start_x(axis_left, group_width, group_index, cluster_width)
        for tool_index, tool in enumerate(TOOLS):
            value = package["compression_x"][tool["name"]]
            bar_x = start_x + tool_index * (BAR_WIDTH + BAR_GAP)
            if value is None:
                fail_height = 24
                fail_y = axis_bottom - fail_height
                elements.append(svg_rect(bar_x, fail_y, BAR_WIDTH, fail_height, FAIL_FILL, rx=5, stroke=FAIL_STROKE, dash="4 4"))
                elements.append(svg_text(bar_x + BAR_WIDTH / 2, fail_y - 10, "fail", size=10, weight="600", anchor="middle", fill=FAIL_TEXT))
                continue
            bar_height = axis_height * (value / max_value)
            bar_y = axis_bottom - bar_height
            elements.append(svg_rect(bar_x, bar_y, BAR_WIDTH, bar_height, tool["color"], rx=4))
            elements.append(svg_text(bar_x + BAR_WIDTH / 2, bar_y - 10, f"{value:.1f}x", size=10, weight="600", anchor="middle"))
        elements.append(svg_text(center, axis_bottom + 20, package["name"], size=11, anchor="middle", fill=MUTED))


def draw_speed_panel(elements):
    x, y = panel_origin(1)
    draw_panel_frame(elements, x, y, PANEL_WIDTH, PANEL_HEIGHT, "Speed", "Mean package minification time; lower is better (log scale)")
    axis_left = x + 54
    axis_right = x + PANEL_WIDTH - 16
    axis_top = y + 82
    axis_bottom = y + PANEL_HEIGHT - 52
    axis_height = axis_bottom - axis_top
    log_min = math.log10(40)
    log_max = math.log10(4000)
    ticks = (50, 100, 500, 1000, 3000)

    for tick in ticks:
        fraction = (math.log10(tick) - log_min) / (log_max - log_min)
        tick_y = axis_bottom - axis_height * fraction
        elements.append(f'<line x1="{axis_left}" y1="{tick_y}" x2="{axis_right}" y2="{tick_y}" stroke="{GRID_COLOR}" />')
        elements.append(svg_text(axis_left - 10, tick_y + 4, f"{tick:g} ms", size=11, anchor="end", fill=MUTED))

    elements.append(f'<line x1="{axis_left}" y1="{axis_top}" x2="{axis_left}" y2="{axis_bottom}" stroke="{AXIS_COLOR}" />')
    elements.append(f'<line x1="{axis_left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="{AXIS_COLOR}" />')

    group_width, cluster_width = layout_groups(axis_left, axis_right, len(PACKAGES))

    for group_index, package in enumerate(PACKAGES):
        center = group_center(axis_left, group_width, group_index)
        start_x = group_start_x(axis_left, group_width, group_index, cluster_width)
        for tool_index, tool in enumerate(TOOLS):
            value = package["speed_ms"][tool["name"]]
            bar_x = start_x + tool_index * (BAR_WIDTH + BAR_GAP)
            if value is None:
                fail_height = 24
                fail_y = axis_bottom - fail_height
                elements.append(svg_rect(bar_x, fail_y, BAR_WIDTH, fail_height, FAIL_FILL, rx=5, stroke=FAIL_STROKE, dash="4 4"))
                elements.append(svg_text(bar_x + BAR_WIDTH / 2, fail_y - 10, "fail", size=10, weight="600", anchor="middle", fill=FAIL_TEXT))
                continue
            fraction = (math.log10(value) - log_min) / (log_max - log_min)
            bar_height = max(axis_height * fraction, 4)
            bar_y = axis_bottom - bar_height
            elements.append(svg_rect(bar_x, bar_y, BAR_WIDTH, bar_height, tool["color"], rx=4))
            elements.append(svg_text(bar_x + BAR_WIDTH / 2, bar_y - 10, f"{value:.1f} ms", size=10, weight="600", anchor="middle"))
        elements.append(svg_text(center, axis_bottom + 20, package["name"], size=11, anchor="middle", fill=MUTED))


def build_svg():
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none">',
        style_block(),
        svg_rect(0, 0, WIDTH, HEIGHT, BG_COLOR, rx=22),
        svg_text(PADDING, TITLE_Y, "pymini Benchmark Snapshot", size=24, weight="700"),
        svg_text(
            PADDING,
            SUBTITLE_Y,
            "Validated package benchmarks from benchmarks/README.md, measured locally on April 7, 2026",
            size=13,
            fill=MUTED,
        ),
    ]
    draw_legend(elements)
    draw_compression_panel(
        elements,
        *panel_origin(0),
        PANEL_WIDTH,
        PANEL_HEIGHT,
        "Compression",
        "Minify-only compression multiplier by package; higher is better",
        PACKAGES,
    )
    draw_speed_panel(elements)
    elements.append("</svg>")
    return "\n".join(elements)

def main():
    OUT.write_text(build_svg() + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
