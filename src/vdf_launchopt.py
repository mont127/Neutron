#!/usr/bin/env python3
# read/modify LaunchOptions for a steam appid inside a text localconfig.vdf.
# steam must be closed while this runs, it rewrites the file on exit.
#
#   vdf_launchopt.py set   <localconfig.vdf> <appid> "<launch options>"
#   vdf_launchopt.py clear <localconfig.vdf> <appid>
#   vdf_launchopt.py list  <localconfig.vdf>

import sys

APP_PATH = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps"]


def parse(text):
    i, n = 0, len(text)

    def skip_ws():
        nonlocal i
        while i < n:
            c = text[i]
            if c in " \t\r\n":
                i += 1
            elif text[i:i + 2] == "//":
                while i < n and text[i] != "\n":
                    i += 1
            else:
                break

    def read_string():
        nonlocal i
        assert text[i] == '"'
        i += 1
        out = []
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                i += 2
            elif c == '"':
                i += 1
                return "".join(out)
            else:
                out.append(c)
                i += 1
        return "".join(out)

    def read_map():
        nonlocal i
        obj = []
        while True:
            skip_ws()
            if i >= n or text[i] == "}":
                i += 1
                return obj
            key = read_string()
            skip_ws()
            if text[i] == "{":
                i += 1
                obj.append((key, read_map()))
            else:
                obj.append((key, read_string()))

    skip_ws()
    root = []
    while i < n and text[i] == '"':
        key = read_string()
        skip_ws()
        if i < n and text[i] == "{":
            i += 1
            root.append((key, read_map()))
        else:
            root.append((key, read_string()))
        skip_ws()
    return root


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def dump(obj, depth=0):
    pad = "\t" * depth
    lines = []
    for key, val in obj:
        if isinstance(val, list):
            lines.append('%s"%s"' % (pad, esc(key)))
            lines.append("%s{" % pad)
            lines.append(dump(val, depth + 1))
            lines.append("%s}" % pad)
        else:
            lines.append('%s"%s"\t\t"%s"' % (pad, esc(key), esc(val)))
    return "\n".join(l for l in lines if l != "")


def find(obj, key):
    for idx, (k, v) in enumerate(obj):
        if k.lower() == key.lower():
            return idx
    return -1


def walk(root, path, create=False):
    node = root
    for key in path:
        idx = find(node, key)
        if idx < 0:
            if not create:
                return None
            child = []
            node.append((key, child))
            node = child
        else:
            k, v = node[idx]
            if not isinstance(v, list):
                if not create:
                    return None
                v = []
                node[idx] = (k, v)
            node = v
    return node


def set_kv(node, key, value):
    idx = find(node, key)
    if idx < 0:
        node.append((key, value))
    else:
        node[idx] = (node[idx][0], value)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    action, path = argv[1], argv[2]
    with open(path, encoding="utf-8", errors="replace") as f:
        root = parse(f.read())

    if action == "list":
        apps = walk(root, APP_PATH)
        for appid, cfg in (apps or []):
            if isinstance(cfg, list):
                idx = find(cfg, "LaunchOptions")
                if idx >= 0:
                    print("%s -> %s" % (appid, cfg[idx][1]))
        return 0

    appid = argv[3]
    if action == "set":
        opts = argv[4]
        apps = walk(root, APP_PATH, create=True)
        idx = find(apps, appid)
        if idx < 0:
            apps.append((appid, []))
            idx = find(apps, appid)
        block = apps[idx][1]
        if not isinstance(block, list):
            block = []
            apps[idx] = (appid, block)
        set_kv(block, "LaunchOptions", opts)
    elif action == "clear":
        apps = walk(root, APP_PATH)
        idx = find(apps or [], appid) if apps else -1
        if idx < 0:
            return 1
        block = apps[idx][1]
        if isinstance(block, list):
            j = find(block, "LaunchOptions")
            if j >= 0:
                del block[j]
    else:
        print("unknown action %r" % action)
        return 2

    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(root) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
