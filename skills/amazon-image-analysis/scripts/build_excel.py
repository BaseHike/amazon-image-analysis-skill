"""Build the competitor image workbook from the work directory.

Usage:
  python -X utf8 build_excel.py --work DIR [--format both|wps|excel]

Reads job.json, bs_list.json, filter.json, products/*/product.json, analysis/*.json, plan.json
(missing analysis / plan just leave those cells empty, so it can run after every step).
Writes <output_dir>/<name>-竞品图片分析-WPS.xlsx and -Excel.xlsx. Re-running overwrites them.

Sheets: 图片分类总表 | A+图片总表 | 新品视觉方案 | 剔除记录
Images go INTO cells (WPS: DISPIMG cell images, Excel: "Place in cell" pictures); both keep the
original aspect ratio (only proportional downscaling happens in scrape_product.py).
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

from amz_common import ROW_MAX_PT, out, read_json, text_height_pt

SHEET_MAIN, SHEET_APLUS, SHEET_PLAN, SHEET_REMOVED = "图片分类总表", "A+图片总表", "新品视觉方案", "剔除记录"
HEADER_COLOR = "#0F766E"
FONT = "微软雅黑"
IMG_COL_W, APLUS_COL_W, IMG_ROW_H, HEADER_H = 27, 22, 98, 36


# ------------------------------------------------------------------ data

def load(work):
    job = read_json(os.path.join(work, "job.json"))
    if not job:
        sys.exit("job.json not found")
    bs = read_json(os.path.join(work, "bs_list.json"), {"items": []})
    flt = read_json(os.path.join(work, "filter.json"), {"decisions": []})
    dec = {d["asin"]: d for d in flt.get("decisions", [])}
    titles = {i["asin"]: i for i in bs.get("items", [])}
    products = []
    pdir = os.path.join(work, "products")
    for asin in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
        p = read_json(os.path.join(pdir, asin, "product.json"))
        if not p or dec.get(asin, {}).get("decision") == "remove":
            continue
        p["analysis"] = read_json(os.path.join(work, "analysis", f"{asin}.json"))
        products.append(p)
    products.sort(key=lambda p: (p.get("rank") is None, p.get("rank") or 0))
    removed = []
    for asin, d in dec.items():
        if d.get("decision") == "remove":
            it = titles.get(asin, {})
            pj = read_json(os.path.join(work, "removed", asin, "product.json"), {})
            removed.append({"asin": asin, "rank": it.get("rank"), "title": it.get("title") or pj.get("title"),
                            "round": d.get("round"), "reason": d.get("reason"), "url": it.get("url")})
    removed.sort(key=lambda r: r["rank"] or 0)
    plan = read_json(os.path.join(work, "plan.json"))
    return job, products, removed, plan, flt.get("standard")


def analysis_text(p):
    if p.get("status") == "failed":
        return "【抓取失败】" + "；".join(p.get("errors") or ["原因未知"])
    a = p.get("analysis")
    if not a:
        return ""
    lines = []
    for im in a.get("images", []):
        lines.append(f"{im.get('position', '')}｜{im.get('type', '')}：{im.get('message', '')}")
    return "\n".join(lines)


def find_image(products, asin, position):
    """position: 主图 | 副图N | A+图N"""
    p = next((x for x in products if x["asin"] == asin), None)
    if not p or not position:
        return None
    if position == "主图":
        lst, idx = p["main_images"], 1
    elif position.startswith("副图"):
        lst, idx = p["main_images"], int(re.sub(r"\D", "", position) or 0) + 1
    elif position.upper().startswith("A+"):
        lst, idx = p["aplus_images"], int(re.sub(r"\D", "", position[2:]) or 0)
    else:
        return None
    return next((m for m in lst if m["index"] == idx and m.get("thumb")), None)


# ------------------------------------------------------------------ layout

def col_px(width_chars):
    return int(width_chars * 7 + 5)


def row_px(height_pt):
    return height_pt * 96 / 72


def row_height(base, texts):
    """base height, raised so every wrapped (text, column width) pair shows in full."""
    need = max([base] + [text_height_pt(t, w) for t, w in texts])
    return min(ROW_MAX_PT, round(need, 1))


def fit(w, h, box_w, box_h, pad=6):
    s = min((box_w - pad) / w, (box_h - pad) / h)
    return max(1, int(w * s)), max(1, int(h * s))


def build_layout(job, products, removed, plan):
    """Returns sheets: list of dicts {name, cols:[(width)], rows:[{height, cells:{col: cell}}]}.
    cell = {"text": str} | {"url": str} | {"image": thumb_path, "w": int, "h": int} | {"header": str}"""
    max_sub = max([max([m["index"] for m in p["main_images"]] + [1]) - 1 for p in products] + [1])
    max_aplus = max([len(p["aplus_images"]) for p in products] + [1])
    sheets = []

    # 1. main gallery
    heads = ["ASIN", "排名", "品牌", "主图"] + [f"副图{i}" for i in range(1, max_sub + 1)] + ["图片分析", "商品页"]
    texts = {p["asin"]: analysis_text(p) for p in products}
    ana_w = 62  # widen the analysis column only when the longest text would not fit the row height limit
    while ana_w < 120 and any(text_height_pt(t, ana_w) > ROW_MAX_PT for t in texts.values()):
        ana_w += 4
    widths = [16, 8, 22, IMG_COL_W] + [IMG_COL_W] * max_sub + [ana_w, 42]
    rows = [{"height": HEADER_H, "cells": {i: {"header": h} for i, h in enumerate(heads)}}]
    for p in products:
        cells = {0: {"text": p["asin"]}, 1: {"text": p.get("rank") if p.get("rank") is not None else ""},
                 2: {"text": p.get("brand") or "未识别品牌"}}
        for m in p["main_images"]:
            if m.get("thumb"):
                cells[3 + m["index"] - 1] = {"image": m["thumb"], "w": m["thumb_width"], "h": m["thumb_height"]}
        cells[4 + max_sub] = {"text": texts[p["asin"]], "wrap": True}
        cells[5 + max_sub] = {"url": p["url"]}
        rows.append({"height": row_height(IMG_ROW_H, [(texts[p["asin"]], ana_w)]), "cells": cells})
    sheets.append({"name": SHEET_MAIN, "cols": widths, "rows": rows, "freeze": (1, 3)})

    # 2. A+
    heads = ["ASIN", "排名", "品牌"] + [f"A+图{i}" for i in range(1, max_aplus + 1)] + ["商品页"]
    widths = [16, 8, 22] + [APLUS_COL_W] * max_aplus + [42]
    rows = [{"height": HEADER_H, "cells": {i: {"header": h} for i, h in enumerate(heads)}}]
    for p in products:
        cells = {0: {"text": p["asin"]}, 1: {"text": p.get("rank") if p.get("rank") is not None else ""},
                 2: {"text": p.get("brand") or "未识别品牌"}}
        if p.get("status") == "failed":
            cells[3] = {"text": "抓取失败"}
        elif not p["aplus_images"]:
            cells[3] = {"text": "无A+"}
        for m in p["aplus_images"]:
            if m.get("thumb"):
                cells[2 + m["index"]] = {"image": m["thumb"], "w": m["thumb_width"], "h": m["thumb_height"]}
        cells[3 + max_aplus] = {"url": p["url"]}
        rows.append({"height": IMG_ROW_H, "cells": cells})
    sheets.append({"name": SHEET_APLUS, "cols": widths, "rows": rows, "freeze": (1, 3)})

    # 3. visual plan
    heads = ["序号", "载体", "画面任务", "用户需求触发", "参考图", "参考链接"]
    widths = [8, 18, 40, 57, 24, 42]
    rows = [{"height": HEADER_H, "cells": {i: {"header": h} for i, h in enumerate(heads)}}]
    for i, r in enumerate((plan or {}).get("rows", []), 1):
        ref = r.get("ref") or {}
        img = find_image(products, ref.get("asin"), ref.get("position"))
        p = next((x for x in products if x["asin"] == ref.get("asin")), None)
        cells = {0: {"text": i}, 1: {"text": r.get("carrier", "")}, 2: {"text": r.get("task", ""), "wrap": True},
                 3: {"text": r.get("trigger", ""), "wrap": True}}
        if img:
            cells[4] = {"image": img["thumb"], "w": img["thumb_width"], "h": img["thumb_height"]}
        elif ref:
            cells[4] = {"text": f"参考图缺失：{ref.get('asin')} {ref.get('position')}"}
        if p:
            cells[5] = {"url": p["url"]}
        h = row_height(IMG_ROW_H, [(r.get("task", ""), widths[2]), (r.get("trigger", ""), widths[3])])
        rows.append({"height": h, "cells": cells})
    sheets.append({"name": SHEET_PLAN, "cols": widths, "rows": rows, "freeze": (1, 0)})

    # 4. removed
    heads = ["排名", "ASIN", "标题", "筛选轮次", "剔除原因", "商品页"]
    widths = [8, 16, 60, 20, 50, 42]
    rows = [{"height": HEADER_H, "cells": {i: {"header": h} for i, h in enumerate(heads)}}]
    for r in removed:
        rnd = {1: "第1轮（标题/形态）", 2: "第2轮（详情/材质）"}.get(r["round"], r["round"] or "")
        h = row_height(36, [(r["title"] or "", widths[2]), (r["reason"] or "", widths[4])])
        rows.append({"height": h, "cells": {0: {"text": r["rank"] or ""}, 1: {"text": r["asin"]},
                                             2: {"text": r["title"] or "", "wrap": True}, 3: {"text": rnd},
                                             4: {"text": r["reason"] or "", "wrap": True},
                                             5: {"url": r["url"] or ""}}})
    sheets.append({"name": SHEET_REMOVED, "cols": widths, "rows": rows, "freeze": (1, 0)})
    return sheets


# ------------------------------------------------------------------ writers

def write_workbook(path, sheets, mode):
    """mode 'excel': embed_image; mode 'wps': blank styled cells, patched afterwards.
    Returns the list of image placements [(sheet_index, cell_ref, cell_dict, box_w, box_h)]."""
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell
    wb = xlsxwriter.Workbook(path, {"strings_to_urls": False})
    base = {"font_name": FONT, "font_size": 10, "valign": "top", "border": 1, "border_color": "#D0D7DE"}
    f_head = wb.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": HEADER_COLOR,
                            "align": "center", "valign": "vcenter", "text_wrap": True})
    f_text = wb.add_format({**base, "valign": "vcenter", "align": "center"})
    f_wrap = wb.add_format({**base, "text_wrap": True})
    f_link = wb.add_format({**base, "valign": "vcenter", "font_color": "#0563C1", "underline": 1})
    f_img = wb.add_format({**base, "align": "center", "valign": "vcenter"})
    placements = []
    for si, sh in enumerate(sheets):
        ws = wb.add_worksheet(sh["name"])
        ws.hide_gridlines(2)
        for c, w in enumerate(sh["cols"]):
            ws.set_column(c, c, w)
        for r, row in enumerate(sh["rows"]):
            ws.set_row(r, row["height"])
            for c, cell in row["cells"].items():
                if "header" in cell:
                    ws.write_string(r, c, cell["header"], f_head)
                elif "url" in cell:
                    if cell["url"]:
                        ws.write_url(r, c, cell["url"], f_link, string=cell["url"])
                elif "image" in cell:
                    box = (col_px(sh["cols"][c]), row_px(row["height"]))
                    if mode == "excel":
                        ws.embed_image(r, c, cell["image"], {"cell_format": f_img})
                    else:
                        ws.write_blank(r, c, None, f_img)
                    placements.append((si, xl_rowcol_to_cell(r, c), cell, box))
                else:
                    v = cell["text"]
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        ws.write_number(r, c, v, f_text)
                    else:
                        ws.write_string(r, c, str(v), f_wrap if cell.get("wrap") else f_text)
        if sh.get("freeze"):
            ws.freeze_panes(*sh["freeze"])
    wb.close()
    return placements


def patch_wps(path, placements):
    """Turn the blank image cells into WPS DISPIMG cell images."""
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    media, entries, rels = {}, [], []
    cell_ids = {}
    for si, ref, cell, (bw, bh) in placements:
        img = os.path.abspath(cell["image"])
        if img not in media:
            n = len(media) + 1
            pic_id = "ID_" + hashlib.md5(img.encode("utf-8")).hexdigest().upper()
            media[img] = (n, pic_id)
            files[f"xl/media/cellimage{n}.jpeg"] = open(img, "rb").read()
            w, h = fit(cell["w"], cell["h"], bw, bh)
            rels.append(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/image" Target="media/cellimage{n}.jpeg"/>')
            entries.append(
                f'<etc:cellImage><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{n + 1}" name="{pic_id}"/>'
                f'<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
                f'<xdr:blipFill><a:blip r:embed="rId{n}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
                f'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{w * 9525}" cy="{h * 9525}"/></a:xfrm>'
                f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic></etc:cellImage>')
        cell_ids[(si, ref)] = media[img][1]
    files["xl/cellimages.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<etc:cellImages xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:etc="http://www.wps.cn/officeDocument/2017/etCustomData">' + "".join(entries) +
        "</etc:cellImages>").encode("utf-8")
    files["xl/_rels/cellimages.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        "".join(rels) + "</Relationships>").encode("utf-8")
    wr = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    wr = wr.replace("</Relationships>", '<Relationship Id="rIdCellImg1" Type="http://www.wps.cn/officeDocument/'
                                        '2020/cellImage" Target="cellimages.xml"/></Relationships>')
    files["xl/_rels/workbook.xml.rels"] = wr.encode("utf-8")
    ct = files["[Content_Types].xml"].decode("utf-8")
    if 'Extension="jpeg"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="jpeg" ContentType="image/jpeg"/><Default ', 1)
    ct = ct.replace("</Types>", '<Override PartName="/xl/cellimages.xml" '
                                'ContentType="application/vnd.wps-officedocument.cellimage+xml"/></Types>')
    files["[Content_Types].xml"] = ct.encode("utf-8")
    for (si, ref), pic_id in cell_ids.items():
        name = f"xl/worksheets/sheet{si + 1}.xml"
        xml = files[name].decode("utf-8")
        q = escape(f'"{pic_id}"', {'"': "&quot;"})
        new, n = re.subn(rf'<c r="{ref}"( s="\d+")?\s*/>',
                         lambda m: f'<c r="{ref}"{m.group(1) or ""} t="str"><f>_xlfn.DISPIMG({q},1)</f>'
                                   f'<v>=DISPIMG({q},1)</v></c>', xml, count=1)
        if n != 1:
            raise RuntimeError(f"image cell {ref} not found in {name}")
        files[name] = new.encode("utf-8")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        ct_first = ["[Content_Types].xml"] + [n for n in files if n != "[Content_Types].xml"]
        for n in ct_first:
            z.writestr(n, files[n])
    os.replace(tmp, path)


def safe_target(path):
    """If the file is open in WPS/Excel (locked), write next to it with a suffix."""
    if not os.path.exists(path):
        return path
    try:
        with open(path, "ab"):
            return path
    except PermissionError:
        root, ext = os.path.splitext(path)
        i = 2
        while os.path.exists(f"{root}-v{i}{ext}"):
            i += 1
        return f"{root}-v{i}{ext}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--format", default="both", choices=["both", "wps", "excel"])
    a = ap.parse_args()
    job, products, removed, plan, _ = load(a.work)
    if not products:
        sys.exit("no products in work dir; run scrape_product.py first")
    sheets = build_layout(job, products, removed, plan)
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", job["product_name"])
    os.makedirs(job["output_dir"], exist_ok=True)
    base = os.path.join(job["output_dir"], f"{safe_name}-竞品图片分析")
    written = []
    for mode in (["wps", "excel"] if a.format == "both" else [a.format]):
        path = safe_target(f"{base}-{'WPS' if mode == 'wps' else 'Excel'}.xlsx")
        tmp = path + ".build.xlsx"
        placements = write_workbook(tmp, sheets, mode)
        if mode == "wps":
            patch_wps(tmp, placements)
        os.replace(tmp, path)
        written.append({"format": mode, "file": path, "images": len(placements),
                        "size_mb": round(os.path.getsize(path) / 1048576, 1)})
    out({"files": written, "products": len(products), "removed": len(removed),
         "with_analysis": sum(1 for p in products if p.get("analysis")),
         "plan_rows": len((plan or {}).get("rows", []))})


if __name__ == "__main__":
    main()
