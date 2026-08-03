#!/usr/bin/env python3
"""
Ubuntu Cursors — installable X11/Wayland cursor theme.

Design language from the user's concept art:
  - Classic filled arrow with rounded tip and clean notch
  - White body, dark outline (readable on light + dark UIs)
  - Ubuntu Circle of Friends for wait / progress
  - Ubuntu orange (#E95420) accents

Build: python3 build_ubuntu_cursors.py
Installs to ~/.local/share/icons/Ubuntu-Cursors
"""

from __future__ import annotations

import math
import os
import shutil
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------
ORANGE = (233, 84, 32, 255)       # #E95420
AUBERGINE = (44, 0, 30, 255)      # #2C001E
WHITE = (255, 255, 255, 255)
OUTLINE = (32, 32, 32, 255)       # near-black for contrast on light bg
SHADOW = (0, 0, 0, 70)

THEME_NAME = "Bibuntu"
THEME_COMMENT = "Ubuntu-inspired cursors: classic arrow + Circle of Friends"
SIZES = (24, 32, 48, 64, 96)
ANIM_FRAMES = 8
ANIM_DELAY_MS = 60

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
PREVIEW = ROOT / "preview"
INSTALL = Path.home() / ".local" / "share" / "icons" / THEME_NAME


# ---------------------------------------------------------------------------
# Drawing helpers (work in a unit canvas 0..1, then scale)
# ---------------------------------------------------------------------------

def new_canvas(size: int) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def scale_pts(pts, size: float, ox: float = 0.0, oy: float = 0.0):
    return [(ox + x * size, oy + y * size) for x, y in pts]


def draw_poly(draw: ImageDraw.ImageDraw, pts, fill, outline=None, width=1):
    if len(pts) < 3:
        return
    draw.polygon(pts, fill=fill)
    if outline and width > 0:
        # closed polyline
        closed = list(pts) + [pts[0]]
        draw.line(closed, fill=outline, width=width, joint="curve")


def stroke_poly(base: Image.Image, pts, fill, outline, stroke: int) -> Image.Image:
    """Draw filled polygon with a clean outer stroke (mask grow + smooth)."""
    if stroke <= 0:
        draw_poly(ImageDraw.Draw(base), pts, fill, outline, 1)
        return base

    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    # Grow for outline thickness; MaxFilter(3) grows ~1px per pass
    grown_mask = mask
    for _ in range(max(1, stroke)):
        grown_mask = grown_mask.filter(ImageFilter.MaxFilter(3))
    # Light blur + re-threshold for less jaggy outline
    if stroke >= 2:
        blurred = grown_mask.filter(ImageFilter.GaussianBlur(radius=0.6))
        grown_mask = blurred.point(lambda p: 255 if p > 96 else 0)

    grown = Image.new("RGBA", base.size, (0, 0, 0, 0))
    grown.paste(outline, mask=grown_mask)
    fill_img = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(fill_img).polygon(pts, fill=fill)
    return Image.alpha_composite(base, Image.alpha_composite(grown, fill_img))


def composite(base: Image.Image, layer: Image.Image) -> Image.Image:
    return Image.alpha_composite(base, layer)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def arrow_points_unit():
    """
    Classic left_ptr geometry in unit space (tip near 0,0).
    Matches the bold triangular arrow from the concept art.
    Tip at top-left; stem trails down-right with a rounded feel via notch.
    """
    # Tip, upper edge, outer corner, lower outer, notch top, notch bottom, stem end, back up
    return [
        (0.06, 0.06),   # tip
        (0.06, 0.72),   # left side bottom
        (0.28, 0.58),   # notch outer
        (0.42, 0.92),   # stem tip-ish
        (0.52, 0.86),   # stem outer
        (0.36, 0.50),   # notch inner
        (0.70, 0.50),   # right wing
    ]


