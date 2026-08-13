#!/usr/bin/env python3
# classify the games in your steam library: native mac, windows-only, or worth a
# look. prefer macos always; neutron only handles windows-only.
#
# the library is everything steam has cached art for, not just what is
# installed.
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


def _ours(entry):
    # the shim we write into a game's launch entries, see appoverlay.DEFAULT_SHIM
    return "Neutron Runtime" in str(entry.get("executable", ""))


def neutronized(app):
    return any(isinstance(e, dict) and _ours(e)
               for e in app.get("config", {}).get("launch", {}).values())


def has_real_mac_launch(app):
    # a mac launch entry that is not the one we added, i.e. a genuine mac build
    for entry in app.get("config", {}).get("launch", {}).values():
        if not isinstance(entry, dict) or _ours(entry):
            continue
        os_ = str(entry.get("config", {}).get("oslist", "")).lower()
        if "macos" in os_ or "macosx" in os_:
            return True
    return False


def main(argv):
    steam = argv[1]
    installed = installed_ids(steam)
    if argv[2:]:
        ids = {int(a) for a in argv[2:]}
        apps = appinfo.load_appinfo(only_appids=ids)
    else:
        # librarycache is steam's artwork cache and fills in as you browse, so on
        # a machine that has just logged in it is nearly empty and most of the
        # library never gets classified: the game keeps a greyed out Install and
        # nothing explains why. appinfo has an entry for every app steam knows
        # about locally, which is what the library list itself is drawn from.
        apps = appinfo.load_appinfo()
        ids = installed | library_ids(steam) | set(apps.keys())
    rows = []
    for i in sorted(ids):
        app = apps.get(i)
        if app:
            common = app.get("common", {})
            # skip things that are not games: tools, demos of demos, redists
            # dlc is not installable on its own and only adds noise to the
            # review list; demos are ordinary installable games, so they stay
            if str(common.get("type", "game")).lower() in ("tool", "config",
                                                           "application", "dlc"):
                continue
            verdict = appinfo.assess_macos_build(app)[0]
            name = common.get("name", "?")
            # our own overlay adds macos to oslist and a macos launch entry with
            # no matching depot, which is exactly the shape assess calls
            # "suspect". left alone, a game we already patched stops being ours
            # on the next run: enable-all skips it and uninstall never reverts it
            # but only when the mac side is ours alone: a game with a real mac
            # launch entry keeps its own verdict, whatever we did to it
            if neutronized(app) and not has_real_mac_launch(app):
                verdict = "windows-only"
        else:
            verdict, name = "unknown", "?"
        rows.append((i, verdict, ACTION.get(verdict, "review"),
                     1 if i in installed else 0, name))

    for appid, verdict, action, inst, name in rows:
        print("%d|%s|%s|%d|%s" % (appid, verdict, action, inst, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
