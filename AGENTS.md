# 迷你世界解包项目 / Mini World Unpacking

## 项目状态

`common_res.pkg`（938 MB，迷你世界 1.58.2 安卓版）已完整解包至 `common_res_unpacked/`。
解包工具：`unpack_common_res.py`（Python 3，依赖 `lz4`：`pip3 install lz4`）。

## 重跑解包

```bash
python3 unpack_common_res.py          # 输出到 common_res_unpacked/，约 3-5 分钟
```

## common_res.pkg 文件格式（逆向结果，Rainbow 引擎 PackageAsset）

```
[16 字节头]  u32 ver=0x00025100 | u32 17 | u32 index_offset | u32 index_size
             (index_offset + index_size == 文件总大小)
[数据区]     连续 LZ4 块（无块内头），块表在索引尾部
[索引区]     前 4 字节 = 解压后大小，其余为单个 LZ4 块，解压后布局：
               u32 N                      # A 记录数（44 字节/条）
               N × [16B 内容md5][u32 X][u32 Y][16B H2][u32 Z]
               u32 M                      # B 记录数（12 字节/条，引导文件）
               M × [u32 X][u32 Y][u32 Z]
               路径区：
                 u32 count                # == N + M
                 条目0: [u32 L][路径 L 字节][补齐到 4 对齐]   # 无 A 字段
                 其余:  [u32 A][u32 L][路径 L 字节][补齐到 4 对齐]
                                        # A 常带 0x80000000 标志位（含义未确认，与定位无关）
               u32 ? ; u32 chunk_count
               (chunk_count-1) × [u32 262144][u32 zsize] + [u32 末块usize][u32 末块zsize]
```

### 关键规则

- **X 是文件坐标**：流内偏移 = X − 16；Y = 文件大小。A 记录按 X 严格链式排列
  （X[i+1] == X[i] + Y[i]），总长精确等于解压流总长 1,414,279,456 字节。
- **H1 = 内容 MD5**（已抽样 100% 验证）。H2 含义未确认，不是任何常见形式的
  md5(路径)/murmur3/fnv。
- **路径 ↔ 记录的配对规则（核心难点，已破解）**：把全部 107,211 条路径按
  **字节序（近似字母序）排序**，前 M=1346 条（全是 `../script/...`）依次对应
  B 记录，其余依次对应 A 记录（按流顺序）。B 记录描述的文件恰为
  `../script/`（攻击/技能配置 JSON + 启动 Lua）。验证方式：`.ogg` 路径 →
  `OggS` 魔数、`.json` 路径 → `{`，命中率 >99.9%。
- **Y == 0 的 A 记录（58,180 条）是占位引用**：真实内容不在本包内
  （服务器按需下载的资源，如 avatar/1000_xxx 玩家装扮）。其 X 指向包内一个
  小的共享占位文件（通常是下一个真实记录，124 字节的引擎序列化空对象）。
  Z ≈ 服务器端真实大小。这些路径统一提取到 `_containers/` +
  `_containers/manifest.json`（含每条路径与占位文件、内容 md5 的对应关系）。
- 数据区中 **zsize == usize 的块是未压缩原始数据**，不能当 LZ4 解。
- 资源内容多为引擎序列化格式（魔数 `02 00 00 00 2C 1C A2 59`，即 0x59A21C2C），
  `.png` 实为引擎纹理容器，`.ogg`/`.json`/`.csv` 为原始明文。

### 同系列文件

`game_script.pkg`、`core_res.pkg`、`first_res.pkg`、`material_ogles*.pkg` 头部
结构相同。`game_script.pkg` 索引无 A 记录（N=0），全部为 B 记录，格式与
common_res 相同（chunk 表 + X 为解压流坐标），**已完整解出**——见下方
续接指南（旧的"逐文件 LZ4/块链接"说法是误解，勿再参考）。其排序路径 ↔
记录配对规则已用 csv 内容验证（achievement.csv → "成就ID..."）。

## 输出结构

```
common_res_unpacked/
  resources/minigame/...   # 游戏资源（纹理/网格/动画/预制体/音频/配置）
  script/...               # 1346 个引导配置与启动脚本（.bil 为 Lua 字节码）
  systemdefault/...        # 默认系统资源
  _containers/             # 58,180 条占位路径 → 4,761 个共享占位 blob + manifest.json
  _unpack_report.json      # 提取统计（md5 全部通过，0 错误）
```

