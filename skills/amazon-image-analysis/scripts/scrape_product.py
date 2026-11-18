"""Scrape product pages and download gallery + A+ images. Writes <work>/products/<ASIN>/product.json.

Usage:
  python -X utf8 scrape_product.py --work DIR --asins B0A,B0B,B0C          # script mode (ranks from bs_list.json)
  python -X utf8 scrape_product.py --work DIR --asins B0A --from-json F --method builtin-browser|chrome

Exit codes: 0 all ok | 1 at least one ASIN failed or partial (see "results")
"""
import argparse
import os
import random
import sys
import time
from urllib.parse import urlparse

from amz_common import (Blocked, dp_url, fetch_bytes, fetch_html, image_sig, make_session, out,
                        parse_product, read_json, save_image, write_json)


def ext_of(url):
    e = os.path.splitext(urlparse(url).path)[1].lower()
    return e if e in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"


def download_all(session, pdir, kind, urls, errors):
    res = []
    for i, u in enumerate(urls, 1):
        name = f"{kind}_{i:02d}"
        orig = os.path.join(pdir, "images", name + ext_of(u))
        thumb = os.path.join(pdir, "thumbs", name + ".jpg")
        os.makedirs(os.path.dirname(thumb), exist_ok=True)
        try:
            w, h, tw, th = save_image(fetch_bytes(session, u), orig, thumb)
            res.append({"index": i, "url": u, "file": orig, "thumb": thumb,
                        "width": w, "height": h, "thumb_width": tw, "thumb_height": th})
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {e}")
            res.append({"index": i, "url": u, "file": None, "thumb": None, "error": str(e)})
        time.sleep(0.2)
    return res


def scrape_one(session, work, job, asin, rank, data=None, method="script"):
    pdir = os.path.join(work, "products", asin)
    url = dp_url(job["site"], asin)
    rec = {"asin": asin, "rank": rank, "url": url, "method": method, "status": "failed",
           "title": None, "brand": None, "product_type": None, "attributes": {}, "main_images": [], "aplus_images": [],
           "errors": []}
    try:
        if data is None:
            data = parse_product(fetch_html(session, url))
        rec.update({"title": data.get("title"), "brand": data.get("brand"),
                    "product_type": data.get("product_type"),
                    "attributes": data.get("attributes") or {}})
        main_urls = data.get("main_images") or []
        if not main_urls:
            raise RuntimeError("no gallery images found on the page")
        rec["main_images"] = download_all(session, pdir, "main", main_urls, rec["errors"])
        rec["aplus_images"] = download_all(session, pdir, "aplus", data.get("aplus_images") or [], rec["errors"])
        bad = [m for m in rec["main_images"] + rec["aplus_images"] if not m.get("file")]
        rec["status"] = "partial" if bad else "ok"
    except Blocked:
        rec["errors"].append("captcha / robot check")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
    rec["sig"] = image_sig(rec)
    write_json(os.path.join(pdir, "product.json"), rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--asins", required=True, help="comma separated ASINs")
    ap.add_argument("--from-json", help="product JSON extracted with a browser (one ASIN)")
    ap.add_argument("--method", default="script", choices=["script", "builtin-browser", "chrome"])
    a = ap.parse_args()
    job = read_json(os.path.join(a.work, "job.json"))
    if not job:
        sys.exit("job.json not found, run init_job.py first")
    bs = read_json(os.path.join(a.work, "bs_list.json"), {"items": []})
    ranks = {i["asin"]: i["rank"] for i in bs["items"]}
    asins = [x.strip().upper() for x in a.asins.split(",") if x.strip()]
    if a.from_json and len(asins) != 1:
        sys.exit("--from-json takes exactly one ASIN")

    session = make_session(job["site"])
    results = []
    for n, asin in enumerate(asins):
        rank = ranks.get(asin)
        data = read_json(a.from_json) if a.from_json else None
        method = a.method if a.from_json else "script"
        r = scrape_one(session, a.work, job, asin, rank, data, method)
        results.append({"asin": asin, "rank": rank, "status": r["status"], "method": r["method"],
                        "title": r["title"], "brand": r["brand"], "product_type": r["product_type"],
                        "material": next((v for k, v in r["attributes"].items() if "aterial" in k or "素材" in k or "Materiale" in k), None),
                        "main_count": sum(1 for m in r["main_images"] if m.get("file")),
                        "aplus_count": sum(1 for m in r["aplus_images"] if m.get("file")),
                        "errors": r["errors"][:5]})
        if n < len(asins) - 1 and not a.from_json:
            time.sleep(2 + random.random() * 2)
    out({"results": results})
    sys.exit(0 if all(r["status"] == "ok" for r in results) else 1)


if __name__ == "__main__":
    main()
