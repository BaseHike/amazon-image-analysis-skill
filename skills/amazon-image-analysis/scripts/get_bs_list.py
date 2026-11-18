"""Seed ASIN -> its Best Sellers category -> top N items. Writes <work>/bs_list.json.

Usage:
  python -X utf8 get_bs_list.py --work DIR                      # auto: seed page -> category -> list
  python -X utf8 get_bs_list.py --work DIR --category hpc/3774411  # after the user picked a category
  python -X utf8 get_bs_list.py --work DIR --from-json FILE       # browser fallback result

Exit codes: 0 ok | 2 need_choice (several / no leaf categories, ask the user) | 1 failed (switch tool)
"""
import argparse
import html as htmlmod
import json
import math
import os
import re
import sys

from amz_common import (Blocked, dp_url, fetch_html, make_session, out, parse_product,
                        read_json, site_info, write_json)


def parse_bs_page(html):
    from bs4 import BeautifulSoup
    items = {}
    m = re.search(r'data-client-recs-list="([^"]+)"', html)
    if m:
        for it in json.loads(htmlmod.unescape(m.group(1))):
            rank = it.get("metadataMap", {}).get("render.zg.rank")
            if it.get("id") and rank:
                items[it["id"]] = {"rank": int(rank), "asin": it["id"], "title": None}
    soup = BeautifulSoup(html, "html.parser")
    for g in soup.select("#gridItemRoot, div.zg-grid-general-faceout"):
        holder = g.select_one("[data-asin]") or g.select_one("div.p13n-sc-uncoverable-faceout")
        asin = holder.get("data-asin") or holder.get("id") if holder else None
        if not asin:
            continue
        tdiv = g.select_one("div[class*='line-clamp']")
        img = g.find("img")
        title = (tdiv.get_text(" ", strip=True) if tdiv else None) or (img.get("alt") if img else None)
        badge = g.select_one(".zg-bdg-text")
        rank = int(re.sub(r"\D", "", badge.get_text())) if badge else None
        it = items.setdefault(asin, {"rank": rank, "asin": asin, "title": None})
        it["title"] = it["title"] or title
        if it["rank"] is None:
            it["rank"] = rank
    name = None
    heads = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"])]
    pat = r"^(Best Sellers in|Bestseller in|Meilleures ventes en|Più venduti in|Más vendidos en|売れ筋ランキング[:：]?)\s*"
    for h in heads:
        if re.match(pat, h):
            name = re.sub(pat, "", h)
            break
    return [i for i in items.values() if i["rank"]], name


def finish(work, job, category, seed, items, method):
    domain = site_info(job["site"])[0]
    items = sorted({i["asin"]: i for i in items}.values(), key=lambda x: x["rank"])
    items = [i for i in items if i["rank"] <= job["top_n"]]
    for i in items:
        i["url"] = f"https://{domain}/dp/{i['asin']}"
    res = {
        "status": "ok",
        "method": method,
        "site": job["site"],
        "category": category,
        "seed": seed,
        "top_n": job["top_n"],
        "count": len(items),
        "missing_title": [i["asin"] for i in items if not i.get("title")],
        "items": items,
    }
    write_json(os.path.join(work, "bs_list.json"), res)
    summary = {k: v for k, v in res.items() if k != "items"}
    summary["first_items"] = items[:5]
    out(summary)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--category", help="category path chosen by the user, e.g. hpc/3774411")
    ap.add_argument("--from-json", help="JSON extracted with a browser (fallback)")
    a = ap.parse_args()
    job = read_json(os.path.join(a.work, "job.json"))
    if not job:
        sys.exit("job.json not found, run init_job.py first")
    domain = site_info(job["site"])[0]
    seed = read_json(os.path.join(a.work, "seed.json"))

    if a.from_json:
        data = read_json(a.from_json)
        cat = data.get("category") or {}
        items = [{"rank": int(i["rank"]), "asin": i["asin"], "title": i.get("title")}
                 for i in data.get("items", []) if i.get("asin") and i.get("rank")]
        if not items:
            out({"status": "failed", "reason": "no items in browser JSON"})
            sys.exit(1)
        finish(a.work, job, cat, seed, items, data.get("method", "browser"))
        return

    s = make_session(job["site"])
    try:
        # 1. seed page -> categories
        if job.get("seed_asin") and (seed is None or (not seed.get("categories") and not a.category)):
            p = parse_product(fetch_html(s, dp_url(job["site"], job["seed_asin"])))
            seed = {"asin": job["seed_asin"], "title": p["title"], "brand": p["brand"],
                    "product_type": p["product_type"],
                    "attributes": p["attributes"], "categories": p["bsr_categories"],
                    "main_images": p["main_images"][:1]}
            write_json(os.path.join(a.work, "seed.json"), seed)

        # 2. pick the category
        if job.get("bs_url"):
            base = job["bs_url"].split("?")[0]
            path = re.sub(r"^.*?/gp/bestsellers/", "", base).split("/ref=")[0].strip("/")
            category = {"name": None, "path": path, "url": base}
        else:
            if a.category:
                path = a.category.strip("/")
            else:
                leaves = [c for c in seed["categories"] if not c["is_root"]]
                if not seed["categories"]:
                    # parsing found no Best Sellers Rank at all: a tool problem, not a user choice
                    out({"status": "failed", "reason": "no Best Sellers Rank found on the seed page",
                         "seed_title": seed["title"]})
                    sys.exit(1)
                if len(leaves) != 1:
                    out({"status": "need_choice",
                         "reason": "several leaf categories" if leaves else "no leaf category found",
                         "seed_title": seed["title"], "categories": seed["categories"]})
                    sys.exit(2)
                path = leaves[0]["path"]
            name = next((c["name"] for c in seed["categories"] if c["path"] == path), None)
            category = {"name": name, "path": path,
                        "url": f"https://{domain}/gp/bestsellers/{path}"}

        # 3. list pages (50 items per page)
        items = []
        for pg in range(1, math.ceil(job["top_n"] / 50) + 1):
            got, h1 = parse_bs_page(fetch_html(s, f"{category['url']}?pg={pg}"))
            if not got:
                raise RuntimeError(f"no items parsed on page {pg}")
            items += got
            category["name"] = category["name"] or h1
    except (Blocked, Exception) as e:
        out({"status": "failed", "reason": f"{type(e).__name__}: {e}"})
        sys.exit(1)
    finish(a.work, job, category, seed, items, "script")


if __name__ == "__main__":
    main()
