#!/usr/bin/env python3
# resolve an installed steam app to its windows exe, install dir and name.
#   gameexe.py <steam_dir> <appid>   ->  "<install dir>|<exe path>|<name>"
# exits non-zero if the app is not installed.

import sys
import os
import re
import glob

import appinfo


def installdir(steam, appid):
    p = os.path.join(steam, "steamapps", "appmanifest_%d.acf" % appid)
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r'"installdir"\s*"([^"]+)"', txt)
    return m.group(1) if m else None


def windows_exe(app):
    launch = app.get("config", {}).get("launch", {})
    fallback = None
    for _, e in sorted(launch.items()):
        if not isinstance(e, dict):
            continue
        exe = e.get("executable", "")
        if not exe:
            continue
        osl = str(e.get("config", {}).get("oslist", "")).split(",")
        if "windows" in osl or osl == [""]:
            return exe
        if fallback is None:
            fallback = exe
    return fallback


def scan_exe(base):
    # last resort: biggest .exe under the install dir that isnt an obvious helper
    best, best_size = None, -1
    skip = ("unins", "vcredist", "dxsetup", "setup", "crashreport", "launcher_installer")
    for root, _, files in os.walk(base):
        for name in files:
            if not name.lower().endswith(".exe"):
                continue
            if any(s in name.lower() for s in skip):
                continue
            p = os.path.join(root, name)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if size > best_size:
                best, best_size = p, size
    return best


def main(argv):
    steam, appid = argv[1], int(argv[2])
    idir = installdir(steam, appid)
    if not idir:
        return 1
    base = os.path.join(steam, "steamapps", "common", idir)
    apps = appinfo.load_appinfo(only_appids={appid})
    app = apps.get(appid, {})
    name = app.get("common", {}).get("name", idir)

    exe = ""
    rel = windows_exe(app)
    if rel:
        cand = os.path.join(base, rel.replace("\\", "/"))
        if os.path.isfile(cand):
            exe = cand
    if not exe:
        exe = scan_exe(base) or ""

    print("%s|%s|%s" % (base, exe, name))
    return 0 if exe else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
