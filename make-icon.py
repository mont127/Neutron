#!/usr/bin/env python3
# build the app icon and the mark the ui draws, from Logo.png.
#
#   make-icon.py [Logo.png] [out-dir]
#
# the source is a small two-tone bitmap. thresholding it back to two levels after
# the upscale carves the original 220px grid into a staircase on every curve, so
# it is left as a smooth resize instead.

import sys, os, subprocess
from PIL import Image, ImageDraw

SRC = sys.argv[1] if len(sys.argv) > 1 else "Logo.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ui/assets"

GLYPH = (0, 0, 0)
TILE_BG = (183, 183, 183)
WORK = 4096


def mask_from(path):
    im = Image.open(path).convert("L")
    w, h = im.size
    side = max(w, h)
    square = Image.new("L", (side, side), 255)
    square.paste(im, ((side - w) // 2, (side - h) // 2))
    big = square.resize((WORK, WORK), Image.LANCZOS)
    return big.point(lambda v: max(0, min(255, int((150 - v) * 255 / 60))))


def squircle(side, radius):
    m = Image.new("L", (side * 4, side * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, side * 4 - 1, side * 4 - 1],
                                        radius=radius * 4, fill=255)
    return m.resize((side, side), Image.LANCZOS)


def mark(mask, side):
    img = Image.new("RGBA", (side, side), GLYPH + (0,))
    img.putalpha(mask.resize((side, side), Image.LANCZOS))
    return img


def icon(mask, side):
    # apple insets the art rather than filling the canvas
    tile = int(side * 0.805)
    art = int(tile * 0.78)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    plate = Image.new("RGBA", (tile, tile), TILE_BG + (255,))
    plate.putalpha(squircle(tile, int(tile * 0.2237)))
    canvas.paste(plate, ((side - tile) // 2, (side - tile) // 2), plate)
    g = mark(mask, art)
    canvas.paste(g, ((side - art) // 2, (side - art) // 2), g)
    return canvas


def main():
    if not os.path.exists(SRC):
        sys.exit("no %s" % SRC)
    os.makedirs(OUT, exist_ok=True)
    m = mask_from(SRC)

    mark(m, 512).save(os.path.join(OUT, "mark.png"))
    print("  mark.png")

    iconset = os.path.join(OUT, "Neutron.iconset")
    os.makedirs(iconset, exist_ok=True)
    for pt in (16, 32, 128, 256, 512):
        icon(m, pt).save(os.path.join(iconset, "icon_%dx%d.png" % (pt, pt)))
        icon(m, pt * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (pt, pt)))
    icns = os.path.join(OUT, "Neutron.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    print("  Neutron.icns (%d KB)" % (os.path.getsize(icns) // 1024))
    icon(m, 1024).save(os.path.join(OUT, "icon-preview.png"))


main()
