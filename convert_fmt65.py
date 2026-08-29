#!/usr/bin/env python3
"""Batch convert fmt65 (CRN/ETC2A) textures via crn2rgba tool."""
import os, sys, struct, subprocess, tempfile

# GPU 纹理按 OpenGL 惯例自下而上存储，解码后需垂直翻转才是正常显示方向。
# 若发现图片方向反了，把这里改成 False 再跑一遍即可。
FLIP_VERTICAL = True
FORCE = "--force" in sys.argv

# 用法: python3 convert_fmt65.py [解包目录] [PNG输出目录] [crn2rgba 可执行文件]
# 默认: ./common_res_unpacked  ./decoded_png  tools/crn2rgba
SRC = sys.argv[1] if len(sys.argv) > 1 else "common_res_unpacked"
DST = sys.argv[2] if len(sys.argv) > 2 else "decoded_png"
TOOL = sys.argv[3] if len(sys.argv) > 3 else "tools/crn2rgba"

def main():
    from collections import Counter
    res = Counter()
    files = []
    for dirpath, _, fs in os.walk(SRC):
        for f in fs:
            if f.endswith(".png"):
                p = os.path.join(dirpath, f)
                try:
                    with open(p, "rb") as g:
                        head = g.read(0x24)
                    if len(head) >= 0x24 and head[:4] == b"\x02\x00\x00\x00" and struct.unpack_from("<I", head, 0x20)[0] == 65:
                        files.append(p)
                except Exception:
                    pass
    print("fmt65 files:", len(files), flush=True)
    for n, p in enumerate(files):
        rel = os.path.relpath(p, SRC)
        dest = os.path.join(DST, rel)
        # 跳过条件：目标已存在且是真 PNG（原地模式下解包出的引擎格式 .png 需要转换）
        if os.path.exists(dest) and not FORCE:
            try:
                with open(dest, "rb") as g:
                    if g.read(8) == b"\x89PNG\r\n\x1a\n":
                        res["cached"] += 1
                        continue
            except OSError:
                pass
        try:
            d = open(p, "rb").read()
            w, h, dsz, fmt, nmip = struct.unpack_from("<IIIII", d, 0x14)
            with open("/tmp/_in.crn", "wb") as g:
                g.write(d[107:])
            r = subprocess.run([TOOL, "/tmp/_in.crn", "/tmp/_out.rgba", "/tmp/_out.info"],
                               capture_output=True, timeout=60)
            if r.returncode != 0:
                res["tool-fail"] += 1
                if res["tool-fail"] <= 5:
                    print("FAIL", rel, r.stderr.decode()[:80], flush=True)
                continue
            info = open("/tmp/_out.info").read().split()
            iw, ih, levels, faces, cfmt = map(int, info)
            if faces != 1:
                res["cubemap-skip"] += 1
                continue
            dd = open("/tmp/_out.rgba", "rb").read()
            lw, lh = struct.unpack_from("<2I", dd, 24)
            from PIL import Image
            img = Image.frombytes("RGBA", (lw, lh), dd[32:32 + lw * lh * 4])
            if FLIP_VERTICAL:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            img.save(dest)
            res["ok"] += 1
        except Exception as e:
            res["err"] += 1
            if res["err"] <= 5:
                print("ERR", rel, str(e)[:80], flush=True)
        if n % 1000 == 0:
            print(n, dict(res), flush=True)
    print("DONE", dict(res), flush=True)

if __name__ == "__main__":
    main()
