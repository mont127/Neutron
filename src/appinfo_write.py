#!/usr/bin/env python3
# surgical rewriter for steam's binary appinfo.vdf.
#
# every app we are not touching keeps its original bytes, so the blast radius is
# one entry. for v29 the key names are indexes into a string table at the end of
# the file; we only ever APPEND to that table, which keeps every existing index
# valid and means untouched entries stay byte-identical.
#
# appinfo.vdf is a cache. if it ever goes wrong, delete it and steam rebuilds it.

import hashlib
import io
import struct
import sys

MAGIC_V28 = 0x07564428
MAGIC_V29 = 0x07564429

MAP, STR, INT32, FLOAT32, PTR, WSTR, COLOR, UINT64, END, INT64 = (
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A)

# entry header: state, lastupdate, picstoken, sha1, changenumber, binsha1
HDR = 4 + 4 + 8 + 20 + 4 + 20


class Appinfo:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        self.magic, self.universe = struct.unpack("<II", self.data[:8])
        if self.magic not in (MAGIC_V28, MAGIC_V29):
            raise ValueError("unsupported appinfo magic 0x%08x" % self.magic)
        self.strings = []
        pos = 8
        if self.magic == MAGIC_V29:
            (self.table_off,) = struct.unpack("<q", self.data[8:16])
            pos = 16
            tf = io.BytesIO(self.data[self.table_off:])
            (count,) = struct.unpack("<I", tf.read(4))
            for _ in range(count):
                out = bytearray()
                while True:
                    c = tf.read(1)
                    if c in (b"\x00", b""):
                        break
                    out += c
                self.strings.append(out.decode("utf-8", "replace"))
            self.end_of_apps = self.table_off
        else:
            self.table_off = None
            self.end_of_apps = len(self.data)

        # (appid, whole entry slice including appid+size)
        self.entries = []
        p = pos
        while p < self.end_of_apps:
            (appid,) = struct.unpack("<I", self.data[p:p + 4])
            if appid == 0:
                break
            (size,) = struct.unpack("<I", self.data[p + 4:p + 8])
            self.entries.append((appid, p, p + 8 + size))
            p += 8 + size
        self.tail_pos = p           # where the 0 terminator sits
        self._index = {a: i for i, (a, _, _) in enumerate(self.entries)}

    # --- key table -------------------------------------------------------

    def key_index(self, name):
        try:
            return self.strings.index(name)
        except ValueError:
            self.strings.append(name)
            return len(self.strings) - 1

    # --- typed kv parse / encode ----------------------------------------

    def parse_kv(self, buf, pos):
        def read_cstr(p):
            e = buf.index(b"\x00", p)
            return buf[p:e].decode("utf-8", "replace"), e + 1

        def read_key(p):
            if self.magic == MAGIC_V29:
                (idx,) = struct.unpack("<I", buf[p:p + 4])
                return self.strings[idx], p + 4
            return read_cstr(p)

        def read_map(p):
            node = []
            while True:
                t = buf[p]; p += 1
                if t == END:
                    return node, p
                key, p = read_key(p)
                if t == MAP:
                    child, p = read_map(p)
                    node.append((MAP, key, child))
                elif t == STR:
                    v, p = read_cstr(p)
                    node.append((STR, key, v))
                elif t in (INT32, COLOR, PTR):
                    v = struct.unpack("<i", buf[p:p + 4])[0]; p += 4
                    node.append((t, key, v))
                elif t == FLOAT32:
                    v = struct.unpack("<f", buf[p:p + 4])[0]; p += 4
                    node.append((t, key, v))
                elif t == UINT64:
                    v = struct.unpack("<Q", buf[p:p + 8])[0]; p += 8
                    node.append((t, key, v))
                elif t == INT64:
                    v = struct.unpack("<q", buf[p:p + 8])[0]; p += 8
                    node.append((t, key, v))
                elif t == WSTR:
                    v, p = read_cstr(p)
                    node.append((t, key, v))
                else:
                    raise ValueError("bad kv type 0x%02x at %d" % (t, p - 1))

        return read_map(pos)

    def encode_kv(self, node):
        out = bytearray()

        def put_key(k):
            if self.magic == MAGIC_V29:
                out.extend(struct.pack("<I", self.key_index(k)))
            else:
                out.extend(k.encode("utf-8") + b"\x00")

        def walk(items):
            for t, key, val in items:
                out.append(t)
                put_key(key)
                if t == MAP:
                    walk(val)
                    out.append(END)
                elif t in (STR, WSTR):
                    out.extend(str(val).encode("utf-8") + b"\x00")
                elif t in (INT32, COLOR, PTR):
                    out.extend(struct.pack("<i", int(val)))
                elif t == FLOAT32:
                    out.extend(struct.pack("<f", float(val)))
                elif t == UINT64:
                    out.extend(struct.pack("<Q", int(val)))
                elif t == INT64:
                    out.extend(struct.pack("<q", int(val)))
                else:
                    raise ValueError("cannot encode type 0x%02x" % t)

        walk(node)
        out.append(END)
        return bytes(out)

    # --- one app ---------------------------------------------------------

    def get_app(self, appid):
        i = self._index.get(appid)
        if i is None:
            return None
        _, start, end = self.entries[i]
        header = self.data[start + 8:start + 8 + HDR]
        node, _ = self.parse_kv(self.data[:end], start + 8 + HDR)
        return header, node

    def rewrite(self, out_path, appid, new_header, new_node):
        i = self._index.get(appid)
        if i is None:
            raise KeyError(appid)
        kv = self.encode_kv(new_node)
        # the second sha1 in the entry header is sha1 of the kv blob (verified
        # against several untouched apps). leave it stale after an edit and steam
        # decides the entry is bad and re-downloads it, wiping the change.
        hdr = bytearray(new_header)
        hdr[40:60] = hashlib.sha1(kv).digest()
        new_header = bytes(hdr)
        payload = new_header + kv
        entry = struct.pack("<II", appid, len(payload)) + payload

        body = bytearray()
        for j, (aid, start, end) in enumerate(self.entries):
            body.extend(entry if j == i else self.data[start:end])
        body.extend(b"\x00\x00\x00\x00")   # terminator

        head = struct.pack("<II", self.magic, self.universe)
        if self.magic == MAGIC_V29:
            table_off = len(head) + 8 + len(body)
            head += struct.pack("<q", table_off)
            table = bytearray(struct.pack("<I", len(self.strings)))
            for s in self.strings:
                table.extend(s.encode("utf-8") + b"\x00")
            blob = head + bytes(body) + bytes(table)
        else:
            blob = head + bytes(body)

        with open(out_path, "wb") as f:
            f.write(blob)
        return len(blob)


