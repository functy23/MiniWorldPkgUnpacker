# MiniWorldPkgUnpacker

迷你世界（Mini World）安卓客户端资源包解包与纹理转换工具。逆向了自研
"Rainbow" 引擎的 `.pkg` 资源容器格式与全部纹理编码，可将 1.58.2 版本
`common_res.pkg`（938 MB）中的 **21,300+ 张纹理全部还原为标准 PNG**，
音频（.ogg）与配置（.json）可直接提取。

**支持 Windows / Linux / macOS**（Python 3.8+ 与任一 C++ 编译器）。

> 仅供格式研究与学习。解包产物的版权归深圳市迷你玩科技有限公司所有，
> 请勿传播游戏资源本身。

## 目录

- [`UnpackAll.py`](UnpackAll.py) — **一键脚本**：解包 + 全部纹理转 PNG，输出到 `unpack/`
- [`unpack_common_res.py`](unpack_common_res.py) — `.pkg` 解包器：解析容器、
  LZ4 分块流、文件索引与路径表，还原全部文件
- [`convert_textures.py`](convert_textures.py) — ASTC/RGB 系纹理 → PNG
- [`convert_fmt65.py`](convert_fmt65.py) + [`tools/crn2rgba.cpp`](tools/crn2rgba.cpp) —
  Crunch (CRN) / ETC2A 纹理 → PNG
- [`AGENTS.md`](AGENTS.md) — 完整格式文档（逆向结果，含全部结构体与偏移）

## 用法

### 快速开始（推荐）

把本仓库 clone 到任意目录，在仓库根目录执行：

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

一条命令完成：解包容器 → 全部纹理转 PNG（自动编译解码器、自动修复
纹理方向）。产物输出到 **当前目录的 `unpack/`**（Windows / Linux / macOS
通用）：

```
unpack/
├── resources/minigame/...   全部资源；*.png 已原地转为可预览的标准 PNG
├── script/...               启动配置 JSON 与 Lua 脚本（明文）
├── systemdefault/...
└── _containers/...          服务器下发资源的占位文件与 manifest
```

> 注意：`*.png` 会被原地替换为转换后的标准 PNG（原始引擎纹理数据被覆盖）；
> `.ogg` / `.json` / `.lua` 等非纹理文件原样保留。

### 分步执行（与 UnpackAll.py 等价）

脚本与 `tools/` 的相对位置需保持仓库结构，**所有命令在仓库根目录执行**。
三个脚本都支持参数指定路径，不传则用括号里的默认值：

```bash
pip install lz4 pillow astc_encoder_py

# 1. 解包容器（约 3-5 分钟，产物约 2.6 GB）
#    python3 unpack_common_res.py [pkg 文件路径] [输出目录]
python3 unpack_common_res.py "迷你世界_1.58.2/assets/common_res.pkg" common_res_unpacked

# 2. 编译 Crunch 解码器（一次性；Windows 用 cl 时加 /O2 /EHsc /W0 /Fe:）
clang++ -O2 -std=c++11 -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba

# 3. 转换纹理为 PNG（输出到 decoded_png/，保持原目录结构）
#    python3 convert_textures.py [解包目录] [PNG输出目录]  —— ASTC 4x4/6x6、RGB24、RGBA32、R8 等
python3 convert_textures.py common_res_unpacked decoded_png

#    python3 convert_fmt65.py [解包目录] [PNG输出目录] [crn2rgba 路径] —— Crunch/ETC2A
python3 convert_fmt65.py common_res_unpacked decoded_png tools/crn2rgba
```

### 常见问题

- **图片上下颠倒**：GPU 纹理按 OpenGL 惯例自下而上存储，两个转换脚本
  默认垂直翻转（`FLIP_VERTICAL = True`）；若方向不对，改成 `False`
  后删掉输出目录里的 PNG 重跑对应脚本。
- **重复转换**：转换脚本默认跳过已存在的 PNG；fmt65 脚本可加 `--force`
  强制重转，其余删除输出目录里的旧 PNG 即可。
- **支持的 pkg**：`common_res.pkg` / `core_res.pkg` / `game_script.pkg` /
  `material_ogles*.pkg`（同一格式）。`first_res.pkg` 为另一种索引变体，
  暂不支持。

## 格式逆向结果摘要

### 资源容器（.pkg）

```
[16B 头]  版本 0x00025100 | 17 | 索引偏移 | 索引大小
[数据区]  连续 LZ4 块（每块解压后 256 KB；压缩前后等大的块为原始存储）
[索引区]  LZ4 压缩，内含：
            44B 文件记录 × N   (内容 MD5 | 流偏移 X | 大小 Y | H2 | Z)
            12B 引导记录 × M   (X | Y | Z)
            路径表             ([A][长度][路径][对齐填充]，首条为计数)
            分块表             ([262144][压缩大小] × n + 末块)
```

- `X` 为文件坐标（流内偏移 = X − 16），记录链严格衔接，总长与解压流精确一致
- **路径 ↔ 记录配对**：把全部路径按字节序排序，前 M 条（`../script/…`）
  对应引导记录，其余按流序对应文件记录——这是解包的关键，已用
  音频魔数 / JSON 内容 / CSV 文件名三重验证

### 纹理

格式枚举与 **Unity TextureFormat** 一致（1=Alpha8, 3=RGB24, 4=RGBA32,
48=ASTC4x4, 50=ASTC6x6, 63=R8…），容器头含宽/高/mip 级数，数据区为
mip0 在前的 mip 链。

`fmt 65`（数量最多的一类）为 **Crunch (.CRN) 容器封装的 ETC2A**：签名
`0x4878`，头字段大端，与 Unity-Technologies/crunch `unity` 分支格式兼容
（原版 crunch 1.04 不支持其 fmt 12 = ETC2A）。块转码后用 ETC2 解码还原。

### 注意事项

- GPU 纹理按 OpenGL 惯例**自下而上**存储，转换脚本默认垂直翻转
  （`FLIP_VERTICAL = True`，方向不对时改回 `False` 重跑）
- LZ4 块压缩前后等大时为**未压缩原始数据**，不可直接当作 LZ4 解码
- 解包出的部分路径（约半数，多为 avatar 玩家装扮）是**服务器按需下发**的
  占位资源，包内只有共享占位文件，manifest.json 记录了其内容 MD5

## 成果

| 类别 | 数量 | 结果 |
|---|---|---|
| 纹理 → PNG | 21,303 | 全部成功（13 个立方体天空图仅提取未拼装） |
| 音频 .ogg | 3,227 | 原生可读 |
| 配置 .json / .xml / .csv | 1,500+ | 原生可读 |
| 启动 Lua 脚本 | 1,346 | 明文 |
| 解包完整性 | — | 47,685 条内容 MD5 校验全部通过 |

`game_script.pkg` / `core_res.pkg` / `material_ogles*.pkg` 头部结构相同，
解包路径已打通（`unpack_common_res.py` 通用；`extract_game_script.py`
为脚本包专用提取器，`build_name_map.py` 可生成贴图 ↔ 中文名对照表，
见 `对照表/`）。
