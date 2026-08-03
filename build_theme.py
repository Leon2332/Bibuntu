#!/usr/bin/env python3
"""
Build Bibuntu (XCursor) from src/svg.

Bibuntu — a cursor theme for Ubuntu based on Bibata.

- Hotspots, sizes, and aliases match Bibata Modern (reference config).
- Sources: src/svg/*.svg plus animated wait/ and left_ptr_watch/.
- Installs to ~/.local/share/icons/Bibuntu
"""

from __future__ import annotations

import math
import re
import shutil
import struct
import sys
from pathlib import Path

import gi

gi.require_version("Rsvg", "2.0")
gi.require_version("cairo", "1.0")
from gi.repository import Rsvg  # noqa: E402
import cairo  # noqa: E402
from PIL import Image  # noqa: E402

# ---------------------------------------------------------------------------
# Paths / theme meta
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "svg"
BUILD = ROOT / "build" / "Bibuntu"
BITMAPS = ROOT / "build" / "bitmaps"
INSTALL = Path.home() / ".local" / "share" / "icons" / "Bibuntu"
# Hotspots, sizes, and X11 aliases (from Bibata Modern x.build.toml)
BIBATA_TOML = ROOT / "configs" / "x.build.toml"

THEME_NAME = "Bibuntu"
THEME_COMMENT = "A cursor theme for Ubuntu based on Bibata"
CANVAS = 256  # design canvas size

# Animation delay: Bibata uses 40ms for 54 frames. We have 8 frames — 50ms
# keeps a readable spin (~0.4s/loop) without looking frantic.
ANIM_DELAY_MS = 50

XCURSOR_MAGIC = b"Xcur"
XCURSOR_IMAGE_TYPE = 0xFFFD0002
XCURSOR_VERSION = 0x00010000


# ---------------------------------------------------------------------------
# Bibata config parser (minimal TOML subset used by x.build.toml)
# ---------------------------------------------------------------------------

def parse_bibata_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"\n\[cursors\.([^\]]+)\]\n", text)

    # Defaults (overwritten by [cursors.fallback_settings] if present)
    sizes = [16, 20, 22, 24, 28, 32, 40, 48, 56, 64, 72, 80, 88, 96]
    def_x, def_y, delay = 128, 128, 40

    cursors: dict[str, dict] = {}
    for i in range(1, len(sections), 2):
        key = sections[i]
        body = sections[i + 1]

        if key == "fallback_settings":
            sizes_m = re.search(r"x11_sizes\s*=\s*\[([^\]]+)\]", body)
            if sizes_m:
                sizes = [int(x.strip()) for x in sizes_m.group(1).split(",")]
            xm = re.search(r"x_hotspot\s*=\s*(\d+)", body)
            ym = re.search(r"y_hotspot\s*=\s*(\d+)", body)
            dm = re.search(r"x11_delay\s*=\s*(\d+)", body)
            if xm:
                def_x = int(xm.group(1))
            if ym:
                def_y = int(ym.group(1))
            if dm:
                delay = int(dm.group(1))
            continue

        def grab_int(name: str, default: int) -> int:
            m = re.search(rf"{name}\s*=\s*(\d+)", body)
            return int(m.group(1)) if m else default

        x11_name_m = re.search(r"x11_name\s*=\s*'([^']+)'", body)
        x11_name = x11_name_m.group(1) if x11_name_m else key

        png_m = re.search(r"png\s*=\s*'([^']+)'", body)
        png = png_m.group(1) if png_m else f"{key}.png"

        aliases: list[str] = []
        sym = re.search(r"x11_symlinks\s*=\s*\[([^\]]*)\]", body, re.S)
        if sym:
            aliases = [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", sym.group(1))]

        cursors[key] = {
            "key": key,
            "x11_name": x11_name,
            "png": png,
            "x_hotspot": grab_int("x_hotspot", def_x),
            "y_hotspot": grab_int("y_hotspot", def_y),
            "aliases": aliases,
            "animated": "*" in png,
        }

    return {
        "sizes": sizes,
        "default_hotspot": (def_x, def_y),
        "delay": delay,
        "cursors": cursors,
    }


# ---------------------------------------------------------------------------
# SVG → PNG (librsvg)
# ---------------------------------------------------------------------------

# Supersample factor: render larger, then Lanczos-downscale for clean edges.
# Small cursors (16–32) need more AA; large sizes use a lighter factor for speed.
def _ss_factor(size: int) -> int:
    if size <= 24:
        return 8
    if size <= 48:
        return 4
    if size <= 72:
        return 2
    return 1


def render_svg(svg_path: Path, size: int) -> Image.Image:
    """Rasterize SVG to `size`×`size` with high-quality anti-aliasing."""
    factor = _ss_factor(size)
    render_size = size * factor

    handle = Rsvg.Handle.new_from_file(str(svg_path))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, render_size, render_size)
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.Antialias.BEST)
    scale = render_size / float(CANVAS)
    ctx.scale(scale, scale)
    viewport = Rsvg.Rectangle()
    viewport.x = 0
    viewport.y = 0
    viewport.width = CANVAS
    viewport.height = CANVAS
    handle.render_document(ctx, viewport)

    # Cairo ARGB32 little-endian → BGRA bytes
    buf = bytes(surface.get_data())
    img = Image.frombuffer("RGBA", (render_size, render_size), buf, "raw", "BGRa", 0, 1).copy()

    if factor == 1:
        return img

    # Resize RGB and alpha separately so edges don't pick up dark fringes
    # from premultiplied-style blending during Lanczos.
    rgb = img.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    alpha = img.getchannel("A").resize((size, size), Image.Resampling.LANCZOS)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def scale_hotspot(hx: int, hy: int, size: int) -> tuple[int, int]:
    return (
        min(size - 1, max(0, round(hx * size / CANVAS))),
        min(size - 1, max(0, round(hy * size / CANVAS))),
    )


