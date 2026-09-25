"""Minimal PDS3 ODL label parser + IMAGE reader for detached-label raw EDRs (MSL Navcam). Read-only; never writes.

Handles CRLF line endings, multi-line values, GROUP/OBJECT nesting and the `^IMAGE = ("file.IMG", <record>)` pointer.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_KV = re.compile(r"^\s*([\^A-Za-z0-9_:]+)\s*=\s*(.*)$")


def _clean(v: str):
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.startswith("(") and v.endswith(")"):
        return [_clean(x) for x in re.findall(r'"[^"]*"|[^,()]+', v[1:-1]) if x.strip()]
    m = re.match(r"^(-?[\d.]+(?:[eE][-+]?\d+)?)\s*(<[^>]+>)?$", v)
    if m:
        num = m.group(1)
        try:
            return int(num) if re.fullmatch(r"-?\d+", num) else float(num)
        except ValueError:
            return v
    return v


def parse_label(text: str) -> dict:
    """{key: value} for top-level keys, {GROUP_NAME: {...}} for groups, {'OBJECT:<NAME>': {...}} for objects."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    root: dict = {}
    stack = [root]
    pending_key, pending_val = None, ""

    def commit(k, v):
        stack[-1][k] = _clean(v)

    for raw in lines:
        line = re.sub(r"/\*.*?\*/", "", raw).rstrip()
        if pending_key is not None:
            pending_val += " " + line.strip()
            if pending_val.count("(") <= pending_val.count(")") and pending_val.count('"') % 2 == 0:
                commit(pending_key, pending_val)
                pending_key = None
            continue
        if not line.strip() or line.strip() == "END":
            continue
        m = _KV.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k in ("GROUP", "OBJECT"):
            node: dict = {}
            stack[-1][f"OBJECT:{v}" if k == "OBJECT" else v] = node
            stack.append(node)
            continue
        if k in ("END_GROUP", "END_OBJECT"):
            if len(stack) > 1:
                stack.pop()
            continue
        if (v.count("(") > v.count(")")) or (v.count('"') % 2 == 1):
            pending_key, pending_val = k, v
            continue
        commit(k, v)
    return root


def read_image(img_path: Path, label: dict) -> np.ndarray:
    """Pixel array (lines × samples) as float32 with the archive's integer values (12-bit data in 16-bit words)."""
    obj = label["OBJECT:IMAGE"]
    ptr = label.get("^IMAGE")
    record_bytes = int(label.get("RECORD_BYTES", 1))
    offset = (int(ptr[1]) - 1) * record_bytes if isinstance(ptr, list) and len(ptr) > 1 else 0
    lines, samples, bits = int(obj["LINES"]), int(obj["LINE_SAMPLES"]), int(obj["SAMPLE_BITS"])
    bands = int(obj.get("BANDS", 1))
    stype = str(obj.get("SAMPLE_TYPE", "MSB_INTEGER"))
    endian = ">" if stype.startswith("MSB") else "<"
    kind = "u" if "UNSIGNED" in stype else "i"
    dtype = np.dtype(f"{endian}{kind}{bits // 8}") if bits > 8 else np.dtype("u1")
    prefix = int(obj.get("LINE_PREFIX_BYTES", 0) or 0)
    n = lines * samples * bands
    with open(img_path, "rb") as fh:
        fh.seek(offset)
        buf = fh.read(n * dtype.itemsize + prefix * lines * bands)
    if prefix:
        row = samples * dtype.itemsize + prefix
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(lines * bands, row)[:, prefix:].copy().view(dtype)
    else:
        arr = np.frombuffer(buf[: n * dtype.itemsize], dtype=dtype)
    return arr.reshape(bands, lines, samples)[0].astype(np.float32)
