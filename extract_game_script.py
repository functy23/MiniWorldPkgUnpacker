#!/usr/bin/env python3
"""Extract game_script.pkg.

Format (same family as common_res.pkg): the data region is a sequence of
independent LZ4 blocks described by a chunk table at the end of the index.
Record X is a coordinate in the DECOMPRESSED stream (stream offset = X - 16),
Y = uncompressed size; records chain strictly: X[i+1] == X[i] + Y[i].
All B records (N=0), sorted-byte-order path pairing, like common_res.
"""
import struct, sys, os
import lz4.block

def parse_index(idx):
    (N,) = struct.unpack_from("<I", idx, 0)
    (M,) = struct.unpack_from("<I", idx, 4)
    assert N == 0, f"expected N=0, got {N}"
    recs = [struct.unpack_from("<III", idx, 8 + i * 12) for i in range(M)]
    pos = 8 + M * 12
    (count,) = struct.unpack_from("<I", idx, pos); pos += 4
    assert count == M, f"path count {count} != M {M}"
    L0 = struct.unpack_from("<I", idx, pos)[0]
    paths = [idx[pos + 4:pos + 4 + L0]]
    pos += 4 * ((4 + L0 + 3) // 4)
    for _ in range(count - 1):
        _A, L = struct.unpack_from("<II", idx, pos)
        paths.append(idx[pos + 8:pos + 8 + L])
        pos += 4 * ((8 + L + 3) // 4)
    # tail: u32 ?; u32 chunk_count; then (chunk_count-1) x [u32 262144][u32 zsize]
    #       + final [u32 usize][u32 zsize]  (same layout as common_res)
    (_u, cc) = struct.unpack_from("<II", idx, pos); pos += 8
    chunks = [struct.unpack_from("<II", idx, pos + i * 8) for i in range(cc)]
    return recs, paths, chunks

def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else "迷你世界_1.58.2/assets/game_script.pkg"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "game_script_out"
    data = open(pkg, "rb").read()
    idx_off, idx_size = struct.unpack_from("<2I", data, 8)
    iblob = data[idx_off:idx_off + idx_size]
    iusize = struct.unpack_from("<I", iblob, 0)[0]
    idx = lz4.block.decompress(iblob[4:], uncompressed_size=iusize)
    recs, paths, chunks = parse_index(idx)
    print(f"records: {len(recs)}  chunks: {len(chunks)}")

    # chain sanity check
    for i in range(len(recs) - 1):
        assert recs[i + 1][0] == recs[i][0] + recs[i][1], f"chain break at rec {i}"
    tot_u = sum(u for u, z in chunks)
    assert recs[-1][0] + recs[-1][1] == 16 + tot_u, "record chain vs chunk totals mismatch"

    # decompress all chunks into one buffer
    out = bytearray(tot_u)
    fo = fo_file = 0
    for i, (u, z) in enumerate(chunks):
        if z == u:
            out[fo:fo + u] = data[16 + fo_file:16 + fo_file + z]   # stored block
        else:
            out[fo:fo + u] = lz4.block.decompress(
                data[16 + fo_file:16 + fo_file + z], uncompressed_size=u)
        fo += u
        fo_file += z
    assert fo == len(out) and fo_file == idx_off - 16, \
        f"consumed {fo_file} != data region {idx_off - 16}"
    print(f"stream: {len(out)} bytes decompressed")

    order = sorted(range(len(paths)), key=lambda i: paths[i])

    os.makedirs(outdir, exist_ok=True)
    ok = 0
    for rec_i, path_i in enumerate(order):
        X, Y, _Z = recs[rec_i]
        off = X - 16
        content = bytes(out[off:off + Y])
        assert len(content) == Y
        rel = paths[path_i].decode("utf-8", "replace")
        while rel.startswith("../"):
            rel = rel[3:]
        dest = os.path.join(outdir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(content)
        ok += 1
    print(f"extracted: {ok}  -> {outdir}")

if __name__ == "__main__":
    main()
