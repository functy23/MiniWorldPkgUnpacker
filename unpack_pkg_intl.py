#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解包迷你世界国际版（Mini World CREATA） .pkg 资源包。

用法:
    python3 unpack_pkg_intl.py 路径/到/common_res.pkg [输出目录]

默认输出到 当前目录/unpack/。同时支持 common_res / first_res / game_res /
script_res / material_ogles* / remote_res / game_language 等同格式资源包。

格式（逆向结果，详见 AGENTS.md）:
    [16B 头] ver=0x000130BA | 17 | 索引偏移 | 索引大小
    [数据区] 原始字节，记录 X 即文件偏移，Y 即长度
    [索引区] 单个 LZ4 块（前 4 字节为解压后大小），解压后:
        u32 N ; N 条变长记录:
            44B = [16B 内容md5][u32 X][u32 Y][u32 Z][16B H2]
            28B = [16B 内容md5][u32 X][u32 Y][u32 Z]
            （Z 的 bit5 置位即为 44B；末条记录必为 28B）
        （可选 16B 页脚）u32 C
        C 条路径条目，紧凑无填充: [u32 L][L 字节路径][u32 A]
            A 位于路径 *之后*，即该路径对应的记录索引
    载荷解码: Z 的 bit0 置位（Z==1 或 Z==33）时为 [u32 usize][LZ4 块]，
              否则为原始字节（Z==0 或 Z==32）
