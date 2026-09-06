#!/usr/bin/env python3
"""Unpack Mini World (迷你世界) common_res.pkg (Rainbow engine PackageAsset format).

Two known index versions, dispatched by header ver:

ver 0x25100 (1.58.2):
  [16B header] u32 ver, u32 17, u32 index_offset, u32 index_size
  [data region] LZ4 chunk stream: chunk table at index tail ([usize=262144][zsize])
  [index region] lz4-compressed:
      u32 N;  N * [16B md5][u32 X][u32 Y][16B H2][u32 Z]      (44B A-records)
      u32 M;  M * [u32 X][u32 Y][u32 Z]                        (12B B-records)
      paths: u32 count; entry0 [u32 L][path][pad4]; rest [u32 A][u32 L][path][pad4]
      u32 ?; u32 chunk_count; chunk table
  Path lookup: sort paths by bytes; first M -> B-records, rest -> A-records in
  stream order. X = file coordinate (stream offset = X - 16); Y == 0 marks
  server-side placeholder records (content not in this pkg).

ver 0x130ba (1.59.x):
  [index region] lz4-compressed:
      u32 N;  N * [16B md5][u32 X][u32 Y][u32 Z][16B H2?]      (44B, H2 omitted -> 28B)
        X = raw file offset, Y = length, records chain: X[i+1] == X[i] + Y[i],
        chain closes exactly at index_offset; H2 presence resolved by lookahead
      paths: tightly packed [u32 record_index][u32 L][path], NO alignment pad;
        record_index in [0, N); ~10% of records have no path entry (orphans)
      u32 tail (?)
  [data region] UNCOMPRESSED raw bytes (md5 of data[X:X+Y] == record md5).
"""
import struct, sys, os, json, hashlib
import lz4.block

# Windows 控制台默认 GBK/cp936，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 用法: python3 unpack_common_res.py [common_res.pkg 路径] [输出目录]
# 默认: ./迷你世界_1.58.2/assets/common_res.pkg  ./common_res_unpacked
PKG = sys.argv[1] if len(sys.argv) > 1 else "迷你世界_1.58.2/assets/common_res.pkg"
OUT = sys.argv[2] if len(sys.argv) > 2 else "common_res_unpacked"

HDR_SIZE = 16
VER_1582 = 0x00025100
VER_V2 = 0x000130BA


def main():
    with open(PKG, "rb") as f:
        hdr = f.read(HDR_SIZE)
    ver, unk, idx_off, idx_size = struct.unpack("<4I", hdr)
    if ver == VER_V2:
        main_v2()
        return
    main_v1()