# ---------------------------------------------------------------------------
# XCursor writer
# ---------------------------------------------------------------------------

def write_xcursor(path: Path, frames: list[tuple[Image.Image, tuple[int, int], int]]) -> None:
    """frames: (image, (xhot, yhot), delay_ms)"""
    norm: list[tuple[Image.Image, tuple[int, int], int]] = []
    for im, hot, delay in frames:
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        norm.append((im, hot, delay))

    ntoc = len(norm)
    header_size = 16
    toc_size = ntoc * 12
    offsets: list[int] = []
    chunks: list[tuple[int, bytes]] = []
    offset = header_size + toc_size

    for im, (xhot, yhot), delay in norm:
        w, h = im.size
        pixels = im.tobytes("raw", "BGRA")
        chunk_header = struct.pack(
            "<IIIIiiIII",
            36,
            XCURSOR_IMAGE_TYPE,
            max(w, h),
            1,
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

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sIII", XCURSOR_MAGIC, header_size, XCURSOR_VERSION, ntoc))
        for (subtype, _), off in zip(chunks, offsets):
            f.write(struct.pack("<III", XCURSOR_IMAGE_TYPE, subtype, off))
        for _, chunk in chunks:
            f.write(chunk)


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def resolve_static_svg(key: str, png_pattern: str) -> Path | None:
    """Map Bibata cursor key / png name to src/svg file."""
    candidates = [
        SRC / f"{key}.svg",
        SRC / png_pattern.replace(".png", ".svg").replace("*", ""),
    ]
    # zoom_in → zoom-in.svg
    if key == "zoom_in":
        candidates.insert(0, SRC / "zoom-in.svg")
    if key == "zoom_out":
        candidates.insert(0, SRC / "zoom-out.svg")
    # hyphen/underscore variants
    candidates.append(SRC / f"{key.replace('_', '-')}.svg")
    candidates.append(SRC / f"{key.replace('-', '_')}.svg")

    for c in candidates:
        if c.is_file():
            return c
    return None


def resolve_anim_frames(key: str) -> list[Path]:
    """Ordered frame SVGs for wait / left_ptr_watch."""
    folder = SRC / key
    if not folder.is_dir():
        # try hyphen variant
        folder = SRC / key.replace("_", "-")
    if not folder.is_dir():
        return []

    frames = list(folder.glob("*.svg"))

    def sort_key(p: Path):
        m = re.search(r"(\d+)", p.stem)
        return int(m.group(1)) if m else p.stem

    return sorted(frames, key=sort_key)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(install: bool = True) -> None:
    if not BIBATA_TOML.is_file():
        sys.exit(f"Missing Bibata config: {BIBATA_TOML}")
    if not SRC.is_dir():
        sys.exit(f"Missing sources: {SRC}")

    cfg = parse_bibata_config(BIBATA_TOML)
    sizes: list[int] = cfg["sizes"]
    # Prefer slightly slower delay for short frame counts
    anim_delay = ANIM_DELAY_MS

    print(f"Theme:     {THEME_NAME}")
    print(f"Sources:   {SRC}")
    print(f"Sizes:     {sizes}")
    print(f"Anim delay:{anim_delay} ms")
    print(f"Cursors:   {len(cfg['cursors'])}")

    # clean build dirs
    if BUILD.exists():
        shutil.rmtree(BUILD)
    if BITMAPS.exists():
        shutil.rmtree(BITMAPS)
    cursors_dir = BUILD / "cursors"
    cursors_dir.mkdir(parents=True)
    BITMAPS.mkdir(parents=True)

    missing: list[str] = []
    built = 0

    for key, meta in cfg["cursors"].items():
        x11_name = meta["x11_name"]
        hx, hy = meta["x_hotspot"], meta["y_hotspot"]
        out_path = cursors_dir / x11_name

        if meta["animated"]:
            frames_svg = resolve_anim_frames(key)
            if not frames_svg:
                missing.append(key)
                print(f"  SKIP animated (no frames): {key}")
                continue

            print(f"  anim {x11_name}: {len(frames_svg)} frames × {len(sizes)} sizes")
            xframes: list[tuple[Image.Image, tuple[int, int], int]] = []
            for size in sizes:
                hot = scale_hotspot(hx, hy, size)
                for i, svg in enumerate(frames_svg):
                    im = render_svg(svg, size)
                    # keep a master preview of first size only
                    if size == 32:
                        prev = BITMAPS / f"{x11_name}_{i:02d}.png"
                        im.save(prev)
                    xframes.append((im, hot, anim_delay))
            write_xcursor(out_path, xframes)
        else:
            svg = resolve_static_svg(key, meta["png"])
            if not svg:
                missing.append(key)
                print(f"  SKIP static (no svg): {key}")
                continue

            print(f"  static {x11_name} ← {svg.name}  hotspot=({hx},{hy})")
            xframes = []
            for size in sizes:
                im = render_svg(svg, size)
                hot = scale_hotspot(hx, hy, size)
                xframes.append((im, hot, 0))
                if size == 32:
                    im.save(BITMAPS / f"{x11_name}.png")
            write_xcursor(out_path, xframes)

        # aliases / symlinks
        for alias in meta["aliases"]:
            link = cursors_dir / alias
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(x11_name)

        built += 1

    # Optional extras in src not in Bibata x11 list (person, pin)
    for extra in ("person", "pin"):
        svg = SRC / f"{extra}.svg"
        dest = cursors_dir / extra
        if svg.is_file() and not dest.exists():
            print(f"  extra {extra} (center hotspot)")
            hx, hy = cfg["default_hotspot"]
            xframes = []
            for size in sizes:
                im = render_svg(svg, size)
                xframes.append((im, scale_hotspot(hx, hy, size), 0))
            write_xcursor(dest, xframes)
            built += 1

    # index.theme + cursor.theme
    (BUILD / "index.theme").write_text(
        f"[Icon Theme]\n"
        f"Name={THEME_NAME}\n"
        f"Comment={THEME_COMMENT}\n"
        f"Inherits=Bibata-Modern-Classic\n",
        encoding="utf-8",
    )
    (BUILD / "cursor.theme").write_text(
        f"[Icon Theme]\nName={THEME_NAME}\n",
        encoding="utf-8",
    )

    print(f"\nBuilt {built} cursors → {BUILD}")
    if missing:
        print("Missing sources:", ", ".join(missing))

    if install:
        if INSTALL.exists():
            shutil.rmtree(INSTALL)
        shutil.copytree(BUILD, INSTALL, symlinks=True)
        print(f"Installed → {INSTALL}")
        print(
            "\nApply with:\n"
            f"  gsettings set org.gnome.desktop.interface cursor-theme '{THEME_NAME}'\n"
            "  gsettings set org.gnome.desktop.interface cursor-size 24\n"
            "  # then log out/in or restart the session if needed"
        )


if __name__ == "__main__":
    install = "--no-install" not in sys.argv
    build(install=install)