## 纹理格式（已全部破解）

`.png`（共 21,318 个）= 引擎序列化容器，格式枚举 = **Unity TextureFormat**：

| fmt | 格式 | 数据起始 | 数量 | 状态 |
|-----|------|---------|------|------|
| 1 / 3 / 4 / 5 | Alpha8 / RGB24 / RGBA32 / ARGB32 | 108 | 87 | ✅ 直接拼 PNG |
| 48 | ASTC 4x4 | 108 | 334 | ✅ astcenc 解码 |
| 50 | ASTC 6x6 | 107 | 4,474 | ✅ astcenc 解码 |
| 63 | R8 | 108 | 1 | ✅ |
| 65 | **Crunch (CRN) → ETC2A** | 107 | 16,421 | ✅ 全部转换 |

- ASTC: mip0 在最前，0x24 字段 = mip 级数（含 mip0），mip 链紧随。ASTC6x6 尺寸
  模型 400/400 精确验证。解码用 `astc_encoder_py`（pip）。
- fmt 65 = **Crunch `.CRN`**（签名 `48 78`=0x4878），头字段**大端**：
  sig/hdrsize/crc16/data_size u32/crc16/w u16/h u16/levels/faces/format(u8=12=ETC2A)/
  flags + 4 个 palette 表(ofs24,size24,num16) + tables_size16/tables_ofs24 +
  level_ofs u32×levels。**与 Unity-Technologies/crunch 的 `unity` 分支完全兼容**
  （master 分支不支持 ETC2A；HearthSim/decrunch 亦可）。解码工具：
  `tools/crn2rgba.cpp`（集成 crn_decomp + iOrange/etcdec.h 的 ETC2A→RGBA），
  编译：`clang++ -O2 -w -I tools tools/crn2rgba.cpp -o crn2rgba`。
  依赖 macOS patch：malloc_usable_size→malloc_size、ptr_bits 强制 uint64。
- 立方体贴图（faces=6，如 ugcenv/skycube1-4）工具支持但 Python 端未拼装，仅 13 个。
- 数据区尾部普遍有 1 字节冗余（dsz 从 107 计数、ASTC 从 108 计数），解码时忽略。

## 批量转 PNG

```bash
python3 convert_textures.py    # fmt 48/50/3/4/5/63/1 → decoded_png/
python3 convert_fmt65.py       # fmt 65 (CRN/ETC2A)   → decoded_png/，需先编译 tools/crn2rgba
```
两步共 21,303 张 PNG，覆盖全部纹理（仅 13 个立方体天空图未拼装）。

**方向**：GPU 纹理按 OpenGL 惯例自下而上存储，两个脚本均已垂直翻转
（`FLIP_VERTICAL = True`；若重新解码发现方向反了，改回 `False` 重跑即可）。
用户已确认翻转后的方向正确（2026-08）。

## 其他可读性结论

- 原生可读：`.ogg`（3,227 全部为标准 OggS）、`.json`（1,384）、`.obj` 部分
  （"3ds Max" 明文导出）、`.lua/.bil`（明文 Lua 源码）、`.xml`、`.csv`。
- 引擎序列化（0x59A21C2C 容器）：`.mat`(type1)、`.prefab`(type1)、
  `.controller`(type1)、`.mesh/.skanim/.skeleton/.filelist`(type2)。
- 其他未知魔数：`.emo`/`.blockmesh`(`89 67 45 23`)、`.ent`、`.omod`、
  `.vmo`("VMOF")、`.fui`(FGUI)。

## 可能的后续工作

1. fmt 65 定制 crunch：逆向 .so 中 crn_symbol_codec 的 canned tables
   （定位点：字符串 "F:/minichina/Engine/ThirdParty/TextureCompressors/Crunch"）。
2. 引擎序列化格式（0x59A21C2C）解析：mesh/skanim/prefab → 通用格式。
3. `_containers/manifest.json` 中的 H1 可用于比对热更新包/服务器资源。


## ★ 续接指南（给下一个会话/模型，2026-08-30）

