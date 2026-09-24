#!/usr/bin/env python3
"""Parse a PowerWorld-style .axd display file and render its bus/branch layout.

The parser focuses on three display objects:
  * DisplayBus
  * DisplayTransmissionLine
  * DisplayTransformer

For lines and transformers, the <SUBDATA Line> coordinate lists are preserved
exactly, so routed bends in the original one-line diagram remain visible.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


FLOAT_RE = re.compile(r"[-+]?\d+(?:[\.,]\d+)?(?:[eE][-+]?\d+)?")
POINT_RE = re.compile(
    r"\[\s*([-+]?\d+(?:[\.,]\d+)?(?:[eE][-+]?\d+)?)\s+"
    r"([-+]?\d+(?:[\.,]\d+)?(?:[eE][-+]?\d+)?)\s*\]"
)


def pw_float(text: str) -> float:
    """Convert a PowerWorld numeric token, including decimal-comma values."""
    return float(text.strip().replace(",", "."))


def _tokenize(line: str) -> list[str]:
    """Split one AXD record line while preserving quoted fields."""
    return shlex.split(line, comments=False, posix=True)


@dataclass
class Bus:
    number: int
    auxiliary_id: str
    x: float
    y: float
    thickness: float
    size: float
    width: float
    orientation: str
    style: str


@dataclass
class Edge:
    kind: str  # "line" or "transformer"
    from_bus: int
    to_bus: int
    circuit: str
    auxiliary_id: str
    x: float
    y: float
    thickness: float
    coordinates: list[tuple[float, float]]
    symbol_segment: Optional[int] = None


@dataclass
class AxdModel:
    buses: list[Bus]
    lines: list[Edge]
    transformers: list[Edge]

    @property
    def edges(self) -> list[Edge]:
        return self.lines + self.transformers


def _find_block(lines: list[str], name: str) -> tuple[int, int]:
    """Return inclusive content bounds inside a named top-level {...} block."""
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith(name + " (")), None)
    if start is None:
        raise ValueError(f"Block {name!r} not found")

    i = start
    while i < len(lines) and "{" not in lines[i]:
        i += 1
    if i >= len(lines):
        raise ValueError(f"Opening '{{' for block {name!r} not found")
    content_start = i + 1

    depth = 1
    i = content_start
    while i < len(lines):
        # Top-level AXD blocks here do not nest braces; count defensively anyway.
        depth += lines[i].count("{")
        depth -= lines[i].count("}")
        if depth == 0:
            return content_start, i - 1
        i += 1
    raise ValueError(f"Closing '}}' for block {name!r} not found")


def _parse_bus_record(line: str) -> Bus:
    t = _tokenize(line)
    # DisplayBus fields used here:
    # BusNum, SOAuxiliaryID, SOX, SOY, SOThickness, SOColor,
    # SOUseFillColor, SOFillColor, SOSize, SOWidth, SOOrientation, ... SOStyle
    if len(t) < 16:
        raise ValueError(f"Unexpected DisplayBus record: {line.rstrip()}")
    return Bus(
        number=int(t[0]),
        auxiliary_id=t[1].strip(),
        x=pw_float(t[2]),
        y=pw_float(t[3]),
        thickness=pw_float(t[4]),
        size=pw_float(t[8]),
        width=pw_float(t[9]),
        orientation=t[10].strip(),
        style=t[15].strip(),
    )


def _parse_edge_record(line: str, kind: str) -> Edge:
    t = _tokenize(line)
    if len(t) < 8:
        raise ValueError(f"Unexpected edge record: {line.rstrip()}")
    symbol_segment = None
    if kind == "transformer":
        # SOSymbolSegment is the final DisplayTransformer field.
        try:
            symbol_segment = int(t[-1])
        except (ValueError, TypeError):
            symbol_segment = None
    return Edge(
        kind=kind,
        from_bus=int(t[0]),
        to_bus=int(t[1]),
        circuit=t[2].strip(),
        auxiliary_id=t[3].strip(),
        x=pw_float(t[4]),
        y=pw_float(t[5]),
        thickness=1, #pw_float(t[6]),
        coordinates=[],
        symbol_segment=symbol_segment,
    )


def _parse_display_bus(lines: list[str]) -> list[Bus]:
    a, b = _find_block(lines, "DisplayBus")
    buses: list[Bus] = []
    for raw in lines[a : b + 1]:
        s = raw.strip()
        if not s or s.startswith("//") or s.startswith("<"):
            continue
        buses.append(_parse_bus_record(raw))
    return buses


def _parse_edge_block(lines: list[str], block_name: str, kind: str) -> list[Edge]:
    a, b = _find_block(lines, block_name)
    edges: list[Edge] = []
    i = a
    while i <= b:
        s = lines[i].strip()
        if not s or s.startswith("//"):
            i += 1
            continue
        if s.startswith("<SUBDATA") or s.startswith("</SUBDATA"):
            i += 1
            continue

        edge = _parse_edge_record(lines[i], kind)
        i += 1

        # Associate the immediately following <SUBDATA Line> polyline, when present.
        while i <= b and not lines[i].strip():
            i += 1
        if i <= b and lines[i].strip().lower().startswith("<subdata line"):
            i += 1
            coords: list[tuple[float, float]] = []
            while i <= b and not lines[i].strip().lower().startswith("</subdata"):
                for mx, my in POINT_RE.findall(lines[i]):
                    coords.append((pw_float(mx), pw_float(my)))
                i += 1
            edge.coordinates = coords
            if i <= b:
                i += 1  # consume </SUBDATA>

        # Fallback to a straight connection between bus attachment positions is
        # performed later, when bus coordinates are available.
        edges.append(edge)

    return edges


def parse_axd(path: str | Path) -> AxdModel:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    buses = _parse_display_bus(lines)
    lines_out = _parse_edge_block(lines, "DisplayTransmissionLine", "line")
    transformers = _parse_edge_block(lines, "DisplayTransformer", "transformer")

    # Fill missing edge polylines with straight center-to-center paths.
    bus_xy = {b.number: (b.x, b.y) for b in buses}
    for e in lines_out + transformers:
        if not e.coordinates:
            p0 = bus_xy.get(e.from_bus, (e.x, e.y))
            p1 = bus_xy.get(e.to_bus, p0)
            e.coordinates = [p0, p1]

    return AxdModel(buses=buses, lines=lines_out, transformers=transformers)


def _segment_midpoint(points: list[tuple[float, float]], one_based_segment: Optional[int]) -> tuple[float, float, float, float]:
    """Return midpoint and unit direction of a selected polyline segment."""
    if len(points) < 2:
        x, y = points[0] if points else (0.0, 0.0)
        return x, y, 1.0, 0.0

    if one_based_segment is not None and 1 <= one_based_segment < len(points):
        i = one_based_segment - 1
        (x0, y0), (x1, y1) = points[i], points[i + 1]
    else:
        # Use the segment containing half the total polyline length.
        lengths = [math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(points, points[1:])]
        total = sum(lengths)
        target = total / 2.0
        acc = 0.0
        i = 0
        for i, seg_len in enumerate(lengths):
            if acc + seg_len >= target:
                break
            acc += seg_len
        (x0, y0), (x1, y1) = points[i], points[i + 1]

    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy) or 1.0
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0, dx / norm, dy / norm


def render_model(
    model: AxdModel,
    output: Optional[str | Path] = None,
    show: bool = True,
    labels: bool = True,
    circuit_labels: bool = False,
    title: Optional[str] = None,
    dpi: int = 160,
) -> None:
    """Render buses, transmission lines, and transformers with matplotlib."""
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
    except ImportError as exc:
        raise SystemExit("matplotlib is required for rendering: pip install matplotlib") from exc

    fig, ax = plt.subplots(figsize=(14, 9))

    # Routed transmission lines.
    for e in model.lines:
        xs = [p[0] for p in e.coordinates]
        ys = [p[1] for p in e.coordinates]
        ax.plot(xs, ys, color="#59636e", linewidth=max(0.8, 0.8 * e.thickness), zorder=1)
        if circuit_labels:
            mid = len(xs) // 2
            ax.text(xs[mid], ys[mid], f"{e.from_bus}-{e.to_bus}/{e.circuit}", fontsize=6, zorder=5)

    # Transformers: preserve the stored path and overlay a conventional two-coil symbol.
    for e in model.transformers:
        xs = [p[0] for p in e.coordinates]
        ys = [p[1] for p in e.coordinates]
        ax.plot(xs, ys, color="#a05a1c", linewidth=max(1.0, 0.9 * e.thickness), zorder=2)

        mx, my, ux, uy = _segment_midpoint(e.coordinates, e.symbol_segment)
        # Place the two coil centers along the branch direction.
        radius = 0.65
        offset = 0.55
        for sign in (-1.0, 1.0):
            cx = mx + sign * offset * ux
            cy = my + sign * offset * uy
            ax.add_patch(Circle((cx, cy), radius=radius, facecolor="white", edgecolor="#a05a1c", linewidth=1.3, zorder=4))
        if circuit_labels:
            ax.text(mx, my + 1.3, f"T {e.from_bus}-{e.to_bus}/{e.circuit}", fontsize=6, ha="center", zorder=5)

    # Bus bars. AXD SOSize maps well to the displayed bar length in this file.
    for b in model.buses:
        orientation = b.orientation.lower()
        lw = max(1.8, 1.5 * b.thickness)
        if orientation == "up":
            ax.plot([b.x, b.x], [b.y, b.y + b.size], color="#20262d", linewidth=lw, solid_capstyle="butt", zorder=6)
            label_x, label_y = b.x + 0.7, b.y
            ha, va = "left", "center"
        elif orientation == "down":
            ax.plot([b.x, b.x], [b.y, b.y - b.size], color="#20262d", linewidth=lw, solid_capstyle="butt", zorder=6)
            label_x, label_y = b.x + 0.7, b.y
            ha, va = "left", "center"
        elif orientation == "right":
            ax.plot([b.x, b.x + b.size], [b.y, b.y], color="#20262d", linewidth=lw, solid_capstyle="butt", zorder=6)
            label_x, label_y = b.x, b.y + 0.9
            ha, va = "center", "bottom"
        else:
            ax.plot([b.x, b.x - b.size], [b.y, b.y], color="#20262d", linewidth=lw, solid_capstyle="butt", zorder=6)
            label_x, label_y = b.x, b.y + 0.9
            ha, va = "center", "bottom"
        if labels:
            ax.text(label_x, label_y, str(b.number), fontsize=8, ha=ha, va=va, zorder=7)

    ax.set_aspect("equal", adjustable="datalim")
    ax.autoscale(enable=True, axis="both", tight=False)
    ax.margins(0.04)
    ax.set_xlabel("AXD X coordinate")
    ax.set_ylabel("AXD Y coordinate")
    ax.set_title(title or f"AXD network: {len(model.buses)} buses, {len(model.lines)} lines, {len(model.transformers)} transformers")
    ax.grid(False)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)


def export_json(model: AxdModel, path: str | Path) -> None:
    payload = {
        "buses": [asdict(b) for b in model.buses],
        "lines": [asdict(e) for e in model.lines],
        "transformers": [asdict(e) for e in model.transformers],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(model: AxdModel) -> None:
    print(f"Buses:        {len(model.buses)}")
    print(f"Lines:        {len(model.lines)}")
    print(f"Transformers: {len(model.transformers)}")
    routed = sum(1 for e in model.edges if len(e.coordinates) >= 2)
    print(f"Routed edges: {routed}/{len(model.edges)}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render an AXD one-line network using its stored Display* coordinates.")
    p.add_argument("axd", help="Input .axd text file")
    p.add_argument("-o", "--output", help="Save figure (.svg, .png, .pdf, ...). If omitted, only the interactive window is shown.")
    p.add_argument("--json", dest="json_output", help="Also export parsed buses/edges and routed coordinates as JSON")
    p.add_argument("--no-labels", action="store_true", help="Hide bus-number labels")
    p.add_argument("--circuit-labels", action="store_true", help="Label line/transformer circuits")
    p.add_argument("--no-show", action="store_true", help="Do not open the interactive matplotlib window")
    p.add_argument("--title", help="Custom figure title")
    p.add_argument("--dpi", type=int, default=160, help="Raster output resolution (default: 160)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    model = parse_axd(args.axd)
    print_summary(model)
    if args.json_output:
        export_json(model, args.json_output)
    if args.output or not args.no_show:
        render_model(
            model,
            output=args.output,
            show=not args.no_show,
            labels=not args.no_labels,
            circuit_labels=args.circuit_labels,
            title=args.title,
            dpi=args.dpi,
        )


if __name__ == "__main__":
    main()
