"""Build one numbered contact sheet per product so the analyst can see every gallery image at once.

Usage:
  python -X utf8 contact_sheet.py --work DIR [--asins B0A,B0B]
Writes <work>/products/<ASIN>/sheet_1.jpg (sheet_2.jpg ... when more than 9 images).
Each tile is labelled with its position (主图 / 副图N) exactly as the analysis must use it.
Prints {"sheets": {"<ASIN>": [paths...]}}.
"""
import argparse
import os

from amz_common import out, read_json

PER_SHEET, COLS, TILE, LABEL_H = 9, 3, 420, 34


def font(size):
    from PIL import ImageFont
    for f in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
              "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def build(pdir, images):
    from PIL import Image, ImageDraw
    paths, f = [], font(22)
    for s in range(0, len(images), PER_SHEET):
        batch = images[s:s + PER_SHEET]
        rows = (len(batch) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * TILE, rows * (TILE + LABEL_H)), "white")
        d = ImageDraw.Draw(sheet)
        for k, m in enumerate(batch):
            x, y = (k % COLS) * TILE, (k // COLS) * (TILE + LABEL_H)
            pos = "主图" if m["index"] == 1 else f"副图{m['index'] - 1}"
            d.rectangle([x, y, x + TILE - 1, y + LABEL_H - 1], fill="#0F766E")
            d.text((x + 10, y + 4), pos, fill="white", font=f)
            with Image.open(m["thumb"]) as im:
                im = im.convert("RGB")
                im.thumbnail((TILE - 8, TILE - 8))
                sheet.paste(im, (x + (TILE - im.width) // 2, y + LABEL_H + (TILE - im.height) // 2))
            d.rectangle([x, y, x + TILE - 1, y + LABEL_H + TILE - 1], outline="#CCCCCC")
        p = os.path.join(pdir, f"sheet_{s // PER_SHEET + 1}.jpg")
        sheet.save(p, "JPEG", quality=88)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--asins", help="comma separated; default: every scraped product")
    a = ap.parse_args()
    root = os.path.join(a.work, "products")
    asins = a.asins.split(",") if a.asins else sorted(os.listdir(root))
    res = {}
    for asin in asins:
        p = read_json(os.path.join(root, asin, "product.json"))
        if not p:
            continue
        imgs = sorted([m for m in p["main_images"] if m.get("thumb")], key=lambda m: m["index"])
        if imgs:
            res[asin] = build(os.path.join(root, asin), imgs)
    out({"sheets": res})


if __name__ == "__main__":
    main()
