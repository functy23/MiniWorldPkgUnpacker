#!/usr/bin/env python3
"""Unpack Mini World (迷你世界) common_res.pkg (Rainbow engine PackageAsset format).

Two index versions, dispatched by header ver:

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

ver 0x130ba (newer builds):
  [index region] lz4-compressed:
      u32 N;  N * [16B md5][u32 X][u32 Y][u32 Z][16B H2?]      (44B, H2 omitted -> 28B)
        X = raw file offset, Y = length, records chain: X[i+1] == X[i] + Y[i],
        chain closes exactly at index_offset; H2 presence resolved by lookahead
      u32 C;  C path entries, tightly packed:
        [u32 L][L path bytes][u32 A]   -- A comes AFTER the path, see below
      u32 tail (?)
  [data region] UNCOMPRESSED raw bytes (md5 of data[X:X+Y] == record md5).

  A = record index for that path (bit31 set -> B/leader record, clear -> A record).
  NOTE: reading this table as [u32 A][u32 L][path] (A before the path) shifts every
  path onto the previous record and silently produces a wrong tree.

Placeholder records (Y == 0, ver 0x25100):
  58,180 paths in common_res.pkg 1.58.2 have Y == 0.  Their content is NOT in the
  package: X points at the *sibling* `all.filelist` of the same directory (or at a
  small shared blob), and the payload is downloaded on demand from the game server.
  Those paths are therefore NOT written at their real location; their target blobs
  are deduplicated by X into _containers/ and listed in _containers/manifest.json.
"""
import struct, sys, os, json, hashlib
import lz4.block

# Windows 控制台默认 GBK/cp936，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HDR_SIZE = 16
VER_1582 = 0x00025100
VER_V2 = 0x000130BA

# 默认用法（与旧版一致）: python3 unpack_common_res.py [pkg] [outdir]
DEFAULT_PKG = "迷你世界_1.58.2/assets/common_res.pkg"
DEFAULT_OUT = "common_res_unpacked"


class UnsupportedVariant(Exception):
    """索引结构不属于已知的任何一种变体。"""


