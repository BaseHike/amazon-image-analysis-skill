"""Validate the relevance decisions in <work>/filter.json and apply them.

Usage:
  python -X utf8 apply_filter.py --work DIR --round 1   # after title screening: prints the ASINs to scrape
  python -X utf8 apply_filter.py --work DIR --round 2   # after material screening: moves removed products away

filter.json (written by the main agent):
  {"standard": {"form": "...", "material": "..." | null, "basis": "..."},
   "decisions": [{"asin": "...", "decision": "keep|remove|pending|ask", "round": 1|2, "reason": "..."}]}

Exit codes: 0 ok | 1 problems listed in "problems" (fix filter.json and run again)
"""
import argparse
import os
import shutil
import sys

from amz_common import out, read_json, write_json

VALID = {1: {"keep", "remove", "pending", "ask"}, 2: {"keep", "remove", "ask"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--round", type=int, choices=[1, 2], required=True)
    a = ap.parse_args()
    bs = read_json(os.path.join(a.work, "bs_list.json"))
    flt = read_json(os.path.join(a.work, "filter.json"))
    if not bs or not flt:
        sys.exit("bs_list.json or filter.json missing")
    problems = []
    std = flt.get("standard") or {}
    if not std.get("form"):
        problems.append("standard.form is empty")
    dec = {}
    for d in flt.get("decisions", []):
        if d.get("asin") in dec:
            problems.append(f"{d.get('asin')}: duplicate decision")
        dec[d.get("asin")] = d
    items = {i["asin"]: i for i in bs["items"]}
    for asin, it in items.items():
        d = dec.get(asin)
        if not d:
            problems.append(f"{asin} (#{it['rank']}): no decision")
            continue
        if d.get("decision") not in VALID[a.round]:
            problems.append(f"{asin}: decision '{d.get('decision')}' not allowed in round {a.round}")
        if d.get("decision") == "remove" and not d.get("reason"):
            problems.append(f"{asin}: remove without reason")
        # a scrape failure is not a relevance decision: the item stays and shows as 【抓取失败】
        pj = read_json(os.path.join(a.work, "products", asin, "product.json")) or \
            read_json(os.path.join(a.work, "removed", asin, "product.json"))
        if a.round == 2 and d.get("decision") == "remove" and pj and pj.get("status") == "failed" \
                and d.get("round") == 2:
            problems.append(f"{asin}: scrape failed, so it cannot be removed in round 2 for lack of details; "
                            f"keep it (the table shows 【抓取失败】) or remove it only for a reason visible in the "
                            f"title (form/material clearly different), with round set to 1")
    for asin in dec:
        if asin not in items:
            problems.append(f"{asin}: not in bs_list.json")
    asks = [{"asin": k, "rank": items[k]["rank"], "title": items[k].get("title"), "reason": v.get("reason")}
            for k, v in dec.items() if v.get("decision") == "ask" and k in items]
    if asks:
        problems.append(f"{len(asks)} item(s) still 'ask': ask the user in one list, then update filter.json")

    if a.round == 2 and not problems:
        rem_dir = os.path.join(a.work, "removed")
        for asin, d in dec.items():
            src = os.path.join(a.work, "products", asin)
            if d["decision"] == "remove" and os.path.isdir(src):
                os.makedirs(rem_dir, exist_ok=True)
                dst = os.path.join(rem_dir, asin)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.move(src, dst)
        missing = [k for k, v in dec.items() if v["decision"] == "keep"
                   and not os.path.exists(os.path.join(a.work, "products", k, "product.json"))]
        if missing:
            problems.append(f"kept but never scraped: {', '.join(missing)}")

    by = lambda v: sorted((k for k, d in dec.items() if d.get("decision") == v and k in items),
                          key=lambda k: items[k]["rank"])
    res = {"ok": not problems, "round": a.round, "problems": problems, "ask": asks,
           "keep": len(by("keep")), "remove": len(by("remove")), "pending": len(by("pending"))}
    if a.round == 1:
        res["to_scrape"] = by("keep") + by("pending")
    else:
        res["kept_asins"] = by("keep")
    if res["ok"]:
        flt[f"round{a.round}_applied"] = True
        write_json(os.path.join(a.work, "filter.json"), flt)
    out(res)
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
