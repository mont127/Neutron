#!/usr/bin/env python3
# list an app's windows depots so they can be pulled with the steam console's
# download_depot command. that path ignores the client platform entirely, so we
# never have to lie to steam about being a windows box.
#   depots.py <appid>   ->  "<depotid> <manifestid> <size> <name>" per line

import sys

import appinfo

SKIP_NAME = ("dlc", "soundtrack", "language pack")


def windows_depots(app):
    out = []
    for key, d in app.get("depots", {}).items():
        if not key.isdigit() or not isinstance(d, dict):
            continue
        cfg = d.get("config", {})
        osl = str(cfg.get("oslist", "")).split(",")
        # a depot with no oslist is shared/common content and still needed
        if osl != [""] and "windows" not in osl:
            continue
        if d.get("dlcappid") or d.get("manifests", {}).get("public") is None:
            continue
        pub = d["manifests"]["public"]
        gid = pub.get("gid") if isinstance(pub, dict) else pub
        size = pub.get("size", 0) if isinstance(pub, dict) else 0
        name = str(d.get("name", ""))
        if any(s in name.lower() for s in SKIP_NAME):
            continue
        out.append((int(key), gid, int(size or 0), name))
    out.sort()
    return out


def main(argv):
    appid = int(argv[1])
    apps = appinfo.load_appinfo(only_appids={appid})
    app = apps.get(appid)
    if not app:
        return 1
    rows = windows_depots(app)
    if not rows:
        return 2
    for depot, manifest, size, name in rows:
        print("%d %s %d %s" % (depot, manifest, size, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
