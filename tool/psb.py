"""PSB (M2 "Packaged Structure Binary") v3 reader / string-level rewriter.

Reference: FreeMote (https://github.com/UlyssesWu/FreeMote), files
  FreeMote.Psb/Psb.cs          (LoadFromStream / Unpack / LoadNames)
  FreeMote.Psb/PsbValues.cs    (PsbArray / PsbNumber / PsbString)
  FreeMote/PsbHeader.cs        (header layout, checksum)

Only what this project needs is implemented:
  * parse the whole object graph (dict / list / int / float / bool / None / str / resource)
  * rewrite the string pool in place (same string count, arbitrary new lengths)
  * MDF shell ("mdf\\0" + u32 raw length + zlib stream) used by this game's *.scn

All integers inside PSB are little-endian.
"""

from __future__ import annotations

import io
import struct
import zlib

PSB_SIG = b"PSB\x00"
MDF_SIG = b"mdf\x00"

# PsbObjType
NONE = 0x00
NULL = 0x01
FALSE = 0x02
TRUE = 0x03
NUMBER_N0 = 0x04
NUMBER_N1 = 0x05
NUMBER_N8 = 0x0C
ARRAY_N1 = 0x0D
ARRAY_N8 = 0x14
STRING_N1 = 0x15
STRING_N4 = 0x18
RESOURCE_N1 = 0x19
RESOURCE_N4 = 0x1C
FLOAT0 = 0x1D
FLOAT = 0x1E
DOUBLE = 0x1F
LIST = 0x20
OBJECTS = 0x21
EXTRA_CHUNK_N1 = 0x22
EXTRA_CHUNK_N4 = 0x25


class PsbError(Exception):
    pass


class _Root:
    """Sentinel: "walk from the root" (distinct from a real `None` node)."""


_ROOT = _Root()


class PsbString:
    """A string slot: `index` is the offset-table index, `value` the decoded text."""

    __slots__ = ("index", "value")

    def __init__(self, index: int, value: str | None = None):
        self.index = index
        self.value = value

    def __repr__(self):
        return f"PsbString(#{self.index}, {self.value!r})"

    def __eq__(self, other):
        return isinstance(other, PsbString) and self.index == other.index

    def __hash__(self):
        return hash(("psbstr", self.index))


class PsbResource:
    __slots__ = ("index", "is_extra", "data")

    def __init__(self, index: int, is_extra: bool = False):
        self.index = index
        self.is_extra = is_extra
        self.data = None

    def __repr__(self):
        return f"PsbResource(#{self.index}{'x' if self.is_extra else ''})"


def _read_le(br: io.BytesIO, n: int) -> int:
    b = br.read(n)
    if len(b) != n:
        raise PsbError("unexpected EOF")
    return int.from_bytes(b, "little")


def _read_array(br: io.BytesIO) -> list[int]:
    """PsbArray: type byte (ArrayN1..N8) -> count bytes, entry-type byte -> entry width."""
    t = br.read(1)
    if not t:
        raise PsbError("unexpected EOF in array")
    t = t[0]
    if not (ARRAY_N1 <= t <= ARRAY_N8):
        raise PsbError(f"not an array type byte: 0x{t:02x} at 0x{br.tell() - 1:x}")
    count = _read_le(br, t - ARRAY_N1 + 1)
    entry_type = br.read(1)[0]
    entry_len = entry_type - NUMBER_N8
    if entry_len == 0 and count == 0:
        return []
    if not (1 <= entry_len <= 8):
        raise PsbError(f"bad array entry width {entry_len}")
    buf = br.read(entry_len * count)
    if len(buf) != entry_len * count:
        raise PsbError("unexpected EOF in array body")
    return [int.from_bytes(buf[i * entry_len:(i + 1) * entry_len], "little") for i in range(count)]


def _array_type(count: int) -> tuple[int, int]:
    """Return (type byte, count-width) for a count value."""
    for width in range(1, 9):
        if count < (1 << (8 * width)):
            return ARRAY_N1 + width - 1, width
    raise PsbError("array too long")


def _read_array_style(br: io.BytesIO) -> tuple[list[int], int, int]:
    """Like _read_array but also reports (count_width, entry_width)."""
    t = br.read(1)[0]
    if not (ARRAY_N1 <= t <= ARRAY_N8):
        raise PsbError(f"not an array type byte: 0x{t:02x}")
    count_width = t - ARRAY_N1 + 1
    count = _read_le(br, count_width)
    entry_width = br.read(1)[0] - NUMBER_N8
    if entry_width == 0 and count == 0:
        return [], count_width, 0
    if not (1 <= entry_width <= 8):
        raise PsbError(f"bad array entry width {entry_width}")
    buf = br.read(entry_width * count)
    if len(buf) != entry_width * count:
        raise PsbError("unexpected EOF in array body")
    return ([int.from_bytes(buf[i * entry_width:(i + 1) * entry_width], "little") for i in range(count)],
            count_width, entry_width)


