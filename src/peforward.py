#!/usr/bin/env python3
# read a pe export table, and build/check the pure export-forwarder that stands
# in for the bridge under a second module name.
#
# a steamworks-drm game loads whatever SteamClientDll64 names, then looks the
# module back up as the literal "steamclient.dll" to reach
# Steam_ReleaseThreadLocalMemory. GetModuleHandle only finds modules that are
# already loaded, so the file the registry names has to itself be called
# steamclient.dll. the real bridge cannot take that name: it looks for a module
# called steamclient.dll, finds its own .data and bump-allocates its interface
# objects over its own globals. so the name goes to a forwarder that has no code
# and no .data, and the bridge keeps allocating from the heap as it does today.
#
# the forwarder is emitted here rather than compiled. it has to be generated from
# the export table of the bridge that is actually on the machine, and the machine
# that needs one is a user's, which has no mingw and no build tree: a forwarder
# that could only be produced where a cross compiler exists could not be
# regenerated after an engine update, and would silently stop being staged. what
# it has to contain is a header, an export directory of forward strings, and
# nothing else, so it is written out byte by byte and then read back through the
# same parser and checked before it is allowed anywhere near a prefix.
#
#   peforward.py machine <dll>                      i386 | x86_64
#   peforward.py gen     <bridge.dll> <target> <out.dll>
#   peforward.py check   <bridge.dll> <forwarder.dll> <target>

import os
import struct
import sys


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class PE(object):
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        if d[:2] != b"MZ":
            raise ValueError("%s: not a pe file" % path)
        pe = u32(d, 0x3C)
        if d[pe:pe + 4] != b"PE\0\0":
            raise ValueError("%s: not a pe file" % path)
        self.machine = u16(d, pe + 4)
        nsec = u16(d, pe + 6)
        optsz = u16(d, pe + 20)
        opt = pe + 24
        plus = u16(d, opt) == 0x20B
        ddoff = opt + (112 if plus else 96)
        ndd = u32(d, opt + (108 if plus else 92))
        self.dd = [(u32(d, ddoff + i * 8), u32(d, ddoff + i * 8 + 4))
                   for i in range(ndd)]
        self.sections = []
        for i in range(nsec):
            o = opt + optsz + i * 40
            self.sections.append((d[o:o + 8].rstrip(b"\0").decode("latin1"),
                                  u32(d, o + 12), u32(d, o + 8),
                                  u32(d, o + 20), u32(d, o + 16)))

    def arch(self):
        return {0x8664: "x86_64", 0x14C: "i386"}.get(self.machine,
                                                     hex(self.machine))

    def off(self, rva):
        for _, va, vsize, roff, rsize in self.sections:
            if va <= rva < va + max(vsize, rsize):
                o = rva - va + roff
                if o < len(self.data):
                    return o
        return None

    def cstr(self, rva):
        o = self.off(rva)
        if o is None:
            return None
        return self.data[o:self.data.index(b"\0", o)].decode("latin1")

    # returns [(ordinal, name, forward-target-or-None)] in ordinal order. an
    # entry whose rva lands inside the export directory is a forwarder string
    # rather than code, which is how a forwarder is told from a real export.
    def exports(self):
        if not self.dd or not self.dd[0][0]:
            return []
        erva, esize = self.dd[0]
        o = self.off(erva)
        d = self.data
        base = u32(d, o + 16)
        nfuncs = u32(d, o + 20)
        nnames = u32(d, o + 24)
        fo = self.off(u32(d, o + 28))
        no = self.off(u32(d, o + 32))
        oo = self.off(u32(d, o + 36))
        names = {}
        for i in range(nnames):
            names[u16(d, oo + i * 2)] = self.cstr(u32(d, no + i * 4))
        out = []
        for i in range(nfuncs):
            rva = u32(d, fo + i * 4)
            if not rva:
                continue
            fwd = self.cstr(rva) if erva <= rva < erva + esize else None
            out.append((base + i, names.get(i), fwd))
        return out

    # the export names in the order the name pointer table lists them.
    # GetProcAddress binary-searches that table, so a name out of ascii order is
    # a name that cannot be found however correct the rest of the file is.
    def name_table(self):
        if not self.dd or not self.dd[0][0]:
            return []
        o = self.off(self.dd[0][0])
        d = self.data
        no = self.off(u32(d, o + 32))
        # "" for a name whose rva lands outside the file: unreadable is not the
        # same as absent, and it sorts first, so the order check below sees it
        return [self.cstr(u32(d, no + i * 4)) or ""
                for i in range(u32(d, o + 24))]