### game_script.pkg 格式（✅ 已完全破解，旧"块链接 LZ4"结论是错的）

与 common_res.pkg 同构：数据区 = 独立 LZ4 块序列，块表在索引尾部
（u32 ?; u32 chunk_count; (count-1)×[u32 262144][u32 zsize] + 末块[usize][zsize]）。
全 B 记录（N=0），**记录 X 是解压后流的坐标（流内偏移 = X−16），不是压缩文件
偏移**；Y = 解压大小，X 链严格相邻且总和精确等于解压流长。之前"7 字节漂移"
是把压缩数据按 X 误切的产物。提取器：`extract_game_script.py`（已重写，全部
10,666 文件解出，含 191 个明文 csvdef + 全部游戏 Lua）。

### 名称对照表（✅ 本轮完成）

- 名称来源：`game_script_out/script/csvdef/utf8/blockdef.csv`（3,367 方块，
  列 0=ID、1=中文名、3/4=英文/Key、45=贴图1、46=贴图2/模型名）、
  `itemdef.csv`（18,590 物品，列 0=ID、1=中文名、38=图标名）。
  注意：英文名/Key 会被多个方块复用（如 GrassBlock 也是"混凝土"99 的 Key），
  不能当唯一键；贴图列才是可靠关联。
- 生成脚本：`build_name_map.py` → `对照表/方块对照.csv`（4,477/4,948 匹配）、
  `对照表/物品对照.csv`（3,175/3,300 匹配）。列：文件名, ID 中文名, 匹配方式。
- 方块贴图匹配链：贴图列精确 → 去尾部特性后缀（_emi/_mix/_top/_side/_snow/
  _x/_y/_z/_m/_on/_off/_rgb…）→ 去尾部数字 → 数字+后缀 → 模型列(46) → 英文名。
- 物品图标匹配：itemdef 列 38（`icon10127` 等图标名）→ 裸数字文件名直连 ID
  → `icon<ID>`。未匹配的多为 UI/活动图（broadcast_vip/centerbg/genius_icon 等）。

### 跨平台适配（✅ 2026-08-31 本轮完成）

- **输出目录**：UnpackAll.py 产物从 `解包输出/` 改为 **`unpack/`**（当前
  工作目录下，不再绑定 macOS 用户目录习惯）。
- **编译器自动探测**：`cl`（MSVC，`/O2 /EHsc /W0 /Fe:`）→ 优先
  `clang++/c++/g++`（Linux）或 `g++/clang++`（Windows MinGW），统一加
  **`-std=c++11`**（Apple clang 默认 C++98，lambda 编不过）。
- **tools/crn_decomp_unity.h**：malloc 查询改为 `CRND_MSIZE` 宏
  （Win=_msize / macOS=malloc_size / 其他=malloc_usable_size），
  `<malloc/malloc.h>` 仅在 `__APPLE__` 下包含。**注意**：crn2rgba.cpp 的
  include 曾写错为 `crn_decomp_u.h`（磁盘上是 `crn_decomp_unity.h`），
  已修复——旧二进制是改名前编译的。
- **convert_fmt65.py**：`/tmp/_in.crn` 等硬编码临时文件改为 `tempfile.mkdtemp`。
- **编码加固**：所有脚本 `sys.stdout/stderr.reconfigure(encoding="utf-8")`
  （Windows 控制台 GBK 防炸）；manifest/report 写文件显式 `encoding="utf-8"`；
  UnpackAll 启动时预检 lz4/Pillow/astc_encoder_py 并给出安装提示。
- 验证：新编 crn2rgba 与旧二进制输出 byte-identical（5 个样本含 208KB 大图）；
  game_script.pkg 全流程跑通，10,666 文件与 extract_game_script.py 产物一致。

### 剩余可选工作

1. 方块表 471 个未匹配：多为引擎通用贴图（anvil_s0、caustics、bullethole、
   粒子/特效辅助图），对应 OBJ 模型材质贴图需解析 .mtl（obj 只引 mtllib，
   无 map_Kd，mtl 文件需从 common_res 深挖）。
2. `对照表/` 与 csvdef 可顺手做成 GitHub 发布物（用户已推 game_script 工具链）。
