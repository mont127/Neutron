#!/usr/bin/env python3
# set/clear steam's CompatToolMapping in registry.vdf. appid "0" is the global
# default that makes windows-only titles installable, same as enabling steam
# play for all titles on linux. steam must be closed, it rewrites this on exit.
#   compatmap.py set   <registry.vdf> <appid> <toolname> [priority]
#   compatmap.py clear <registry.vdf> <appid>
#   compatmap.py list  <registry.vdf>

import sys

import textvdf as v

PATH = ["Registry", "HKCU", "Software", "Valve", "Steam", "CompatToolMapping"]


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    action, path = argv[1], argv[2]
    root = v.load(path)

    if action == "list":
        node = v.walk(root, PATH)
        for appid, cfg in (node or []):
            if isinstance(cfg, list):
                idx = v.find(cfg, "name")
                print("%s -> %s" % (appid, cfg[idx][1] if idx >= 0 else "?"))
        return 0

    appid = argv[3]
    if action == "set":
        tool = argv[4]
        prio = argv[5] if len(argv) > 5 else "250"
        node = v.walk(root, PATH, create=True)
        idx = v.find(node, appid)
        if idx < 0:
            node.append((appid, []))
            idx = v.find(node, appid)
        entry = node[idx][1]
        if not isinstance(entry, list):
            entry = []
            node[idx] = (appid, entry)
        v.set_kv(entry, "name", tool)
        v.set_kv(entry, "config", "")
        v.set_kv(entry, "priority", prio)
    elif action == "clear":
        node = v.walk(root, PATH)
        if not node:
            return 1
        idx = v.find(node, appid)
        if idx < 0:
            return 1
        del node[idx]
    else:
        print("unknown action %r" % action)
        return 2

    v.save(path, root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
