"""Create the work directory and job.json for one run.

Usage:
  python -X utf8 init_job.py --site US --top 50 --name "示例复合镁" --points "7种镁形态" "睡眠" \
      (--asin B07P5K7DQP | --bs-url https://www.amazon.com/gp/bestsellers/hpc/3774411) [--out-root DIR]
Prints: {"work_dir": ..., "output_dir": ...}
"""
import argparse
import datetime as dt
import os
import re
import tempfile

from amz_common import SITES, out, write_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, choices=list(SITES))
    ap.add_argument("--top", type=int, required=True)
    ap.add_argument("--name", required=True, help="new product name")
    ap.add_argument("--points", nargs="+", required=True, help="new product selling points")
    ap.add_argument("--asin")
    ap.add_argument("--bs-url")
    ap.add_argument("--out-root", default=os.path.join(os.getcwd(), "output"))
    a = ap.parse_args()
    if not a.asin and not a.bs_url:
        ap.error("--asin or --bs-url is required")
    if not 1 <= a.top <= 100:
        ap.error("--top must be 1..100 (Best Sellers shows 100 items)")
    if a.asin and not re.fullmatch(r"[A-Z0-9]{10}", a.asin.upper()):
        ap.error(f"invalid ASIN: {a.asin}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = (a.asin or "bs").upper()
    work = os.path.join(tempfile.gettempdir(), "amazon-image-analysis", f"{tag}-{stamp}")
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", a.name)
    output = os.path.join(a.out_root, f"{safe_name}-竞品图片分析-{stamp[:8]}")
    os.makedirs(os.path.join(work, "products"), exist_ok=True)
    os.makedirs(os.path.join(work, "analysis"), exist_ok=True)
    os.makedirs(output, exist_ok=True)
    job = {
        "seed_asin": a.asin.upper() if a.asin else None,
        "bs_url": a.bs_url,
        "site": a.site,
        "top_n": a.top,
        "product_name": a.name,
        "selling_points": a.points,
        "work_dir": work,
        "output_dir": output,
        "created": stamp,
    }
    write_json(os.path.join(work, "job.json"), job)
    out({"work_dir": work, "output_dir": output})


if __name__ == "__main__":
    main()