def _pack_array_styled(values: list[int], count_width: int | None = None,
                       entry_width: int | None = None) -> bytes:
    """Encode a PsbArray, keeping the original field widths when they still fit."""
    needed_entry = 0
    for v in values:
        for w in range(1, 9):
            if v < (1 << (8 * w)):
                needed_entry = max(needed_entry, w)
                break
    if entry_width is not None:
        needed_entry = max(needed_entry, entry_width)
    needed_count = 1
    for w in range(1, 9):
        if len(values) < (1 << (8 * w)):
            needed_count = w
            break
    if count_width is not None:
        needed_count = max(needed_count, count_width)
    out = bytearray([ARRAY_N1 + needed_count - 1])
    out += len(values).to_bytes(needed_count, "little")
    out.append(NUMBER_N8 + needed_entry)
    for v in values:
        out += v.to_bytes(needed_entry, "little")
    return bytes(out)


def _pack_array(values: list[int]) -> bytes:
    if not values:
        return bytes([ARRAY_N1, 0, NUMBER_N1])
    width = 1
    for v in values:
        for w in range(1, 9):
            if v < (1 << (8 * w)):
                width = max(width, w)
                break
    type_byte, count_width = _array_type(len(values))
    out = bytearray([type_byte])
    out += len(values).to_bytes(count_width, "little")
    out.append(NUMBER_N8 + width)
    for v in values:
        out += v.to_bytes(width, "little")
    return bytes(out)


