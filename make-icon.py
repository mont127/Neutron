#!/usr/bin/env python3
# build the app icon, the mark the ui draws and the readme wordmark, from the
# purple-on-grey artwork.
#
#   make-icon.py [Logo.png] [out-dir] [Wordmark.png]
#
# the artwork is flat colour on flat grey. coverage is taken as the largest
# per-channel drop from the background, then the pixel is un-premultiplied
# against that background, so antialiased strokes keep their real colour instead
# of picking up a grey halo. exact for any ink with a channel at 0, which the
# red/green/blue rings all have.

import sys, os, subprocess
from PIL import Image, ImageDraw

SRC = sys.argv[1] if len(sys.argv) > 1 else "Logo.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ui/assets"
WORD = sys.argv[3] if len(sys.argv) > 3 else None

BG = (183, 183, 183)
TILE_BG = BG
WORK = 4096


def keyed(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    out = Image.new("RGBA", (w, h))
    src, dst = im.load(), out.load()
    for y in range(h):
        for x in range(w):
            p = src[x, y]
            a = max((BG[i] - p[i]) / BG[i] for i in range(3))
            if a <= 0.004:
                dst[x, y] = (0, 0, 0, 0)
                continue
            if a > 1.0:
                a = 1.0
            r, g, b = p
            # undo the blend against the grey so edges are not milky
            cr = (r - BG[0] * (1 - a)) / a
            cg = (g - BG[1] * (1 - a)) / a
            cb = (b - BG[2] * (1 - a)) / a
            clamp = lambda v: 0 if v < 0 else (255 if v > 255 else int(round(v)))
            dst[x, y] = (clamp(cr), clamp(cg), clamp(cb), int(round(a * 255)))
    return out


def squircle(side, radius):
    m = Image.new("L", (side * 4, side * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, side * 4 - 1, side * 4 - 1],
                                        radius=radius * 4, fill=255)
    return m.resize((side, side), Image.LANCZOS)


def square(img):
    w, h = img.size
    side = max(w, h)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(img, ((side - w) // 2, (side - h) // 2))
    return out


def icon(mark, side):
    # apple insets the art rather than filling the canvas
    tile = int(side * 0.805)
    art = int(tile * 0.80)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    plate = Image.new("RGBA", (tile, tile), TILE_BG + (255,))
    plate.putalpha(squircle(tile, int(tile * 0.2237)))
    canvas.paste(plate, ((side - tile) // 2, (side - tile) // 2), plate)
    g = mark.resize((art, art), Image.LANCZOS)
    canvas.paste(g, ((side - art) // 2, (side - art) // 2), g)
    return canvas


def main():
    if not os.path.exists(SRC):
        sys.exit("no %s" % SRC)
    os.makedirs(OUT, exist_ok=True)

    ink = keyed(SRC)
    # tight, original aspect, for the readme
    tight = ink.crop(ink.getbbox()) if ink.getbbox() else ink
    tight = tight.resize((tight.width * 3, tight.height * 3), Image.LANCZOS)
    tight.save(os.path.join(OUT, "logo.png"))
    print("  logo.png (%dx%d)" % tight.size)

    mark = square(ink).resize((WORK, WORK), Image.LANCZOS)
    mark.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "mark.png"))
    print("  mark.png")

    iconset = os.path.join(OUT, "Neutron.iconset")
    os.makedirs(iconset, exist_ok=True)
    for pt in (16, 32, 128, 256, 512):
        icon(mark, pt).save(os.path.join(iconset, "icon_%dx%d.png" % (pt, pt)))
        icon(mark, pt * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (pt, pt)))
    icns = os.path.join(OUT, "Neutron.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    print("  Neutron.icns (%d KB)" % (os.path.getsize(icns) // 1024))
    icon(mark, 1024).save(os.path.join(OUT, "icon-preview.png"))

    if WORD and os.path.exists(WORD):
        w = keyed(WORD)
        w = w.resize((w.width * 2, w.height * 2), Image.LANCZOS)
        w.save(os.path.join(OUT, "wordmark.png"))
        print("  wordmark.png (%dx%d)" % w.size)


main()
