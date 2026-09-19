#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained pairing test for unpack_common_res.py (no game assets needed).

Covered:
  1. ver 0x25100: sorted-path <-> record pairing on a synthetic LZ4-chunk package
  2. ver 0x25100: Y == 0 placeholder paths are NOT written, and their target blob is
     deduplicated per X into _containers/ + manifest.json
  3. ver 0x130BA: the path table is [u32 L][path][u32 A] (A AFTER the path) — reading
     it as [u32 A][u32 L][path] must not be what the parser does
  4. Content sniffing rejects a record whose bytes do not match its extension
"""
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lz4.block  # noqa: E402
import unpack_common_res as U  # noqa: E402

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   %s" % msg)
    else:
        print("  FAIL %s" % msg)
        FAILURES.append(msg)


# --------------------------------------------------------------------------- v1 builder
def build_v1(path, files, script_files):
    """files: [(relpath, payload_bytes)]  — stream order == byte-sorted order.
    A record with payload None becomes a Y == 0 placeholder pointing at the previous
    real record (like all.filelist does in the real package)."""
    data = bytearray()
    records = []
    for rel, payload in files:
        if payload is None:
            # 真实包里 Z 是服务器端的真实大小；这里取目标记录长度，便于逐字节比对
            records.append({"X": records[-1]["X"], "Y": 0, "Z": records[-1]["Y"],
                            "H1": hashlib.md5(b"placeholder").digest()})
            continue
        off = len(data)
        data += payload
        records.append({"X": off + 16, "Y": len(payload), "Z": len(payload),
                        "H1": hashlib.md5(payload).digest()})

    idx = bytearray()
    idx += struct.pack("<I", len(records))
    for r in records:
        # 44B 布局：[16B md5][u32 X][u32 Y][16B H2][u32 Z]
        idx += r["H1"]
        idx += struct.pack("<II", r["X"], r["Y"])
        idx += b"\x00" * 16
        idx += struct.pack("<I", r["Z"])
    idx += struct.pack("<I", len(script_files))
    for rel, payload in script_files:
        off = len(data)
        data += payload
        idx += struct.pack("<III", off + 16, len(payload), len(payload))
    idx += struct.pack("<I", len(records) + len(script_files))
    # entry 0 has no A field
    p0 = script_files[0][0].encode()
    idx += struct.pack("<I", len(p0)) + p0
    idx += b"\x00" * ((4 - (len(p0) % 4)) % 4)
    for k, (rel, _p) in enumerate(script_files[1:], start=1):
        pb = rel.encode()
        idx += struct.pack("<II", k, len(pb)) + pb
        idx += b"\x00" * ((4 - (len(pb) % 4)) % 4)
    for k, (rel, _p) in enumerate(files, start=len(script_files)):
        pb = rel.encode()
        idx += struct.pack("<II", k, len(pb)) + pb
        idx += b"\x00" * ((4 - (len(pb) % 4)) % 4)
    # chunk table: one raw chunk (zsize == usize)
    idx += struct.pack("<II", 0, 1)
    idx += struct.pack("<II", len(data), len(data))

    idx_off = 16 + len(data)
    blob = struct.pack("<I", len(idx)) + lz4.block.compress(bytes(idx), store_size=False)
    with open(path, "wb") as f:
        f.write(struct.pack("<4I", 0x00025100, 17, idx_off, len(blob)))
        f.write(bytes(data))
        f.write(blob)


def test_v1_pairing(tmp):
    print("[1] 国内版 ver 0x25100：路径排序配对 + 占位记录")
    files = [
        ("resources/m/00.bin", b"AAA"),
        ("resources/m/01.bin", b"BBBB"),
        ("resources/m/02.bin", None),          # placeholder -> 01.bin
        ("resources/m/03.bin", None),          # placeholder -> 01.bin
        ("resources/m/04.bin", b"CCCCC"),
    ]
    scripts = [("../script/a.lua", b"print('a')"), ("../script/b.json", b'{"b":1}')]
    pkg = os.path.join(tmp, "v1.pkg")
    build_v1(pkg, files, scripts)
    out = os.path.join(tmp, "v1_out")
    rc = U.main_v1(pkg, out)
    check(rc == 0, "main_v1 正常返回")

    got = {}
    for dp, _dn, fs in os.walk(out):
        for f in fs:
            p = os.path.join(dp, f)
            got[os.path.relpath(p, out).replace(os.sep, "/")] = open(p, "rb").read()
    check(got.get("resources/m/00.bin") == b"AAA", "00.bin 内容正确")
    check(got.get("resources/m/01.bin") == b"BBBB", "01.bin 内容正确")
    check(got.get("resources/m/04.bin") == b"CCCCC", "04.bin 内容正确")
    check(got.get("script/a.lua") == b"print('a')", "B 记录（../script）内容正确")
    check(got.get("script/b.json") == b'{"b":1}', "B 记录 json 内容正确")
    check("resources/m/02.bin" not in got, "占位路径 02.bin 不落盘")
    check("resources/m/03.bin" not in got, "占位路径 03.bin 不落盘")

    man = json.load(open(os.path.join(out, "_containers", "manifest.json"), encoding="utf-8"))
    check(man["summary"]["placeholder_paths"] == 2, "manifest 记录 2 条占位路径")
    check(man["summary"]["placeholder_groups"] == 1, "两条占位路径按 X 去重为 1 组")
    grp = man["groups"][0]
    check(grp["target"] == "resources/m/01.bin", "占位组指向同目录的真实记录（%s）" % grp["target"])
    check(grp["members"] == 2, "占位组成员数 = 2")
    blob = open(os.path.join(out, "_containers", grp["container"]), "rb").read()
    check(blob == b"BBBB", "占位 blob 内容 == 目标记录内容")

    rep = json.load(open(os.path.join(out, "_unpack_report.json"), encoding="utf-8"))
    check(rep["files_extracted"] == 5, "报告里写出 5 个文件（3 真实 + 2 脚本）")
    check(rep["md5_bad"] == 0, "md5 全部通过")


# --------------------------------------------------------------------------- v2 builder
def build_v2(path, files):
    """files: [(relpath, payload_bytes, leader_bool)]"""
    data = bytearray(b"\x00" * 16)
    records = []
    for rel, payload, _leader in files:
        off = len(data)
        data += payload
        records.append({"off": off, "len": len(payload), "md5": hashlib.md5(payload).digest()})
    idx_off = len(data)

    idx = bytearray()
    idx += struct.pack("<I", len(records))
    for i, r in enumerate(records):
        idx += r["md5"]
        idx += struct.pack("<III", r["off"], r["len"], 32)     # Z bit5 set -> 44B record
        if i + 1 < len(records):
            idx += b"\x22" * 16
        # 末条记录 X+Y == index_offset，必为 28 字节（不带 H2）
    idx += struct.pack("<I", len(files))
    for k, (rel, _p, leader) in enumerate(files):
        pb = rel.encode()
        a = k | (0x80000000 if leader else 0)
        idx += struct.pack("<I", len(pb)) + pb + struct.pack("<I", a)
    blob = struct.pack("<I", len(idx)) + lz4.block.compress(bytes(idx), store_size=False)
    with open(path, "wb") as f:
        f.write(struct.pack("<4I", 0x000130BA, 17, idx_off, len(blob)))
        f.write(bytes(data[16:]))
        f.write(blob)


def test_v2_path_table(tmp):
    print("[2] 新版 ver 0x130BA：路径表 A 字段在路径 *之后*")
    files = [
        ("resources/aa.bin", b"one", False),
        ("resources/bb.bin", b"two!!", False),
        ("../script/boot.lua", b"print('boot')", True),
    ]
    pkg = os.path.join(tmp, "v2.pkg")
    build_v2(pkg, files)
    out = os.path.join(tmp, "v2_out")
    rc = U.main_v2(pkg, out)
    check(rc == 0, "main_v2 正常返回")
    got = {}
    for dp, _dn, fs in os.walk(out):
        for f in fs:
            p = os.path.join(dp, f)
            got[os.path.relpath(p, out).replace(os.sep, "/")] = open(p, "rb").read()
    check(got.get("resources/aa.bin") == b"one", "aa.bin 配对正确（A 在路径之后）")
    check(got.get("resources/bb.bin") == b"two!!", "bb.bin 配对正确")
    check(got.get("script/boot.lua") == b"print('boot')", "引导记录（bit31）配对正确")
    check("_orphans" not in got, "没有孤立记录")
    # 旧写法 [u32 A][u32 L][path] 会把第一条路径配到最后一条记录
    wrong = 0
    for k, (rel, payload, _l) in enumerate(files):
        if got.get(rel.replace("../", "")) != payload:
            wrong += 1
    check(wrong == 0, "三条路径内容全部与原始字节一致")


def test_sniff_rejects(tmp):
    print("[3] 内容嗅探：扩展名与魔数不符时计为失败")
    bad = os.path.join(tmp, "bad.bin")
    with open(bad, "wb") as f:
        f.write(b"this is not a texture")
    files = [("resources/fake.png", b"this is not a texture")]
    pkg = os.path.join(tmp, "v1bad.pkg")
    build_v1(pkg, files, [("../script/a.lua", b"print('a')")])
    out = os.path.join(tmp, "v1bad_out")
    U.main_v1(pkg, out)
    rep = json.load(open(os.path.join(out, "_unpack_report.json"), encoding="utf-8"))
    check(rep["content_sniff_bad"] == 1, "伪装成 .png 的内容被嗅探拒绝")
    check(rep["md5_ok"] == 1, "同一文件的 md5 仍然通过（嗅探不影响解包）")


def main():
    tmp = tempfile.mkdtemp(prefix="mwpkg_pairing_")
    try:
        test_v1_pairing(tmp)
        test_v2_path_table(tmp)
        test_sniff_rejects(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILURES:
        print("失败 %d 项:" % len(FAILURES))
        for f in FAILURES:
            print("  -", f)
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