# --------------------------------------------------------------------------- 索引解析
def parse_v1_index(idx):
    """ver 0x25100 的索引区（已解压）。返回 (recA, recB, paths, pos)。

    recA[i] = {H1, X, Y, H2, Z}   recB[i] = {X, Y, Z}
    paths 为原始字节路径（未排序）；pos 指向分块表前的那个 u32。
    """
    pos = 0
    (N,) = struct.unpack_from("<I", idx, pos); pos += 4
    recA = []
    for _ in range(N):
        recA.append({
            "H1": idx[pos:pos + 16],
            "X": struct.unpack_from("<I", idx, pos + 16)[0],
            "Y": struct.unpack_from("<I", idx, pos + 20)[0],
            "H2": idx[pos + 24:pos + 40],
            "Z": struct.unpack_from("<I", idx, pos + 40)[0],
        })
        pos += 44
    (M,) = struct.unpack_from("<I", idx, pos); pos += 4
    recB = []
    for _ in range(M):
        X, Y, Z = struct.unpack_from("<III", idx, pos); pos += 12
        recB.append({"X": X, "Y": Y, "Z": Z})

    (count,) = struct.unpack_from("<I", idx, pos); pos += 4
    if count != N + M:
        raise UnsupportedVariant(
            "路径数 %d != 记录数 %d（N=%d M=%d）——此 pkg 的索引为未知变体；"
            "common_res.pkg / core_res.pkg / game_script.pkg / material_ogles*.pkg 不受影响"
            % (count, N + M, N, M))
    L0 = struct.unpack_from("<I", idx, pos)[0]
    paths = [idx[pos + 4:pos + 4 + L0]]
    pos += 4 * ((4 + L0 + 3) // 4)
    for _ in range(count - 1):
        A, L = struct.unpack_from("<II", idx, pos)
        paths.append(idx[pos + 8:pos + 8 + L])
        pos += 4 * ((8 + L + 3) // 4)
    return recA, recB, paths, pos


def parse_chunk_table(idx, pos):
    """分块表：u32 ?; u32 chunk_count; (count-1)*[u32 262144][u32 zsize] + 末块。"""
    chunk_count = struct.unpack_from("<I", idx, pos + 4)[0]
    tpos = pos + 8
    usizes, zsizes = [], []
    for _ in range(chunk_count - 1):
        us, z = struct.unpack_from("<II", idx, tpos); tpos += 8
        usizes.append(us); zsizes.append(z)
    lus, lz = struct.unpack_from("<II", idx, tpos)
    usizes.append(lus); zsizes.append(lz)
    return usizes, zsizes


def parse_v2_index(idx, idx_off):
    """ver 0x130BA 的索引区（已解压）。返回 (records, entries, pos)。

    records[i] = {md5, X, Y, Z}          （28B / 44B 变长，靠 X 链判定）
    entries[k] = (record_index, path, is_leader)

    路径表布局是 [u32 C][u32 L][path][u32 A]：**A 在路径之后**，且 bit31 表示该索引
    指向引导记录（B）而不是文件记录（A）。旧实现按 [u32 A][u32 L][path] 解析，
    会把每条路径配到前一条的记录上（静默错位），这里已修正。
    """
    pos = 0
    (N,) = struct.unpack_from("<I", idx, pos); pos += 4
    records = []
    while len(records) < N:
        if pos + 28 > len(idx):
            raise UnsupportedVariant("记录区越界（第 %d 条 / 共 %d 条）" % (len(records), N))
        md5 = idx[pos:pos + 16]
        X, Y, Z = struct.unpack_from("<III", idx, pos + 16)
        nxt = X + Y
        n28 = struct.unpack_from("<I", idx, pos + 44)[0] if pos + 48 <= len(idx) else -1
        n44 = struct.unpack_from("<I", idx, pos + 60)[0] if pos + 64 <= len(idx) else -1
        # 末条记录 X+Y == index_offset，必为 28 字节
        short = (nxt == idx_off) or (n28 == nxt and n44 != nxt)
        records.append({"md5": md5, "X": X, "Y": Y, "Z": Z})
        pos += 28 if short else 44
    if pos + 4 > len(idx):
        raise UnsupportedVariant("索引在记录区后提前结束")
    (count,) = struct.unpack_from("<I", idx, pos); pos += 4

    entries = []
    for k in range(count):
        if pos + 4 > len(idx):
            raise UnsupportedVariant("路径表越界（第 %d 条 / 共 %d 条）" % (k, count))
        (plen,) = struct.unpack_from("<I", idx, pos); pos += 4
        if plen < 1 or pos + plen + 4 > len(idx):
            raise UnsupportedVariant("路径长度异常（第 %d 条，L=%d）" % (k, plen))
        raw = idx[pos:pos + plen]; pos += plen
        (a,) = struct.unpack_from("<I", idx, pos); pos += 4
        entries.append((a & 0x7FFFFFFF, raw, bool(a & 0x80000000)))
    return records, entries, pos


def safe_relpath(raw_path):
    """把包内路径规范化为安全的相对路径；不可用时返回 None。

    新版索引里同样存在 `../script/...` 这类路径，直接 join 会写到输出目录之外。
    """
    if isinstance(raw_path, bytes):
        s = raw_path.decode("utf-8", "replace")
    else:
        s = raw_path
    s = s.replace("\\", "/")
    while s.startswith("../"):
        s = s[3:]
    s = s.lstrip("/")
    parts = [p for p in s.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    return "/".join(parts)


def read_header(pkg):
    with open(pkg, "rb") as f:
        ver, unk, idx_off, idx_size = struct.unpack("<4I", f.read(HDR_SIZE))
    return ver, unk, idx_off, idx_size


def load_index(pkg, idx_off, idx_size):
    with open(pkg, "rb") as f:
        f.seek(idx_off)
        iblob = f.read(idx_size)
    iusize = struct.unpack_from("<I", iblob, 0)[0]
    return lz4.block.decompress(iblob[4:], uncompressed_size=iusize)


def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PKG
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    ver, _unk, idx_off, idx_size = read_header(pkg)
    try:
        if ver == VER_V2:
            return main_v2(pkg, out)
        return main_v1(pkg, out)
    except UnsupportedVariant as e:
        print("错误: %s" % e, file=sys.stderr)
        return 2


# --------------------------------------------------------------------------- v2 (0x130BA)
def main_v2(pkg, out):
    """ver 0x130ba: variable-length records + tight path table + raw data."""
    ver, unk, idx_off, idx_size = read_header(pkg)
    print("header: ver=%#x unk=%d index@%d+%d" % (ver, unk, idx_off, idx_size))
    idx = load_index(pkg, idx_off, idx_size)
    print("index: %d bytes" % len(idx))

    recs, entries, pos = parse_v2_index(idx, idx_off)
    print("records: %d   paths: %d   (index consumed %d / %d bytes)"
          % (len(recs), len(entries), pos, len(idx)))

    os.makedirs(out, exist_ok=True)
    orphan_dir = os.path.join(out, "_orphans")
    containers_dir = os.path.join(out, "_containers")
    os.makedirs(orphan_dir, exist_ok=True)
    os.makedirs(containers_dir, exist_ok=True)

    by_record = {}
    for rec_index, raw, _is_leader in entries:
        by_record.setdefault(rec_index, []).append(raw)

    md5_ok = md5_bad = 0
    extracted = 0
    orphans = {}
    errors = []
    with open(pkg, "rb") as f:
        for i, rec in enumerate(recs):
            X, Y = rec["X"], rec["Y"]
            try:
                f.seek(X)
                blob = f.read(Y)
            except OSError as e:
                errors.append((i, "read fail: %s" % e))
                continue
            if hashlib.md5(blob).digest() == rec["md5"]:
                md5_ok += 1
            else:
                md5_bad += 1
                if md5_bad <= 10:
                    errors.append((i, "md5 mismatch"))
            named = by_record.get(i)
            if named:
                for p in named:
                    rel = safe_relpath(p)
                    if rel is None:
                        continue
                    dest = os.path.join(out, rel)
                    d = os.path.dirname(dest)
                    if d:
                        os.makedirs(d, exist_ok=True)
                    with open(dest, "wb") as g:
                        g.write(blob)
                    extracted += 1
            else:
                orphans[i] = blob
            if (i + 1) % 5000 == 0:
                print("  %d/%d ... extracted=%d" % (i + 1, len(recs), extracted), flush=True)

    for i, blob in orphans.items():
        with open(os.path.join(orphan_dir, "record_%d.bin" % i), "wb") as g:
            g.write(blob)

    # 记录长度分布（28B/44B 变长），便于排查链式判定
    short_n = sum(1 for r in recs if r["Z"] & 0x20 == 0)
    with open(os.path.join(containers_dir, "manifest.json"), "w", encoding="utf-8") as g:
        json.dump({
            "records": [{"index": i, "X": r["X"], "Y": r["Y"], "Z": r["Z"],
                         "md5": r["md5"].hex(),
                         "paths": [p.decode("utf-8", "replace") for p in by_record.get(i, [])]}
                        for i, r in enumerate(recs)],
            "note": "ver 0x130ba: raw (uncompressed) records; X=raw offset, md5 verified; "
                    "path entries are [u32 L][path][u32 A] (A AFTER the path)",
        }, g, ensure_ascii=False)

    print("extracted: %d  md5 ok: %d bad: %d" % (extracted, md5_ok, md5_bad))
    print("pathless (orphan) records: %d -> _orphans/" % len(orphans))
    if errors:
        print("errors: %d" % len(errors))
        for e in errors[:10]:
            print("  ", e)
    with open(os.path.join(out, "_unpack_report.json"), "w", encoding="utf-8") as g:
        json.dump({"pkg": pkg, "format": "v2 (0x130ba)",
                   "records": len(recs), "records_28b": short_n,
                   "records_44b": len(recs) - short_n,
                   "paths": len(entries),
                   "files_extracted": extracted, "orphans": len(orphans),
                   "md5_ok": md5_ok, "md5_bad": md5_bad,
                   "errors": errors[:100]}, g, ensure_ascii=False, indent=1)
    return 0


# --------------------------------------------------------------------------- v1 (0x25100)
def main_v1(pkg, out):
    os.makedirs(out, exist_ok=True)
    containers_dir = os.path.join(out, "_containers")
    os.makedirs(containers_dir, exist_ok=True)

    ver, unk, idx_off, idx_size = read_header(pkg)
    print("header: ver=%#x unk=%d index@%d+%d" % (ver, unk, idx_off, idx_size))

    idx = load_index(pkg, idx_off, idx_size)
    print("index: %d bytes" % len(idx))

    recA, recB, paths, pos = parse_v1_index(idx)
    N, M = len(recA), len(recB)
    print("A-records: %d  B-records: %d" % (N, M))
    print("paths: %d" % len(paths))

    usizes, zsizes = parse_chunk_table(idx, pos)
    total_unc = sum(usizes)
    print("chunks: %d  stream: %d bytes" % (len(usizes), total_unc))

    coffs, acc = [], HDR_SIZE
    for z in zsizes:
        coffs.append(acc); acc += z
    uoff, acc = [], 0
    for u in usizes:
        uoff.append(acc); acc += u

    f = open(pkg, "rb")
    cache = {}
    CACHE_MAX = 48

    def read_stream(off, ln):
        outb = bytearray()
        while ln > 0:
            lo, hi = 0, len(uoff) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if uoff[mid] <= off:
                    lo = mid
                else:
                    hi = mid - 1
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
            if take <= 0:
                raise ValueError("流内读取越界（offset=%d，chunk %d 长度 %d）" % (off, ci, len(ch)))
            outb += ch[s:s + take]
            off += take; ln -= take
        return bytes(outb)

    # ---- mapping: sort paths, pair with records in stream order ----
    order = sorted(range(len(paths)), key=lambda i: paths[i])
    n_script = sum(1 for p in paths if p.startswith(b"../"))
    print("script paths: %d (B count %d)" % (n_script, M))
    if n_script != M:
        raise UnsupportedVariant("以 ../ 开头的路径数 %d != B 记录数 %d，配对规则不适用" % (n_script, M))
    for k in range(M):
        if not paths[order[k]].startswith(b"../"):
            raise UnsupportedVariant("按字节序排序后第 %d 条路径不是 ../ 开头，配对规则不适用" % k)

    def safe_rel(p):
        return safe_relpath(p) or p.decode("utf-8", "replace")

    def record_for(k):
        """排序后第 k 条路径对应的记录。"""
        if k < M:
            return recB[k], None, True
        return recA[k - M], recA[k - M]["H1"], False

    # 扩展名 -> 内容校验（仅统计一致性，不影响解包）。
    # 各魔数均在 1.58.2 common_res.pkg 的 49,031 个真实记录上实测得出。
    TYPE2 = b"\x02\x00\x00\x00\x2c\x1c\xa2\x59"   # 引擎 type2 容器（纹理/网格/动画/清单）
    TYPE3 = b"\x89\x67\x45\x23"                       # 引擎 type3 容器（omod/ent/otex/emo）

    def sniff(p, data, size):
        ext = p.rsplit(b".", 1)[-1].lower() if b"." in p else b""
        if ext == b"ogg":
            return data[:4] == b"OggS"
        if ext == b"json":
            return data.lstrip()[:1] in (b"{", b"[")
        if ext in (b"png", b"mesh", b"skanim", b"skeleton", b"animmask", b"filelist"):
            return data.startswith(TYPE2)
        if ext in (b"omod", b"ent", b"otex", b"emo"):
            return data.startswith(TYPE3)
        if ext in (b"mat", b"prefab", b"controller", b"overridecontroller", b"templatemat"):
            # type1 容器：01 00 00 00 <u32 主体长度>，主体长度恒小于文件大小（尾部另有索引）
            if data[:4] != b"\x01\x00\x00\x00" or len(data) < 8:
                return False
            body = struct.unpack_from("<I", data, 4)[0]
            return 0 < body < size
        if ext == b"uprefab":
            # 两种形态：[u32 名字长度][名字...]（长度 < 文件大小），或直接是 JSON 文本
            if data.lstrip()[:1] == b"{":
                return True
            if len(data) < 4:
                return False
            ln = struct.unpack_from("<I", data, 0)[0]
            return 0 < ln < size and 4 + ln <= size
        if ext == b"vmo":
            return data.startswith(b"VMOF")
        if ext == b"fui":
            return data.startswith(b"FGUI")
        if ext == b"vox":
            return data.startswith(b"VOX ")
        if ext == b"blockmesh":
            return data[:4] == b"\x00\x00\x80\x3f"      # 首个 float = 1.0
        return None

    md5_ok = md5_bad = 0
    ext_ok = ext_bad = 0
    ext_fail = []
    extracted = 0
    placeholders = []          # {"path", "group", "H1", "Z"}
    groups = {}                # X -> {"z", "paths", "target"}
    errors = []

    # 先建 X -> 真实记录 的索引，用于标注占位记录指向谁。
    # 占位记录的 Z 不是大小，而是「资源组 id」：Z >> 2 恒等于其目标真实记录的 Z >> 2
    # （低 2 位为 2 或 3 的标记位）；真实记录的 Z 低 2 位恒为 0。已用 58,180 条全部验证。
    real_by_X = {}
    for k in range(len(paths)):
        rec, _H1, _isB = record_for(k)
        if rec["Y"] > 0:
            real_by_X.setdefault(rec["X"], (paths[order[k]], rec["Z"]))

    for k in range(len(paths)):
        p = paths[order[k]]
        rec, H1, _isB = record_for(k)
        rel = safe_rel(p)
        if rec["Y"] <= 0:
            X = rec["X"]
            g = groups.get(X)
            if g is None:
                g = {"z": 0, "paths": [], "target": None}
                groups[X] = g
            g["z"] = max(g["z"], rec["Z"])
            g["paths"].append(rel)
            placeholders.append({"path": rel, "X": X, "group_id": rec["Z"] >> 2,
                                 "H1": H1.hex() if H1 else None, "Z": rec["Z"]})
            continue
        try:
            data = read_stream(rec["X"] - HDR_SIZE, rec["Y"])
        except Exception as e:
            errors.append((rel, "read fail: %s" % e))
            continue
        if H1 is not None:
            if hashlib.md5(data).digest() == H1:
                md5_ok += 1
            else:
                md5_bad += 1
        v = sniff(p, data[:16], len(data))
        if v is not None:
            if v:
                ext_ok += 1
            else:
                ext_bad += 1
                if len(ext_fail) < 20:
                    ext_fail.append(rel)
        dest = os.path.join(out, rel)
        d = os.path.dirname(dest)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(dest, "wb") as g:
            g.write(data)
        extracted += 1
        if extracted % 5000 == 0:
            print("  extracted %d ..." % extracted)

    # ---- 占位 blob：按 X 去重（同一目录的多条占位路径指向同一个 all.filelist） ----
    group_ok = 0
    for X, g in groups.items():
        target = real_by_X.get(X)
        g["target"] = target[0].decode("utf-8", "replace") if target else None
        g["group_id"] = (g["z"] >> 2) if not target else (target[1] >> 2)
        if target and (g["z"] >> 2) == (target[1] >> 2):
            group_ok += 1
        name = "container_%x_%d.bin" % (X, g["z"])
        g["container"] = name
        try:
            blob = read_stream(X - HDR_SIZE, g["z"])
        except Exception as e:
            errors.append((name, "container read fail: %s" % e))
            g["container"] = None
            continue
        with open(os.path.join(containers_dir, name), "wb") as fh:
            fh.write(blob)

    n_filelist = sum(1 for g in groups.values()
                     if g["target"] and g["target"].endswith("all.filelist"))
    with open(os.path.join(containers_dir, "manifest.json"), "w", encoding="utf-8") as g:
        json.dump({
            "summary": {
                "placeholder_paths": len(placeholders),
                "placeholder_groups": len(groups),
                "groups_targeting_filelist": n_filelist,
                "groups_targeting_shared_blob": len(groups) - n_filelist,
                "group_ids_verified": group_ok,
            },
            "groups": [{"X": X, "container": g["container"], "target": g["target"],
                        "group_id": g["group_id"],
                        "members": len(g["paths"]), "Z": g["z"]}
                       for X, g in sorted(groups.items())],
            "placeholders": placeholders,
            "note": ("Y == 0 记录：内容不在 pkg 内（服务器按需下载）。X 指向同目录的 "
                     "all.filelist 或一个共享 blob，因此这些路径不会出现在解包目录里。"),
        }, g, ensure_ascii=False)

    print("extracted: %d  md5 ok: %d bad: %d" % (extracted, md5_ok, md5_bad))
    print("extension/content agreement: ok %d bad %d" % (ext_ok, ext_bad))
    print("placeholder paths (content not in this pkg): %d -> %d deduped blobs in _containers/"
          % (len(placeholders), len(groups)))
    print("  of which %d point at a sibling all.filelist, %d at a shared blob"
          % (n_filelist, len(groups) - n_filelist))
    print("  group id (Z >> 2) matches the target record: %d/%d" % (group_ok, len(groups)))
    if errors:
        print("errors: %d" % len(errors))
        for e in errors[:10]:
            print("  ", e)
    with open(os.path.join(out, "_unpack_report.json"), "w", encoding="utf-8") as g:
        json.dump({"pkg": pkg, "files_extracted": extracted,
                   "md5_ok": md5_ok, "md5_bad": md5_bad,
                   "content_sniff_ok": ext_ok, "content_sniff_bad": ext_bad,
                   "content_sniff_bad_examples": ext_fail,
                   "placeholders": len(placeholders),
                   "placeholder_groups": len(groups),
                   "placeholder_groups_targeting_filelist": n_filelist,
                   "placeholders_note": ("Y == 0 记录的内容不在 pkg 内（服务器按需下载），"
                                         "不会写到原路径；详见 _containers/manifest.json"),
                   "errors": errors[:100]}, g, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
