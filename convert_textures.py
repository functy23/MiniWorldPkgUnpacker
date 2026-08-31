#!/usr/bin/env python3
"""Convert Mini World engine textures (fmt 50=ASTC6x6, 3=RGB24, 63=R8) to real PNGs."""
import os, sys, struct, math

# Windows 控制台默认 GBK/cp936，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# GPU 纹理按 OpenGL 惯例自下而上存储，解码后需垂直翻转（与 convert_fmt65.py 一致）
FLIP_VERTICAL = True
from PIL import Image

# astc_encoder 延迟到首次需要时导入：其 C 扩展在某些环境（如 x64 Python 跑在
# ARM64 Windows 模拟下）加载失败，不应拖垮其余 2 万张非 ASTC 纹理的转换
_astc = None        # (ctx6, ctx4, SW) once imported
_astc_state = ""    # "", "ok", "broken"

def _astc_setup():
    global _astc, _astc_state
    if _astc_state == "ok":
        return _astc
    if _astc_state == "broken":
        return None
    try:
        from astc_encoder import (ASTCConfig, ASTCContext, ASTCImage, ASTCProfile,
                                  ASTCQualityPreset, ASTCSwizzle,
                                  ASTCSwizzleComponentSelector, ASTCType)
        SW = ASTCSwizzle(ASTCSwizzleComponentSelector.R, ASTCSwizzleComponentSelector.G,
                         ASTCSwizzleComponentSelector.B, ASTCSwizzleComponentSelector.A)
        ctx6 = ASTCContext(ASTCConfig(ASTCProfile.LDR, 6, 6, 1, quality=ASTCQualityPreset.FASTEST))
        ctx4 = ASTCContext(ASTCConfig(ASTCProfile.LDR, 4, 4, 1, quality=ASTCQualityPreset.FASTEST))
        _astc = (ctx6, ctx4, SW, ASTCImage, ASTCType)
        _astc_state = "ok"
        return _astc
    except Exception as e:
        print(f"警告: astc_encoder 导入失败，ASTC 纹理将跳过（{type(e).__name__}: {e}）",
              file=sys.stderr, flush=True)
        _astc_state = "broken"
        return None

# 用法: python3 convert_textures.py [解包目录] [PNG输出目录]
# 默认: ./common_res_unpacked  ./decoded_png
SRC = sys.argv[1] if len(sys.argv) > 1 else "common_res_unpacked"
DST = sys.argv[2] if len(sys.argv) > 2 else "decoded_png"

def convert(path, rel):
    d = open(path, "rb").read()
    if len(d) < 0x24 or d[:4] != b"\x02\x00\x00\x00" or d[4:8] != b"\x2c\x1c\xa2\x59":
        return "not-tex"
    w, h, dsz, fmt, nmip = struct.unpack_from("<IIIII", d, 0x14)
    data = d[107:len(d)-1]  # payload between 107-byte header and 1 trailing byte
    try:
        if fmt in (48, 50):
            astc = _astc_setup()
            if astc is None:
                return "astc-unavailable"
            ctx6, ctx4, SW, ASTCImage, ASTCType = astc
            if fmt == 50:
                bw, bh = math.ceil(w/6), math.ceil(h/6)
                need = bw*bh*16
                if len(data) < need: data = data + bytes(need - len(data))
                out_img = ctx6.decompress(data[:need], ASTCImage(ASTCType.U8, w, h, 1), SW)
            else:
                bw, bh = math.ceil(w/4), math.ceil(h/4)
                need = bw*bh*16
                if len(data) < need: data = data + bytes(need - len(data))
                out_img = ctx4.decompress(data[:need], ASTCImage(ASTCType.U8, w, h, 1), SW)
            img = Image.frombytes("RGBA", (w, h), bytes(out_img.data))
        elif fmt == 3:
            if len(data) < w*h*3: return "short"
            img = Image.frombytes("RGB", (w, h), data[:w*h*3])
        elif fmt == 4:
            if len(data) < w*h*4: return "short"
            img = Image.frombytes("RGBA", (w, h), data[:w*h*4])
        elif fmt == 5:
            if len(data) < w*h*4: return "short"
            raw = data[:w*h*4]
            img = Image.frombytes("RGBA", (w, h), bytes(bytearray(raw[i:i+4][::-1] for i in range(0, len(raw), 4))))
        elif fmt == 63:
            if len(data) < w*h: return "short"
            img = Image.frombytes("L", (w, h), data[:w*h])
        elif fmt == 1:
            if len(data) < w*h: return "short"
            img = Image.frombytes("L", (w, h), data[:w*h])
        else:
            return f"unsup-fmt{fmt}"
    except Exception as e:
        return f"err:{str(e)[:30]}"
    if FLIP_VERTICAL:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    dest = os.path.join(DST, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.save(dest, optimize=False)
    return "ok"

def main():
    from collections import Counter
    res = Counter()
    n = 0
    for dirpath, _, files in os.walk(SRC):
        for f in files:
            if not f.endswith(".png"): continue
            src = os.path.join(dirpath, f)
            rel = os.path.relpath(src, SRC)
            r = convert(src, rel)
            res[r.split(":")[0] if r.startswith("err") else r] += 1
            n += 1
            if n % 2000 == 0:
                print(f"  {n} ... {dict(res)}", flush=True)
    print("DONE", n, dict(res))

if __name__ == "__main__":
    main()
