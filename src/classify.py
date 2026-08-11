#!/usr/bin/env python3
# classify the games in your steam library: native mac, windows-only, or worth a
# look. prefer macos always; neutron only handles windows-only.
#
# the library is everything steam has cached art for, not just what is installed
# - an installer ui has to be able to show you a game you have NOT installed yet.
#
#   classify.py <steam_dir> [appid ...]
# prints:  appid|verdict|action|installed|name

import glob
import os
import re
import sys

import appinfo

ACTION = {"native-ok": "macos", "windows-only": "neutron", "suspect": "review"}


def installed_ids(steam):
    ids = set()
    for acf in glob.glob(os.path.join(steam, "steamapps", "appmanifest_*.acf")):
        m = re.search(r"appmanifest_(\d+)\.acf", acf)
        if m:
            ids.add(int(m.group(1)))
    return ids


def library_ids(steam):
    ids = set()
    cache = os.path.join(steam, "appcache", "librarycache")
    if os.path.isdir(cache):
        for name in os.listdir(cache):
            if name.isdigit():
                ids.add(int(name))
    return ids


def main(argv):
    steam = argv[1]
    installed = installed_ids(steam)
    if argv[2:]:
        ids = {int(a) for a in argv[2:]}
    else:
        ids = installed | library_ids(steam)

    apps = appinfo.load_appinfo(only_appids=ids)
    rows = []
    for i in sorted(ids):
        app = apps.get(i)
        if app:
            common = app.get("common", {})
            # skip things that are not games: tools, demos of demos, redists
            if str(common.get("type", "game")).lower() in ("tool", "config", "application"):
                continue
            verdict = appinfo.assess_macos_build(app)[0]
            name = common.get("name", "?")
        else:
            verdict, name = "unknown", "?"
        rows.append((i, verdict, ACTION.get(verdict, "review"),
                     1 if i in installed else 0, name))

    for appid, verdict, action, inst, name in rows:
        print("%d|%s|%s|%d|%s" % (appid, verdict, action, inst, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
