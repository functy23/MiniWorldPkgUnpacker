#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迷你世界国际版（Mini World CREATA 1.7.x） .pkg 索引解析库。

与国内版（1.58.2，ver 0x00025100）的区别见 AGENTS.md。本模块只负责
「头部 -> 记录数组 -> 路径表」的解析与载荷解码，供解包脚本与转换脚本复用。

    from pkg_intl import open_pkg
    with open_pkg("assets/common_res.pkg") as p:
        for rel, data, rec, branch in p.iter_files():
            ...
"""
import os
import struct

try:
    import lz4.block as _lz4block
except ImportError:  # pragma: no cover - 由调用方给出友好提示
    _lz4block = None

HDR_SIZE = 16
VER_INTL = 0x000130BA

# 载荷解码：Z 取值为「压缩」分支（注意 1 & 0x20 == 0，不能用位与判定）
Z_LZ4 = frozenset((1, 33))
Z_RAW = frozenset((0, 32))


def _need_lz4():
    if _lz4block is None:
        raise RuntimeError("缺少 lz4 模块：请执行 pip3 install lz4")
    return _lz4block


class PkgFormatError(Exception):
    pass


class IntlPackage(object):
    """已解析的 .pkg（国际版索引格式）。

    records[i] = (X, Y, Z, md5_16, H2)   X 为原始文件偏移，Y 为长度
    entries[k] = (record_index, path_bytes)
    """

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._fh = None
        self._read_index()

    # ------------------------------------------------------------ 索引解析
    def _read_index(self):
        lz4 = _need_lz4()
        with open(self.path, "rb") as f:
            f.seek(0, os.SEEK_END)
            fsize = f.tell()
            if fsize < HDR_SIZE + 4:
                raise PkgFormatError("文件过小，不是有效的 pkg：%s" % self.path)
            f.seek(0)
            hdr = f.read(HDR_SIZE)
            ver, unk, idx_off, idx_size = struct.unpack("<4I", hdr)
            if idx_off + idx_size != fsize:
                raise PkgFormatError(
                    "索引偏移与文件大小不符（index_offset+index_size=%d，实际 %d）"
                    % (idx_off + idx_size, fsize))
            f.seek(idx_off)
            iblob = f.read(idx_size)
        if len(iblob) != idx_size:
            raise PkgFormatError("索引区读取不完整")

        self.ver, self.unk = ver, unk
        self.index_offset, self.index_size = idx_off, idx_size
        self.file_size = fsize

        (iusize,) = struct.unpack_from("<I", iblob, 0)
        idx = lz4.decompress(iblob[4:], uncompressed_size=iusize)
        if len(idx) != iusize:
            raise PkgFormatError("索引解压长度不符：%d != %d" % (len(idx), iusize))
        self.index = idx

        pos = 0
        (n,) = struct.unpack_from("<I", idx, pos)
        pos += 4
        records = []
        for i in range(n):
            if pos + 28 > len(idx):
                raise PkgFormatError("记录区越界（第 %d 条 / 共 %d 条）" % (i, n))
            md5 = idx[pos:pos + 16]
            X, Y, Z = struct.unpack_from("<III", idx, pos + 16)
            nxt = X + Y
            n28 = struct.unpack_from("<I", idx, pos + 44)[0] if pos + 48 <= len(idx) else -1
            n44 = struct.unpack_from("<I", idx, pos + 60)[0] if pos + 64 <= len(idx) else -1
            # 末条记录 X+Y == index_offset，必为 28 字节
            short = (nxt == idx_off) or (n28 == nxt and n44 != nxt)
            H2 = b"" if short else idx[pos + 28:pos + 44]
            records.append((X, Y, Z, md5, H2))
            pos += 28 if short else 44
        self.records = records
        self.record_count = len(records)

        # 变体 A（common_res 等）：此处直接是路径计数
        # 变体 B（game_res / game_language）：先有一个 16 字节页脚，再是计数
        footer = None
        (count,) = struct.unpack_from("<I", idx, pos)
        if not 0 < count <= (len(idx) - pos) // 8:
            footer = idx[pos:pos + 16]
            pos += 16
            (count,) = struct.unpack_from("<I", idx, pos)
        pos += 4

        entries = []
        for k in range(count):
            if pos + 4 > len(idx):
                raise PkgFormatError("路径表越界（第 %d 条）" % k)
            (plen,) = struct.unpack_from("<I", idx, pos)
            pos += 4
            if plen < 1 or pos + plen + 4 > len(idx):
                raise PkgFormatError("路径长度异常（第 %d 条，L=%d）" % (k, plen))
            raw_path = idx[pos:pos + plen]
            pos += plen
            # A 字段位于路径 *之后*，即该路径对应的记录索引
            (rec_index,) = struct.unpack_from("<I", idx, pos)
            pos += 4
            entries.append((rec_index, raw_path))
        self.entries = entries
        self.path_count = len(entries)
        self.footer = footer
        self.index_tail_unused = len(idx) - pos

        if self.index_tail_unused:
            raise PkgFormatError("索引尾部残留 %d 字节未消费" % self.index_tail_unused)

    # ------------------------------------------------------------ 读取
    def open(self):
        if self._fh is None:
            self._fh = open(self.path, "rb")
        return self._fh

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def read_raw(self, index):
        X, Y, Z, md5, _H2 = self.records[index]
        fh = self.open()
        fh.seek(X)
        return fh.read(Y)

    def decode(self, index):
        """返回 (payload_bytes, branch)，branch 取值 'raw' 或 'lz4'。"""
        raw = self.read_raw(index)
        Z = self.records[index][2]
        if Z not in Z_LZ4:
            return raw, "raw"
        if len(raw) < 4:
            return raw, "raw"
        (usize,) = struct.unpack_from("<I", raw, 0)
        try:
            out = _need_lz4().decompress(raw[4:], uncompressed_size=usize)
        except Exception:
            return raw, "raw"
        if len(out) != usize:
            return raw, "raw"
        return out, "lz4"

    def iter_files(self):
        """按路径表顺序产出 (safe_relpath, payload, record_index, branch)。"""
        for rec_index, raw_path in self.entries:
            rel = safe_relpath(raw_path)
            if rel is None:
                continue
            payload, branch = self.decode(rec_index)
            yield rel, payload, rec_index, branch


def safe_relpath(raw_path):
    """把包内路径规范化为安全的相对路径；不可用时返回 None。"""
    if isinstance(raw_path, bytes):
        s = raw_path.decode("utf-8", "surrogateescape")
    else:
        s = raw_path
    s = s.replace(chr(92), "/")
    while s.startswith("../"):
        s = s[3:]
    s = s.lstrip("/")
    parts = [p for p in s.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    return "/".join(parts)


def is_pkg(path):
    """快速判断是否为本格式的 .pkg（头部版本号 + 索引精确落在文件尾）。"""
    try:
        size = os.path.getsize(path)
        if size < HDR_SIZE + 4:
            return False
        with open(path, "rb") as f:
            ver, _unk, idx_off, idx_size = struct.unpack("<4I", f.read(HDR_SIZE))
        return ver == VER_INTL and idx_off + idx_size == size
    except (OSError, struct.error):
        return False


def open_pkg(path):
    return IntlPackage(path)
