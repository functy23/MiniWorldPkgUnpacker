<div align="center">

# 🎮 MiniWorldPkgUnpacker

**迷你世界（Mini World）安卓客户端 `.pkg` 资源包解包与纹理转换工具 —— 自研 "Rainbow" 引擎容器格式的逆向实现。**

[![MiniWorldPkgUnpacker](https://img.shields.io/badge/MiniWorldPkgUnpacker-MWPU-orange.svg)](https://github.com/functy23/MiniWorldPkgUnpacker)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Top Language](https://img.shields.io/github/languages/top/functy23/MiniWorldPkgUnpacker?style=flat)](https://github.com/functy23/MiniWorldPkgUnpacker)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/functy23/MiniWorldPkgUnpacker)

[![CI](https://img.shields.io/github/actions/workflow/status/functy23/MiniWorldPkgUnpacker/ci.yml?branch=main&label=CI&logo=githubactions&logoColor=white)](https://github.com/functy23/MiniWorldPkgUnpacker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

[![Downloads](https://img.shields.io/github/downloads/functy23/MiniWorldPkgUnpacker/total?label=Downloads&logo=github)](https://github.com/functy23/MiniWorldPkgUnpacker/releases)
[![Stars](https://img.shields.io/github/stars/functy23/MiniWorldPkgUnpacker?style=flat&logo=github)](https://github.com/functy23/MiniWorldPkgUnpacker/stargazers)
[![Repo Size](https://img.shields.io/github/repo-size/functy23/MiniWorldPkgUnpacker?style=flat&logo=github)](https://github.com/functy23/MiniWorldPkgUnpacker)
[![Contributors](https://img.shields.io/github/contributors/functy23/MiniWorldPkgUnpacker?color=ee8449&logo=githubsponsors)](https://github.com/functy23/MiniWorldPkgUnpacker/graphs/contributors)

[Issues](https://github.com/functy23/MiniWorldPkgUnpacker/issues) • [格式文档](../AGENTS.md)

[English](../README.md) | **简体中文**
</div>

---

## 概述

迷你世界把游戏资源打包在自研 **"Rainbow" 引擎**的 `.pkg` 容器里。本项目逆向
了该容器格式与全部纹理编码，可把整棵资源树还原成普通文件，并把
**21,000+ 张纹理解码为标准 PNG**。

支持两个版本分支，**按头部版本号自动识别**：

| 分支 | 索引版本 | 结构 | 纹理还原 |
|---|---|---|---|
| 国内版 1.58.2 | `0x00025100` | LZ4 分块数据区 + 路径排序配对 | 21,303 张 PNG |
| **国际版 1.7.x（CREATA）** | `0x000130BA` | 原始数据区 + 路径自带记录索引 | 13,871 张 PNG |

**支持 Windows / Linux / macOS**（Python 3.8+ 与任一 C++ 编译器）。

> 仅供格式研究与学习。解包产物的版权归迷你世界（深圳市迷你玩科技有限公司）
> 所有，请勿传播游戏资源本身。

## 仓库结构

- [`UnpackAll.py`](../UnpackAll.py) — **一键脚本**：自动识别版本，解包 + 全部纹理
  转 PNG，输出到 `unpack/`
- [`unpack_pkg_intl.py`](../unpack_pkg_intl.py) + [`pkg_intl.py`](../pkg_intl.py) —
  **国际版**（1.7.x）解包器与索引解析库
- [`unpack_common_res.py`](../unpack_common_res.py) — **国内版**（1.58.2）解包器：
  解析容器、LZ4 分块流、文件索引与路径表
- [`convert_textures.py`](../convert_textures.py) — ASTC / RGB 系纹理 → PNG
- [`convert_fmt65.py`](../convert_fmt65.py) + [`tools/crn2rgba.cpp`](../tools/crn2rgba.cpp) —
  Crunch (CRN) / ETC2A 纹理 → PNG
- [`tests/smoke_test.py`](../tests/smoke_test.py) — 自包含 CI 测试（合成 pkg，无需游戏资源）
- [`AGENTS.md`](../AGENTS.md) — 完整格式文档（含全部结构体与偏移）

## 用法

### 快速开始（推荐）

把仓库 clone 到任意目录，在仓库根目录执行：

```bash
# 1. 安装 Python 依赖
pip install lz4 pillow astc_encoder_py
#   macOS Homebrew 或部分 Linux 发行版需加 --break-system-packages：
# pip3 install --break-system-packages lz4 pillow astc_encoder_py

# 2. 确保有 C++ 编译器（一键脚本会自动探测并编译 Crunch 解码器）
#    Windows: 安装 "Visual Studio 生成工具"（cl）或 MinGW-w64（g++）
#    Linux:   sudo apt install g++
#    macOS:   xcode-select --install

python UnpackAll.py "路径/到/common_res.pkg"        # Windows
python3 UnpackAll.py "路径/到/common_res.pkg"       # Linux / macOS
```

一条命令完成：**按头部版本号自动选择解包器** → 解包 → 全部纹理转 PNG
（自动编译解码器、自动修复纹理方向）。产物输出到 **当前目录的 `unpack/`**：

```
unpack/
├── resources/minigame/...   全部资源；*.png 已原地转为可预览的标准 PNG
├── script/...               启动配置 JSON 与 Lua 脚本（明文）
├── systemdefault/...
├── _containers/...          国内版专有：服务器下发资源的占位文件与 manifest
└── _unpack_report.json      解包统计（md5 校验、解码分支、扩展名一致性）
```

> 注意：`*.png` 会被原地替换为转换后的标准 PNG（原始引擎纹理数据被覆盖）；
> `.ogg` / `.json` / `.lua` 等非纹理文件原样保留。

### 分步执行（与 UnpackAll.py 等价）

脚本与 `tools/` 的相对位置需保持仓库结构，**所有命令在仓库根目录执行**：

```bash
pip install lz4 pillow astc_encoder_py

# 1. 解包容器
#    国内版 1.58.2（约 3-5 分钟，产物约 2.6 GB）
python3 unpack_common_res.py "迷你世界_1.58.2/assets/common_res.pkg" common_res_unpacked

#    国际版 1.7.x（667 MB 包约 5 秒，产物约 870 MB）
python3 unpack_pkg_intl.py "Mini+World_+CREATA_1.7.15_APKPure/assets/common_res.pkg" unpack

# 2. 编译 Crunch 解码器（一次性；Windows 用 cl 时加 /O2 /EHsc /W0 /Fe:）
clang++ -O2 -std=c++11 -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba

# 3. 转换纹理为 PNG（输出到 decoded_png/，保持原目录结构）
#    python3 convert_textures.py [解包目录] [PNG输出目录]  —— ASTC 4x4/6x6、RGB24、RGBA32、R8 等
python3 convert_textures.py common_res_unpacked decoded_png

#    python3 convert_fmt65.py [解包目录] [PNG输出目录] [crn2rgba 路径] —— Crunch/ETC2A
python3 convert_fmt65.py common_res_unpacked decoded_png tools/crn2rgba
```

### 跑测试

```bash
python3 tests/smoke_test.py
```

冒烟测试会在临时目录里合成 `.pkg` 并完整往返一遍，不依赖任何游戏资源，
CI 上可直接跑。

## 常见问题

- **图片上下颠倒**：GPU 纹理按 OpenGL 惯例自下而上存储，两个转换脚本
  默认垂直翻转（`FLIP_VERTICAL = True`）；若方向不对，改成 `False`
  后删掉输出目录里的 PNG 重跑对应脚本。
- **重复转换**：转换脚本默认跳过已存在的 PNG；fmt65 脚本可加 `--force`
  强制重转，其余删除输出目录里的旧 PNG 即可。
- **支持的 pkg（国内版 1.58.2）**：`common_res.pkg` / `core_res.pkg` /
  `game_script.pkg` / `material_ogles*.pkg`。国内版的 `first_res.pkg`
  为另一种索引变体，暂不支持。
- **支持的 pkg（国际版 1.7.x）**：`common_res.pkg` / `game_res.pkg` /
  `script_res.pkg` / `material_ogles2.pkg` / `material_ogles3.pkg` /
  `first_res.pkg` / `game_language.pkg`（**全部 8 个包均实测解析通过**）。
  `remote_res.pkg` 结构可解，但其记录 `X` 恒为 16、内容不在包内（服务器按需
  下发），提取出来的是同一段占位数据。
- **两个版本不能混用脚本**：国内版走 `unpack_common_res.py`，国际版走
  `unpack_pkg_intl.py`（`UnpackAll.py` 会自动判断版本号分派）。

## 格式逆向摘要

### 国际版（1.7.x，ver `0x000130BA`）

```
[16B 头]  u32 ver=0x000130BA | u32 17 | u32 index_offset | u32 index_size
[数据区]  原始字节（无 LZ4 分块）；记录 X 即文件偏移，Y 即长度
[索引区]  单个 LZ4 块（u32 解压后大小 + 块），解压后：
    u32 N
    N 条变长记录（长度靠 X 链判定）：
        44B = [16B 内容md5][u32 X][u32 Y][u32 Z][16B H2]   # Z 的 bit5 置位
        28B = [16B 内容md5][u32 X][u32 Y][u32 Z]           # Z 的 bit5 清零
    （变体 B 专有）16B 页脚
    u32 C
    C 条路径条目，紧凑无填充：[u32 L][L 字节路径][u32 A]
```

- **路径 ↔ 记录配对（核心）**：路径 `k` 的记录索引 = **紧跟在它后面**的那个 u32
  —— 布局是 `[u32 L][path][u32 A]`。已验证 100%：ogg 2,719/2,719 · vmo 108/108 ·
  zip 14/14 · dls 1/1 · json 144/144 · png 13,879/13,879。
  ⚠️ 若误读成 `[A][L][path]`，索引会错位到前一条，表现为「92% 命中」的假象。
- **载荷解码看 Z 的 bit0，不是 bit5**：`Z ∈ {1, 33}` 为 `[u32 usize][LZ4 块]`；
  `Z ∈ {0, 32}` 为原始字节。（Z 的 bit5 是记录种类标志：置位即 44 字节记录。）

### 国内版（1.58.2，ver `0x00025100`）

```
[16B 头]  u32 ver=0x00025100 | u32 17 | u32 index_offset | u32 index_size
[数据区]  连续 LZ4 块（每块 256 KB），块表在索引尾部
[索引区]  LZ4 压缩，解压后：
    44B 文件记录 × N  (内容 MD5 | 流偏移 X | 大小 Y | H2 | Z)
    12B 引导记录 × M
    路径表，随后是分块表
```

- `X` 为文件坐标（流内偏移 = X − 16）；记录链严格衔接，总长与解压流精确一致。
- **路径 ↔ 记录配对**：把全部路径按字节序排序，前 `M` 条（全是 `../script/...`）
  对应引导记录，其余按流序对应文件记录——已用音频魔数、JSON 内容、CSV 文件名
  三重验证。

### 纹理

格式枚举与 **Unity TextureFormat** 一致（1=Alpha8, 3=RGB24, 4=RGBA32,
48=ASTC4x4, 50=ASTC6x6, 63=R8, 65=Crunch…）。容器头含宽/高/mip 级数，
数据区为 mip0 在前的 mip 链。

| | 国内版 1.58.2 | 国际版 1.7.x |
|---|---|---|
| 魔数 | `0x59A21C2C`（偏移 4） | `0x054C8245`（偏移 8） |
| 数据起始 | 107 | 107 |

`fmt 65`（数量最多）为 **Crunch (.CRN) 容器封装的 ETC2A**：签名 `0x4878`，
头字段大端，与 Unity-Technologies/crunch 的 `unity` 分支兼容（上游 master
不支持 format 12 = ETC2A）。解码用
[`tools/crn2rgba.cpp`](../tools/crn2rgba.cpp)（crn_decomp + iOrange/etcdec.h 的
ETC2A→RGBA），编译：`clang++ -O2 -std=c++11 -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba`。

## 成果

| 类别 | 数量 | 结果 |
|---|---|---|
| 纹理 → PNG | 21,303（国内版） | 全部成功（13 个立方体天空图仅提取未拼装） |
| 纹理 → PNG | 13,871（国际版） | 全部成功（8 个立方体天空图仅提取未拼装） |
| 音频 `.ogg` | 3,227（国内版）/ 2,719（国际版） | 原生可读 |
| 配置 `.json` / `.xml` / `.csv` | 1,500+ / 565 | 原生可读 |
| 启动 Lua 脚本 | 1,346（国内版） | 明文 |
| 完整性 | — | 每条记录 MD5 全部通过（100%），0 错误 |

国际版 `common_res.pkg`（667 MB）解包耗时 **4.6 秒**（~132 MB/s）：
写出 33,283 个文件，MD5 **33,283/33,283** 通过。

## 许可证

以 [MIT 许可证](../LICENSE) 发布。

用本工具解包出的游戏资源版权归其所有者；本仓库仅包含逆向所得的
工具链与文档。
