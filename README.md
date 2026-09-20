<div align="center">

# 🎮 MiniWorldPkgUnpacker

**Unpacker & texture decoder for Mini World (迷你世界) .pkg resource packages — a reverse-engineered "Rainbow" engine container format.**

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

[Issues](https://github.com/functy23/MiniWorldPkgUnpacker/issues) • [Format Docs](AGENTS.md)

**English** | [简体中文](doc/README_zh-CN.md)
</div>

---

## Overview

Mini World (迷你世界) ships its game assets inside `.pkg` containers built on the
in-house **"Rainbow" engine**. This project reverse-engineers that container format
together with every texture encoding it uses, so the whole asset tree can be
restored to plain files — and **21,000+ textures decoded to standard PNG**.

Two format branches are supported and **auto-detected from the header version**:

| Branch | Index version | Layout | Textures recovered |
|---|---|---|---|
| Domestic 1.58.2 | `0x00025100` | LZ4-chunked data region + sorted path pairing | 21,303 PNG |
| **International 1.7.x (CREATA)** | `0x000130BA` | Raw data region + per-path record index | 13,871 PNG |

**Windows / Linux / macOS** supported (Python 3.8+). No C++ compiler needed —
Windows and Linux use the prebuilt Crunch decoders shipped in [`tools/`](tools/).

> For format research and study only. Unpacked assets are copyright
> Mini World (深圳市迷你玩科技有限公司) — do not redistribute the game content itself.

## Repository Layout

- [`UnpackAll.py`](UnpackAll.py) — **one-shot script**: detects the version and runs
  unpack + full texture conversion, output to `unpack/`
- [`unpack_pkg_intl.py`](unpack_pkg_intl.py) + [`pkg_intl.py`](pkg_intl.py) —
  **international** (1.7.x) unpacker and index-parsing library
- [`unpack_common_res.py`](unpack_common_res.py) — **domestic** (1.58.2) unpacker:
  container, LZ4 chunk stream, file index and path table
- [`convert_textures.py`](convert_textures.py) — ASTC / RGB family textures → PNG
- [`convert_fmt65.py`](convert_fmt65.py) + [`tools/crn2rgba.cpp`](tools/crn2rgba.cpp) —
  Crunch (CRN) / ETC2A textures → PNG, via the prebuilt decoders in `tools/`
  (`crn2rgba_linux_x64` / `crn2rgba_linux_arm64` / `crn2rgba_x64.exe` / `crn2rgba_arm64.exe`)
- [`tests/smoke_test.py`](tests/smoke_test.py) — self-contained CI test
  (synthetic packages, no game assets required)
- [`tests/test_pairing.py`](tests/test_pairing.py) — pairing regression test:
  path ↔ record mapping, `Y == 0` placeholder dedup, and the `[L][path][A]` layout
  of the newer path table
- [`tests/test_linux_binary.py`](tests/test_linux_binary.py) — keeps the shipped
  Linux decoders honest: decodes a synthetic ETC2A fixture and compares against a
  freshly compiled build
- [`AGENTS.md`](AGENTS.md) — full format documentation (every struct and offset)

## Usage

### Quick start (recommended)

Clone the repository and run from its root:

```bash
# 1. Install Python dependencies
pip install lz4 pillow astc_encoder_py
#   macOS Homebrew or some Linux distros need --break-system-packages:
# pip3 install --break-system-packages lz4 pillow astc_encoder_py

# 2. Nothing else to install — the Crunch decoder is handled for you:
#    Windows / Linux: the prebuilt binary in tools/ is used as-is
#    macOS: compiled on the fly (xcode-select --install provides the compiler)

python UnpackAll.py "path/to/common_res.pkg"        # Windows
python3 UnpackAll.py "path/to/common_res.pkg"       # Linux / macOS
```

One command does everything: **picks the unpacker by header version** → unpacks →
converts every texture to PNG (compiling the decoder and fixing texture orientation
automatically). Output lands in `unpack/` under the current directory:

```
unpack/
├── resources/minigame/...   all assets; *.png already converted to standard PNG
├── script/...               bootstrap configs (JSON) and Lua scripts (plain text)
├── systemdefault/...
├── _containers/...          domestic only: server-side placeholder blobs (deduped) + manifest
└── _unpack_report.json      statistics (md5 checks, decode branches, consistency)
```

> Note: `*.png` files are replaced in place with standard PNGs (the original engine
> texture data is overwritten). Non-texture files such as `.ogg` / `.json` / `.lua`
> are kept as-is.

### Step by step (equivalent to UnpackAll.py)

Keep the repository layout intact and run everything from the repository root:

```bash
pip install lz4 pillow astc_encoder_py

# 1. Unpack the container
#    Domestic 1.58.2 (about 3-5 minutes, ~2.6 GB output)
python3 unpack_common_res.py "迷你世界_1.58.2/assets/common_res.pkg" common_res_unpacked

#    International 1.7.x (a 667 MB package takes ~5 seconds, ~870 MB output)
python3 unpack_pkg_intl.py "Mini+World_+CREATA_1.7.15_APKPure/assets/common_res.pkg" unpack

# 2. Get the Crunch decoder (once). UnpackAll.py does this automatically; by hand:
#    Linux — nothing to build, the repo ships statically linked binaries:
cp tools/crn2rgba_linux_x64 tools/crn2rgba          # x86_64
cp tools/crn2rgba_linux_arm64 tools/crn2rgba        # aarch64 / ARM servers
#    macOS — compile it (Apple clang defaults to C++98, so -std=c++11 is required):
c++ -O2 -std=c++11 -fno-strict-aliasing -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba
#    Windows — copy the shipped exe, or compile with MSVC / MinGW:
copy tools\crn2rgba_x64.exe tools\crn2rgba.exe      # x64
copy tools\crn2rgba_arm64.exe tools\crn2rgba.exe    # ARM64
cl /O2 /EHsc /W0 /nologo /Itools tools\crn2rgba.cpp /Fe:tools\crn2rgba.exe

# 3. Convert textures to PNG (output to decoded_png/, directory tree preserved)
#    python3 convert_textures.py [unpack dir] [png out dir]  — ASTC 4x4/6x6, RGB24, RGBA32, R8, ...
python3 convert_textures.py common_res_unpacked decoded_png

#    python3 convert_fmt65.py [unpack dir] [png out dir] [crn2rgba path] — Crunch/ETC2A
python3 convert_fmt65.py common_res_unpacked decoded_png tools/crn2rgba
```

### Running the tests

```bash
python3 tests/smoke_test.py        # synthetic .pkg round-trip
python3 tests/test_pairing.py      # path <-> record pairing regression
python3 tests/test_linux_binary.py # prebuilt Crunch decoders vs a local build
```

All three build their inputs synthetically (temp `.pkg` files, a synthetic ETC2A
`.crn` fixture), so they need no game assets and run fine in CI.

## FAQ

- **Images look upside down**: GPU textures are stored bottom-up following OpenGL
  convention; both converters flip vertically by default (`FLIP_VERTICAL = True`).
  If the orientation is wrong, set it to `False`, delete the generated PNGs and
  re-run.
- **Re-running conversions**: the converters skip PNGs that already exist;
  `convert_fmt65.py` accepts `--force`, for the others just delete the old output.
- **`fatal error: 'malloc/malloc.h' file not found` (Linux)**: your checkout
  predates the fix — run `git pull`. The header includes `<malloc/malloc.h>` only
  on `__APPLE__` and `<malloc.h>` elsewhere. You can also skip compiling entirely:
  `cp tools/crn2rgba_linux_x64 tools/crn2rgba`.
- **Supported packages (domestic 1.58.2)**: `common_res.pkg` (107,211 paths /
  49,031 files) and `core_res.pkg` (6,810 paths) and `game_script.pkg`
  (10,666 paths) — all unpack with MD5 100% passing.
  `first_res.pkg`, `material_ogles2.pkg` and `material_ogles3.pkg` carry the same
  header version but a **different path-table variant** (their path count does not
  equal `N + M`, and the `../script/`-sort rule does not apply); the unpacker now
  **refuses them with an explicit error** instead of silently writing a wrong tree.
  Cracking those three is open work.
- **Supported packages (international 1.7.x)**: `common_res.pkg` / `game_res.pkg` /
  `script_res.pkg` / `material_ogles2.pkg` / `material_ogles3.pkg` /
  `first_res.pkg` / `game_language.pkg` — **all 8 packages verified**. The
  `remote_res.pkg` structure parses too, but its records all point at offset 16
  (content is downloaded from the server on demand), so extraction yields the same
  placeholder blob.
- **The two branches are not interchangeable**: domestic uses
  `unpack_common_res.py`, international uses `unpack_pkg_intl.py`
  (`UnpackAll.py` dispatches automatically by version number).

## Format Summary

### International (1.7.x, ver `0x000130BA`)

```
[16B header]  u32 ver=0x000130BA | u32 17 | u32 index_offset | u32 index_size
[data region] raw bytes (no LZ4 chunking); record X is the file offset, Y the length
[index region] single LZ4 block (u32 uncompressed size + block), decompressing to:
    u32 N
    N variable-length records (length resolved through the X chain):
        44B = [16B content md5][u32 X][u32 Y][u32 Z][16B H2]   # Z bit5 set
        28B = [16B content md5][u32 X][u32 Y][u32 Z]           # Z bit5 clear
    (variant B only) 16B footer
    u32 C
    C path entries, tightly packed: [u32 L][L path bytes][u32 A]
```

- **Path ↔ record pairing (the crux)**: the record index for path `k` is the u32
  **immediately after** it — the layout is `[u32 L][path][u32 A]`. Verified 100%:
  ogg 2,719/2,719 · vmo 108/108 · zip 14/14 · dls 1/1 · json 144/144 · png 13,879/13,879.
  ⚠️ Reading it as `[A][L][path]` shifts the index onto the previous entry and
  produces a misleading "92% hit rate".
- **Payload decoding uses Z bit0, not bit5**: `Z ∈ {1, 33}` means
  `[u32 usize][LZ4 block]`; `Z ∈ {0, 32}` means raw bytes. (Z bit5 is the record-kind
  flag: set == 44-byte record.)

### Domestic (1.58.2, ver `0x00025100`)

```
[16B header]  u32 ver=0x00025100 | u32 17 | u32 index_offset | u32 index_size
[data region] consecutive LZ4 chunks (256 KB each), chunk table at the index tail
[index region] LZ4, decompressing to:
    44B file records x N  (content MD5 | stream offset X | size Y | H2 | Z)
    12B bootstrap records x M
    path table, then the chunk table
```

- `X` is a file coordinate (stream offset = X − 16); the record chain is strictly
  contiguous and its total matches the decompressed stream length exactly.
- **Path ↔ record pairing**: sort all paths by byte order; the first `M` (all
  `../script/...`) map to the bootstrap records, the rest to file records in stream
  order. Re-verified on the real 1.58.2 package by sniffing every extracted file
  against its extension: **47,374 / 47,374 pass, 0 counterexamples**.
  ⚠️ The u32 that follows each path in the path table is **not** a record index
  (bit31 is set on only 1,346 entries; indexing by it hits ~30%).
- **Server-side placeholders (`Y == 0`, 58,180 paths)**: their content is **not in
  the package** — `X` points at another real record, mostly the sibling
  `all.filelist` of the same directory (3,796 of 3,797 groups; the remaining one
  points at a shared `100000.uprefab` blob). Nearly all of them (57,528) live under
  `resources/minigame/remotes/entity/**` — player skins and weapon looks downloaded
  on demand. For those records **`Z` is not a size but a resource-group id**:
  `Z >> 2` always equals the `Z >> 2` of the target record (58,180/58,180 verified).
  These paths are therefore **not written at their original location**; they are
  deduplicated by `X` into `_containers/` with a full mapping in
  `_containers/manifest.json` (`groups` + `placeholders`, each with `group_id` and
  the server-side `H1` md5).

### Textures

The format enum matches **Unity's TextureFormat** (1=Alpha8, 3=RGB24, 4=RGBA32,
48=ASTC4x4, 50=ASTC6x6, 63=R8, 65=Crunch…). The container header carries
width/height/mip count and the data region is the mip chain with mip0 first.

