#!/usr/bin/env python3
"""Build texture-name <-> Chinese-name mapping tables.

Uses game_script_out/script/csvdef/utf8/{blockdef,itemdef}.csv (extracted by
extract_game_script.py) and decoded_png/resources/minigame/{blocks,items} PNGs.

Outputs:
  对照表/方块对照.csv  文件名, 方块ID, 中文名, 匹配方式
  对照表/物品对照.csv  文件名, 物品ID, 中文名, 匹配方式
"""
import csv, os, re, sys
from collections import defaultdict

csv.field_size_limit(10**7)
ROOT = os.path.dirname(os.path.abspath(__file__))
CSVDEF = os.path.join(ROOT, "game_script_out", "script", "csvdef", "utf8")
PNG_ROOT = os.path.join(ROOT, "decoded_png", "resources", "minigame")

def load_def(name):
    rows = list(csv.reader(open(os.path.join(CSVDEF, name), encoding="utf-8")))
    return rows[0], rows[1:]

def block_label(ids, byid):
    return "; ".join(f"{i} {byid[i][1]}" for i in sorted(ids, key=int) if i in byid)

def item_label(ids, byid):
    return "; ".join(f"{i} {byid[i][1]}" for i in sorted(ids, key=int) if i in byid)

def build_blocks():
    hdr, rows = load_def("blockdef.csv")
    byid = {r[0]: r for r in rows}
    tex2ids = defaultdict(set)      # texture col 45/46 (also serves as model col)
    model2ids = defaultdict(set)    # model col 46
    en2ids = defaultdict(set)       # ENName(3) / Key(4), underscore/space-insensitive
    for r in rows:
        for ci in (45, 46):
            v = r[ci].strip().lower() if len(r) > ci else ""
            if v: tex2ids[v].add(r[0])
        v = r[46].strip().lower() if len(r) > 46 else ""
        if v: model2ids[v].add(r[0])
        for ci in (3, 4):
            v = r[ci].strip().lower() if len(r) > ci else ""
            if v: en2ids[re.sub(r"[_\s]+", "", v)].add(r[0])

    d = os.path.join(PNG_ROOT, "blocks")
    names = sorted(f[:-4] for f in os.listdir(d) if f.endswith(".png"))

    def match(ln):
        # 1. exact texture name
        if ln in tex2ids:
            return tex2ids[ln], "贴图列精确"
        # 2. trailing feature suffix: _emi/_mix/_on/_top/... (longest first)
        parts = ln.rsplit("_", 1)
        while len(parts) > 1 and parts[1]:
            if parts[0] in tex2ids:
                return tex2ids[parts[0]], f"贴图列+_{parts[1]}"
            parts = parts[0].rsplit("_", 1)
        # 3. trailing digits: button_stone1 -> button_stone
        m = re.fullmatch(r"([a-z0-9_]+?)(\d+)", ln)
        if m and m.group(1) in tex2ids:
            return tex2ids[m.group(1)], f"贴图列+{m.group(2)}"
        # 4. digits then feature suffix: aluminum1_x
        m = re.fullmatch(r"([a-z0-9_]+?)\d+(_[a-z0-9]+)", ln)
        if m and m.group(1) in tex2ids:
            return tex2ids[m.group(1)], f"贴图列+数字_{m.group(2)[1:]}"
        # 5. model name (col 46) exact or with suffix
        m = re.fullmatch(r"([a-z0-9_]+?)(\d+)?(_[a-z0-9]+)?", ln)
        if m:
            base = m.group(1)
            if base in model2ids:
                how = "模型列" + (f"+{m.group(2) or ''}{m.group(3) or ''}")
                return model2ids[base], how
            if base + "_proto" in model2ids and (m.group(2) or m.group(3)):
                return model2ids[base + "_proto"], "模型列(_proto)"
        # 6. ENName/Key without separators
        flat = re.sub(r"[_\s]+", "", ln)
        if flat in en2ids:
            return en2ids[flat], "英文名"
        return set(), ""

    out, matched = [], 0
    for n in names:
        ids, how = match(n.lower())
        if ids: matched += 1
        out.append([n + ".png", block_label(ids, byid) if ids else "", how])
    return out, matched

def build_items():
    hdr, rows = load_def("itemdef.csv")
    byid = {r[0]: r for r in rows}
    # icon column 38: "icon10127" / "43000" / special tokens (#=avatar etc.)
    icon2ids = defaultdict(set)
    for r in rows:
        ic = r[38].strip()
        if ic and re.fullmatch(r"[A-Za-z0-9_]+", ic):
            icon2ids[ic.lower()].add(r[0])
        elif ic:
            # may contain special prefixes; still try raw
            icon2ids[ic.lower()].add(r[0])

    d = os.path.join(PNG_ROOT, "items")
    names = sorted(f[:-4] for f in os.listdir(d) if f.endswith(".png"))

    out, matched = [], 0
    for n in names:
        ln = n.lower()
        ids, how = set(), ""
        if ln in icon2ids:
            ids, how = icon2ids[ln], "图标列"
        elif n in byid:
            ids, how = {n}, "ID直连"
        elif ln.startswith("icon") and ln[4:] in byid:
            ids, how = {ln[4:]}, "icon+ID"
        if ids: matched += 1
        out.append([n + ".png", item_label(ids, byid) if ids else "", how])
    return out, matched

def main():
    os.makedirs(os.path.join(ROOT, "对照表"), exist_ok=True)
    for name, fn, cols in (("方块对照.csv", build_blocks, ["文件名", "方块ID 中文名", "匹配方式"]),
                           ("物品对照.csv", build_items, ["文件名", "物品ID 中文名", "匹配方式"])):
        rows, matched = fn()
        # split combined label into id + name columns per spec
        with open(os.path.join(ROOT, "对照表", name), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"{name}: {matched}/{len(rows)} matched  -> 对照表/{name}")

if __name__ == "__main__":
    main()
