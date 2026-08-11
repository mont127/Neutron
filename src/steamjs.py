#!/usr/bin/env python3
# talk to the steam client's own javascript context over its CEF debugging port.
# steam must be started with -cef-enable-debugging.
#
# this is how we reach SteamClient.* without patching anything: the client
# exposes the same api its own ui uses, including Console.ExecCommand, which is
# the only way found so far to actually set @sSteamCmdForcePlatformType.
#
#   steamjs.py targets
#   steamjs.py eval "<javascript>"          (runs in SharedJSContext)
#   steamjs.py cmd  "<steam console cmd>"

import base64
import json
import os
import socket
import struct
import sys
import urllib.request

PORT = int(os.environ.get("STEAM_CEF_PORT", "8080"))


def targets():
    with urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=10) as r:
        return json.load(r)


def pick(name_hint="SharedJSContext"):
    for t in targets():
        if name_hint.lower() in (t.get("title", "") + t.get("url", "")).lower():
            if t.get("webSocketDebuggerUrl"):
                return t
    for t in targets():
        if t.get("webSocketDebuggerUrl"):
            return t
    return None


class WS:
    """just enough websocket for CDP on localhost"""

    def __init__(self, url):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b"101" not in buf.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake failed: %s" % buf[:120])
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def send(self, obj):
        payload = json.dumps(obj).encode()
        header = bytearray([0x81])
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", n))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        b0, b1 = self._read(2)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read(8))[0]
        data = self._read(length)
        if b0 & 0x0F == 0x01:
            return json.loads(data.decode("utf-8", "replace"))
        return None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def evaluate(js, await_promise=True):
    t = pick()
    if not t:
        raise RuntimeError("no debuggable steam context; start steam with -cef-enable-debugging")
    ws = WS(t["webSocketDebuggerUrl"])
    try:
        ws.send({"id": 1, "method": "Runtime.enable"})
        ws.send({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": js,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
        })
        for _ in range(400):
            msg = ws.recv()
            if msg and msg.get("id") == 2:
                return msg.get("result", {})
        raise RuntimeError("no reply from steam")
    finally:
        ws.close()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    action = argv[1]

    if action == "targets":
        for t in targets():
            print("%-30s %s" % (t.get("title", "")[:30], t.get("url", "")[:60]))
        return 0

    if action == "eval":
        res = evaluate(argv[2])
        print(json.dumps(res, indent=1)[:4000])
        return 0

    if action == "evalfile":
        with open(argv[2], encoding="utf-8") as f:
            js = f.read()
        # evalfile <file> [appid [depot [manifest]]] - simple placeholder subst
        if len(argv) > 3:
            js = js.replace("__APPID__", str(int(argv[3])))
        if len(argv) > 4:
            js = js.replace("__DEPOT__", str(int(argv[4])))
        if len(argv) > 5:
            js = js.replace("__MANIFEST__", str(argv[5]))
        res = evaluate(js)
        val = res.get("result", {}).get("value")
        print(val if val is not None else json.dumps(res, indent=1)[:4000])
        return 0

    if action == "cmd":
        cmd = argv[2].replace("\\", "\\\\").replace('"', '\\"')
        res = evaluate(
            '(async () => { if (!window.SteamClient || !SteamClient.Console) return "no SteamClient.Console";'
            ' await SteamClient.Console.ExecCommand("%s"); return "ok"; })()' % cmd)
        print(json.dumps(res, indent=1)[:2000])
        return 0

    print("unknown action %r" % action)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
