"""Count which image type competitors use in each gallery slot. Writes <work>/stats.json.

Usage:
  python -X utf8 summarize_analysis.py --work DIR

Only kept products (filter.json) with an analysis file are counted.
Output (also printed): gallery size stats, per-slot type ranking, per-type coverage,
and example images for every type (rank order) to pick reference images from.
"""
import argparse
import collections
import os
import statistics
import sys

from amz_common import out, read_json, write_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    flt = read_json(os.path.join(a.work, "filter.json"), {"decisions": []})
    bs = read_json(os.path.join(a.work, "bs_list.json"), {"items": []})
    rank = {i["asin"]: i["rank"] for i in bs["items"]}
    kept = [d["asin"] for d in flt["decisions"] if d.get("decision") == "keep"]
    analyses = {}
    for asin in kept:
        an = read_json(os.path.join(a.work, "analysis", f"{asin}.json"))
        if an and an.get("images"):
            analyses[asin] = an
    if not analyses:
        sys.exit("no analysis files for kept products; finish step 4 first")

    sizes = [len(an["images"]) for an in analyses.values()]
    slot = collections.defaultdict(collections.Counter)
    coverage = collections.Counter()
    examples = collections.defaultdict(list)
    for asin in sorted(analyses, key=lambda x: rank.get(x, 999)):
        types_here = set()
        for im in analyses[asin]["images"]:
            t = im.get("type", "其他")
            slot[im["position"]][t] += 1
            types_here.add(t)
            examples[t].append({"asin": asin, "rank": rank.get(asin), "position": im["position"],
                                "message": im.get("message", "")[:80]})
        coverage.update(types_here)
    n = len(analyses)
    order = ["主图"] + [f"副图{i}" for i in range(1, max(sizes))]
    res = {
        "products_counted": n,
        "gallery_size": {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes)},
        "slots": [{"position": p, "total": sum(slot[p].values()),
                   "types": [{"type": t, "count": c, "share": round(c / sum(slot[p].values()), 2)}
                             for t, c in slot[p].most_common(4)]} for p in order if slot[p]],
        "type_coverage": [{"type": t, "products": c, "share": round(c / n, 2)} for t, c in coverage.most_common()],
        "examples": {t: v[:5] for t, v in examples.items()},
    }
    write_json(os.path.join(a.work, "stats.json"), res)
    out({k: v for k, v in res.items() if k != "examples"})


if __name__ == "__main__":
    main()
