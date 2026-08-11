#!/usr/bin/env python3
# pick a game's main exe: the biggest one that isnt an installer or helper.
#   findexe.py <dir>

import os
import sys

SKIP = ("unins", "vcredist", "dxsetup", "crashhandler", "setup",
        "launcher_installer", "dotnetfx", "directx")


def main(argv):
    base = argv[1]
    best, size = "", -1
    for root, _, files in os.walk(base):
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            if any(s in f.lower() for s in SKIP):
                continue
            p = os.path.join(root, f)
            try:
                n = os.path.getsize(p)
            except OSError:
                continue
            if n > size:
                best, size = p, n
    print(best)
    return 0 if best else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
