#!/usr/bin/env python3
# give a non-steam shortcut the game's real steam artwork, so it looks like any
# other game in the library instead of a grey box with a filename.
#
# steam keeps art for owned apps in appcache/librarycache/<appid>/, so we copy
# from there first and only hit the cdn for what is missing.
#   artwork.py <steam_dir> <appid> <shortcut_name> <exe>

import os
import shutil
import sys
import urllib.request

import shortcuts

# grid file suffix -> (librarycache names to try, cdn names to try)
ART = {
    "p": (["library_600x900.jpg", "library_600x900_2x.jpg"],
          ["library_600x900_2x.jpg", "library_600x900.jpg"]),
    "": (["header.jpg"], ["header.jpg"]),
    "_hero": (["library_hero.jpg"], ["library_hero.jpg"]),
    "_logo": (["logo.png", "library_logo.png"], ["logo.png"]),
}

CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/%s/%s"


def grid_dirs(steam):
    out = []
    base = os.path.join(steam, "userdata")
    if not os.path.isdir(base):
        return out
    for user in os.listdir(base):
        cfg = os.path.join(base, user, "config")
        if os.path.isdir(cfg):
            g = os.path.join(cfg, "grid")
            os.makedirs(g, exist_ok=True)
            out.append(g)
    return out


def fetch(appid, name, dest):
    try:
        req = urllib.request.Request(CDN % (appid, name), headers={"User-Agent": "neutron"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status != 200:
                return False
            data = r.read()
        if len(data) < 1000:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def main(argv):
    steam, appid, name, exe = argv[1], argv[2], argv[3], argv[4]
    short_id = shortcuts.shortcut_appid('"%s"' % exe, name)
    cache = os.path.join(steam, "appcache", "librarycache", appid)
    installed = 0

    for suffix, (local_names, cdn_names) in ART.items():
        src = None
        for n in local_names:
            p = os.path.join(cache, n)
            if os.path.isfile(p) and os.path.getsize(p) > 1000:
                src = p
                break
        for g in grid_dirs(steam):
            ext = ".png" if (src or "").endswith(".png") or suffix == "_logo" else ".jpg"
            dest = os.path.join(g, "%d%s%s" % (short_id, suffix, ext))
            if src:
                shutil.copyfile(src, dest)
                installed += 1
            else:
                for n in cdn_names:
                    if fetch(appid, n, dest):
                        installed += 1
                        break

    print("installed %d artwork files for shortcut %d" % (installed, short_id))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
