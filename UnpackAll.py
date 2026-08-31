#!/usr/bin/env python3
"""UnpackAll — 一键解包迷你世界 .pkg 资源包（Windows / Linux / macOS 通用）。

用法:
    python UnpackAll.py 路径/到/common_res.pkg      (Windows)
    python3 UnpackAll.py 路径/到/common_res.pkg     (Linux / macOS)

全部产物输出到 当前目录/unpack/：
    unpack/resources/...   解包出的全部文件（.ogg/.json/.lua 原生可读）
    unpack/.../*.png       纹理已原地转换为可预览的标准 PNG
                           （注意：会覆盖原始引擎纹理数据）

需要本脚本与 unpack_common_res.py / convert_textures.py / convert_fmt65.py /
tools/ 处于同一目录（即本仓库的完整克隆）。
"""
import os
import struct
import sys
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "unpack")
NEEDED = ["unpack_common_res.py", "convert_textures.py", "convert_fmt65.py"]

# Windows 控制台默认 GBK/cp936，重定向时还会退回 ANSI 代码页，统一按 UTF-8 输出
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def die(msg):
    print("错误:", msg)
    sys.exit(1)


def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        die(f"步骤失败（退出码 {r.returncode}）: {' '.join(cmd)}")


def _msvc_via_vsdevcmd():
    """普通 PowerShell 里 cl 通常不在 PATH。借 vswhere 定位 Visual Studio /
    Build Tools，再用 VsDevCmd.bat 拿到带环境变量的 cl 完整路径。"""
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.isfile(vswhere):
        return None
    try:
        r = subprocess.run(
            [vswhere, "-latest", "-products", "*",
             "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-property", "installationPath"],
            capture_output=True, text=True, timeout=30)
        vs_root = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    except Exception:
        return None
    if not vs_root or not os.path.isdir(vs_root):
        return None
    devcmd = os.path.join(vs_root, "Common7", "Tools", "VsDevCmd.bat")
    if not os.path.isfile(devcmd):
        return None
    # 在 dev 环境里问一句 cl 在哪；构出完整可执行路径
    try:
        r = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c",
             f'call "{devcmd}" -arch=arm64 -no_logo >NUL && where cl'],
            capture_output=True, text=True, timeout=120)
        lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().lower().endswith("cl.exe")]
        if lines:
            return lines[-1]
    except Exception:
        return None
    return None


def find_compiler(tools_dir):
    """探测可用的 C++ 编译器，返回 (命令列表前缀, 是否 MSVC)。"""
    msvc = shutil.which("cl")
    if msvc:
        return [msvc], True
    if os.name == "nt":
        # ARM64 Windows 上 VS 的 cl 是宿主 x86_64/arm64 交叉版，PATH 没有，
        # 尝试 vswhere + VsDevCmd 定位
        msvc_full = _msvc_via_vsdevcmd()
        if msvc_full:
            return [msvc_full], True
    for name in (("g++", "c++", "clang++") if os.name == "nt"
                 else ("clang++", "c++", "g++")):
        path = shutil.which(name)
        if path:
            return [path], False
    if os.name == "nt":
        die("未找到 C++ 编译器。crn2rgba.cpp 是 C++ 源码，需要编译成 exe 才能运行。"
            "请任选其一安装：\n"
            "  1) Visual Studio 生成工具（含 C++ 工作负载，装完重开 PowerShell）:\n"
            "     https://visualstudio.microsoft.com/zh-hans/visual-cpp-build-tools/\n"
            "  2) 轻量替代 MinGW-w64（g++）: winget install MartinStorsjo.LLVM-MinGW\n"
            "     或 https://github.com/niXman/mingw-builds-binaries/releases\n"
            f"  3) 在其他电脑上编译 tools/crn2rgba.cpp，把 crn2rgba.exe 放入 {tools_dir}")
    die("未找到 C++ 编译器。请安装其中之一：\n"
        "  Linux:   sudo apt install g++（或发行版等价命令）\n"
        "  macOS:   xcode-select --install\n"
        f"也可用其他机器编译 tools/crn2rgba.cpp 后把可执行文件放入 {tools_dir}")


def build_tool():
    """编译 Crunch 解码器，返回可执行文件路径。"""
    exe = "crn2rgba.exe" if os.name == "nt" else "crn2rgba"
    tool = os.path.join(HERE, "tools", exe)
    src = os.path.join(HERE, "tools", "crn2rgba.cpp")
    if os.path.isfile(tool):
        return tool
    if not os.path.isfile(src):
        die("缺少 tools/crn2rgba.cpp")
    print("\n== 编译 Crunch 解码器 ==")
    comp, is_msvc = find_compiler(os.path.join(HERE, "tools"))
    if is_msvc:
        cmd = comp + ["/O2", "/EHsc", "/W0", "/nologo",
                      "/I" + os.path.join(HERE, "tools"), src, "/Fe:" + tool]
    else:
        cmd = comp + ["-O2", "-std=c++11", "-fno-strict-aliasing", "-w",
                      "-I", os.path.join(HERE, "tools"), src, "-o", tool]
    run(cmd, cwd=HERE)
    return tool