# --- helpers for the neutron transform -----------------------------------

def find(node, key):
    for i, (t, k, v) in enumerate(node):
        if k.lower() == key.lower():
            return i
    return -1


def get(node, key):
    i = find(node, key)
    return node[i][2] if i >= 0 else None


def set_str(node, key, value):
    i = find(node, key)
    if i >= 0:
        node[i] = (STR, node[i][1], value)
    else:
        node.append((STR, key, value))


def add_os(node, key, want="macos"):
    """append an os to a comma list, returns True if it changed anything"""
    cur = get(node, key)
    if cur is None:
        return False
    parts = [p for p in str(cur).split(",") if p]
    if want in parts:
        return False
    parts.append(want)
    set_str(node, key, ",".join(parts))
    return True


def main(argv):
    # round-trip self test: re-encode an app unchanged, file must be identical
    path, appid = argv[1], int(argv[2])
    a = Appinfo(path)
    got = a.get_app(appid)
    if not got:
        print("app %d not in cache" % appid)
        return 1
    header, node = got
    import tempfile, os
    tmp = tempfile.mktemp(suffix=".vdf")
    a.rewrite(tmp, appid, header, node)
    same = open(tmp, "rb").read() == open(path, "rb").read()
    os.unlink(tmp)
    print("round-trip identical: %s" % same)
    return 0 if same else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
