#!/usr/bin/env python3
"""Batch convert fmt65 (CRN/ETC2A) textures via crn2rgba tool.

支持国内版（魔数 0x59A21C2C）与国际版（魔数 0x054C8245）两种引擎容器头，
两者数据区均从偏移 107 开始、格式字段均在 0x20。
"""
import os, sys, struct, subprocess, tempfile

# Windows 控制台默认 GBK/cp936，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# GPU 纹理按 OpenGL 惯例自下而上存储，解码后需垂直翻转才是正常显示方向。
# 若发现图片方向反了，把这里改成 False 再跑一遍即可。
FLIP_VERTICAL = True
FORCE = "--force" in sys.argv

MAGIC_DOMESTIC = b"\x2c\x1c\xa2\x59"
MAGIC_INTL = b"\x45\x82\x4c\x05"
TEX_DATA_OFFSET = 107
FMT65 = 65

# 用法: python3 convert_fmt65.py [解包目录] [PNG输出目录] [crn2rgba 可执行文件]
# 默认: ./unpack  ./decoded_png  tools/crn2rgba
SRC = sys.argv[1] if len(sys.argv) > 1 else "unpack"
DST = sys.argv[2] if len(sys.argv) > 2 else "decoded_png"
TOOL = sys.argv[3] if len(sys.argv) > 3 else "tools/crn2rgba"


def is_fmt65(d):
    """判断是否为 fmt65 的引擎纹理容器（国内版或国际版）。"""
    if len(d) < 0x24:
        return False
    if struct.unpack_from("<I", d, 0x20)[0] != FMT65:
        return False
    if d[:4] == b"\x02\x00\x00\x00" and d[4:8] == MAGIC_DOMESTIC:
        return True
    if d[:4] == b"\x00\x00\x00\x00" and d[8:12] == MAGIC_INTL:
        return True
    return False


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
                    if is_fmt65(head):
                        files.append(p)
                except Exception:
                    pass
    print("fmt65 files:", len(files), flush=True)
    tmpdir = tempfile.mkdtemp(prefix="crn2rgba_")
    fin = os.path.join(tmpdir, "in.crn")
    fout = os.path.join(tmpdir, "out.rgba")
    finfo = os.path.join(tmpdir, "out.info")
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
            with open(fin, "wb") as g:
                g.write(d[TEX_DATA_OFFSET:])
            r = subprocess.run([TOOL, fin, fout, finfo],
                               capture_output=True, timeout=60)
            if r.returncode != 0:
                res["tool-fail"] += 1
                if res["tool-fail"] <= 5:
                    print("FAIL", rel, r.stderr.decode("utf-8", "replace")[:80], flush=True)
                continue
            info = open(finfo).read().split()
            iw, ih, levels, faces, cfmt = map(int, info)
            if faces != 1:
                res["cubemap-skip"] += 1
                continue
            dd = open(fout, "rb").read()
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
    try:
        os.remove(fin); os.remove(fout); os.remove(finfo); os.rmdir(tmpdir)
    except OSError:
        pass
    print("DONE", dict(res), flush=True)

if __name__ == "__main__":
    main()
