"""Check the output workbooks against the scraped data. Every issue names the step that caused it.

Usage:
  python -X utf8 check_excel.py --work DIR [--stage table|analysis|final]
    table    : after step 3 (rows, images, ratios, A+, removed sheet)
    analysis : after step 4 (+ the 图片分析 column)
    final    : after step 5 (+ the 新品视觉方案 sheet)   [default]

Exit codes: 0 no errors | 1 errors found (see "issues")
"""
import argparse
import collections
import glob
import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

from amz_common import ROW_MAX_PT, image_sig, ocr_images, out, read_json, text_height_pt, text_matches

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
      "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "etc": "http://www.wps.cn/officeDocument/2017/etCustomData",
      "rv": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata",
      "rvr": "http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel",
      "xlrd": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"}
RID = "{%s}id" % NS["r"]
EMBED = "{%s}embed" % NS["r"]
SHEETS = ["图片分类总表", "A+图片总表", "新品视觉方案", "剔除记录"]
STEP_NAMES = {1: "第1步 榜单/第1轮筛选", 2: "第2步 抓取/第2轮筛选", 3: "第3步 制表",
              4: "第4步 图片分析", 5: "第5步 视觉方案"}


def rels_of(z, part):
    d, f = os.path.split(part)
    p = f"{d}/_rels/{f}.rels"
    if p not in z.namelist():
        return {}
    root = ET.fromstring(z.read(p))
    res = {}
    for r in root.findall("pr:Relationship", NS):
        t = r.get("Target")
        res[r.get("Id")] = t.lstrip("/") if t.startswith("/") else os.path.normpath(f"{d}/{t}").replace("\\", "/")
    return res


def media_size(z, name):
    from PIL import Image
    with Image.open(io.BytesIO(z.read(name))) as im:
        return im.size


