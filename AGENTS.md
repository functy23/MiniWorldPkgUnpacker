# 迷你世界解包项目 / Mini World Unpacking

> 文档与许可：README 为英文主文档（`README.md`）+ 中文版（`doc/README_zh-CN.md`），
> 两者内容对应，改一边记得同步另一边。许可证 **MIT**（`LICENSE`）。
> CI 在 `.github/workflows/ci.yml`：三平台 × Python 3.9/3.12，跑 compileall +
> 编译 crn2rgba + `tests/smoke_test.py` / `tests/test_pairing.py` /
> `tests/test_linux_binary.py`（合成输入，不需要游戏资源）；另有
> `prebuilt-linux` job 在真实 Linux x64/arm64 上校验仓库自带的静态解码器。
> 本文件（AGENTS.md）是给 AI/维护者的**唯一权威格式文档**，保持中文即可。

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
  `../script/`（攻击/技能配置 JSON + 启动 Lua）。
  ⚠️ 路径表里每条路径后面那个 u32 A 字段**不是记录索引**：它的高位（bit31）
  只在 1,346 条路径上置位，低 31 位范围 0..105864，但按它取记录只有 ~30% 命中。
  真正可用的索引是「按字节序排序后的位次」，这也是 `unpack_common_res.py` 的做法。
- **内容一致性验证（2026-09 复核，真实包 1.58.2）**：对全部 49,031 条真实记录做
  扩展名 ↔ 魔数嗅探，**47,374 / 47,374 通过、0 反例**（.ogg→`OggS`、
  .json→`{`、.png/.mesh/.skanim/.skeleton/.animmask/.filelist→type2 容器头、
  .omod/.ent/.otex/.emo→`89 67 45 23`、.mat/.prefab/.controller→
  `01 00 00 00` + u32 主体长度、.uprefab→u32 名字长度或 JSON、.vmo→`VMOF`、
  .fui→`FGUI`、.vox→`VOX `、.blockmesh→首 float 1.0）。配错一条就会立刻表现为
  嗅探失败，因此排序配对在真实包上是 100% 正确的。
- **Y == 0 的 A 记录（58,180 条）= 服务器下发资源**：内容**不在包内**，X 指向
  包内另一个真实记录，绝大多数（57,528 条）属于
  `resources/minigame/remotes/entity/**`（玩家装扮/武器外观等按需下载的资源）。
  这些 X 全部落在 3,797 个 `all.filelist` 记录上（每个资源目录一个清单），
  另有 652 条指向同一个 `sandbox/game/prefab/block/100000.uprefab` 共享 blob。
  - **Z 不是大小，是资源组 id**：占位记录 `Z >> 2` 恒等于其目标真实记录的
    `Z >> 2`（占位记录低 2 位为 2/3，真实记录低 2 位恒为 0）。**58,180/58,180
    全部成立**，可作为「这条占位路径属于哪个资源组」的强校验。
  - `all.filelist` 是真实记录，格式为 `[u32 ?][u32 ?][u32 n][n × (16B md5 + u32 size)]`
    （数据从 0x18 起），描述该目录下应有哪些文件——但它们的内容同样不在包内。
  - 这些路径**不会写到原路径**（内容确实不存在），只按 X 去重后落到
    `_containers/` 并在 `manifest.json` 里给出完整映射（见下）。
- 数据区中 **zsize == usize 的块是未压缩原始数据**，不能当 LZ4 解。
- 资源内容多为引擎序列化格式（魔数 `02 00 00 00 2C 1C A2 59`，即 0x59A21C2C），
  `.png` 实为引擎纹理容器，`.ogg`/`.json`/`.csv` 为原始明文。

### 同系列文件

`game_script.pkg`、`core_res.pkg`、`first_res.pkg`、`material_ogles*.pkg` 头部
结构相同（ver 都是 0x25100，16B 头 + LZ4 分块数据区 + 尾部块表），但**路径表
有两种变体**：

