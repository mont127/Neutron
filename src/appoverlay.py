#!/usr/bin/env python3
# make one windows-only app look macOS-eligible to the local steam client, by
# editing only its entry in the appinfo cache. nothing on valve's side changes
# and no other app is touched.
#
#   appoverlay.py show   <appinfo.vdf> <appid>
#   appoverlay.py enable <appinfo.vdf> <appid> [launch-exe-relative-path]
#   appoverlay.py revert <appinfo.vdf> <appid> <backup-appinfo.vdf>
#
# steam refreshes appinfo from its servers, so an overlay is not permanent;
# re-run enable after steam updates the app.

import sys

from appinfo_write import (Appinfo, MAP, STR, find, get, set_str, add_os)

LAUNCH_KEY = "9000"           # our own launch entry, well clear of valve's
DEFAULT_SHIM = "../Neutron Runtime/neutron-launch"


def app_root(node):
    # entry is a single "appinfo" map
    if len(node) == 1 and node[0][1].lower() == "appinfo":
        return node[0][2]
    return node


def describe(root):
    common = get(root, "common") or []
    config = get(root, "config") or []
    depots = get(root, "depots") or []
    print("  name:        %s" % (get(common, "name") or "?"))
    print("  common oslist: %s" % (get(common, "oslist") or "-"))
    launches = get(config, "launch") or []
    for t, key, entry in launches:
        if t != MAP:
            continue
        cfg = get(entry, "config") or []
        print("  launch %-5s exe=%-42s oslist=%s" % (
            key, str(get(entry, "executable"))[:42], get(cfg, "oslist") or "-"))
    for t, key, d in depots:
        if t != MAP or not key.isdigit():
            continue
        cfg = get(d, "config") or []
        print("  depot %-9s oslist=%s" % (key, get(cfg, "oslist") or "-"))


def neutronize(root, appid, shim):
    changed = []
    common = get(root, "common")
    if common is not None and add_os(common, "oslist"):
        changed.append("common.oslist += macos")

    depots = get(root, "depots") or []
    for t, key, d in depots:
        if t != MAP or not key.isdigit():
            continue
        cfg = get(d, "config")
        if cfg is None:
            continue
        osl = str(get(cfg, "oslist") or "")
        if "windows" in osl and add_os(cfg, "oslist"):
            changed.append("depot %s oslist += macos" % key)

    config = get(root, "config")
    if config is None:
        config = []
        root.append((MAP, "config", config))
    i = find(config, "launch")
    if i < 0:
        launches = []
        config.append((MAP, "launch", launches))
    else:
        launches = config[i][2]

    # a launch entry with no oslist matches every platform, so on a mac steam
    # would offer BOTH the raw .exe and ours and ask the user which to run. pin
    # the game's own entries to windows so only ours shows up here.
    for t, key, entry in launches:
        if t != MAP or key == LAUNCH_KEY:
            continue
        cfg = get(entry, "config")
        if cfg is None:
            cfg = []
            entry.append((MAP, "config", cfg))
        if not str(get(cfg, "oslist") or "").strip():
            set_str(cfg, "oslist", "windows")
            changed.append("launch %s pinned to windows (was any-platform)" % key)

    # replace ours if it is already there, so fixes land on a re-run
    old = find(launches, LAUNCH_KEY)
    if old >= 0:
        del launches[old]
    if True:
        entry = [
            (STR, "executable", shim),
            (STR, "arguments", "--appid %d" % appid),
            (STR, "type", "default"),
            # say 64-bit explicitly: with no osarch steam assumes the macOS build
            # is a legacy 32-bit one and warns that it cannot run
            (MAP, "config", [(STR, "oslist", "macos"), (STR, "osarch", "64")]),
        ]
        launches.append((MAP, LAUNCH_KEY, entry))
        changed.append("%s macOS launch entry %s -> %s" % ("refreshed" if old >= 0 else "added", LAUNCH_KEY, shim))

    # same reason, at the app level
    if common is not None and str(get(common, "osarch") or "") != "64":
        set_str(common, "osarch", "64")
        changed.append("common.osarch = 64 (stops the 32-bit warning)")
    return changed


def main(argv):
    action, path, appid = argv[1], argv[2], int(argv[3])
    a = Appinfo(path)
    got = a.get_app(appid)
    if not got:
        print("app %d is not in the cache" % appid)
        return 1
    header, node = got
    root = app_root(node)

    if action == "show":
        describe(root)
        return 0

    # "is this app fully up to date with the current overlay?" - exit 0 if yes.
    # checks more than mere presence, so an overlay written by an older neutron
    # gets refreshed instead of being left half-done.
    if action == "check":
        config = get(root, "config") or []
        launches = get(config, "launch") or []
        i = find(launches, LAUNCH_KEY)
        if i < 0:
            return 1
        cfg = get(launches[i][2], "config") or []
        if str(get(cfg, "osarch") or "") != "64":
            return 1
        common = get(root, "common") or []
        if "macos" not in str(get(common, "oslist") or ""):
            return 1
        if str(get(common, "osarch") or "") != "64":
            return 1
        # any of the game's own entries still matching every platform?
        for t, key, entry in launches:
            if t != MAP or key == LAUNCH_KEY:
                continue
            c = get(entry, "config") or []
            if not str(get(c, "oslist") or "").strip():
                return 1
        return 0

    if action == "enable":
        shim = argv[4] if len(argv) > 4 else DEFAULT_SHIM
        print("before:")
        describe(root)
        changed = neutronize(root, appid, shim)
        if not changed:
            print("nothing to change")
            return 0
        # steam refreshes an entry whose change number is older than the one PICS
        # reports, which wipes the overlay on the next start. pin it high so the
        # local copy looks current.
        import struct as _s
        header = bytearray(header)
        old_change = _s.unpack("<I", bytes(header[36:40]))[0]
        _s.pack_into("<I", header, 36, 0xFFFFFFF0)
        header = bytes(header)
        changed.append("pinned change number %d -> 4294967280" % old_change)
        a.rewrite(path, appid, header, node)
        print("\nchanged:")
        for c in changed:
            print("  - %s" % c)
        print("\nafter:")
        describe(app_root(Appinfo(path).get_app(appid)[1]))
        return 0

    if action == "revert":
        backup = argv[4]
        b = Appinfo(backup)
        got_b = b.get_app(appid)
        if not got_b:
            print("app not in backup")
            return 1
        hdr_b, node_b = got_b
        a.rewrite(path, appid, hdr_b, node_b)
        print("reverted app %d from %s" % (appid, backup))
        return 0

    print("unknown action %r" % action)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
