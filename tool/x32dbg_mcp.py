"""Minimal client for the local x32Dbg MCP server (streamable HTTP) plus memory helpers.

The server exposes a disassembler but no "read N bytes" call, so `read_bytes` rebuilds a
buffer from the disassembly listing (bytes are placed by their absolute address, and any
gap left by a truncated line is filled with a follow-up read at that exact address).

Endpoints used by this project:
    127.0.0.1:13337  IDA Pro    (tool/ida_mcp.py)
    127.0.0.1:50301  x32dbg     (this module)
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

URL = "http://127.0.0.1:50301/mcp"
_session = {"id": None, "rid": 0}


def _post(payload):
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    if _session["id"]:
        req.add_header("Mcp-Session-Id", _session["id"])
    try:
        resp = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read()[:400]!r}")
    sid = resp.headers.get("Mcp-Session-Id")
    if sid:
        _session["id"] = sid
    body = resp.read().decode("utf-8", "replace")
    if "text/event-stream" in resp.headers.get("Content-Type", ""):
        body = "\n".join(l[5:].strip() for l in body.splitlines() if l.startswith("data:"))
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"_raw": body}


def init(url: str | None = None):
    global URL
    if url:
        URL = url
    _session["id"] = None
    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "pi", "version": "1"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})


def call(tool: str, args: dict | None = None) -> str:
    _session["rid"] += 1
    r = _post({"jsonrpc": "2.0", "id": _session["rid"], "method": "tools/call",
               "params": {"name": tool, "arguments": args or {}}})
    res = r.get("result", r)
    content = res.get("content") or []
    if content and content[0].get("type") == "text":
        return content[0]["text"]
    return json.dumps(res, ensure_ascii=False)


# --------------------------------------------------------------------------- state

def registers() -> dict[str, int]:
    out: dict[str, int] = {}
    for line in call("GetAllRegisters").splitlines():
        for part in line.split("|"):
            toks = part.replace(":", " ").split()
            for i in range(0, len(toks) - 1, 2):
                if len(toks[i]) == 3 and toks[i].isupper():
                    try:
                        out[toks[i]] = int(toks[i + 1], 16)
                    except ValueError:
                        pass
    return out


MODULE_RE = re.compile(r"^(\S+\.(?:dll|exe))\s+\S*\s+0x(\d+)\s+0x(\d+)")


def modules() -> dict[str, tuple[int, int]]:
    """name -> (base, end). The server prints decimal numbers behind a `0x` prefix."""
    out = {}
    for line in call("GetAllModulesFromMemMap").splitlines():
        m = MODULE_RE.match(line.strip())
        if m:
            out[m.group(1).lower()] = (int(m.group(2)), int(m.group(3)))
    return out


# --------------------------------------------------------------------------- memory

LINE_RE = re.compile(r"^([0-9A-Fa-f]{6,16})\s+((?:[0-9A-Fa-f]{2})(?:-[0-9A-Fa-f]{2})*)")


def _read_once(addr: int, n: int, out: dict[int, int]) -> None:
    for line in call("ReadDismAtAddress", {"address": hex(addr), "byteCount": str(n)}).splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        try:
            start = int(m.group(1), 16)
        except ValueError:
            continue
        raw = bytes(int(b, 16) for b in m.group(2).split("-"))
        for i, b in enumerate(raw):
            out[start + i] = b


def read_bytes(addr: int, n: int, tries: int = 40) -> bytes:
    """Return `n` bytes at `addr` (shorter only if the region really ends earlier)."""
    seen: dict[int, int] = {}
    _read_once(addr, n, seen)
    for _ in range(tries):
        missing = next((a for a in range(addr, addr + n) if a not in seen), None)
        if missing is None:
            break
        before = len(seen)
        _read_once(missing, addr + n - missing, seen)
        if len(seen) == before:
            break
    return bytes(seen[a] for a in range(addr, addr + n) if a in seen)


def read_u32(addr: int, count: int) -> list[int]:
    import struct
    raw = read_bytes(addr, count * 4)
    return list(struct.unpack(f"<{len(raw) // 4}I", raw[:len(raw) // 4 * 4]))