# the two the whole design exists for: CreateInterface is how steam_api reaches
# the bridge at all, and Steam_ReleaseThreadLocalMemory is the one a drm wrapper
# looks up by module name, which is what forced a second module name in the
# first place. a "forwarder" without them is not one.
REQUIRED = ("CreateInterface", "Steam_ReleaseThreadLocalMemory")

SECT_ALIGN = 0x1000
FILE_ALIGN = 0x200
TEXT_RVA = 0x1000
EDATA_RVA = 0x2000

# DllMain: return TRUE and touch nothing. the loader will not call an entry point
# of 0, so this could be left out entirely, but a module with no code at all is
# unusual enough that it is cheaper to emit the six bytes than to find out which
# loader minds. stdcall on i386, so it pops its three arguments.
ENTRY = {0x8664: b"\xb8\x01\x00\x00\x00\xc3",
         0x14C: b"\xb8\x01\x00\x00\x00\xc2\x0c\x00"}


def _align(v, a):
    return (v + a - 1) // a * a


# the export directory, its three tables and every string they point at, as one
# blob that becomes the .edata section. every rva in it is EDATA_RVA + an offset
# into this blob, which is why the section's address is fixed above rather than
# worked out afterwards.
def _edata(ent, target, dllname):
    base = min(o for o, _ in ent)
    nfuncs = max(o for o, _ in ent) - base + 1
    # ascii order, because GetProcAddress binary-searches this table
    by_name = sorted(ent, key=lambda e: e[1].encode("latin1"))
    nnames = len(by_name)

    fo = 40
    no = fo + nfuncs * 4
    oo = no + nnames * 4
    so = oo + nnames * 2
    strings = bytearray()

    def put(s):
        at = so + len(strings)
        strings.extend(s.encode("latin1") + b"\0")
        return EDATA_RVA + at

    name_rva = put(dllname)
    fwd = dict((o, put("%s.%s" % (target, n))) for o, n in ent)
    nm = dict((n, put(n)) for _, n in by_name)

    buf = bytearray(so) + strings
    struct.pack_into("<IIHHIIII", buf, 0, 0, 0, 0, 0, name_rva, base,
                     nfuncs, nnames)
    struct.pack_into("<III", buf, 28, EDATA_RVA + fo, EDATA_RVA + no,
                     EDATA_RVA + oo)
    for o, _ in ent:
        struct.pack_into("<I", buf, fo + (o - base) * 4, fwd[o])
    for i, (o, n) in enumerate(by_name):
        struct.pack_into("<I", buf, no + i * 4, nm[n])
        struct.pack_into("<H", buf, oo + i * 2, o - base)
    return bytes(buf)


def _image(machine, edata):
    plus = machine == 0x8664
    text = ENTRY[machine]
    # one relocation block covering the code page with two ABSOLUTE (do-nothing)
    # entries. there is nothing here that needs fixing up, but wine refuses to
    # move an image that has no relocation directory at all, and an image with a
    # fixed base is one conflicting mapping away from failing to load.
    reloc = struct.pack("<IIHH", TEXT_RVA, 12, 0, 0)
    reloc_rva = EDATA_RVA + _align(len(edata), SECT_ALIGN)

    secs = [(b".text", TEXT_RVA, text, 0x60000020),
            (b".edata", EDATA_RVA, edata, 0x40000040),
            (b".reloc", reloc_rva, reloc, 0x42000040)]
    hdrs = _align(0x80 + 24 + (240 if plus else 224) + len(secs) * 40,
                  FILE_ALIGN)

    out = bytearray(hdrs)
    out[0:2] = b"MZ"
    struct.pack_into("<I", out, 0x3C, 0x80)
    struct.pack_into("<I", out, 0x80, 0x4550)
    struct.pack_into("<HHIIIHH", out, 0x84, machine, len(secs), 0, 0, 0,
                     240 if plus else 224,
                     # dll, executable; not RELOCS_STRIPPED, see above
                     0x2002 | (0x0020 if plus else 0x0100))
    opt = 0x98
    struct.pack_into("<HBB", out, opt, 0x20B if plus else 0x10B, 14, 0)
    struct.pack_into("<III", out, opt + 4, _align(len(text), FILE_ALIGN),
                     _align(len(edata), FILE_ALIGN)
                     + _align(len(reloc), FILE_ALIGN), 0)
    struct.pack_into("<II", out, opt + 16, TEXT_RVA, TEXT_RVA)
    if plus:
        struct.pack_into("<Q", out, opt + 24, 0x180000000)
    else:
        struct.pack_into("<II", out, opt + 24, EDATA_RVA, 0x10000000)
    struct.pack_into("<II", out, opt + 32, SECT_ALIGN, FILE_ALIGN)
    struct.pack_into("<HHHHHHI", out, opt + 40, 6, 0, 0, 0, 6, 0, 0)
    struct.pack_into("<III", out, opt + 56,
                     reloc_rva + _align(len(reloc), SECT_ALIGN), hdrs, 0)
    struct.pack_into("<HH", out, opt + 68, 3, 0x0140)  # cui, dynamic base + nx
    if plus:
        struct.pack_into("<QQQQII", out, opt + 72, 0x100000, 0x1000,
                         0x100000, 0x1000, 0, 16)
    else:
        struct.pack_into("<IIIIII", out, opt + 72, 0x100000, 0x1000,
                         0x100000, 0x1000, 0, 16)
    dd = opt + (112 if plus else 96)
    struct.pack_into("<II", out, dd, EDATA_RVA, len(edata))
    struct.pack_into("<II", out, dd + 5 * 8, reloc_rva, len(reloc))

    sh = dd + 128
    raw = hdrs
    for i, (name, rva, body, flags) in enumerate(secs):
        struct.pack_into("<8sIIIIIIHHI", out, sh + i * 40, name, len(body),
                         rva, _align(len(body), FILE_ALIGN), raw, 0, 0, 0, 0,
                         flags)
        out.extend(body)
        out.extend(b"\0" * (_align(len(body), FILE_ALIGN) - len(body)))
        raw += _align(len(body), FILE_ALIGN)
    return bytes(out)