"""
import argparse
import collections
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from pkg_intl import open_pkg, PkgFormatError, is_pkg
except ImportError:
    print("错误: 缺少 pkg_intl.py，请使用完整仓库克隆（脚本需与本文件同目录）", file=sys.stderr)
    raise

# 扩展名 -> 内容校验器（仅用于统计一致性，不影响解包）
SNIFFERS = {
    ".ogg": lambda d: d[:4] == b"OggS",
    ".json": lambda d: d.lstrip(b"\xef\xbb\xbf \t\r\n")[:1] in (b"{", b"["),
    ".vmo": lambda d: d[:4] == b"VMOF",
    ".zip": lambda d: d[:4] == b"PK\x03\x04",
    ".png": lambda d: d[:4] == b"\x00\x00\x00\x00" or d[:8] == b"\x89PNG\r\n\x1a\n",
    ".emo": lambda d: d[:4] in (b"\x89gE#", b"\x00\x00\x00\x00"),
    ".dls": lambda d: d[:4] == b"RIFF",
}


def main():
    ap = argparse.ArgumentParser(description="解包迷你世界国际版 .pkg")
    ap.add_argument("pkg", help="pkg 文件路径（或包含 pkg 的目录）")
    ap.add_argument("outdir", nargs="?", default=None, help="输出目录（默认 当前目录/unpack）")
    ap.add_argument("--no-md5", action="store_true", help="跳过内容 md5 校验（更快）")
    args = ap.parse_args()

    pkg = os.path.abspath(args.pkg)
    if os.path.isdir(pkg):
        cands = [os.path.join(dp, f) for dp, _dn, fs in os.walk(pkg)
                 for f in fs if f.endswith(".pkg") and is_pkg(os.path.join(dp, f))]
        if not cands:
            print("错误: 目录中没有找到有效的国际版 .pkg: %s" % pkg, file=sys.stderr)
            return 1
        pkg = max(cands, key=os.path.getsize)
        print("检测到传入的是目录，已自动选择: %s" % pkg)
    if not os.path.isfile(pkg):
        print("错误: 找不到 pkg 文件: %s" % pkg, file=sys.stderr)
        return 1
    if not is_pkg(pkg):
        print("错误: 不是国际版格式的 pkg（头部版本号应为 0x130BA 且索引落在文件尾）:\n  %s\n"
              "pkg 在 APK 解包后的 assets/ 目录里。" % pkg, file=sys.stderr)
        return 1

    outdir = os.path.abspath(args.outdir or os.path.join(os.getcwd(), "unpack"))
    os.makedirs(outdir, exist_ok=True)

    t0 = time.time()
    print("pkg : %s" % pkg)
    print("输出: %s" % outdir)
    try:
        p = open_pkg(pkg)
    except PkgFormatError as e:
        print("错误: 解析失败: %s" % e, file=sys.stderr)
        return 1
    print("格式: ver=0x%X  记录 %d 条  路径 %d 条%s"
          % (p.ver, p.record_count, p.path_count,
             "  页脚 %s" % p.footer.hex() if p.footer else ""))

    md5_ok = md5_bad = md5_skip = 0
    md5_bad_list = []
    branches = collections.Counter()
    branches_by_z = collections.Counter()
    ext_stat = collections.defaultdict(lambda: [0, 0, 0])   # ext -> [checked, ok, fail]
    ext_counts = collections.Counter()
    errors = []
    written = 0
    total_raw = 0
    collisions = []

    for rel, payload, rec_index, branch in p.iter_files():
        X, Y, Z, H1, _H2 = p.records[rec_index]
        total_raw += Y
        branches[branch] += 1
        branches_by_z["Z=%d/%s" % (Z, branch)] += 1

        if args.no_md5:
            md5_skip += 1
        else:
            raw = p.read_raw(rec_index)
            if hashlib.md5(raw).digest() == H1:
                md5_ok += 1
            else:
                md5_bad += 1
                if len(md5_bad_list) < 20:
                    md5_bad_list.append({"path": rel, "record": rec_index})

        dst = os.path.join(outdir, rel)
        if os.path.exists(dst):
            collisions.append(rel)
        try:
            d = os.path.dirname(dst)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(dst, "wb") as w:
                w.write(payload)
        except OSError as e:
            errors.append({"path": rel, "error": str(e)})
            continue
        written += 1

        ext = os.path.splitext(rel)[1].lower()
        ext_counts[ext] += 1
        fn = SNIFFERS.get(ext)
        if fn is not None:
            st = ext_stat[ext]
            st[0] += 1
            if fn(payload):
                st[1] += 1
            else:
                st[2] += 1

        if written % 5000 == 0:
            print("  已写出 %d ..." % written, flush=True)

    p.close()
    elapsed = time.time() - t0

    print()
    print("===== 汇总 =====")
    print("提取文件: %d" % written)
    print("内容 md5: 通过 %d / 失败 %d / 跳过 %d" % (md5_ok, md5_bad, md5_skip))
    print("解码分支: %s" % dict(branches))
    print("按 Z 统计: %s" % dict(sorted(branches_by_z.items())))
    if ext_stat:
        print("扩展名与内容一致性:")
        for ext in sorted(ext_stat, key=lambda e: -ext_stat[e][0]):
            checked, ok, fail = ext_stat[ext]
            print("  %-7s %6d/%6d%s" % (ext, ok, checked,
                                        "" if fail == 0 else "  失败 %d" % fail))
    if errors:
        print("错误 %d 条（前 5 条）:" % len(errors))
        for e in errors[:5]:
            print("  ", e)
    if collisions:
        print("路径重复 %d 条（后者覆盖前者，前 5 条）: %s" % (len(collisions), collisions[:5]))
    print("耗时 %.1fs，读取 %.1f MB" % (elapsed, total_raw / 1048576.0))

    report = {
        "pkg": pkg,
        "pkg_size": os.path.getsize(pkg),
        "format": "intl ver=0x%X" % p.ver,
        "records": p.record_count,
        "paths": p.path_count,
        "files_written": written,
        "md5_ok": md5_ok,
        "md5_bad": md5_bad,
        "md5_bad_examples": md5_bad_list,
        "decode_branches": dict(branches),
        "decode_by_z": dict(sorted(branches_by_z.items())),
        "ext_consistency": {e: {"checked": v[0], "ok": v[1], "fail": v[2]}
                            for e, v in sorted(ext_stat.items())},
        "ext_counts": dict(ext_counts.most_common()),
        "path_collisions": collisions[:100],
        "errors": errors[:100],
        "elapsed_sec": round(elapsed, 2),
    }
    rp = os.path.join(outdir, "_unpack_report.json")
    with open(rp, "w", encoding="utf-8") as w:
        json.dump(report, w, ensure_ascii=False, indent=1)
    print("报告: %s" % rp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
