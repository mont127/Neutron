#!/usr/bin/env python3
# minimal text vdf reader/writer, key order preserved.
# used for registry.vdf (steam's own registry) and anything else keyvalues.

import sys


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
    return s.replace("\\", "\\\\").replace('"', '\\"')


def dump(obj, depth=0):
    pad = "\t" * depth
    out = []
    for key, val in obj:
        if isinstance(val, list):
            out.append('%s"%s"' % (pad, esc(key)))
            out.append("%s{" % pad)
            inner = dump(val, depth + 1)
            if inner:
                out.append(inner)
            out.append("%s}" % pad)
        else:
            out.append('%s"%s"\t\t"%s"' % (pad, esc(key), esc(val)))
    return "\n".join(out)


def find(obj, key):
    for idx, (k, _) in enumerate(obj):
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


def load(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse(f.read())


def save(path, root):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(root) + "\n")
