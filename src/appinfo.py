#!/usr/bin/env python3
# parse steam's binary appinfo.vdf and decide if an app has a usable native mac
# build or should run through wine. handles the v28 and v29 (string-table) formats.
#   appinfo.py <appid> [appid...]   per-app verdict
#   appinfo.py --scan               verdict for every cached app

import io
import os
import struct
import sys

APPINFO_PATH = os.path.expanduser(
    "~/Library/Application Support/Steam/appcache/appinfo.vdf")

MAGIC_V28 = 0x07564428
MAGIC_V29 = 0x07564429

BIN_NONE = 0x00     # nested map
BIN_STRING = 0x01
BIN_INT32 = 0x02
BIN_FLOAT32 = 0x03
BIN_WSTRING = 0x05
BIN_COLOR = 0x06
BIN_UINT64 = 0x07
BIN_END = 0x08
BIN_INT64 = 0x0A


class AppinfoError(Exception):
    pass


def _read_cstr(f):
    out = bytearray()
    while True:
        b = f.read(1)
        if not b:
            raise AppinfoError("eof inside string")
        if b == b"\x00":
            return out.decode("utf-8", "replace")
        out += b


def _read_key(f, strings):
    if strings is None:
        return _read_cstr(f)
    (idx,) = struct.unpack("<I", f.read(4))
    try:
        return strings[idx]
    except IndexError:
        raise AppinfoError("string table index %d out of range" % idx)


def _parse_kv(f, strings):
    # one binary-vdf map, recursive
    node = {}
    while True:
        t = f.read(1)
        if not t:
            raise AppinfoError("eof inside kv")
        t = t[0]
        if t == BIN_END:
            return node
        key = _read_key(f, strings)
        if t == BIN_NONE:
            node[key] = _parse_kv(f, strings)
        elif t == BIN_STRING:
            node[key] = _read_cstr(f)
        elif t == BIN_INT32 or t == BIN_COLOR:
            node[key] = struct.unpack("<i", f.read(4))[0]
        elif t == BIN_FLOAT32:
            node[key] = struct.unpack("<f", f.read(4))[0]
        elif t == BIN_UINT64:
            node[key] = struct.unpack("<Q", f.read(8))[0]
        elif t == BIN_INT64:
            node[key] = struct.unpack("<q", f.read(8))[0]
        else:
            raise AppinfoError("unknown kv type 0x%02x" % t)


def load_appinfo(path=APPINFO_PATH, only_appids=None):
    # only_appids narrows what we parse, though every blob still gets walked over
    with open(path, "rb") as fh:
        data = fh.read()
    f = io.BytesIO(data)
    magic, universe = struct.unpack("<II", f.read(8))
    strings = None
    if magic == MAGIC_V29:
        (table_off,) = struct.unpack("<q", f.read(8))
        tf = io.BytesIO(data[table_off:])
        (count,) = struct.unpack("<I", tf.read(4))
        strings = [_read_cstr(tf) for _ in range(count)]
        end_of_apps = table_off
    elif magic == MAGIC_V28:
        end_of_apps = len(data)
    else:
        raise AppinfoError("unsupported appinfo magic 0x%08x" % magic)

    apps = {}
    while f.tell() < end_of_apps:
        (appid,) = struct.unpack("<I", f.read(4))
        if appid == 0:
            break
        (size,) = struct.unpack("<I", f.read(4))
        entry_end = f.tell() + size
        # entry header: state(4) lastupdate(4) picstoken(8) sha1(20)
        # changenumber(4) binsha1(20) then the kv blob
        f.seek(4 + 4 + 8 + 20 + 4 + 20, io.SEEK_CUR)
        if only_appids is not None and appid not in only_appids:
            f.seek(entry_end)
            continue
        kv = _parse_kv(f, strings)
        # each entry is one root map keyed "appinfo", unwrap it
        apps[appid] = kv.get("appinfo", kv)
        f.seek(entry_end)
        if only_appids is not None and set(apps) >= only_appids:
            break
    return apps