def main_v2():
    """ver 0x130ba: variable-length records + tight path table + raw data."""
    with open(PKG, "rb") as f:
        hdr = f.read(HDR_SIZE)
    ver, unk, idx_off, idx_size = struct.unpack("<4I", hdr)
    print(f"header: ver={ver:#x} unk={unk} index@{idx_off}+{idx_size}")
    with open(PKG, "rb") as f:
        f.seek(idx_off)
        iblob = f.read(idx_size)
    iusize = struct.unpack_from("<I", iblob, 0)[0]
    idx = lz4.block.decompress(iblob[4:], uncompressed_size=iusize)
    print(f"index: {len(idx)} bytes")

    (N,) = struct.unpack_from("<I", idx, 0)
    # records: variable length (28B without H2, 44B with), resolved by chain lookahead
    pos = 4
    recs = []           # (X, Y, Z, md5)
    while pos < len(idx):
        if pos + 28 > len(idx):
            break
        X, Y, Z = struct.unpack_from("<III", idx, pos + 16)
        md5 = idx[pos:pos + 16]
        nxt = X + Y
        if nxt == idx_off:          # last record: chain closes at index start
            recs.append((X, Y, Z, md5))
            pos += 28
            break
        n44 = struct.unpack_from("<I", idx, pos + 60)[0] if pos + 64 <= len(idx) else -1
        n28 = struct.unpack_from("<I", idx, pos + 44)[0] if pos + 48 <= len(idx) else -1
        recs.append((X, Y, Z, md5))
        pos += 28 if (n28 == nxt and n44 != nxt) else 44
    print(f"records: {len(recs)}  (declared N={N})")
    if len(recs) != N:
        print(f"警告: 解析出 {len(recs)} 条记录 != N={N}")

    # paths: tightly packed [u32 record_index][u32 L][path L bytes]
    entries = []
    q = pos
    while q + 8 <= len(idx) - 4:
        Xi, L = struct.unpack_from("<II", idx, q)
        if Xi >= len(recs) or L < 1 or L > 400 or q + 8 + L > len(idx):
            break
        p = idx[q + 8:q + 8 + L]
        if not all(32 <= b < 127 for b in p):
            break
        entries.append((Xi, p))
        q += 8 + L
    tail = struct.unpack_from("<I", idx, q)[0] if q + 4 <= len(idx) else None
    print(f"paths: {len(entries)}  tail u32: {tail}")

    os.makedirs(OUT, exist_ok=True)
    orphan_dir = os.path.join(OUT, "_orphans")
    os.makedirs(orphan_dir, exist_ok=True)
    os.makedirs(os.path.join(OUT, "_containers"), exist_ok=True)

    md5_ok = md5_bad = 0
    extracted = 0
    orphans = {}
    errors = []
    with open(PKG, "rb") as f:
        for i, (X, Y, Z, md5) in enumerate(recs):
            try:
                f.seek(X)
                blob = f.read(Y)
            except OSError as e:
                errors.append((i, f"read fail: {e}"))
                continue
            if hashlib.md5(blob).digest() == md5:
                md5_ok += 1
            else:
                md5_bad += 1
                if md5_bad <= 10:
                    errors.append((i, "md5 mismatch"))
            named = [p for xi, p in entries if xi == i]
            if named:
                for p in named:
                    rel = p.decode("utf-8", "replace")
                    dest = os.path.join(OUT, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as g:
                        g.write(blob)
                    extracted += 1
            else:
                orphans[i] = blob
            if (i + 1) % 5000 == 0:
                print(f"  {i+1}/{len(recs)} ... extracted={extracted}", flush=True)

    for i, blob in orphans.items():
        with open(os.path.join(orphan_dir, f"record_{i}.bin"), "wb") as g:
            g.write(blob)
    with open(os.path.join(OUT, "_containers", "manifest.json"), "w", encoding="utf-8") as g:
        json.dump({
            "records": [{"index": i, "X": X, "Y": Y, "Z": Z, "md5": md5.hex(),
                         "paths": [p.decode() for xi, p in entries if xi == i]}
                        for i, (X, Y, Z, md5) in enumerate(recs)],
            "tail_u32": tail,
            "note": "ver 0x130ba: raw (uncompressed) records; X=raw offset, md5 verified"},
            g, ensure_ascii=False)
    print(f"extracted: {extracted}  md5 ok: {md5_ok} bad: {md5_bad}")
    print(f"pathless (orphan) records: {len(orphans)} -> _orphans/")
    if errors:
        print(f"errors: {len(errors)}")
        for e in errors[:10]:
            print("  ", e)
    with open(os.path.join(OUT, "_unpack_report.json"), "w", encoding="utf-8") as g:
        json.dump({"pkg": PKG, "format": "v2 (0x130ba)",
                   "records": len(recs), "paths": len(entries),
                   "files_extracted": extracted, "orphans": len(orphans),
                   "md5_ok": md5_ok, "md5_bad": md5_bad,
                   "errors": errors[:100]}, g, ensure_ascii=False, indent=1)


def main_v1():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "_containers"), exist_ok=True)
    with open(PKG, "rb") as f:
        hdr = f.read(HDR_SIZE)
    ver, unk, idx_off, idx_size = struct.unpack("<4I", hdr)
    print(f"header: ver={ver:#x} unk={unk} index@{idx_off}+{idx_size}")

    # ---- index ----
    f = open(PKG, "rb")
    f.seek(idx_off)
    iblob = f.read(idx_size)
    iusize = struct.unpack("<I", iblob[:4])[0]
    idx = lz4.block.decompress(iblob[4:], uncompressed_size=iusize)
    print(f"index: {len(idx)} bytes")

    pos = 0
    (N,) = struct.unpack_from("<I", idx, pos); pos += 4
    recA = []
    for i in range(N):
        H1 = idx[pos:pos+16]
        X, Y = struct.unpack_from("<II", idx, pos+16)
        H2 = idx[pos+24:pos+40]
        (Z,) = struct.unpack_from("<I", idx, pos+40)
        pos += 44
        recA.append({"H1": H1, "X": X, "Y": Y, "H2": H2, "Z": Z})
    (M,) = struct.unpack_from("<I", idx, pos); pos += 4
    recB = []
    for i in range(M):
        X, Y, Z = struct.unpack_from("<III", idx, pos); pos += 12
        recB.append({"X": X, "Y": Y, "Z": Z})
    print(f"A-records: {N}  B-records: {M}")

    # ---- paths ----
    (count,) = struct.unpack_from("<I", idx, pos); pos += 4
    if count != N + M:
        sys.exit(f"此 pkg 的索引为未支持的变体（路径数 {count} != 记录数 {N + M}），"
                 f"common_res.pkg / core_res.pkg / game_script.pkg 不受影响")
    L0 = struct.unpack_from("<I", idx, pos)[0]
    p0 = idx[pos+4:pos+4+L0]
    pos += 4 * ((4 + L0 + 3) // 4)
    paths = [p0]
    for k in range(count - 1):
        A, L = struct.unpack_from("<II", idx, pos)
        p = idx[pos+8:pos+8+L]
        assert all(32 <= b < 127 for b in p), (k, p[:40])
        paths.append(p)
        pos += 4 * ((8 + L + 3) // 4)
    print(f"paths: {len(paths)}")

    # ---- chunk table ----
    chunk_count = struct.unpack_from("<I", idx, pos+4)[0]
    tpos = pos + 8
    zsizes, usizes = [], []
    for k in range(chunk_count - 1):
        us, z = struct.unpack_from("<II", idx, tpos); tpos += 8
        usizes.append(us); zsizes.append(z)
    lus, lz = struct.unpack_from("<II", idx, tpos)
    usizes.append(lus); zsizes.append(lz)
    total_unc = sum(usizes)
    print(f"chunks: {len(usizes)}  stream: {total_unc} bytes")

    coffs, acc = [], HDR_SIZE
    for z in zsizes:
        coffs.append(acc); acc += z
    uoff, acc = [], 0
    for u in usizes:
        uoff.append(acc); acc += u

    cache = {}
    CACHE_MAX = 48
    def read_stream(off, ln):
        out = bytearray()
        while ln > 0:
            lo, hi = 0, len(uoff) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if uoff[mid] <= off: lo = mid
                else: hi = mid - 1
            ci = lo
            ch = cache.get(ci)
            if ch is None:
                f.seek(coffs[ci])
                if zsizes[ci] == usizes[ci]:
                    ch = f.read(zsizes[ci])
                else:
                    ch = lz4.block.decompress(f.read(zsizes[ci]), uncompressed_size=usizes[ci])
                cache[ci] = ch
                if len(cache) > CACHE_MAX:
                    cache.pop(next(iter(cache)))
            s = off - uoff[ci]
            take = min(ln, len(ch) - s)
            out += ch[s:s+take]
            off += take; ln -= take
        return bytes(out)

    # ---- mapping: sort paths, pair with records in stream order ----
    order = sorted(range(len(paths)), key=lambda i: paths[i])
    # sanity: first M sorted paths should be the ../script ones
    n_script = sum(1 for p in paths if p.startswith(b"../"))
    print(f"script paths: {n_script} (B count {M})")
    assert n_script == M
    for k in range(M):
        assert paths[order[k]].startswith(b"../")

    def safe_rel(p):
        s = p.decode("utf-8", "replace")
        while s.startswith("../"):
            s = s[3:]
        return s

    md5_ok = md5_bad = 0
    ext_ok = ext_bad = 0
    extracted = 0
    alias_manifest = []       # (path, container_name, H1hex)
    containers = {}           # (X, Z) -> name
    errors = []

    for k in range(len(paths)):
        p = paths[order[k]]
        if k < M:
            r = recB[k]; is_alias = r["Y"] <= 0; H1 = None
        else:
            r = recA[k - M]; is_alias = r["Y"] <= 0; H1 = r["H1"]
        rel = safe_rel(p)
        if is_alias:
            key = (r["X"], r["Z"])
            cname = containers.get(key)
            if cname is None:
                cname = f"container_{r['X']:x}_{r['Z']}.bin"
                containers[key] = cname
                try:
                    blob = read_stream(r["X"] - HDR_SIZE, r["Z"])
                    with open(os.path.join(OUT, "_containers", cname), "wb") as g:
                        g.write(blob)
                except Exception as e:
                    errors.append((rel, f"container read fail: {e}"))
                    continue
            alias_manifest.append({"path": rel, "container": cname,
                                   "H1": H1.hex() if H1 else None, "Z": r["Z"]})
            continue
        try:
            data = read_stream(r["X"] - HDR_SIZE, r["Y"])
        except Exception as e:
            errors.append((rel, f"read fail: {e}"))
            continue
        if H1 is not None:
            if hashlib.md5(data).digest() == H1: md5_ok += 1
            else: md5_bad += 1
        ext = p.rsplit(b".", 1)[-1] if b"." in p else b""
        if ext == b"ogg" and len(data) >= 4:
            if data[:4] == b"OggS": ext_ok += 1
            else: ext_bad += 1
        elif ext == b"json" and len(data) >= 4:
            if data.lstrip()[:1] == b"{": ext_ok += 1
            else: ext_bad += 1
        dest = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as g:
            g.write(data)
        extracted += 1
        if extracted % 5000 == 0:
            print(f"  extracted {extracted} ...")

    print(f"extracted: {extracted}  md5 ok: {md5_ok} bad: {md5_bad}")
    print(f"extension/content agreement: ok {ext_ok} bad {ext_bad}")
    print(f"alias (containerized) paths: {len(alias_manifest)}  containers: {len(containers)}")
    if errors:
        print(f"errors: {len(errors)}")
        for e in errors[:10]: print("  ", e)
    with open(os.path.join(OUT, "_containers", "manifest.json"), "w", encoding="utf-8") as g:
        json.dump({"aliases": alias_manifest,
                   "note": "Y==0 records reference bundles stored in _containers; H1 = md5 of the sub-file content"},
                  g, ensure_ascii=False)
    with open(os.path.join(OUT, "_unpack_report.json"), "w", encoding="utf-8") as g:
        json.dump({"pkg": PKG, "files_extracted": extracted,
                   "md5_ok": md5_ok, "md5_bad": md5_bad,
                   "aliases": len(alias_manifest), "containers": len(containers),
                   "errors": errors[:100]}, g, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