| pkg | N | M | path count | 路径表变体 | 现状 |
|---|---|---|---|---|---|
| common_res.pkg | 105,865 | 1,346 | 107,211 = N+M | A：排序配对 | ✅ 49,031 文件，md5 全通过 |
| core_res.pkg | 6,810 | 0 | 6,810 = N+M | A：排序配对（无 B） | ✅ 6,810 文件 |
| game_script.pkg | 0 | 10,666 | 10,666 = N+M | A：排序配对（全 B） | ✅ 10,666 文件 |
| first_res.pkg | 75 | 3,472 | **3,430 ≠ N+M** | **B：未知** | ❌ 报错拒绝 |
| material_ogles2.pkg | 210 | 27,259 | **27,469 ≠ N+M** | **B：未知** | ❌ 报错拒绝 |
| material_ogles3.pkg | 210 | 59,501 | **59,711 ≠ N+M** | **B：未知** | ❌ 报错拒绝 |

- 变体 A（path count == N+M）用「按字节序排序 → 前 M 条配 B、其余按流序配 A」。
- 变体 B 的三个包：路径数与记录数不等，且 `unpack_common_res.py` 现在会
  **显式抛 `UnsupportedVariant` 并退出码 2**（旧版是 `assert` 崩栈），
  不再静默产出错位目录树。已试过的假设（A 字段当索引、按标志位顺序消费、
  排序尾部配 A 等）都不成立，属未破解。
- `game_script.pkg` 的排序配对已用 csv 内容验证（achievement.csv → "成就ID..."）。

## 输出结构

```
common_res_unpacked/
  resources/minigame/...   # 游戏资源（纹理/网格/动画/预制体/音频/配置）
  script/...               # 1346 个引导配置与启动脚本（.bil 为 Lua 字节码）
  systemdefault/...        # 默认系统资源
  _containers/             # 58,180 条服务器下发路径 → 3,797 个去重 blob（全是 all.filelist）
                           #   + manifest.json（含 groups/placeholders 完整映射与资源组 id）
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
  编译：`c++ -O2 -std=c++11 -fno-strict-aliasing -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba`。
  依赖 macOS patch：malloc_usable_size→malloc_size、ptr_bits 强制 uint64。
- 立方体贴图（faces=6，如 ugcenv/skycube1-4）工具支持但 Python 端未拼装，仅 13 个。
- 数据区尾部普遍有 1 字节冗余（dsz 从 107 计数、ASTC 从 108 计数），解码时忽略。

## 批量转 PNG

```bash
python3 convert_textures.py    # fmt 48/50/3/4/5/63/1 → decoded_png/
python3 convert_fmt65.py       # fmt 65 (CRN/ETC2A)   → decoded_png/，需先准备 tools/crn2rgba
```

两步共 21,303 张 PNG，覆盖全部纹理（仅 13 个立方体天空图未拼装）。

`tools/crn2rgba` 一般**不需要本机编译**：Windows 用 `crn2rgba_{x64,arm64}.exe`、
Linux 用 `crn2rgba_linux_{x64,arm64}`（zig 交叉编译的 musl 静态二进制），
`UnpackAll.py` 的 `prebuilt_candidates()` 会自动按平台/架构挑一个复制成
`tools/crn2rgba`；macOS 无预编译版，现场 `c++ -std=c++11` 编译。

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
3. `_containers/manifest.json` 中每条占位路径都带 `group_id`（= Z >> 2）与
   `H1`（服务器端内容的 md5），可用于比对热更新包 / 服务器下发的资源。


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

## ★★ 国际版（Mini World CREATA）支持（✅ 2026-09-19 本轮完成）

### 版本与文件

国际版 APK（Mini World + CREATA 1.7.15）的 assets/ 里 8 个 pkg **全部**是同一种
新索引格式 **ver = 0x000130BA**，与国内版 1.58.2（0x00025100）**不兼容**：

| pkg | 记录 N | 路径 C | 变体 | 说明 |
|---|---|---|---|---|
| common_res.pkg | 36,615 | 33,283 | A | 667 MB 主资源包 |
| game_res.pkg | 3,521 | 3,517 | B | 有 16B 页脚 |
| script_res.pkg | 8,172 | 8,172 | A | Lua 字节码 + csv/xml/json |
| material_ogles2/3.pkg | 2,926 / 3,711 | 同 N | A | 材质 |
| first_res.pkg | 2,455 | 2,362 | A | 首包 |
| remote_res.pkg | 21,528 | 21,528 | A | **X 恒为 16，内容全不在包内**（服务器下发占位） |
| game_language.pkg | 39 | 39 | B | 语言包，有 16B 页脚 |

### 索引格式（与国内版的差异）

```
[16B 头]  u32 ver=0x000130BA | u32 17 | u32 index_offset | u32 index_size
[数据区]  原始字节（无 LZ4 分块！），记录 X 即文件偏移、Y 即长度
[索引区]  单个 LZ4 块（前 4 字节为解压后大小），解压后：
    u32 N
    N 条变长记录（靠 X 链判定长度）：
        44B = [16B 内容md5][u32 X][u32 Y][u32 Z][16B H2]     # Z 的 bit5 置位
        28B = [16B 内容md5][u32 X][u32 Y][u32 Z]             # Z 的 bit5 清零
    （变体 B 专有）16B 页脚
    u32 C
    C 条路径条目，紧凑无填充：[u32 L][L 字节路径][u32 A]