# write a forwarder for every named export of the bridge, then read it back and
# refuse to hand it over if it is not exactly what was asked for.
def gen(bridge, target, out, dllname=None):
    b = PE(bridge)
    if b.machine not in ENTRY:
        raise ValueError("%s is not an x86 pe (%s)" % (bridge, b.arch()))
    ent = sorted((o, n) for o, n, _ in b.exports() if n)
    if not ent:
        raise ValueError("%s exports nothing by name" % bridge)
    tmp = "%s.new.%d" % (out, os.getpid())
    with open(tmp, "wb") as fh:
        fh.write(_image(b.machine,
                        _edata(ent, target,
                               dllname or os.path.basename(out))))
    bad = check(bridge, tmp, target)
    if bad:
        os.unlink(tmp)
        raise ValueError("; ".join(bad))
    os.replace(tmp, out)
    return len(ent)


def check(bridge, fwd, target):
    b, f = PE(bridge), PE(fwd)
    bad = []
    if b.machine != f.machine:
        bad.append("built for %s, bridge is %s" % (f.arch(), b.arch()))
    bex = dict((o, n) for o, n, _ in b.exports() if n)
    fex = dict((o, n) for o, n, _ in f.exports() if n)
    # every comparison below is over a list, so all of them pass on a file that
    # exports nothing. that is the one shape that must never get through: it
    # loads, it resolves nothing, and the game it was staged for fails somewhere
    # far away from here.
    if not fex:
        bad.append("exports nothing")
    if bex != fex:
        bad.append("exports do not match the bridge (%d vs %d)"
                   % (len(fex), len(bex)))
    fwds = dict((n, w) for _, n, w in f.exports() if n)
    for want in REQUIRED:
        if fwds.get(want) != "%s.%s" % (target, want):
            bad.append("does not forward %s to %s" % (want, target))
    code = [n for _, n, w in f.exports() if w is None]
    if code:
        bad.append("%d exports are real code, not forwards" % len(code))
    wrong = [w for _, _, w in f.exports()
             if w and not w.startswith(target + ".")]
    if wrong:
        bad.append("forwards somewhere else: %s" % wrong[0])
    # GetProcAddress binary-searches the name pointer table. out of order it
    # returns null for names that are right there in the file.
    nt = f.name_table()
    if nt != sorted(nt, key=lambda n: n.encode("latin1")):
        bad.append("export names are not in ascii order")
    # the invariant the whole design rests on. the bridge hunts the section
    # table of whatever module is called steamclient.dll for a .data to
    # allocate into; a forwarder that grew one would be written over.
    data = [s[0] for s in f.sections if s[0].startswith(".data")]
    if data:
        bad.append("has a %s section, the bridge would allocate into it"
                   % data[0])
    return bad


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    action = argv[1]
    if action == "machine":
        print(PE(argv[2]).arch())
        return 0
    if action == "gen":
        try:
            n = gen(argv[2], argv[3], argv[4])
        # TypeError as well: a truncated pe reaches the readers below with a
        # None where an offset should be, and this has to fail like any other
        # unusable bridge rather than land a traceback in the install output
        except (ValueError, TypeError, OSError, struct.error) as e:
            print("forwarder: %s" % e, file=sys.stderr)
            return 1
        print("%d forwards -> %s.*" % (n, argv[3]))
        return 0
    if action == "check":
        bad = check(argv[2], argv[3], argv[4])
        for b in bad:
            print("forwarder: %s" % b, file=sys.stderr)
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