| | Domestic 1.58.2 | International 1.7.x |
|---|---|---|
| Magic | `0x59A21C2C` at offset 4 | `0x054C8245` at offset 8 |
| Data starts at | 107 | 107 |

`fmt 65` (the most common one) is **ETC2A wrapped in a Crunch (.CRN) container**:
signature `0x4878`, big-endian header fields, compatible with the
Unity-Technologies/crunch `unity` branch (upstream master does not support
format 12 = ETC2A). Decoding uses
[`tools/crn2rgba.cpp`](tools/crn2rgba.cpp) (crn_decomp + iOrange/etcdec.h for
ETC2A→RGBA). Ready-to-run binaries ship with the repository —
`crn2rgba_linux_x64` / `crn2rgba_linux_arm64` (static musl: any distribution, no
glibc version issues), `crn2rgba_x64.exe` / `crn2rgba_arm64.exe` — so only macOS
needs a local compiler:
`c++ -O2 -std=c++11 -fno-strict-aliasing -w -I tools tools/crn2rgba.cpp -o tools/crn2rgba`.

## Results

| Category | Count | Status |
|---|---|---|
| Textures → PNG | 21,303 (domestic) | all converted (13 cubemaps extracted but not assembled) |
| Textures → PNG | 13,871 (international) | all converted (8 cubemaps extracted but not assembled) |
| Audio `.ogg` | 3,227 (domestic) / 2,719 (international) | natively readable |
| Configs `.json` / `.xml` / `.csv` | 1,500+ / 565 | natively readable |
| Bootstrap Lua scripts | 1,346 (domestic) | plain text |
| Integrity | — | every record MD5 verified (100%), 0 errors |
| Content sniffing | 47,374 (domestic) | extension ↔ magic, 0 mismatches |
| Server-side placeholders | 58,180 paths → 3,797 blobs (domestic) | content not shipped in the package |

The international `common_res.pkg` (667 MB) unpacks in **4.6 s** (~132 MB/s):
33,283 files written, MD5 **33,283/33,283** passing.

## License

Released under the [MIT License](LICENSE).

Game assets extracted with these tools remain the property of their respective
owners; this repository contains only the reverse-engineered tooling and
documentation.
