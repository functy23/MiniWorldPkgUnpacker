# MiniWorldPkgUnpacker

迷你世界（Mini World）安卓客户端资源包解包与纹理转换工具。逆向了自研
"Rainbow" 引擎的 `.pkg` 资源容器格式与全部纹理编码，可将 1.58.2 版本
`common_res.pkg`（938 MB）中的 **21,300+ 张纹理全部还原为标准 PNG**，
音频（.ogg）与配置（.json）可直接提取。

> 仅供格式研究与学习。解包产物的版权归深圳市迷你玩科技有限公司所有，
> 请勿传播游戏资源本身。

## 目录

- [`unpack_common_res.py`](unpack_common_res.py) — `.pkg` 解包器：解析容器、
  LZ4 分块流、文件索引与路径表，还原全部文件
- [`convert_textures.py`](convert_textures.py) — ASTC/RGB 系纹理 → PNG
- [`convert_fmt65.py`](convert_fmt65.py) + [`tools/crn2rgba.cpp`](tools/crn2rgba.cpp) —
  Crunch (CRN) / ETC2A 纹理 → PNG
- [`AGENTS.md`](AGENTS.md) — 完整格式文档（逆向结果，含全部结构体与偏移）

## 用法

### 0. 准备

把本仓库 clone/下载到任意目录，**所有命令都在仓库根目录下执行**（脚本与
`tools/` 的相对位置不能变）。三个脚本都支持命令行参数指定路径，不传参则
使用括号里的默认值：

```
仓库根目录/
├── unpack_common_res.py      # 解包器
├── convert_textures.py       # ASTC/RGB 纹理转换
├── convert_fmt65.py          # Crunch/ETC2A 纹理转换
└── tools/                    # CRN 解码器源码
```

游戏资源 `common_res.pkg` 默认从 `./迷你世界_1.58.2/assets/` 读取，
放在别处没关系——第 1 步用第一个参数传入完整路径即可。

### 1. 安装依赖

```bash
pip3 install lz4 pillow astc_encoder_py
```

### 2. 解包资源容器（约 3-5 分钟，产物约 2.6 GB）

```bash
# python3 unpack_common_res.py [pkg 文件路径] [输出目录]
python3 unpack_common_res.py "迷你世界_1.58.2/assets/common_res.pkg" common_res_unpacked
```

### 3. 编译 Crunch 解码器（转换 fmt65 纹理用，一次性）

```bash
clang++ -O2 -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba
```

### 4. 转换纹理为 PNG（产物在 decoded_png/，保持原目录结构）

```bash
# python3 convert_textures.py [解包目录] [PNG输出目录]  —— ASTC 4x4/6x6、RGB24、RGBA32、R8 等
python3 convert_textures.py common_res_unpacked decoded_png

# python3 convert_fmt65.py [解包目录] [PNG输出目录] [crn2rgba 路径] —— Crunch/ETC2A
python3 convert_fmt65.py common_res_unpacked decoded_png tools/crn2rgba
```

两步合计划输出约 21,300 张 PNG（811 MB）。`.ogg` 音频与 `.json` 配置
在第 2 步已原样解出，直接可用。

### 常见问题

- **图片上下颠倒**：GPU 纹理按 OpenGL 惯例自下而上存储，两个转换脚本
  默认垂直翻转（`FLIP_VERTICAL = True`）；若方向不对，改成 `False`
  后删掉 `decoded_png` 重跑对应脚本。
- **重新转换**：转换脚本默认跳过已存在的 PNG，加 `--force` 参数
  （仅 fmt65 脚本）或删除 `decoded_png` 里的旧文件强制重转。

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
解包路径已打通（脚本包为"逐文件 LZ4 + 排序路径配对"变体）。