def _oslist(node):
    # steam writes these with a space after the comma often enough that not
    # stripping reads "windows, macos" as windows-only, and a game with a real
    # mac build is then handed to wine. that is the one thing neutron must not do
    v = node.get("oslist", "")
    return [s.strip().lower() for s in str(v).split(",") if s.strip()]


def assess_macos_build(app):
    # returns (verdict, reasons); verdict is native-ok, suspect or windows-only
    reasons = []
    common = app.get("common", {})
    config = app.get("config", {})
    depots = app.get("depots", {})

    mac_launch = []
    for key, entry in sorted(config.get("launch", {}).items()):
        if not isinstance(entry, dict):
            continue
        entry_os = _oslist(entry.get("config", {}))
        if "macos" in entry_os or "macosx" in entry_os:
            mac_launch.append(entry)

    mac_depots = []
    for depot_id, depot in depots.items():
        if not isinstance(depot, dict):
            continue
        dep_os = _oslist(depot.get("config", {}))
        if "macos" in dep_os or "macosx" in dep_os:
            mac_depots.append(depot_id)

    common_os = _oslist(common)
    has_mac_flag = "macos" in common_os or "macosx" in common_os

    # steam gates its own Install button on common.oslist. without macos in
    # there the library page reads "Available for Windows" and Install stays
    # greyed no matter what else the app carries, and plenty of windows-only
    # games keep a launch entry and depot from a mac build they dropped years
    # ago (among us still lists AmongUs.app). those are not something steam will
    # ever install, so the app needs neutron.
    if common_os and not has_mac_flag:
        stale = []
        if mac_launch:
            stale.append("%d launch entr%s" % (len(mac_launch),
                                               "y" if len(mac_launch) == 1 else "ies"))
        if mac_depots:
            stale.append("%d depot%s" % (len(mac_depots),
                                         "" if len(mac_depots) == 1 else "s"))
        why = "common oslist is %s" % ",".join(common_os)
        if stale:
            why += ", the leftover mac %s is not installable" % " and ".join(stale)
        return "windows-only", [why]

    if not (mac_launch or mac_depots or has_mac_flag):
        return "windows-only", ["no macOS launch config, depot or oslist flag"]

    if not mac_launch:
        reasons.append("macOS depot/flag exists but no macOS launch entry")
        return "suspect", reasons
    if not mac_depots and depots:
        reasons.append("macOS launch entry exists but no macOS depot")
        return "suspect", reasons

    # 32-bit relic check: catalina killed 32-bit, a mac build thats 32-only is dead
    arches = set()
    for entry in mac_launch:
        arch = str(entry.get("config", {}).get("osarch", ""))
        if arch:
            arches.add(arch)
    if arches and "64" not in arches:
        reasons.append("macOS launch entries are 32-bit only (%s)" % ",".join(sorted(arches)))
        return "suspect", reasons

    reasons.append("%d macOS launch entr%s, %d macOS depot%s" % (
        len(mac_launch), "y" if len(mac_launch) == 1 else "ies",
        len(mac_depots), "" if len(mac_depots) == 1 else "s"))
    return "native-ok", reasons


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--scan":
        apps = load_appinfo()
        for appid, app in sorted(apps.items()):
            name = app.get("common", {}).get("name", "?")
            verdict, reasons = assess_macos_build(app)
            print("%9d  %-14s %s  (%s)" % (appid, verdict, name, "; ".join(reasons)))
        return 0
    want = set(int(a) for a in argv[1:])
    apps = load_appinfo(only_appids=want)
    for appid in sorted(want):
        if appid not in apps:
            print("%d: not in appinfo cache" % appid)
            continue
        app = apps[appid]
        name = app.get("common", {}).get("name", "?")
        verdict, reasons = assess_macos_build(app)
        print("%d (%s): %s" % (appid, name, verdict))
        for r in reasons:
            print("    - %s" % r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
