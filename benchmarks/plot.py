#!/usr/bin/env python3
"""Generate a benchmark summary chart for the benchmarks README.

This emits a plain SVG so the chart can be regenerated without adding plotting
dependencies to the repository.

Usage:
    python3 benchmarks/plot.py
    python3 benchmarks/plot.py --output benchmarks/summary.svg
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

TOOLS = (
    {"name": "pymini", "color": "#1f7a5a"},
    {"name": "pyminifier", "color": "#6e7c91"},
    {"name": "python-minifier", "color": "#c06b3e"},
)

PACKAGES = (
    {
        "name": "TexSoup",
        "minify_x": {"pymini": 4.0, "pyminifier": 2.8, "python-minifier": 1.2},
        "wheel_x": {"pymini": 7.3, "pyminifier": 6.6, "python-minifier": 3.6},
    },
    {
        "name": "timefhuman",
        "minify_x": {"pymini": 1.9, "pyminifier": 1.2, "python-minifier": 1.6},
        "wheel_x": {"pymini": 3.4, "pyminifier": 3.1, "python-minifier": 3.2},
    },
    {
        "name": "rich",
        "minify_x": {"pymini": 2.6, "pyminifier": None, "python-minifier": 1.6},
        "wheel_x": {"pymini": 6.6, "pyminifier": None, "python-minifier": 4.6},
    },
)

WIDTH = 980
HEIGHT = 344
PADDING = 0
LEGEND_Y = 22
PANEL_GAP = 20
PANEL_TOP = 40
PANEL_HEIGHT = 282
PANEL_WIDTH = (WIDTH - PADDING * 2 - PANEL_GAP) / 2
BAR_GAP = 8
BAR_WIDTH = 26
BG = 'var(--bg)'
PANEL = 'var(--panel)'
PANEL_STROKE = 'var(--panel-stroke)'
GRID = 'var(--grid)'
AXIS = 'var(--axis)'
TEXT = 'var(--text)'
MUTED = 'var(--muted)'
FONT = 'ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('benchmarks/summary.svg'),
        help='Where to write the SVG chart.',
    )
    return parser.parse_args()


def style_block():
    return """
<style>
  svg {
    color-scheme: light dark;
    --bg: #ffffff;
    --panel: #fafbfc;
    --panel-stroke: #e4e7ec;
    --grid: #eceef2;
    --axis: #d5d8df;
    --text: #1c1f24;
    --muted: #5d6674;
  }

  @media (prefers-color-scheme: dark) {
    svg {
      --bg: #0e1117;
      --panel: #151a23;
      --panel-stroke: #2f3847;
      --grid: #2a3140;
      --axis: #3a4456;
      --text: #f3f5f8;
      --muted: #b7bfcb;
    }
  }
</style>""".strip()


def svg_text(x, y, text, size=14, weight='400', anchor='start', fill=TEXT):
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">'
        f"{escape(text)}</text>"
    )


def svg_rect(x, y, width, height, fill, rx=8, stroke='none', stroke_width=1, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr} />'
    )


def panel_origin(index):
    return PADDING + index * (PANEL_WIDTH + PANEL_GAP), PANEL_TOP


def draw_panel_frame(elements, x, y, width, height, title, subtitle):
    elements.append(svg_rect(x, y, width, height, PANEL, rx=14, stroke=PANEL_STROKE))
    elements.append(svg_text(x + 16, y + 26, title, size=16, weight='600'))
    elements.append(svg_text(x + 16, y + 44, subtitle, size=12, fill=MUTED))


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


def draw_multiplier_panel(elements, x, y, width, height, title, subtitle, packages, key, max_value, tick_values):
    draw_panel_frame(elements, x, y, width, height, title, subtitle)
    axis_left = x + 46
    axis_right = x + width - 12
    axis_top = y + 72
    axis_bottom = y + height - 36
    axis_height = axis_bottom - axis_top

    for tick in tick_values:
        tick_y = axis_bottom - axis_height * (tick / max_value)
        elements.append(f'<line x1="{axis_left}" y1="{tick_y}" x2="{axis_right}" y2="{tick_y}" stroke="{GRID}" />')
        elements.append(svg_text(axis_left - 10, tick_y + 4, f"{tick}x", size=11, anchor='end', fill=MUTED))

    elements.append(f'<line x1="{axis_left}" y1="{axis_top}" x2="{axis_left}" y2="{axis_bottom}" stroke="{AXIS}" />')
    elements.append(f'<line x1="{axis_left}" y1="{axis_bottom}" x2="{axis_right}" y2="{axis_bottom}" stroke="{AXIS}" />')

    group_width, cluster_width = layout_groups(axis_left, axis_right, len(packages))

    for group_index, package in enumerate(packages):
        center = group_center(axis_left, group_width, group_index)
        start_x = group_start_x(axis_left, group_width, group_index, cluster_width)
        for tool_index, tool in enumerate(TOOLS):
            value = package[key][tool["name"]]
            bar_x = start_x + tool_index * (BAR_WIDTH + BAR_GAP)
            if value is None:
                fail_height = 24
                fail_y = axis_bottom - fail_height
                elements.append(svg_rect(bar_x, fail_y, BAR_WIDTH, fail_height, 'none', rx=5, stroke=tool["color"], stroke_width=1.5, dash='6 4'))
                elements.append(svg_text(bar_x + BAR_WIDTH / 2, fail_y - 10, 'fail', size=10, weight='600', anchor='middle', fill=MUTED))
                continue
            bar_height = axis_height * (value / max_value)
            bar_y = axis_bottom - bar_height
            elements.append(svg_rect(bar_x, bar_y, BAR_WIDTH, bar_height, tool["color"], rx=4))
            elements.append(svg_text(bar_x + BAR_WIDTH / 2, bar_y - 10, f"{value:.1f}x", size=10, weight='600', anchor='middle'))
        elements.append(svg_text(center, axis_bottom + 20, package["name"], size=11, anchor='middle', fill=MUTED))


def draw_wheel_panel(elements):
    x, y = panel_origin(1)
    draw_multiplier_panel(
        elements,
        x,
        y,
        PANEL_WIDTH,
        PANEL_HEIGHT,
        'Compression',
        'Minify + wheel compression multiplier by package; higher is better',
        PACKAGES,
        'wheel_x',
        8.0,
        (0, 2, 4, 6, 8),
    )


def build_svg():
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none">',
        style_block(),
        svg_rect(0, 0, WIDTH, HEIGHT, BG, rx=0),
    ]
    draw_legend(elements)
    draw_multiplier_panel(
        elements,
        *panel_origin(0),
        PANEL_WIDTH,
        PANEL_HEIGHT,
        'Minification',
        'Minify-only compression multiplier by package; higher is better',
        PACKAGES,
        'minify_x',
        4.0,
        (0, 1, 2, 3, 4),
    )
    draw_wheel_panel(elements)
    elements.append('</svg>')
    return "\n".join(elements)


def main():
    args = parse_args()
    args.output.write_text(build_svg() + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
