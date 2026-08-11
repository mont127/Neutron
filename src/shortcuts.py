#!/usr/bin/env python3
# add/remove non-steam shortcuts in a userdata config/shortcuts.vdf (binary vdf).
# a shortcut gives a windows-only game a Play button that runs through neutron.
# steam reads this file at start and rewrites it at exit, so quit steam first.
#   shortcuts.py add    <shortcuts.vdf> <AppName> <Exe> <StartDir> <LaunchOptions>
#   shortcuts.py remove <shortcuts.vdf> <AppName>
#   shortcuts.py list   <shortcuts.vdf>

import sys
import os
import struct
import binascii

MAP, STR, INT, END = 0x00, 0x01, 0x02, 0x08


def parse(data):
    i = 0

    def cstr():
        nonlocal i
        s = i
        while data[i] != 0:
            i += 1
        v = data[s:i].decode("utf-8", "replace")
        i += 1
        return v

    def rmap():
        nonlocal i
        m = {}
        while True:
            t = data[i]; i += 1
            if t == END:
                return m
            key = cstr()
            if t == MAP:
                m[key] = rmap()
            elif t == STR:
                m[key] = cstr()
            elif t == INT:
                m[key] = struct.unpack("<I", data[i:i + 4])[0]; i += 4
            else:
                raise ValueError("bad tag 0x%02x" % t)

    if not data:
        return {}
    t = data[i]; i += 1          # MAP
    cstr()                        # "shortcuts"
    return rmap()


def ser_map(name, items):
    out = bytearray([MAP]) + name.encode() + b"\x00"
    for tag, key, val in items:
        if tag == MAP:
            out += ser_map(key, val)
        elif tag == STR:
            out += bytes([STR]) + key.encode() + b"\x00" + val.encode("utf-8") + b"\x00"
        elif tag == INT:
            out += bytes([INT]) + key.encode() + b"\x00" + struct.pack("<I", val & 0xffffffff)
    out += bytes([END])
    return bytes(out)


def shortcut_appid(exe, name):
    return binascii.crc32((exe + name).encode("utf-8")) | 0x80000000


def entry_items(sc):
    exe, name = sc["Exe"], sc["AppName"]
    return [
        (INT, "appid", sc.get("appid", shortcut_appid(exe, name))),
        (STR, "AppName", name),
        (STR, "Exe", exe),
        (STR, "StartDir", sc.get("StartDir", "")),
        (STR, "icon", sc.get("icon", "")),
        (STR, "ShortcutPath", ""),
        (STR, "LaunchOptions", sc.get("LaunchOptions", "")),
        (INT, "IsHidden", 0),
        (INT, "AllowDesktopConfig", 1),
        (INT, "AllowOverlay", 1),
        (INT, "OpenVR", 0),
        (INT, "Devkit", 0),
        (STR, "DevkitGameID", ""),
        (INT, "DevkitOverrideAppID", 0),
        (INT, "LastPlayTime", 0),
        (MAP, "tags", []),
    ]


def write(path, shortcuts):
    children = []
    for idx, sc in enumerate(shortcuts):
        children.append((MAP, str(idx), entry_items(sc)))
    data = ser_map("shortcuts", children) + bytes([END])
    with open(path, "wb") as f:
        f.write(data)


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        root = parse(f.read())
    out = []
    for _, sc in sorted(root.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        if isinstance(sc, dict):
            out.append(sc)
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    action, path = argv[1], argv[2]
    shortcuts = load(path)

    if action == "list":
        for sc in shortcuts:
            print("%s | %s %s" % (sc.get("AppName", "?"), sc.get("Exe", ""), sc.get("LaunchOptions", "")))
        return 0

    if action == "add":
        name, exe, startdir, opts = argv[3], argv[4], argv[5], argv[6]
        shortcuts = [s for s in shortcuts if s.get("AppName") != name]
        shortcuts.append({"AppName": name, "Exe": exe, "StartDir": startdir, "LaunchOptions": opts})
        write(path, shortcuts)
        return 0

    if action == "remove":
        name = argv[3]
        kept = [s for s in shortcuts if s.get("AppName") != name]
        if len(kept) == len(shortcuts):
            return 1
        write(path, kept)
        return 0

    if action == "clean":
        # ours are the ones launched through neutron; leave the user's alone
        def ours(s):
            e = s.get("Exe", "")
            return "neutron-play" in e or "neutron-run" in e
        kept = [s for s in shortcuts if not ours(s)]
        if len(kept) != len(shortcuts):
            write(path, kept)
        return 0

    print("unknown action %r" % action)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
