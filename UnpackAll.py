#!/usr/bin/env python3
"""UnpackAll — 一键解包迷你世界 .pkg 资源包。

用法:
    python3 UnpackAll.py 路径/到/common_res.pkg

全部产物输出到 当前目录/解包输出/：
    解包输出/resources/...   解包出的全部文件（.ogg/.json/.lua 原生可读）
    解包输出/.../*.png       纹理已原地转换为可预览的标准 PNG
                             （注意：会覆盖原始引擎纹理数据）

需要本脚本与 unpack_common_res.py / convert_textures.py / convert_fmt65.py /
tools/ 处于同一目录（即本仓库的完整克隆）。
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.getcwd(), "解包输出")
NEEDED = ["unpack_common_res.py", "convert_textures.py", "convert_fmt65.py"]


def die(msg):
    print("错误:", msg)
    sys.exit(1)


def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        die(f"步骤失败（退出码 {r.returncode}）: {' '.join(cmd)}")


def main():
    if len(sys.argv) < 2:
        die("用法: python3 UnpackAll.py 路径/到/common_res.pkg")

    pkg = os.path.abspath(sys.argv[1])
    if not os.path.isfile(pkg):
        die(f"找不到 pkg 文件: {pkg}")

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
    tool = os.path.join(HERE, "tools", "crn2rgba")
    if not os.path.isfile(tool):
        print("\n== 步骤 3/4：编译 Crunch 解码器 ==")
        if not os.path.isfile(os.path.join(HERE, "tools", "crn2rgba.cpp")):
            die("缺少 tools/crn2rgba.cpp")
        run(["clang++", "-O2", "-fno-strict-aliasing", "-w",
             "-I", os.path.join(HERE, "tools"),
             os.path.join(HERE, "tools", "crn2rgba.cpp"),
             "-o", tool], cwd=HERE)

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
