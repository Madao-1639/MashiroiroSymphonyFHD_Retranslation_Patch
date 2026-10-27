"""Regression test for tool/hxv4.py crypto primitives against published vectors.

Usage (from project root): mamba run -n GalRev python script/verify_crypto.py
"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import hxv4

FAILED = []


def check(name, got, want):
    ok = got == want
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        FAILED.append(name)
        print(f"     got  {got}\n     want {want}")


def main():
    # Poly1305, RFC 7539 section 2.5.2
    key = bytes.fromhex("85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b")
    check("poly1305 rfc7539",
          hxv4.poly1305(key, b"Cryptographic Forum Research Group").hex(),
          "a8061dc1305136c6c22b8baf0c0127a9")

    # ChaCha20 permutation, RFC 7539 section 2.3.2 (IETF layout assembled by hand
    # from the shared permutation so the DJB-specific layout stays out of the test)
    s = list(hxv4._SIGMA) + list(struct.unpack("<8I", bytes(range(32)))) + \
        [1] + list(struct.unpack("<3I", bytes.fromhex("000000090000004a00000000")))
    x = s[:]
    hxv4._permute(x)
    block = struct.pack("<16I", *[(x[i] + s[i]) & 0xFFFFFFFF for i in range(16)]).hex()
    check("chacha20 block rfc7539", block,
          "10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
          "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e")

    # HChaCha20, draft-irtf-cfrg-xchacha section 2.2.1
    check("hchacha20 draft-xchacha",
          hxv4.hchacha20(bytes(range(32)), bytes.fromhex("000000090000004a0000000031415927")).hex(),
          "82413b4227b27bfed30e42508a877d73a0f9e4d58a74a853c12ec41326d3ecdc")

    # AEAD round trip + tag rejection
    key32, nonce, pt = bytes(range(24)) * 1 + bytes(8), bytes(range(24)), b"hello hxv4" * 10
    sealed = hxv4.xchacha_seal(key32, nonce, pt)
    check("aead roundtrip", hxv4.xchacha_open(key32, nonce, sealed), pt)
    check("aead rejects bad tag", hxv4.xchacha_open(key32, nonce, b"\x00" * 16 + sealed[16:]), None)

    if FAILED:
        print(f"FAILED: {len(FAILED)} check(s)")
        return 1
    print("all crypto checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