[索引末尾] 最后一个 u32 就是最后一条路径的 A 字段本身，不是额外字段
```

### 关键规则（全部 100% 验证）

- **记录长度判定**：`bool(Z & 0x20) == (记录为 44B)` 对全部 36,615 条成立
  （44B → Z∈{32,33}，28B → Z∈{0,1}）。判定顺序很重要：**末条记录必为 28B**
  （其 X+Y == index_offset），先判末条再按 X 链 lookahead。
- **X 链**：X[i+1] == X[i] + Y[i] 无违规；ΣY == index_offset − 16；记录精确铺满
  [16, index_offset) 无空洞无重叠。**md5(raw[X:X+Y]) == H1，36,615/36,615 零反例。**
- **★ 路径 ↔ 记录配对（核心，已破解）**：路径条目 k 的记录索引 = **紧跟在它
  后面**的那个 u32 A（`[u32 L][path][u32 A]`，A 在路径之后）。
  命中率：ogg 2,719/2,719、vmo 108/108、zip 14/14、dls 1/1、json 144/144、
  png 13,879/13,879、emo 1,998/1,998 —— **全部 100%**。
  ⚠️ 易踩坑：若误读成 `[u32 A][u32 L][path]`（A 在前），会把 A 错位到前一条，
  表现为「92% 命中」的假象（ogg 的 2,500/2,719 是记录局部性巧合）。
- **载荷解码按 Z 的 bit0**（不是 bit5！）：
  - Z ∈ {1, 33} → `[u32 usize][LZ4 块]`，解码长度 == usize（11,057 条全通过）
  - Z ∈ {0, 32} → 原始未压缩字节（22,226 条）
  ⚠️ `1 & 0x20 == 0`，用位与判压缩会漏掉 Z==1 的 23 条材质 xml。
- **无占位机制**：Y == 0 的记录 **0 条**，A 值 33,283 个全互异 → 国内版的
  `_containers/` 共享占位机制在国际版**完全不适用**。
- 配对**不需要排序**（国内版那套「按字节序排序再切分」在国际版命中 0）。

### 国际版纹理容器（与国内版魔数不同）

```
国内版: [u32 2][magic 0x59A21C2C]  ...  fmt@0x20 w@0x14 h@0x18 dsz@0x1C
国际版: [u32 0][u32 2][magic 0x054C8245] ...  同样的字段偏移
两者数据区都从偏移 107 开始，尾部 0~3 字节对齐冗余
```

- 国际版 common_res 的 13,879 个 `.png` **全部**是引擎容器（无真 PNG）。
- fmt 分布：65(CRN) 13,502、48(ASTC4x4) 334、4 32、3 9、63 1、1 1。
- **CRN 签名 `Hx` 固定在偏移 107**（13,502/13,502），头字段大端；
  容器 w/h 与 CRN 头 w/h 一致，dsz == CRN 的 data_size（偏移 6）。
- ASTC 数据也在 107，dsz == mip 链尺寸模型（fmt48 用 4x4、fmt50 用 6x6）。
- 解码工具链**完全复用**（`tools/crn2rgba` + astc_encoder_py + Pillow）。

### 实测结果（common_res.pkg，667 MB）

- 解包 33,283 个文件，md5 **33,283/33,283 通过**，0 错误，耗时 **4.6 s**（~132 MB/s）。
- 纹理转换：**13,871 张标准 PNG**（CRN 13,494 + ASTC/RGB 377），0 损坏；
  尺寸与引擎容器头交叉校验 2,000/2,000 吻合。
- **8 张立方体贴图未拼装**（与国内版 13 张同类，属已知限制，不是 bug）：
  `resources/minigame/entity/universal_textures/cubemap_diamond.png`、
  `entity/universal_textures/env_skylight.png`、`sky/env_skylight.png`、
  `sky/reflect_cubemap.png`、`ugcenv/skycube1.png`、`ugcenv/skycube2.png`、
  `systemdefault/textures/default_env.png`、`default_skybox.png`。
  它们的 CRN 头 faces=6（普通纹理 faces=1），crn2rgba 走 cubemap-skip 分支，
  文件保持引擎容器原样。
- 一键脚本 `UnpackAll.py` 端到端：33,284 文件（含报告）+ 13,879 PNG。

### 新增文件

- `pkg_intl.py` — 国际版索引解析库（`IntlPackage` / `open_pkg` / `is_pkg`），
  同时支持变体 A（无页脚）与变体 B（16B 页脚）。
- `unpack_pkg_intl.py` — 国际版解包脚本，产出 `_unpack_report.json`。
- `UnpackAll.py` — 按头部版本号自动分派国内版/国际版解包器。
- `convert_textures.py` / `convert_fmt65.py` — 同时识别两种魔数（国内版行为不变）。

### 剩余可选工作

1. 方块表 471 个未匹配：多为引擎通用贴图（anvil_s0、caustics、bullethole、
   粒子/特效辅助图），对应 OBJ 模型材质贴图需解析 .mtl（obj 只引 mtllib，
   无 map_Kd，mtl 文件需从 common_res 深挖）。
2. `对照表/` 与 csvdef 可顺手做成 GitHub 发布物（用户已推 game_script 工具链）。

## ★★★ Linux 免编译器支持（✅ 2026-09-20 本轮完成，issue #1）

### 背景：issue #1 报的错早就修了，但用户仍卡住

issue #1（deepumt，2026-08-30）报 `tools/crn_decomp_unity.h:24: fatal error:
'malloc/malloc.h' file not found`。该问题在 `c2da737` 当天已修（头文件只在
`__APPLE__` 下包含 `<malloc/malloc.h>`，其他平台 `<malloc.h>`），CI 的
ubuntu job 早已绿。用户仍卡住的真正原因有三：

1. 报错的是**旧检出**，且 issue 一直没回帖；
2. README 让人照抄 `clang++ ...`，Ubuntu 上通常没装 clang++；
3. 仓库只有 Windows 预编译 exe，Linux 用户**被迫装 g++**。

### 本轮改动（方案 3：预编译 Linux 二进制 + CI 校验）

- **新增 `tools/crn2rgba_linux_x64` / `tools/crn2rgba_linux_arm64`**：用
  zig 0.16 交叉编译的 **musl 静态**二进制（无 glibc 版本依赖、无需运行时库）：
  ```bash
  zig c++ -O2 -std=c++11 -fno-strict-aliasing -w -static -target x86_64-linux-musl  -I tools tools/crn2rgba.cpp -o tools/crn2rgba_linux_x64  -Wl,-s
  zig c++ -O2 -std=c++11 -fno-strict-aliasing -w -static -target aarch64-linux-musl -I tools tools/crn2rgba.cpp -o tools/crn2rgba_linux_arm64 -Wl,-s
  ```
  各约 240 KB（`-Wl,-s` 去掉调试符号；不加约 3.2 MB）。
- **`UnpackAll.py` 新增 `prebuilt_candidates()`**：按平台/架构返回候选名
  （Windows `crn2rgba_{x64,arm64}.exe`、Linux `crn2rgba_linux_{x64,arm64}`），
  `build_tool()` 命中即复制成 `tools/crn2rgba` 并 `chmod +x`，**本机无需编译器**；
  找不到才回落到现场编译。架构归一化含 `AMD64/X86_64 → x64`、`ARM64/AARCH64 → arm64`。
- **`tests/fixtures/etc2a_64x64_mips.crn`**（1,302 B）：合成 ETC2A 夹具，
  64×64、7 级 mip 链、faces=1、format=12。用 Unity crunch `unity` 分支的 CLI
  从一张**现场合成的渐变 PNG** 编出来（不是游戏素材，可入库）。
  `.gitignore` 加了 `!tests/fixtures/*.crn` 例外（原本 `*.crn` 全忽略）。
- **`tests/test_linux_binary.py`**：Linux 上断言预编译二进制解夹具的
  RGBA 摘要 == `b1e1246e41986b9c8457150742bdafd4a1f5f0107db810b82b9f6b6333e90fcd`，
  并与**现场编译版**逐字节比对（防止提交的二进制过期）；macOS/Windows 只校验
  夹具头，保持 CI 全绿。
- **CI 新增 `prebuilt-linux` job**：`ubuntu-latest`(x64) + `ubuntu-24.04-arm`
  (arm64，公开仓库免费) 各跑一次上面的测试；主 job 也加了该测试。

### 验证证据（本地实测）

- **真 Linux（lima Ubuntu 26.04 aarch64）原生跑 arm64 二进制**：3 个真实
  国际版纹理（32×32 fmt12、256×256 fmt12、128×256 fmt12）+ 合成夹具，
  输出与 macOS 原生二进制 **sha256 完全一致**；`g++ 15.2` 现场编译版同样一致。
- 3 个真实样本：`ui_32x32 bca2fe32…`、`ui_256x256 104da8eb…`、
  `blocks_128x256 54d7a96f…`（macOS 原生 == Linux arm64）。
- 在 Linux VM 里跑 `UnpackAll.build_tool()`：输出
  `使用仓库预编译解码器 crn2rgba_linux_arm64（无需本机 C++ 编译器）`。
- **端到端对照**：用国际版 `game_language.pkg`（1 MB，38 张 fmt65）在
  macOS 与 lima Ubuntu 26.04 aarch64 上各跑一次 `UnpackAll.py`：两边都是
  40 个文件 / 38 张 PNG、路径集合完全一致，**PNG 像素级一致**
  （同一路径 `startlotterytitle.png` 解出的 RGBA sha256 相同：`36c5fd7c…`）。
  文件字节 md5 不同只是 Pillow 版本差异导致的 PNG 编码/元数据不同，非解码差异。
- Linux 侧运行日志关键行：`使用仓库预编译解码器 crn2rgba_linux_arm64
  （无需本机 C++ 编译器）`，全程未调用 g++。

### 编译 crunch 编码器（只为造夹具，非仓库必需）

夹具是用 Unity-Technologies/crunch 的 `unity` 分支源码编出的 CLI 生成的。
在本机/交叉编译时踩到并绕过的坑（若将来需要重新造夹具可复用）：

- `crn_threading_pthreads.h` 的 `pthread_spinlock_t` 在 musl 不存在 → 用
  `__sync_lock_test_and_set` 自旋实现替换；
- `CRNLIB_BREAKPOINT asm("int $3")` 在 aarch64 非法 → `__builtin_trap()`；
- `crn_vector.cpp` 的 `math::is_power_of_2(size_t)` 在 64 位下歧义 → 显式 `(uint32)`；
- musl 缺 `fseeko64/fopen64` → `-D_LARGEFILE64_SOURCE -D_GNU_SOURCE`；
- macOS：`malloc.h` 不存在（且 `malloc/malloc.h` 会经 `mach/dyld_kernel.h`
  触发 `uuid_t` 报错）→ 直接 `extern "C" size_t malloc_size(const void*);`；
  `pthread_self()` 不能 `static_cast` 成整数；无 `sem_timedwait` 与未命名信号量
  （`sem_init` 返 ENOSYS）→ 命名信号量 + `sem_trywait` 轮询；
- crnlib 的 Makefile 里 `crn_zeng.o` 是**幽灵对象**（源文件不在 unity 分支），
  按 Makefile 列表编译必须跳过不存在的源文件。