def sheet_parts(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = rels_of(z, "xl/workbook.xml")
    return {s.get("name"): rels[s.get(RID)] for s in wb.find("m:sheets", NS)}


def col_row(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    c = 0
    for ch in m.group(1):
        c = c * 26 + ord(ch) - 64
    return c - 1, int(m.group(2)) - 1


def read_cells(z, part):
    """{(row, col): {"text":..., "img": (media_name) or None, "wps_id":..., "vm":...}}"""
    sst = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            sst.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    cells = {}
    root = ET.fromstring(z.read(part))
    for c in root.iter("{%s}c" % NS["m"]):
        col, row = col_row(c.get("r"))
        f, v, is_ = c.find("m:f", NS), c.find("m:v", NS), c.find("m:is", NS)
        rec = {"text": "", "formula": f.text if f is not None else None, "vm": c.get("vm")}
        if c.get("t") == "s" and v is not None:
            rec["text"] = sst[int(v.text)]
        elif is_ is not None:
            rec["text"] = "".join(t.text or "" for t in is_.iter("{%s}t" % NS["m"]))
        elif v is not None and c.get("t") != "e":
            rec["text"] = v.text or ""
        cells[(row, col)] = rec
    return cells


def wps_images(z):
    """name -> (media part, ext ratio)"""
    if "xl/cellimages.xml" not in z.namelist():
        return {}
    rels = rels_of(z, "xl/cellimages.xml")
    res = {}
    for pic in ET.fromstring(z.read("xl/cellimages.xml")).iter("{%s}pic" % NS["xdr"]):
        name = pic.find("xdr:nvPicPr/xdr:cNvPr", NS).get("name")
        blip = pic.find("xdr:blipFill/a:blip", NS)
        ext = pic.find("xdr:spPr/a:xfrm/a:ext", NS)
        ratio = int(ext.get("cx")) / int(ext.get("cy")) if ext is not None else None
        res[name] = (rels.get(blip.get(EMBED)), ratio)
    return res


def excel_images(z):
    """vm (1-based str) -> media part"""
    names = z.namelist()
    if "xl/metadata.xml" not in names:
        return {}
    md = ET.fromstring(z.read("xl/metadata.xml"))
    fut = [bk.find(".//xlrd:rvb", NS).get("i") for bk in md.find("m:futureMetadata", NS).findall("m:bk", NS)]
    vmeta = [bk.find("m:rc", NS).get("v") for bk in md.find("m:valueMetadata", NS).findall("m:bk", NS)]
    rv = [[v.text for v in r.findall("rv:v", NS)] for r in
          ET.fromstring(z.read("xl/richData/rdrichvalue.xml")).findall("rv:rv", NS)]
    rel_ids = [r.get(RID) for r in ET.fromstring(z.read("xl/richData/richValueRel.xml")).findall("rvr:rel", NS)]
    rels = rels_of(z, "xl/richData/richValueRel.xml")
    res = {}
    for i, v in enumerate(vmeta, 1):
        rich = rv[int(fut[int(v)])]
        res[str(i)] = rels.get(rel_ids[int(rich[0])])
    return res


def sheet_geometry(z, part):
    """({row: height_pt}, {col: width_chars}) as stored in the sheet XML."""
    root = ET.fromstring(z.read(part))
    heights = {int(r.get("r")) - 1: float(r.get("ht")) for r in root.iter("{%s}row" % NS["m"]) if r.get("ht")}
    widths = {}
    for c in root.iter("{%s}col" % NS["m"]):
        for i in range(int(c.get("min")) - 1, int(c.get("max"))):
            widths[i] = float(c.get("width", 8.43))
    return heights, widths


def load_workbook_view(path):
    """Returns (view, geo): view[sheet] = cells, geo[sheet] = (row heights, col widths)."""
    z = zipfile.ZipFile(path)
    parts = sheet_parts(z)
    wimg, ximg = wps_images(z), excel_images(z)
    view, geo = {}, {}
    for name, part in parts.items():
        geo[name] = sheet_geometry(z, part)
        cells = read_cells(z, part)
        for rc, cell in cells.items():
            media, ext_ratio = None, None
            if cell["formula"] and "DISPIMG" in cell["formula"]:
                m = re.search(r'DISPIMG\("([^"]+)"', cell["formula"])
                media, ext_ratio = wimg.get(m.group(1), (None, None)) if m else (None, None)
                cell["img_missing"] = media is None
            elif cell["vm"]:
                media = ximg.get(cell["vm"])
                cell["img_missing"] = media is None
            if media:
                w, h = media_size(z, media)
                cell["img"] = {"media": media, "ratio": w / h, "ext_ratio": ext_ratio}
        view[name] = cells
    return view, geo


def header_map(cells):
    return {cell["text"]: col for (r, col), cell in cells.items() if r == 0 and cell["text"]}


def rows_by_asin(cells, col):
    return {cell["text"]: r for (r, c), cell in cells.items() if c == col and r > 0 and cell["text"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--stage", default="final", choices=["table", "analysis", "final"])
    a = ap.parse_args()
    stage = {"table": 3, "analysis": 4, "final": 5}[a.stage]
    job = read_json(os.path.join(a.work, "job.json"))
    bs = read_json(os.path.join(a.work, "bs_list.json"), {"items": []})
    flt = read_json(os.path.join(a.work, "filter.json"), {"decisions": []})
    plan = read_json(os.path.join(a.work, "plan.json"))
    issues = []

    def issue(step, check, detail, level="error"):
        issues.append({"step": step, "step_name": STEP_NAMES[step], "level": level, "check": check, "detail": detail})

    # ---- data-level checks
    dec = {d["asin"]: d for d in flt.get("decisions", [])}
    if not flt.get("round2_applied"):
        issue(2, "筛选未完成", "filter.json 没有通过 apply_filter.py --round 2")
    undecided = [i["asin"] for i in bs["items"] if dec.get(i["asin"], {}).get("decision") not in ("keep", "remove")]
    if undecided:
        issue(1, "榜单商品没有筛选结论", ", ".join(undecided))
    if bs.get("count", 0) < min(job["top_n"], 1):
        issue(1, "榜单为空", "bs_list.json 没有商品")
    kept = [i["asin"] for i in bs["items"] if dec.get(i["asin"], {}).get("decision") == "keep"]
    removed = [i["asin"] for i in bs["items"] if dec.get(i["asin"], {}).get("decision") == "remove"]
    prods = {}
    for asin in kept:
        p = read_json(os.path.join(a.work, "products", asin, "product.json"))
        if not p:
            issue(2, "保留商品未抓取", asin)
            continue
        prods[asin] = p
        if p.get("sig") != image_sig(p):
            issue(2, "product.json 被手改", f"{asin}: 图片列表和抓取时不一致，只能用 scrape_product.py 重新抓取")
        if p["status"] == "failed":
            issue(2, "抓取失败", f"{asin}: {'; '.join(p.get('errors') or [])}（三种工具都试过才能保留为失败）")
        elif p["status"] == "partial":
            bad = [m.get("url") for m in p["main_images"] + p["aplus_images"] if not m.get("file")]
            issue(2, "部分图片下载失败", f"{asin}: {len(bad)} 张，例如 {bad[:2]}")
        if p["status"] != "failed" and not p["main_images"]:
            issue(2, "没有主图", asin)

    # ---- file-level checks
    files = sorted(glob.glob(os.path.join(job["output_dir"], "*-竞品图片分析-*.xlsx")))
    fmt_seen = {"WPS": False, "Excel": False}
    for path in files:
        for k in fmt_seen:
            if path.endswith(f"-{k}.xlsx") or re.search(rf"-{k}-v\d+\.xlsx$", path):
                fmt_seen[k] = True
    for k, seen in fmt_seen.items():
        if not seen:
            issue(3, "缺少输出文件", f"没有 {k} 版文件")
    analysis_texts = collections.defaultdict(set)
    for path in files:
        fname = os.path.basename(path)
        try:
            view, geo = load_workbook_view(path)
        except Exception as e:
            issue(3, "文件无法解析", f"{fname}: {type(e).__name__}: {e}")
            continue
        for s in SHEETS:
            if s not in view:
                issue(3, "缺少工作表", f"{fname}: {s}")
        if any(s not in view for s in SHEETS):
            continue
        main, aplus, plan_sh, rem = (view[s] for s in SHEETS)
        # wrapped text must show in full (row tall enough for its column width)
        for s, heads in ((SHEETS[0], ("图片分析",)), (SHEETS[2], ("画面任务", "用户需求触发")),
                         (SHEETS[3], ("标题", "剔除原因"))):
            heights, widths = geo[s]
            hm_s = header_map(view[s])
            for h in heads:
                col = hm_s.get(h)
                if col is None:
                    continue
                for (r, c), cell in view[s].items():
                    if r == 0 or c != col or not cell["text"]:
                        continue
                    need = min(ROW_MAX_PT, text_height_pt(cell["text"], widths.get(col, 8.43)))
                    have = heights.get(r, 15)
                    if need > have + 2:
                        issue(3, "文字被截断", f"{fname} {s} 第{r + 1}行 {h}: 行高 {have:.0f} / 需要 {need:.0f}")
        # main sheet
        hm = header_map(main)
        rows = rows_by_asin(main, hm.get("ASIN", 0))
        for asin in removed:
            if asin in rows:
                issue(2, "已剔除的商品出现在表里", f"{fname} {SHEETS[0]}: {asin}")
        for asin, p in prods.items():
            if asin not in rows:
                issue(3, "保留商品没有出现在表里", f"{fname} {SHEETS[0]}: {asin}")
                continue
            r = rows[asin]
            for m in p["main_images"]:
                pos = "主图" if m["index"] == 1 else f"副图{m['index'] - 1}"
                col = hm.get(pos)
                cell = main.get((r, col), {}) if col is not None else {}
                where = f"{fname} {SHEETS[0]} {asin} {pos}"
                if not m.get("file"):
                    continue  # reported as step 2 above
                if not cell.get("img"):
                    issue(3, "图片没有嵌入单元格", where)
                    continue
                src = m["width"] / m["height"]
                if abs(cell["img"]["ratio"] / src - 1) > 0.015:
                    issue(3, "图片比例被改变", f"{where}: 原图 {src:.3f} / 表内 {cell['img']['ratio']:.3f}")
                er = cell["img"].get("ext_ratio")
                if er and abs(er / src - 1) > 0.03:
                    issue(3, "显示框比例被改变", f"{where}: 原图 {src:.3f} / 显示 {er:.3f}")
            if stage >= 4 and p["status"] != "failed":
                col = hm.get("图片分析")
                txt = main.get((r, col), {}).get("text", "") if col is not None else ""
                lines = [x for x in txt.split("\n") if x.strip()]
                n_img = sum(1 for m in p["main_images"] if m.get("file"))
                if not lines:
                    issue(4, "图片分析为空", f"{fname} {asin}")
                elif len(lines) != n_img:
                    issue(4, "分析条数和图片数不一致", f"{fname} {asin}: {len(lines)} 条 / {n_img} 张")
                else:
                    for i, ln in enumerate(lines):
                        exp = "主图｜" if i == 0 else f"副图{i}｜"
                        if not ln.startswith(exp):
                            issue(4, "分析顺序或格式不对", f"{fname} {asin} 第{i + 1}行应以“{exp}”开头")
                            break
                    for ln in lines:
                        analysis_texts[ln.split("：", 1)[-1].strip()].add(asin)
        # A+ sheet
        hm2 = header_map(aplus)
        rows2 = rows_by_asin(aplus, hm2.get("ASIN", 0))
        for asin, p in prods.items():
            if asin not in rows2:
                issue(3, "A+表缺少商品", f"{fname}: {asin}")
                continue
            got = sum(1 for (r, c), cell in aplus.items() if r == rows2[asin] and cell.get("img"))
            exp = sum(1 for m in p["aplus_images"] if m.get("file"))
            if got != exp:
                issue(3, "A+图片数量不对", f"{fname} {asin}: 表内 {got} / 应有 {exp}")
        # removed sheet
        rem_asins = {cell["text"] for (r, c), cell in rem.items() if r > 0 and c == header_map(rem).get("ASIN", 1)}
        if set(removed) != rem_asins:
            issue(3, "剔除记录与筛选结果不一致", f"{fname}: 缺 {sorted(set(removed) - rem_asins)} 多 {sorted(rem_asins - set(removed))}")
        # plan sheet
        if stage >= 5:
            hm3 = header_map(plan_sh)
            prow = sorted({r for (r, c) in plan_sh if r > 0})
            if len(prow) < 5:
                issue(5, "方案行数太少", f"{fname}: {len(prow)} 行（主图+副图至少 5 行）")
            for r in prow:
                for h in ("载体", "画面任务", "用户需求触发"):
                    if not plan_sh.get((r, hm3.get(h)), {}).get("text", "").strip():
                        issue(5, "方案字段为空", f"{fname} 第{r + 1}行 {h}")
                if not plan_sh.get((r, hm3.get("参考图")), {}).get("img"):
                    issue(5, "方案缺少参考图", f"{fname} 第{r + 1}行")
                if not plan_sh.get((r, hm3.get("参考链接")), {}).get("text"):
                    issue(5, "方案缺少参考链接", f"{fname} 第{r + 1}行")

    if stage >= 4:
        # every analysed image must quote words that really are on the image (catches made-up analysis)
        pairs = []
        for asin, p in prods.items():
            an = read_json(os.path.join(a.work, "analysis", f"{asin}.json"))
            if p["status"] == "failed" or not an:
                continue
            imgs = sorted([m for m in p["main_images"] if m.get("thumb")], key=lambda m: m["index"])
            for m, im in zip(imgs, an.get("images", [])):
                if "text" not in im:
                    issue(4, "分析缺少图上文字", f"{asin} {im.get('position')}: 没有 text 字段")
                else:
                    # OCR reads the full-size file far better than the thumbnail (Windows OCR limit: 2600 px)
                    big = m.get("file") and max(m.get("width") or 0, m.get("height") or 0) <= 2600
                    pairs.append((asin, im, m["file"] if big else m["thumb"]))
        if pairs:
            ocr = ocr_images([t for _, _, t in pairs], os.path.join(a.work, "ocr_cache.json"))
            if ocr is None:
                issue(4, "无法核对图上文字", "本机没有可用的文字识别，分析是否看过图没有核对", "warn")
            else:
                for asin, im, thumb in pairs:
                    got = ocr.get(thumb)
                    if got is None or len(re.sub(r"\W", "", got)) < 8:
                        continue  # OCR could not read this image: nothing to verify against
                    claimed = (im.get("text") or "").strip()
                    if not claimed and len(re.sub(r"\W", "", got)) >= 40:
                        issue(4, "分析与图片不符", f"{asin} {im.get('position')}: 图上有大量文字，text 却写了空")
                        continue
                    ok, found, n = text_matches(claimed, got)
                    if n == 0 and len(re.sub(r"\W", "", got)) >= 40:
                        issue(4, "分析与图片不符", f"{asin} {im.get('position')}: 图上文字很多，text 只写了“{claimed}”，"
                                                 f"要照抄 2～6 个完整的词")
                    elif not ok:
                        issue(4, "分析与图片不符",
                              f"{asin} {im.get('position')}: 写的图上文字“{claimed[:40]}”只核对到 {found}/{n} 个词")
        dup ={t: s for t, s in analysis_texts.items() if len(s) >= 3 and len(t) > 8}
        if dup:
            t, s = next(iter(dup.items()))
            issue(4, "分析像套模板", f"{len(dup)} 条文字在 3 个以上商品里完全相同，例如“{t[:40]}”出现在 {sorted(s)[:4]}")
    if stage >= 5:
        if not plan or not plan.get("rows"):
            issue(5, "没有 plan.json", "第5步还没写方案")
        else:
            for i, r in enumerate(plan["rows"]):
                exp = r"^主图$" if i == 0 else rf"^副图{i}｜\S.{{0,7}}$"
                if not re.match(exp, r.get("carrier", "")):
                    want = "主图" if i == 0 else f"副图{i}｜主题"
                    issue(5, "载体命名不对", f"plan.json 第{i + 1}行“{r.get('carrier', '')}”应为“{want}”")
            text = " ".join(f"{r.get('task', '')} {r.get('trigger', '')}" for r in plan["rows"])
            miss = [pt for pt in job["selling_points"] if pt and pt not in text]
            if len(miss) == len(job["selling_points"]):
                issue(5, "方案没有体现新品卖点", f"卖点 {job['selling_points']} 一个都没出现在画面任务/需求里", "warn")

    errors = [i for i in issues if i["level"] == "error"]
    res = {"ok": not errors, "stage": a.stage, "files": [os.path.basename(f) for f in files],
           "kept": len(kept), "removed": len(removed),
           "failed": sum(1 for p in prods.values() if p["status"] == "failed"),
           "errors_by_step": dict(collections.Counter(i["step"] for i in errors)),
           "issues": issues[:80], "issues_total": len(issues)}
    out(res)
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
