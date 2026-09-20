#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for the prebuilt Linux Crunch decoders.

Windows users get `tools/crn2rgba_x64.exe` / `crn2rgba_arm64.exe` straight from the
repository; Linux users used to need a local C++ compiler (see issue #1). The
repository now ships statically linked musl binaries for Linux too, and this test
keeps them honest:

  1. `tests/fixtures/etc2a_64x64_mips.crn` is a synthetic ETC2A (Crunch) container
     with a full 7-level mip chain — no game assets involved.
  2. On Linux, the prebuilt binary for the current architecture must decode it to
     exactly `EXPECTED_RGBA_SHA256`.
  3. If a C++ compiler is available, a freshly compiled decoder must produce the
     very same bytes — that is what proves the checked-in binary is not stale.

On macOS / Windows steps 2-3 are skipped (only the fixture header is validated),
so the test stays green everywhere while still guarding the Linux path in CI.
"""
import hashlib
import os
import platform
import shutil
import subprocess
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
FIXTURE = os.path.join(HERE, "fixtures", "etc2a_64x64_mips.crn")

# Windows 控制台默认 GBK/cp936，重定向时还会退回 cp1252，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# crn2rgba 对夹具的确定输出（已在 macOS + Linux aarch64 上交叉验证一致）
EXPECTED_INFO = "64 64 7 1 12"
EXPECTED_RGBA_SHA256 = "b1e1246e41986b9c8457150742bdafd4a1f5f0107db810b82b9f6b6333e90fcd"

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   %s" % msg)
    else:
        print("  FAIL %s" % msg)
        FAILURES.append(msg)


def read_crn_header(data):
    """crn_header 是打包的大端结构（见 tools/crn_decomp_unity.h）。"""
    sig, header_size, _crc, data_size, _dcrc, w, h, levels, faces, fmt, _flags = \
        struct.unpack_from(">HHHIHHHBBBH", data, 0)
    return dict(sig=sig, header_size=header_size, data_size=data_size,
                width=w, height=h, levels=levels, faces=faces, format=fmt)


def arch_suffix():
    machine = platform.machine().upper()
    return {"AMD64": "x64", "X86_64": "x64", "ARM64": "arm64", "AARCH64": "arm64"}.get(machine)


def run_decoder(exe, workdir):
    out_rgba = os.path.join(workdir, "out.rgba")
    out_info = os.path.join(workdir, "out.info")
    r = subprocess.run([exe, FIXTURE, out_rgba, out_info],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        return None, None, r.stderr.decode("utf-8", "replace")
    with open(out_info) as f:
        info = f.read().strip()
    with open(out_rgba, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return info, digest, ""


def compile_reference(workdir):
    """现场编译一份解码器作为对照；没有编译器就返回 None。"""
    for name in ("c++", "clang++", "g++"):
        comp = shutil.which(name)
        if comp:
            break
    else:
        return None
    exe = os.path.join(workdir, "crn2rgba_ref")
    cmd = [comp, "-O2", "-std=c++11", "-fno-strict-aliasing", "-w",
           "-I", TOOLS, os.path.join(TOOLS, "crn2rgba.cpp"), "-o", exe]
    r = subprocess.run(cmd, capture_output=True, timeout=600)
    if r.returncode != 0 or not os.path.isfile(exe):
        print("  note: 现场编译失败，跳过对照（%s）"
              % r.stderr.decode("utf-8", "replace").strip()[:120])
        return None
    return exe


def main():
    print("== 合成 ETC2A 夹具 ==")
    check(os.path.isfile(FIXTURE), "夹具存在: %s" % os.path.relpath(FIXTURE, ROOT))
    if not os.path.isfile(FIXTURE):
        print("\n%d 项失败" % len(FAILURES))
        return 1

    with open(FIXTURE, "rb") as f:
        data = f.read()
    hdr = read_crn_header(data)
    check(hdr["sig"] == 0x4878, "CRN 签名 0x4878（实际 0x%04X）" % hdr["sig"])
    check(hdr["format"] == 12, "格式 12 = ETC2A（实际 %d）" % hdr["format"])
    check((hdr["width"], hdr["height"]) == (64, 64),
          "尺寸 64x64（实际 %dx%d）" % (hdr["width"], hdr["height"]))
    check(hdr["levels"] == 7, "mip 级数 7（实际 %d）" % hdr["levels"])
    check(hdr["faces"] == 1, "faces 1（实际 %d）" % hdr["faces"])

    if not sys.platform.startswith("linux"):
        print("\n== 预编译 Linux 二进制 ==")
        print("  skip 当前平台是 %s，仅 Linux 会执行二进制校验" % sys.platform)
        print("\n%d 项失败" % len(FAILURES))
        return 1 if FAILURES else 0

    print("\n== 预编译 Linux 二进制 ==")
    suffix = arch_suffix()
    check(suffix is not None, "能识别本机架构（%s）" % platform.machine())
    prebuilt = os.path.join(TOOLS, "crn2rgba_linux_%s" % suffix) if suffix else None
    check(bool(prebuilt) and os.path.isfile(prebuilt),
          "预编译二进制存在: tools/crn2rgba_linux_%s" % suffix)

    with tempfile.TemporaryDirectory() as tmp:
        ref_exe = compile_reference(tmp)

        if prebuilt and os.path.isfile(prebuilt):
            if not os.access(prebuilt, os.X_OK):
                os.chmod(prebuilt, 0o755)
            info, digest, err = run_decoder(prebuilt, tmp)
            check(info == EXPECTED_INFO,
                  "预编译二进制输出 info == %r（实际 %r%s）"
                  % (EXPECTED_INFO, info, (" " + err) if err else ""))
            check(digest == EXPECTED_RGBA_SHA256,
                  "预编译二进制 RGBA 摘要与基准一致")

        if ref_exe:
            info, digest, err = run_decoder(ref_exe, tmp)
            check(info == EXPECTED_INFO,
                  "现场编译版输出 info == %r（实际 %r）" % (EXPECTED_INFO, info))
            check(digest == EXPECTED_RGBA_SHA256,
                  "现场编译版 RGBA 摘要与预编译版一致（预编译版未过期）")
        else:
            print("  skip 本机无 C++ 编译器，跳过与现场编译版的对照")

    print("\n%d 项失败" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
