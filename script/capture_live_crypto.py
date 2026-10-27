"""Capture the live Hxv4 crypto state from a *running* game under x32dbg.

Why this is needed: `CxdecKeyStatic.dll` derives a key/nonce set that does **not** decrypt
the shipping archives, and its DRIP `context` table differs from the one the game actually
uses (the 128 lane programs do match). The real values live in the game's manager struct,
which only exists between `ManagerCtor` and shutdown, so they have to be read out of a
running process.

Prerequisite: the game must be **launched from x32dbg** (attaching later is too late --
those calls happen during startup). This script:

  1. puts a breakpoint on `LoadLibraryW`,
  2. watches the loaded module names and picks the randomly-named bootstrap module
     (`<hex>.dll`); steps out to get its base, then arms
     `ManagerCtor`, `BootstrapDerive`, `ArchiveDerive` at the RVAs below,
  3. on `BootstrapDerive` records its arguments, steps out, and dumps the resulting
     manager core: 6 holder words, `+0x3038` key, `+0x3058` nonce1, `+0x3078` nonce0,
     plus the DRIP context table and the 128 lane programs,
  4. writes a profile json that `tool/hxv4.py` can load directly.

Usage (from project root, with the game paused at the entry point in x32dbg):
    mamba run -n GalRev python script/capture_live_crypto.py \
        --out resource/hxv4/profile_live.json

Note: every MCP round-trip shows up in x32dbg's log window; that is expected.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import x32dbg_mcp as dbg

RVAS = {"ManagerCtor": 0xE2D0, "BootstrapDerive": 0x15630, "ArchiveDerive": 0x157D0}
SEED_RVA = 0x81758
MANAGER_SIZE = 0x30B0
HEXNAME = re.compile(r"^[0-9a-f]{8,16}\.dll$")


class Capture:
    def __init__(self):
        self.module_base = 0
        self.bpaths: dict[int, str] = {}
        self.result: dict = {}

    # -- breakpoints
    def arm(self, base: int):
        self.module_base = base
        for name, rva in RVAS.items():
            dbg.call("SetBreakpoint", {"target": hex(base + rva)})
            self.bpaths[base + rva] = name
        print(f">>> armed at 0x{base:08x}", flush=True)

    # -- dumps
    def read_core(self, core: int, label: str) -> dict:
        out = {}
        for name, off, size in (("holder", 0x00, 24), ("key", 0x3038, 32),
                                ("nonce1", 0x3058, 24), ("nonce0", 0x3078, 24)):
            raw = dbg.read_bytes(core + off, size)
            print(f"  {label:11s} {name:7s} {raw.hex()}", flush=True)
            out[name] = raw.hex()
        return out

    def dump_drip(self, core: int) -> dict:
        holder = dbg.read_u32(core, 6)
        drip_impl = holder[0]
        head = dbg.read_bytes(drip_impl, 0x20)
        context_ptr = struct.unpack_from("<I", head, 0x04 + 0x0C)[0]
        count = (core - 8 + MANAGER_SIZE - context_ptr) // 4
        context = dbg.read_u32(context_ptr, count)
        lanes = []
        for li in range(128):
            lane = dbg.read_bytes(drip_impl + 0x04 + li * 0x10, 16)
            begin, end = struct.unpack_from("<II", lane, 0)
            if end < begin or (end - begin) % 8:
                lanes.append([])
                continue
            n = (end - begin) // 8
            raw = dbg.read_bytes(begin, n * 8) if n else b""
            lanes.append([list(struct.unpack_from("<2I", raw, i * 8))
                          for i in range(len(raw) // 8)])
        print(f"  drip_impl=0x{drip_impl:08x} context_ptr=0x{context_ptr:08x} "
              f"context={len(context)} lanes={sum(len(l) for l in lanes)} records", flush=True)
        return {"holder_words": holder, "drip_impl": drip_impl,
                "context_u32": context, "lanes": lanes}

    # -- main loop
    def run(self, timeout_s: int = 1200) -> int:
        dbg.init()
        dbg.call("SetBreakpoint", {"target": "LoadLibraryW"})
        print("BP on LoadLibraryW set; waiting for the bootstrap module ...", flush=True)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            regs = dbg.registers()
            eip = regs.get("EIP")
            if eip is None:
                time.sleep(0.3)
                continue
            name = self.bpaths.get(eip)
            if name == "BootstrapDerive":
                return self.on_bootstrap(regs)
            if name in ("ManagerCtor", "ArchiveDerive"):
                print(f"HIT {name} (continue)", flush=True)
                dbg.call("run")
                continue
            # any other stop is treated as the LoadLibraryW breakpoint
            args = dbg.read_bytes(regs["ESP"], 8)
            if len(args) < 8:
                dbg.call("run")
                continue
            _ret, arg = struct.unpack("<2I", args)
            mod = dbg.read_bytes(arg, 520).decode("utf-16-le", "replace").split("\x00")[0]
            if ".dll" not in mod.lower() and ".exe" not in mod.lower():
                dbg.call("run")
                continue
            leaf = mod.replace(chr(92), "/").rsplit("/", 1)[-1].lower()
            if HEXNAME.match(leaf):
                print(f"LoadLibraryW({mod!r})", flush=True)
                dbg.call("StepOut")
                time.sleep(0.4)
                base = dbg.registers().get("EAX")
                if base:
                    self.arm(base)
            dbg.call("run")
        print("timeout", flush=True)
        return 1

    def on_bootstrap(self, regs: dict) -> int:
        core = regs["ECX"]
        args = dbg.read_bytes(regs["ESP"], 20)
        ret, path_ptr, path_bytes, params_ptr, params_len = struct.unpack("<5I", args)
        path = dbg.read_bytes(path_ptr, min(path_bytes, 512)).decode("utf-16-le", "replace")
        params = dbg.read_bytes(params_ptr, min(params_len, 256)) if params_len else b""
        print(f"=== BootstrapDerive core=0x{core:08x} path={path!r} "
              f"params_len={params_len} params={params.hex()}", flush=True)
        self.result.update(bootstrap_path=path, params_hex=params.hex(),
                           core_va=hex(core), manager_va=hex(core - 8))
        before = self.read_core(core, "before")
        dbg.call("StepOut")
        time.sleep(0.5)
        after = self.read_core(core, "after")
        drip = self.dump_drip(core)
        if self.module_base:
            seed = dbg.read_bytes(self.module_base + SEED_RVA, 8)
            print(f"  archive_seed {seed.hex()}", flush=True)
            self.result["seed_global"] = seed.hex()
        self.result["before"], self.result["after"] = before, after
        self.result.update(drip)
        return 0

    # -- output
    def write_profile(self, path: str):
        base = self.module_base
        prof = {
            "schema": "hxv4-live-profile/1",
            "note": ("Captured from the running game after BootstrapDerive (see "
                     "doc/hxv4.md). Lane opcodes are normalised to module RVAs, so "
                     "source_module_base is 0."),
            "source_module_base": 0,
            "module_base": hex(base),
            "manager_va": self.result.get("manager_va"),
            "core_va": self.result.get("core_va"),
            "hxv4_key": self.result["after"]["key"],
            "hxv4_nonce0": self.result["after"]["nonce0"],
            "hxv4_nonce1": self.result["after"]["nonce1"],
            "hash_domain": "xp3hnp",
            "holder_words": self.result["holder_words"],
            "context_u32": self.result["context_u32"],
            "lanes": [{"index": i, "records": [[p, op - base] for p, op in lane]}
                      for i, lane in enumerate(self.result["lanes"])],
            "bootstrap_path": self.result.get("bootstrap_path"),
            "bootstrap_params_hex": self.result.get("params_hex"),
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(prof, fp, indent=1)
        print(f"written {path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="resource/hxv4/profile_live.json")
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args()
    cap = Capture()
    rc = cap.run(args.timeout)
    if rc == 0:
        cap.write_profile(args.out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