def check_deps():
    missing = []
    errors = []
    for mod, pkgname in (("lz4.block", "lz4"), ("PIL", "pillow"),
                         ("astc_encoder", "astc_encoder_py")):
        try:
            __import__(mod)
        except Exception as e:  # 非 ImportError 也要兜住（如依赖自身的原生扩展崩了）
            missing.append(pkgname)
            errors.append(f"  {pkgname}: {type(e).__name__}: {e}")
    if missing:
        msg = ("以下 Python 依赖在当前解释器中不可用: " + " ".join(missing) +
               "\n当前解释器: " + sys.executable +
               "\n请用【同一个解释器】安装（注意: `pip` 可能属于另一个 Python，"
               "务必用 python -m pip 形式）:\n"
               f'  "{sys.executable}" -m pip install ' + " ".join(missing))
        if errors:
            msg += "\n导入失败的具体原因:\n" + "\n".join(errors)
            joined = "\n".join(errors).lower()
            if "winerror 193" in joined or "dll load failed" in joined or "%1 不是有效" in joined \
                    or "找不到指定的模块" in joined:
                msg += ("\n提示: 这是 C 运行库缺失或架构不匹配的典型报错。\n"
                        "最常见原因：新系统没装 VC++ Redistributable（astc 扩展依赖\n"
                        "MSVCP140.dll / VCRUNTIME140.dll）。安装与本机架构对应的版本：\n"
                        "  ARM64 Windows: https://aka.ms/vs/17/release/vc_redist.arm64.exe\n"
                        "  x64 Windows:   https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
                        "装完重开 PowerShell 再试。若仍失败再检查 Python 架构是否与本机 CPU 一致。")
        die(msg)


def is_pkg(path):
    """pkg 文件校验：16 字节头 + ver=0x00025100 + 索引偏移在文件范围内。"""
    try:
        size = os.path.getsize(path)
        if size < 32:
            return False
        with open(path, "rb") as f:
            hdr = f.read(16)
        ver, _unk, idx_off, idx_size = struct.unpack("<4I", hdr)
        return ver == 0x00025100 and idx_off + idx_size == size
    except OSError:
        return False


def main():
    if len(sys.argv) < 2:
        die("用法: python3 UnpackAll.py 路径/到/common_res.pkg")

    check_deps()

    pkg = os.path.abspath(sys.argv[1])
    # 常见误操作 2：传入目录 —— 自动定位其中最大的有效 pkg
    if os.path.isdir(pkg):
        cands = [os.path.join(dp, f)
                 for dp, _dns, fs in os.walk(pkg)
                 for f in fs
                 if f.endswith(".pkg") and is_pkg(os.path.join(dp, f))]
        if not cands:
            die(f"目录里没有找到有效的 .pkg 资源包: {pkg}")
        pkg = max(cands, key=os.path.getsize)
        print(f"检测到传入的是目录，已自动选择其中的资源包: {pkg}")
    elif not os.path.isfile(pkg):
        die(f"找不到 pkg 文件: {pkg}")
    elif not is_pkg(pkg):
        # 常见误操作 1：把脚本/其他文件当 pkg 传入
        die(f"第二个参数应是 .pkg 资源包，传入的却是无效文件:\n  {pkg}\n"
            "pkg 文件在 APK 解包后的 assets/ 目录里，例如:\n"
            '  ...\\迷你世界_1.58.2\\assets\\common_res.pkg\n'
            "（也可以直接把 assets 目录路径传给本脚本，会自动选择其中的资源包）")

    for f in NEEDED:
        if not os.path.isfile(os.path.join(HERE, f)):
            die(f"缺少辅助脚本 {f} —— 请使用完整仓库克隆，所有文件需在同一目录")

    print(f"pkg : {pkg}")
    print(f"输出: {OUT}")
    os.makedirs(OUT, exist_ok=True)

    # 1. 解包容器
    print("\n== 步骤 1/4：解包容器 ==")
    run([sys.executable, os.path.join(HERE, "unpack_common_res.py"), pkg, OUT])

    # 2. ASTC / RGB 纹理 → PNG（原地覆盖）
    print("\n== 步骤 2/4：转换 ASTC/RGB 纹理 ==")
    run([sys.executable, os.path.join(HERE, "convert_textures.py"), OUT, OUT])

    # 3. 确保 Crunch 解码器已编译
    tool = build_tool()

    # 4. Crunch/ETC2A 纹理 → PNG（原地覆盖）
    print("\n== 步骤 4/4：转换 Crunch/ETC2A 纹理 ==")
    run([sys.executable, os.path.join(HERE, "convert_fmt65.py"), OUT, OUT, tool])

    # 统计
    total = 0
    pngs = 0
    for dp, _, fs in os.walk(OUT):
        for f in fs:
            total += 1
            if f.endswith(".png"):
                pngs += 1
    print(f"\n完成！共 {total} 个文件（其中 {pngs} 张 PNG）→ {OUT}")
    print("提示: 纹理已原地转为标准 PNG（原始引擎纹理数据已被覆盖）；"
          "如需保留原始数据请先备份。")


if __name__ == "__main__":
    main()