def draw_arrow(size: int, hot: tuple[int, int] | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """
    Default pointer — bold classic arrow matching the concept silhouette:
    long diagonal leading edge, clean triangular body, notched stem.
    Hotspot at tip (top-left). Rendered 2× then downscaled.
    """
    ss = 2
    S = size * ss
    img = new_canvas(S)
    pad = 0.05
    scale = S * (1 - 2 * pad)
    ox = oy = S * pad
    pts = scale_pts(
        [
            (0.00, 0.00),  # tip
            (0.02, 0.78),  # left heel
            (0.26, 0.58),  # notch outer
            (0.40, 0.98),  # stem bottom
            (0.54, 0.90),  # stem outer tip
            (0.34, 0.50),  # notch inner
            (0.78, 0.48),  # right wing tip
        ],
        scale,
        ox,
        oy,
    )
    stroke = max(2, round(S / 14))
    img = stroke_poly(img, pts, WHITE, OUTLINE, stroke)

    d = ImageDraw.Draw(img)
    accent_r = max(2, S // 26)
    ax = (pts[2][0] + pts[5][0]) / 2
    ay = (pts[2][1] + pts[5][1]) / 2
    d.ellipse([ax - accent_r, ay - accent_r, ax + accent_r, ay + accent_r], fill=ORANGE)

    img = img.resize((size, size), Image.LANCZOS)
    return img, (int(ox / ss), int(oy / ss))


def _draw_thick_arc(draw, cx, cy, radius, a0, a1, fill, width, steps=64):
    """Smooth thick arc as a single filled ribbon polygon (no line artifacts)."""
    half = width / 2.0
    outer_pts = []
    inner_pts = []
    for s in range(steps + 1):
        t = s / steps
        ang = math.radians(a0 + (a1 - a0) * t)
        c, sn = math.cos(ang), math.sin(ang)
        outer_pts.append((cx + (radius + half) * c, cy - (radius + half) * sn))
        inner_pts.append((cx + (radius - half) * c, cy - (radius - half) * sn))
    poly = outer_pts + list(reversed(inner_pts))
    draw.polygon(poly, fill=fill)


def circle_of_friends(size: int, rotation_deg: float = 0.0, orange: bool = True) -> Image.Image:
    """
    Ubuntu Circle of Friends from the concept art:
    3 hollow nodes at 120° + 3 connecting arcs (outline style).
    Supersampled 2× then downscaled for clean edges.
    """
    ss = 2
    S = size * ss
    img = new_canvas(S)
    d = ImageDraw.Draw(img)
    cx = cy = S / 2.0
    ring_r = S * 0.30
    node_r = S * 0.145
    stroke = max(2, round(S / 11))
    outline_extra = max(2, stroke // 2)
    color = ORANGE if orange else WHITE

    angles = [rotation_deg + a for a in (90.0, 210.0, 330.0)]

    def node_center(deg):
        rad = math.radians(deg)
        return cx + ring_r * math.cos(rad), cy - ring_r * math.sin(rad)

    centers = [node_center(a) for a in angles]

    # Arc arms — stop short of each node
    arc_margin_deg = 30
    for i in range(3):
        a0 = angles[i] + arc_margin_deg
        a1 = angles[i] + 120.0 - arc_margin_deg
        _draw_thick_arc(d, cx, cy, ring_r, a0, a1, OUTLINE, stroke + outline_extra)
        _draw_thick_arc(d, cx, cy, ring_r, a0, a1, color, stroke)

    # Hollow nodes
    node_layer = new_canvas(S)
    nd = ImageDraw.Draw(node_layer)
    hole = Image.new("L", (S, S), 0)
    hd = ImageDraw.Draw(hole)
    for nx, ny in centers:
        outer = node_r
        inner = node_r * 0.50
        nd.ellipse(
            [nx - outer - ss, ny - outer - ss, nx + outer + ss, ny + outer + ss],
            fill=OUTLINE,
        )
        nd.ellipse([nx - outer, ny - outer, nx + outer, ny + outer], fill=color)
        hd.ellipse([nx - inner, ny - inner, nx + inner, ny + inner], fill=255)

    r, g, b, a = node_layer.split()
    keep = Image.eval(hole, lambda p: 0 if p > 128 else 255)
    a = ImageChops.multiply(a, keep)
    node_layer = Image.merge("RGBA", (r, g, b, a))
    img = composite(img, node_layer)

    return img.resize((size, size), Image.LANCZOS)


def draw_progress(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """Arrow + Circle of Friends badge — the concept art composition."""
    # Larger canvas feel: arrow on left, CoF floating upper-right of it
    img = new_canvas(size)
    # Draw arrow slightly smaller so badge fits
    arrow_size = int(size * 0.88)
    arrow, (hx, hy) = draw_arrow(arrow_size)
    layer = new_canvas(size)
    layer.paste(arrow, (0, int(size * 0.08)), arrow)
    img = composite(img, layer)

    badge = max(int(size * 0.48), 14)
    cof = circle_of_friends(badge, rotation_deg=0, orange=True)
    bx = int(size * 0.50)
    by = int(size * 0.00)
    layer = new_canvas(size)
    layer.paste(cof, (bx, by), cof)
    img = composite(img, layer)
    return img, (hx, hy + int(size * 0.08))


def draw_wait_frame(size: int, frame: int, total: int) -> tuple[Image.Image, tuple[int, int]]:
    """Animated Circle of Friends (spinning)."""
    img = new_canvas(size)
    rot = (frame / total) * 360.0
    # slightly inset so rotation doesn't clip
    pad = int(size * 0.06)
    inner = size - 2 * pad
    cof = circle_of_friends(inner, rotation_deg=rot, orange=True)
    img.paste(cof, (pad, pad), cof)
    return img, (size // 2, size // 2)


def draw_hand(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """Pointing hand / link cursor."""
    img = new_canvas(size)
    s = size
    stroke = max(1, s // 16)
    # simplified pointing hand silhouette (index up)
    pts = scale_pts(
        [
            (0.42, 0.08),  # index tip
            (0.32, 0.08),
            (0.32, 0.42),
            (0.22, 0.40),  # middle knuckle area
            (0.18, 0.52),
            (0.14, 0.48),  # ring
            (0.10, 0.58),
            (0.08, 0.55),  # pinky
            (0.06, 0.68),
            (0.12, 0.88),  # palm bottom left
            (0.55, 0.92),  # palm bottom right
            (0.62, 0.55),  # thumb outer
            (0.48, 0.48),
            (0.48, 0.20),  # index right side
            (0.48, 0.08),
        ],
        s * 0.9,
        s * 0.05,
        s * 0.04,
    )
    img = stroke_poly(img, pts, WHITE, OUTLINE, stroke)
    # orange cuff accent
    d = ImageDraw.Draw(img)
    d.rectangle(
        [s * 0.20, s * 0.84, s * 0.48, s * 0.92],
        fill=ORANGE,
    )
    return img, (int(s * 0.37), int(s * 0.10))


def draw_text(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """I-beam text cursor."""
    img = new_canvas(size)
    d = ImageDraw.Draw(img)
    s = size
    stroke = max(2, s // 12)
    cx = s // 2
    # vertical bar
    d.line([(cx, int(s * 0.12)), (cx, int(s * 0.88))], fill=OUTLINE, width=stroke + 2)
    d.line([(cx, int(s * 0.12)), (cx, int(s * 0.88))], fill=WHITE, width=stroke)
    # top serifs
    w = int(s * 0.18)
    for y in (int(s * 0.12), int(s * 0.88)):
        d.line([(cx - w, y), (cx + w, y)], fill=OUTLINE, width=stroke + 2)
        d.line([(cx - w, y), (cx + w, y)], fill=WHITE, width=stroke)
    return img, (cx, s // 2)


def draw_crosshair(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img = new_canvas(size)
    d = ImageDraw.Draw(img)
    s = size
    stroke = max(2, s // 14)
    cx = cy = s // 2
    gap = int(s * 0.12)
    arm = int(s * 0.38)
    for col, w in ((OUTLINE, stroke + 2), (WHITE, stroke)):
        d.line([(cx, cy - arm), (cx, cy - gap)], fill=col, width=w)
        d.line([(cx, cy + gap), (cx, cy + arm)], fill=col, width=w)
        d.line([(cx - arm, cy), (cx - gap, cy)], fill=col, width=w)
        d.line([(cx + gap, cy), (cx + arm, cy)], fill=col, width=w)
    # center orange dot
    r = max(1, s // 20)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ORANGE)
    return img, (cx, cy)


def draw_move(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """4-way move arrows."""
    img = new_canvas(size)
    s = size
    stroke = max(1, s // 16)
    cx = cy = s / 2
    # four arrowheads + cross
    arms = []
    # up
    arms.append([(cx, s * 0.08), (cx - s * 0.12, s * 0.26), (cx + s * 0.12, s * 0.26)])
    # down
    arms.append([(cx, s * 0.92), (cx - s * 0.12, s * 0.74), (cx + s * 0.12, s * 0.74)])
    # left
    arms.append([(s * 0.08, cy), (s * 0.26, cy - s * 0.12), (s * 0.26, cy + s * 0.12)])
    # right
    arms.append([(s * 0.92, cy), (s * 0.74, cy - s * 0.12), (s * 0.74, cy + s * 0.12)])
    for tri in arms:
        img = stroke_poly(img, tri, WHITE, OUTLINE, stroke)
    d = ImageDraw.Draw(img)
    for col, w in ((OUTLINE, stroke + 2), (WHITE, stroke)):
        d.line([(cx, s * 0.22), (cx, s * 0.78)], fill=col, width=w)
        d.line([(s * 0.22, cy), (s * 0.78, cy)], fill=col, width=w)
    return img, (int(cx), int(cy))


def draw_not_allowed(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img = new_canvas(size)
    d = ImageDraw.Draw(img)
    s = size
    stroke = max(2, s // 12)
    m = int(s * 0.12)
    bbox = [m, m, s - m, s - m]
    d.ellipse(bbox, outline=OUTLINE, width=stroke + 2)
    d.ellipse(bbox, outline=WHITE, width=stroke)
    # diagonal
    inset = m + stroke
    d.line([(inset, inset), (s - inset, s - inset)], fill=OUTLINE, width=stroke + 2)
    d.line([(inset, inset), (s - inset, s - inset)], fill=ORANGE, width=stroke)
    return img, (s // 2, s // 2)


def draw_help(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """Arrow with question badge."""
    img = new_canvas(size)
    arrow, hot = draw_arrow(size)
    img = composite(img, arrow)
    # question circle
    d = ImageDraw.Draw(img)
    s = size
    r = int(s * 0.18)
    cx, cy = int(s * 0.72), int(s * 0.72)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=OUTLINE)
    d.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=ORANGE)
    # simple "?"
    font_size_proxy = max(8, s // 4)
    # draw ? with lines
    d.arc([cx - r // 2, cy - r // 2 - 1, cx + r // 2, cy + 1], 200, 20, fill=WHITE, width=max(2, s // 20))
    d.ellipse([cx - 2, cy + r // 3, cx + 2, cy + r // 3 + 4], fill=WHITE)
    return img, hot


def draw_resize(size: int, direction: str) -> tuple[Image.Image, tuple[int, int]]:
    """
    direction: n, s, e, w, ne, nw, se, sw, ns, ew, nesw, nwse
    """
    img = new_canvas(size)
    s = size
    stroke = max(1, s // 16)
    cx = cy = s / 2

    def arrowhead(tip, base_left, base_right):
        return [tip, base_left, base_right]

    tris = []
    lines = []
    a = s * 0.18  # arrow size
    if direction in ("n", "s", "ns"):
        if direction in ("n", "ns"):
            tris.append(arrowhead((cx, s * 0.10), (cx - a * 0.7, s * 0.10 + a), (cx + a * 0.7, s * 0.10 + a)))
        if direction in ("s", "ns"):
            tris.append(arrowhead((cx, s * 0.90), (cx - a * 0.7, s * 0.90 - a), (cx + a * 0.7, s * 0.90 - a)))
        lines.append([(cx, s * 0.22), (cx, s * 0.78)])
    if direction in ("e", "w", "ew"):
        if direction in ("w", "ew"):
            tris.append(arrowhead((s * 0.10, cy), (s * 0.10 + a, cy - a * 0.7), (s * 0.10 + a, cy + a * 0.7)))
        if direction in ("e", "ew"):
            tris.append(arrowhead((s * 0.90, cy), (s * 0.90 - a, cy - a * 0.7), (s * 0.90 - a, cy + a * 0.7)))
        lines.append([(s * 0.22, cy), (s * 0.78, cy)])
    if direction in ("ne", "sw", "nesw"):
        if direction in ("ne", "nesw"):
            tris.append(arrowhead((s * 0.82, s * 0.18), (s * 0.82 - a, s * 0.18), (s * 0.82, s * 0.18 + a)))
        if direction in ("sw", "nesw"):
            tris.append(arrowhead((s * 0.18, s * 0.82), (s * 0.18 + a, s * 0.82), (s * 0.18, s * 0.82 - a)))
        lines.append([(s * 0.28, s * 0.72), (s * 0.72, s * 0.28)])
    if direction in ("nw", "se", "nwse"):
        if direction in ("nw", "nwse"):
            tris.append(arrowhead((s * 0.18, s * 0.18), (s * 0.18 + a, s * 0.18), (s * 0.18, s * 0.18 + a)))
        if direction in ("se", "nwse"):
            tris.append(arrowhead((s * 0.82, s * 0.82), (s * 0.82 - a, s * 0.82), (s * 0.82, s * 0.82 - a)))
        lines.append([(s * 0.28, s * 0.28), (s * 0.72, s * 0.72)])

    for t in tris:
        img = stroke_poly(img, t, WHITE, OUTLINE, stroke)
    d = ImageDraw.Draw(img)
    for ln in lines:
        d.line(ln, fill=OUTLINE, width=stroke + 2)
        d.line(ln, fill=WHITE, width=stroke)

    # hotspot map
    hot_map = {
        "n": (0.5, 0.12), "s": (0.5, 0.88), "e": (0.88, 0.5), "w": (0.12, 0.5),
        "ne": (0.82, 0.18), "nw": (0.18, 0.18), "se": (0.82, 0.82), "sw": (0.18, 0.82),
        "ns": (0.5, 0.5), "ew": (0.5, 0.5), "nesw": (0.5, 0.5), "nwse": (0.5, 0.5),
    }
    hx, hy = hot_map[direction]
    return img, (int(s * hx), int(s * hy))


def draw_pen(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img = new_canvas(size)
    s = size
    stroke = max(1, s // 16)
    pts = scale_pts(
        [
            (0.18, 0.82),  # tip
            (0.28, 0.55),
            (0.72, 0.12),
            (0.88, 0.28),
            (0.42, 0.72),
        ],
        s * 0.9,
        s * 0.05,
        s * 0.05,
    )
    img = stroke_poly(img, pts, WHITE, OUTLINE, stroke)
    d = ImageDraw.Draw(img)
    # orange tip
    d.polygon(
        [
            (s * 0.18, s * 0.82),
            (s * 0.26, s * 0.62),
            (s * 0.38, s * 0.72),
        ],
        fill=ORANGE,
    )
    return img, (int(s * 0.18), int(s * 0.82))


def draw_zoom(size: int, plus: bool = True) -> tuple[Image.Image, tuple[int, int]]:
    img = new_canvas(size)
    d = ImageDraw.Draw(img)
    s = size
    stroke = max(2, s // 14)
    # lens
    m = int(s * 0.12)
    r = int(s * 0.32)
    cx, cy = int(s * 0.42), int(s * 0.42)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=OUTLINE, width=stroke + 2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=stroke)
    # handle
    d.line([(cx + r * 0.7, cy + r * 0.7), (s * 0.88, s * 0.88)], fill=OUTLINE, width=stroke + 3)
    d.line([(cx + r * 0.7, cy + r * 0.7), (s * 0.88, s * 0.88)], fill=WHITE, width=stroke + 1)
    # + or -
    arm = int(r * 0.45)
    d.line([(cx - arm, cy), (cx + arm, cy)], fill=ORANGE, width=stroke)
    if plus:
        d.line([(cx, cy - arm), (cx, cy + arm)], fill=ORANGE, width=stroke)
    return img, (cx, cy)


def draw_alias(size: int) -> tuple[Image.Image, tuple[int, int]]:
    """Arrow with curved alias arrow badge."""
    img, hot = draw_arrow(size)
    d = ImageDraw.Draw(img)
    s = size
    # small curved arrow bottom-right
    box = [s * 0.52, s * 0.55, s * 0.92, s * 0.95]
    d.arc(box, 200, 40, fill=OUTLINE, width=max(3, s // 14))
    d.arc(box, 200, 40, fill=ORANGE, width=max(2, s // 16))
    # arrowhead
    d.polygon(
        [(s * 0.88, s * 0.62), (s * 0.78, s * 0.55), (s * 0.82, s * 0.72)],
        fill=ORANGE,
    )
    return img, hot


def draw_context_menu(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img, hot = draw_arrow(size)
    d = ImageDraw.Draw(img)
    s = size
    # menu card
    x0, y0 = s * 0.55, s * 0.55
    x1, y1 = s * 0.95, s * 0.95
    d.rounded_rectangle([x0, y0, x1, y1], radius=s // 20, fill=WHITE, outline=OUTLINE, width=max(1, s // 24))
    for i, yy in enumerate((0.62, 0.74, 0.86)):
        col = ORANGE if i == 0 else OUTLINE
        d.line([(x0 + s * 0.06, s * yy), (x1 - s * 0.06, s * yy)], fill=col, width=max(2, s // 20))
    return img, hot


def draw_copy(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img, hot = draw_arrow(size)
    d = ImageDraw.Draw(img)
    s = size
    # two offset squares
    for ox, oy in ((0.55, 0.55), (0.65, 0.65)):
        d.rectangle(
            [s * ox, s * oy, s * (ox + 0.28), s * (oy + 0.28)],
            outline=OUTLINE,
            width=max(2, s // 18),
        )
        d.rectangle(
            [s * ox + 2, s * oy + 2, s * (ox + 0.28) - 2, s * (oy + 0.28) - 2],
            outline=WHITE,
            width=max(1, s // 24),
        )
    return img, hot


def draw_cell(size: int) -> tuple[Image.Image, tuple[int, int]]:
    img = new_canvas(size)
    d = ImageDraw.Draw(img)
    s = size
    stroke = max(2, s // 14)
    m = int(s * 0.18)
    d.rectangle([m, m, s - m, s - m], outline=OUTLINE, width=stroke + 1)
    d.rectangle([m, m, s - m, s - m], outline=WHITE, width=stroke)
    cx = cy = s // 2
    d.line([(cx, m), (cx, s - m)], fill=ORANGE, width=max(1, stroke - 1))
    d.line([(m, cy), (s - m, cy)], fill=ORANGE, width=max(1, stroke - 1))
    return img, (cx, cy)


# ---------------------------------------------------------------------------
# XCursor writer
# ---------------------------------------------------------------------------

XCURSOR_MAGIC = b"Xcur"
XCURSOR_IMAGE_TYPE = 0xFFFD0002
XCURSOR_VERSION = 0x00010000


def write_xcursor(path: Path, frames: list[tuple[Image.Image, tuple[int, int], int]]):
    """
    frames: list of (image, (xhot, yhot), delay_ms)
    Each image may be different size; subtype = nominal size (max dimension).
    """
    # Normalize to RGBA
    norm = []
    for im, hot, delay in frames:
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        norm.append((im, hot, delay))

    ntoc = len(norm)
    header_size = 16
    toc_size = ntoc * 12
    # each image chunk: 36-byte header + pixels
    offsets = []
    chunks = []
    offset = header_size + toc_size
    for im, (xhot, yhot), delay in norm:
        w, h = im.size
        pixels = im.tobytes("raw", "BGRA")  # XCursor is ARGB little-endian = BGRA bytes on LE
        # Actually XCursor pixel format is CARD32 ARGB in native endian.
        # On little-endian: B,G,R,A in memory — PIL "BGRA" raw is correct for that.
        chunk_header = struct.pack(
            "<IIIIiiIII",
            36,  # header size
            XCURSOR_IMAGE_TYPE,
            max(w, h),  # subtype / nominal size
            1,  # version
            w,
            h,
            xhot,
            yhot,
            delay,
        )
        chunk = chunk_header + pixels
        offsets.append(offset)
        chunks.append((max(w, h), chunk))
        offset += len(chunk)

    with open(path, "wb") as f:
        f.write(struct.pack("<4sIII", XCURSOR_MAGIC, header_size, XCURSOR_VERSION, ntoc))
        for subtype, off in ((c[0], o) for c, o in zip(chunks, offsets)):
            f.write(struct.pack("<III", XCURSOR_IMAGE_TYPE, subtype, off))
        for _, chunk in chunks:
            f.write(chunk)


def write_multi_size_xcursor(path: Path, sized: list[tuple[Image.Image, tuple[int, int]]], delay: int = 0):
    """One static cursor with multiple size images, or animated if sized is list of frames at one size.
    For multi-size static: pass one frame per size, delay=0.
    """
    frames = [(im, hot, delay) for im, hot in sized]
    write_xcursor(path, frames)


# ---------------------------------------------------------------------------
# Theme assembly
# ---------------------------------------------------------------------------

# XDG / legacy cursor names → our generator key
# (name, kind, kwargs)
CURSOR_SPEC = [
    ("left_ptr", "arrow"),
    ("arrow", "arrow"),
    ("default", "arrow"),
    ("top_left_arrow", "arrow"),
    ("right_ptr", "arrow_mirror"),
    ("draft_large", "arrow"),
    ("draft_small", "arrow"),
    ("pointer", "hand"),
    ("hand1", "hand"),
    ("hand2", "hand"),
    ("pointing_hand", "hand"),
    ("openhand", "hand"),
    ("grab", "hand"),
    ("grabbing", "hand"),
    ("text", "text"),
    ("xterm", "text"),
    ("ibeam", "text"),
    ("vertical-text", "text"),
    ("crosshair", "crosshair"),
    ("cross", "crosshair"),
    ("tcross", "crosshair"),
    ("move", "move"),
    ("fleur", "move"),
    ("size_all", "move"),
    ("all-scroll", "move"),
    ("not-allowed", "not_allowed"),
    ("crossed_circle", "not_allowed"),
    ("circle", "not_allowed"),
    ("no-drop", "not_allowed"),
    ("forbidden", "not_allowed"),
    ("help", "help"),
    ("question_arrow", "help"),
    ("whats_this", "help"),
    ("progress", "progress"),
    ("left_ptr_watch", "progress"),
    ("half-busy", "progress"),
    ("wait", "wait"),
    ("watch", "wait"),
    ("pencil", "pen"),
    ("cell", "cell"),
    ("plus", "cell"),
    ("alias", "alias"),
    ("context-menu", "context_menu"),
    ("copy", "copy"),
    ("dnd-copy", "copy"),
    ("dnd-move", "move"),
    ("dnd-none", "not_allowed"),
    ("dnd-no-drop", "not_allowed"),
    ("zoom-in", "zoom_in"),
    ("zoom-out", "zoom_out"),
    ("sb_v_double_arrow", "resize", {"direction": "ns"}),
    ("sb_h_double_arrow", "resize", {"direction": "ew"}),
    ("col-resize", "resize", {"direction": "ew"}),
    ("row-resize", "resize", {"direction": "ns"}),
    ("n-resize", "resize", {"direction": "n"}),
    ("s-resize", "resize", {"direction": "s"}),
    ("e-resize", "resize", {"direction": "e"}),
    ("w-resize", "resize", {"direction": "w"}),
    ("ne-resize", "resize", {"direction": "ne"}),
    ("nw-resize", "resize", {"direction": "nw"}),
    ("se-resize", "resize", {"direction": "se"}),
    ("sw-resize", "resize", {"direction": "sw"}),
    ("ew-resize", "resize", {"direction": "ew"}),
    ("ns-resize", "resize", {"direction": "ns"}),
    ("nesw-resize", "resize", {"direction": "nesw"}),
    ("nwse-resize", "resize", {"direction": "nwse"}),
    ("size_ver", "resize", {"direction": "ns"}),
    ("size_hor", "resize", {"direction": "ew"}),
    ("size_bdiag", "resize", {"direction": "nesw"}),
    ("size_fdiag", "resize", {"direction": "nwse"}),
    ("top_side", "resize", {"direction": "n"}),
    ("bottom_side", "resize", {"direction": "s"}),
    ("left_side", "resize", {"direction": "w"}),
    ("right_side", "resize", {"direction": "e"}),
    ("top_left_corner", "resize", {"direction": "nw"}),
    ("top_right_corner", "resize", {"direction": "ne"}),
    ("bottom_left_corner", "resize", {"direction": "sw"}),
    ("bottom_right_corner", "resize", {"direction": "se"}),
    ("up_arrow", "resize", {"direction": "n"}),
]


def mirror_arrow(size: int) -> tuple[Image.Image, tuple[int, int]]:
    im, (hx, hy) = draw_arrow(size)
    im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im, (size - 1 - hx, hy)


def generate_static(kind: str, size: int, kwargs: dict) -> tuple[Image.Image, tuple[int, int]]:
    if kind == "arrow":
        return draw_arrow(size)
    if kind == "arrow_mirror":
        return mirror_arrow(size)
    if kind == "hand":
        return draw_hand(size)
    if kind == "text":
        return draw_text(size)
    if kind == "crosshair":
        return draw_crosshair(size)
    if kind == "move":
        return draw_move(size)
    if kind == "not_allowed":
        return draw_not_allowed(size)
    if kind == "help":
        return draw_help(size)
    if kind == "progress":
        return draw_progress(size)
    if kind == "pen":
        return draw_pen(size)
    if kind == "cell":
        return draw_cell(size)
    if kind == "alias":
        return draw_alias(size)
    if kind == "context_menu":
        return draw_context_menu(size)
    if kind == "copy":
        return draw_copy(size)
    if kind == "zoom_in":
        return draw_zoom(size, plus=True)
    if kind == "zoom_out":
        return draw_zoom(size, plus=False)
    if kind == "resize":
        return draw_resize(size, kwargs.get("direction", "ns"))
    raise ValueError(kind)


def build_theme():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    cursors_dir = BUILD / THEME_NAME / "cursors"
    cursors_dir.mkdir(parents=True)
    PREVIEW.mkdir(parents=True, exist_ok=True)

    # Deduplicate by kind+kwargs so we write each unique cursor once, then symlink names
    unique: dict[tuple, list[str]] = {}
    for entry in CURSOR_SPEC:
        name = entry[0]
        kind = entry[1]
        kwargs = entry[2] if len(entry) > 2 else {}
        key = (kind, tuple(sorted(kwargs.items())))
        unique.setdefault(key, []).append(name)

    built_files = {}  # key -> path

    for key, names in unique.items():
        kind, kw_items = key
        kwargs = dict(kw_items)
        primary = names[0]
        out = cursors_dir / primary

        if kind == "wait":
            # multi-size × multi-frame animation
            frames = []
            for size in SIZES:
                for fi in range(ANIM_FRAMES):
                    im, hot = draw_wait_frame(size, fi, ANIM_FRAMES)
                    frames.append((im, hot, ANIM_DELAY_MS))
            write_xcursor(out, frames)
        else:
            sized = []
            for size in SIZES:
                im, hot = generate_static(kind, size, kwargs)
                sized.append((im, hot))
            write_multi_size_xcursor(out, sized, delay=0)

        built_files[key] = primary
        # symlinks for aliases
        for alias in names[1:]:
            link = cursors_dir / alias
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(primary)

        print(f"  ✓ {primary}  (+{len(names)-1} aliases)")

    # index.theme
    index = BUILD / THEME_NAME / "index.theme"
    index.write_text(
        f"[Icon Theme]\n"
        f"Name={THEME_NAME}\n"
        f"Comment={THEME_COMMENT}\n"
        f'Inherits="hicolor"\n',
        encoding="utf-8",
    )

    # cursor.theme (some desktops)
    (BUILD / THEME_NAME / "cursor.theme").write_text(
        f"[Icon Theme]\nName={THEME_NAME}\n",
        encoding="utf-8",
    )

    # Preview sheet: concept recreation + key cursors
    make_preview(cursors_dir)

    return BUILD / THEME_NAME


def make_preview(cursors_dir: Path):
    """Generate a dark preview sheet in the spirit of the concept art."""
    cell = 160
    cols, rows = 5, 3
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 255))
    items = [
        ("left_ptr", "Default"),
        ("progress", "Progress"),
        ("wait", "Busy"),
        ("pointer", "Hand"),
        ("text", "Text"),
        ("crosshair", "Cross"),
        ("move", "Move"),
        ("not-allowed", "No"),
        ("help", "Help"),
        ("copy", "Copy"),
        ("nwse-resize", "Resize"),
        ("zoom-in", "Zoom+"),
        ("pencil", "Pen"),
        ("context-menu", "Menu"),
        ("cell", "Cell"),
    ]
    # Render fresh high-res for preview (cleaner than decoding xcursor)
    renderers = {
        "left_ptr": lambda s: draw_arrow(s)[0],
        "progress": lambda s: draw_progress(s)[0],
        "wait": lambda s: draw_wait_frame(s, 0, ANIM_FRAMES)[0],
        "pointer": lambda s: draw_hand(s)[0],
        "text": lambda s: draw_text(s)[0],
        "crosshair": lambda s: draw_crosshair(s)[0],
        "move": lambda s: draw_move(s)[0],
        "not-allowed": lambda s: draw_not_allowed(s)[0],
        "help": lambda s: draw_help(s)[0],
        "copy": lambda s: draw_copy(s)[0],
        "nwse-resize": lambda s: draw_resize(s, "nwse")[0],
        "zoom-in": lambda s: draw_zoom(s, True)[0],
        "pencil": lambda s: draw_pen(s)[0],
        "context-menu": lambda s: draw_context_menu(s)[0],
        "cell": lambda s: draw_cell(s)[0],
    }
    for i, (name, _label) in enumerate(items):
        r, c = divmod(i, cols)
        im = renderers[name](96)
        # center in cell
        x = c * cell + (cell - im.size[0]) // 2
        y = r * cell + (cell - im.size[1]) // 2
        sheet.paste(im, (x, y), im)

    sheet_path = PREVIEW / "sheet.png"
    sheet.save(sheet_path)
    print(f"  Preview → {sheet_path}")

    # Large concept-style hero: arrow + CoF like the reference
    hero = Image.new("RGBA", (1000, 1000), (0, 0, 0, 255))
    arrow, _ = draw_arrow(700)
    cof = circle_of_friends(320, 0, orange=False)  # white CoF like the concept
    # also orange version badge
    hero.paste(arrow, (80, 150), arrow)
    hero.paste(cof, (620, 80), cof)
    hero_path = PREVIEW / "concept_hero.png"
    hero.save(hero_path)
    print(f"  Hero    → {hero_path}")

    # Export individual PNG masters for the user
    masters = PREVIEW / "masters"
    masters.mkdir(exist_ok=True)
    for name, fn in renderers.items():
        fn(128).save(masters / f"{name}.png")
    # Animated wait frames
    for fi in range(ANIM_FRAMES):
        draw_wait_frame(128, fi, ANIM_FRAMES)[0].save(masters / f"wait_{fi:02d}.png")
    print(f"  Masters → {masters}")


def install_theme(theme_dir: Path):
    INSTALL.parent.mkdir(parents=True, exist_ok=True)
    if INSTALL.exists():
        shutil.rmtree(INSTALL)
    shutil.copytree(theme_dir, INSTALL)
    print(f"Installed → {INSTALL}")


def main():
    print(f"Building {THEME_NAME}…")
    theme = build_theme()
    install_theme(theme)
    # Apply for GNOME/Ubuntu
    try:
        import subprocess

        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", THEME_NAME],
            check=False,
        )
        print(f"gsettings cursor-theme → {THEME_NAME}")
    except Exception as e:
        print(f"(could not set gsettings: {e})")
    print("Done.")


if __name__ == "__main__":
    main()
