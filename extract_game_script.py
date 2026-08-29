#!/usr/bin/env python3
"""Extract game_script.pkg: block-linked LZ4 across files.

The data region is one continuous LZ4 stream cut into per-file segments; each
segment may back-reference the previous file's decompressed output (64KB
window). Strategy: fast token-scan to get per-file uncompressed sizes, then
C-speed per-file decompression with the previous file's tail as dictionary.
"""
import struct, sys, os
import lz4.block

def scan_sizes(data, start, end, recs):
    """Walk LZ4 tokens without materializing output; return per-record uncompressed sizes."""
    i = start
    sizes = []
    cur = 0
    ri = 0
    bounds = [r[0] for r in recs] + [end]
    n = end
    while i < n and ri < len(recs):
        token = data[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = data[i]; i += 1; lit += b
                if b != 255: break
        i += lit
        cur += lit
        if i >= n:
            sizes.append(cur); ri += 1
            while ri < len(recs): sizes.append(0); ri += 1
            break
        ofs = data[i] | (data[i+1] << 8); i += 2
        if ofs == 0:
            sizes.append(cur); ri += 1
            cur = 0
            if ri >= len(recs): break
            # 跳过子流之间的零填充
            while i < n and data[i] == 0: i += 1
            continue
        ml = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                b = data[i]; i += 1; ml += b
                if b != 255: break
        cur += ml
        while ri < len(recs) and i >= bounds[ri+1]:
            sizes.append(cur); cur = 0; ri += 1
            if ri >= len(recs): break
    while len(sizes) < len(recs): sizes.append(0)
    return sizes

def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else "迷你世界_1.58.2/assets/game_script.pkg"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "game_script_out"
    data = open(pkg, "rb").read()
    idx_off, idx_size = struct.unpack_from("<2I", data, 8)
    iblob = data[idx_off:idx_off+idx_size]
    iusize = struct.unpack_from("<I", iblob, 0)[0]
    idx = lz4.block.decompress(iblob[4:], uncompressed_size=iusize)
    (N,) = struct.unpack_from("<I", idx, 0)
    (M,) = struct.unpack_from("<I", idx, 4)
    recs = [struct.unpack_from("<III", idx, 8+i*12) for i in range(M)]
    pos = 8 + M*12
    (count,) = struct.unpack_from("<I", idx, pos); pos += 4
    L0 = struct.unpack_from("<I", idx, pos)[0]
    paths = [idx[pos+4:pos+4+L0]]
    pos += 4 * ((4 + L0 + 3) // 4)
    for k in range(count-1):
        A, L = struct.unpack_from("<II", idx, pos)
        p = idx[pos+8:pos+8+L]
        if not all(32 <= b < 127 for b in p): break
        paths.append(p)
        pos += 4 * ((8 + L + 3) // 4)
    print(f"records: {M}  paths: {len(paths)}")

    order = sorted(range(len(paths)), key=lambda i: paths[i])

    print("scan sizes...")
    sizes = scan_sizes(data, 16, idx_off, recs)
    print("sizes ok:", sum(1 for s in sizes if s > 0), "of", M)

    os.makedirs(outdir, exist_ok=True)
    ok = raw = 0
    prev_out = b""
    for rec_i, path_i in enumerate(order):
        X = recs[rec_i][0]
        Xn = recs[rec_i+1][0] if rec_i+1 < M else idx_off
        usize = sizes[rec_i]
        rel = paths[path_i].decode("utf-8", "replace")
        while rel.startswith("../"): rel = rel[3:]
        dest = os.path.join(outdir, rel)
        content = None
        if usize > 0:
            dd = prev_out[-65536:] if prev_out else None
            us = usize
            while us <= usize + 65536:
                try:
                    if dd:
                        content = lz4.block.decompress(data[X:Xn], uncompressed_size=us, dict=dd)
                    else:
                        content = lz4.block.decompress(data[X:Xn], uncompressed_size=us)
                    break
                except lz4.block.LZ4BlockError:
                    break  # 真损坏
                except Exception:
                    us += 1  # 尺寸猜测偏小,逐步放宽
        if content is None:
            content = data[X:Xn]; raw += 1
        else:
            ok += 1
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(content)
        prev_out = content
    print(f"lz4: {ok}  raw-fallback: {raw}  -> {outdir}")

if __name__ == "__main__":
    main()
