#!/usr/bin/env python3
# classify installed steam apps: native mac, windows-only, or worth a look.
# prefer macos always; neutron only handles windows-only.
#   classify.py <steam_dir> [appid ...]      (no appids = every installed app)
# prints one line per app:  appid|verdict|action|name

import sys
import os
import re
import glob

import appinfo

ACTION = {"native-ok": "macos", "windows-only": "neutron", "suspect": "review"}


def installed_ids(steam):
    ids = []
    for acf in glob.glob(os.path.join(steam, "steamapps", "appmanifest_*.acf")):
        m = re.search(r"appmanifest_(\d+)\.acf", acf)
        if m:
            ids.append(int(m.group(1)))
    return ids


def main(argv):
    steam = argv[1]
    ids = [int(a) for a in argv[2:]] or installed_ids(steam)
    apps = appinfo.load_appinfo(only_appids=set(ids))
    for i in sorted(set(ids)):
        app = apps.get(i)
        if app:
            verdict = appinfo.assess_macos_build(app)[0]
            name = app.get("common", {}).get("name", "?")
        else:
            verdict, name = "unknown", "?"
        print("%d|%s|%s|%s" % (i, verdict, ACTION.get(verdict, "review"), name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