class PsbFile:
    """Parsed PSB (optionally wrapped in an MDF shell)."""

    def __init__(self, data: bytes):
        self.raw = data
        self.is_mdf = data[:3].lower() == b"mdf"
        body = data
        if self.is_mdf:
            self.mdf_length = struct.unpack_from("<I", data, 4)[0]
            body = zlib.decompress(data[8:])
            if len(body) != self.mdf_length:
                raise PsbError(f"mdf length mismatch: {len(body)} != {self.mdf_length}")
        self.body = body
        self._parse()

    # ---------------------------------------------------------------- parse
    def _parse(self):
        body = self.body
        if body[:4] != PSB_SIG:
            raise PsbError(f"not a PSB: {body[:4]!r}")
        self.version = struct.unpack_from("<H", body, 4)[0]
        self.header_encrypt = struct.unpack_from("<H", body, 6)[0]
        if self.header_encrypt:
            raise PsbError("encrypted header is not supported")
        if self.version != 3:
            raise PsbError(f"unsupported PSB version {self.version}")
        (self.header_length, self.offset_names, self.offset_strings,
         self.offset_strings_data, self.offset_chunk_offsets, self.offset_chunk_lengths,
         self.offset_chunk_data, self.offset_entries, self.checksum) = struct.unpack_from("<9I", body, 8)

        br = io.BytesIO(body)
        # --- names (charset / trie data / trie roots)
        br.seek(self.offset_names)
        self.charset = _read_array(br)
        self.names_data = _read_array(br)
        self.name_indexes = _read_array(br)
        self.names = [self._decode_name(i) for i in self.name_indexes]

        # --- string offset table
        br.seek(self.offset_strings)
        self.string_offsets, self._str_count_width, self._str_entry_width = _read_array_style(br)
        self.strings: dict[int, PsbString] = {}
        self.string_order: list[int] = []

        # --- resources
        br.seek(self.offset_chunk_offsets)
        self.chunk_offsets = _read_array(br)
        br.seek(self.offset_chunk_lengths)
        self.chunk_lengths = _read_array(br)
        self.resources: dict[object, PsbResource] = {}

        # --- object graph
        br.seek(self.offset_entries)
        self.root = self._unpack(br)

    def _decode_name(self, root_idx: int) -> str:
        out = []
        node = self.names_data[root_idx]
        for _ in range(4096):
            if node == 0:
                break
            nxt = self.names_data[node]
            delta = self.charset[nxt]
            out.append((node - delta) & 0xFF)
            node = nxt
        else:
            raise PsbError("name trie loop")
        out.reverse()
        return bytes(out).decode("utf-8", errors="replace")

    def get_string(self, index: int) -> PsbString:
        """Resolve a string slot by index (cached)."""
        s = self.strings.get(index)
        if s is not None:
            return s
        start = self.offset_strings_data + self.string_offsets[index]
        end = self.body.index(b"\x00", start)
        s = PsbString(index, self.body[start:end].decode("utf-8", errors="replace"))
        self.strings[index] = s
        self.string_order.append(index)
        return s

    def string_value(self, index: int) -> str:
        return self.get_string(index).value

    def _unpack(self, br: io.BytesIO):
        pos = br.tell()
        t = br.read(1)
        if not t:
            raise PsbError("unexpected EOF in object")
        t = t[0]
        if t in (NONE, NULL):
            return None
        if t == FALSE:
            return False
        if t == TRUE:
            return True
        if t == NUMBER_N0:
            return 0
        if NUMBER_N1 <= t <= NUMBER_N8:
            return _read_le(br, t - NUMBER_N0)
        if ARRAY_N1 <= t <= ARRAY_N8:
            br.seek(pos)
            return _read_array(br)
        if STRING_N1 <= t <= STRING_N4:
            return self.get_string(_read_le(br, t - STRING_N1 + 1))
        if RESOURCE_N1 <= t <= RESOURCE_N4:
            idx = _read_le(br, t - RESOURCE_N1 + 1)
            res = self.resources.get(idx)
            if res is None:
                res = self.resources[idx] = PsbResource(idx)
            return res
        if t == FLOAT0:
            return 0.0
        if t == FLOAT:
            return struct.unpack("<f", br.read(4))[0]
        if t == DOUBLE:
            return struct.unpack("<d", br.read(8))[0]
        if t == LIST:
            offsets = _read_array(br)
            base = br.tell()
            out = []
            for off in offsets:
                br.seek(base + off)
                out.append(self._unpack(br))
            br.seek(base)
            return out
        if t == OBJECTS:
            name_refs = _read_array(br)
            offsets = _read_array(br)
            base = br.tell()
            out = {}
            for i, nref in enumerate(name_refs):
                br.seek(base + offsets[i])
                out[self.names[nref]] = self._unpack(br)
            br.seek(base)
            return out
        if EXTRA_CHUNK_N1 <= t <= EXTRA_CHUNK_N4:
            idx = _read_le(br, t - EXTRA_CHUNK_N1 + 1)
            key = ("x", idx)
            res = self.resources.get(key)
            if res is None:
                res = self.resources[key] = PsbResource(idx, True)
            return res
        raise PsbError(f"unknown object type 0x{t:02x} at 0x{pos:x}")

    # ---------------------------------------------------------------- write
    def rebuild(self, new_strings: dict[int, str] | None = None) -> bytes:
        """Re-emit the file, replacing the value of the given string slots.

        Everything except the string pool is copied verbatim, so the object graph,
        name trie and resource chunks stay byte-identical.
        """
        new_strings = new_strings or {}
        count = len(self.string_offsets)
        data = bytearray()
        offsets = []
        for i in range(count):
            offsets.append(len(data))
            value = new_strings.get(i)
            if value is None:
                start = self.offset_strings_data + self.string_offsets[i]
                end = self.body.index(b"\x00", start)
                raw = self.body[start:end]
            else:
                raw = value.encode("utf-8")
            data += raw + b"\x00"

        offsets_blob = _pack_array_styled(offsets, self._str_count_width, self._str_entry_width)
        header = bytearray(self.body[:self.header_length])
        names_region = self.body[self.header_length:self.offset_strings]
        tail = self.body[self.offset_chunk_offsets:]

        new_offsets_strings_data = self.offset_strings + len(offsets_blob)
        shift = (len(offsets_blob) - (self.offset_strings_data - self.offset_strings)) + \
                (len(data) - (self.offset_chunk_offsets - self.offset_strings_data))

        vals = [self.header_length, self.offset_names, self.offset_strings,
                new_offsets_strings_data,
                self.offset_chunk_offsets + shift, self.offset_chunk_lengths + shift,
                self.offset_chunk_data + shift, self.offset_entries + shift]
        struct.pack_into("<8I", header, 8, *vals)
        checksum = zlib.adler32(bytes(header[8:8 + 32])) & 0xFFFFFFFF
        struct.pack_into("<I", header, 0x28, checksum)

        body = bytes(header) + names_region + offsets_blob + bytes(data) + tail
        if self.is_mdf:
            return MDF_SIG + struct.pack("<I", len(body)) + zlib.compress(body, 9)
        return body

    # ---------------------------------------------------------------- helpers
    def iter_strings(self, node=_ROOT, path: str = "$"):
        """Yield (path, PsbString) for every string slot in the graph.

        Iterative on purpose: a `node=None` default would collide with the many
        real `null` values inside the graph and silently restart the walk from
        the root, which recurses until the stack dies.
        """
        if node is _ROOT:
            node = self.root
        stack = [(node, path)]
        while stack:
            cur, cur_path = stack.pop()
            if isinstance(cur, PsbString):
                yield cur_path, cur
            elif isinstance(cur, dict):
                for k, v in reversed(list(cur.items())):
                    stack.append((v, f"{cur_path}.{k}"))
            elif isinstance(cur, list):
                for i in range(len(cur) - 1, -1, -1):
                    stack.append((cur[i], f"{cur_path}[{i}]"))


def load(path: str) -> PsbFile:
    with open(path, "rb") as fp:
        return PsbFile(fp.read())
