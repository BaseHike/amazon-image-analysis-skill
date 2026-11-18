"""Shared helpers: site map, HTTP session, page parsing, JSON I/O, image handling."""
import json
import os
import random
import re
import sys
import time

SITES = {
    "US": ("www.amazon.com", "en-US,en;q=0.9"),
    "UK": ("www.amazon.co.uk", "en-GB,en;q=0.9"),
    "DE": ("www.amazon.de", "de-DE,de;q=0.9,en;q=0.8"),
    "FR": ("www.amazon.fr", "fr-FR,fr;q=0.9,en;q=0.8"),
    "IT": ("www.amazon.it", "it-IT,it;q=0.9,en;q=0.8"),
    "ES": ("www.amazon.es", "es-ES,es;q=0.9,en;q=0.8"),
    "JP": ("www.amazon.co.jp", "ja-JP,ja;q=0.9,en;q=0.8"),
    "CA": ("www.amazon.ca", "en-CA,en;q=0.9"),
}

CAPTCHA_MARKERS = (
    "/errors/validateCaptcha",
    "Type the characters you see in this image",
    "api-services-support@amazon.com",
    "Enter the characters you see below",
)


class Blocked(Exception):
    """Amazon returned a captcha / robot check page."""


def site_info(site):
    site = site.upper()
    if site not in SITES:
        sys.exit(f"Unknown site '{site}'. Supported: {', '.join(SITES)}")
    return SITES[site]


def dp_url(site, asin):
    return f"https://{site_info(site)[0]}/dp/{asin}"


def make_session(site):
    try:
        from curl_cffi import requests as creq
        s = creq.Session(impersonate="chrome")
    except ImportError:
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    s.headers["Accept-Language"] = site_info(site)[1]
    return s


def fetch_html(session, url, tries=3):
    last = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=40)
            text = r.text
            if any(m in text for m in CAPTCHA_MARKERS):
                last = Blocked("captcha page")
            elif r.status_code == 200 and len(text) > 5000:
                return text
            else:
                last = RuntimeError(f"HTTP {r.status_code}, {len(text)} bytes")
        except Exception as e:  # network errors
            last = e
        time.sleep(2 + i * 3 + random.random())
    raise last


def fetch_bytes(session, url, tries=3):
    last = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 500:
                return r.content
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
        time.sleep(1 + i * 2)
    raise last


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def image_sig(rec):
    """Signature of a product.json image list, written by scrape_product.py and verified by
    check_excel.py, so hand edits of the scraped image lists are detected."""
    import hashlib
    key = [[m.get("url"), m.get("file")] for m in rec.get("main_images", []) + rec.get("aplus_images", [])]
    return hashlib.sha256(json.dumps([rec.get("asin"), key], ensure_ascii=False).encode()).hexdigest()[:16]


def out(data):
    """Print a JSON result for the calling agent."""
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- parsing

def _clean(s):
    return re.sub(r"[\s‎‏]+", " ", s or "").strip(" : ")


def original_image_url(url):
    """Drop Amazon size modifiers (._AC_SL1500_. etc.) to get the full-size file."""
    if not url:
        return url
    if "/images/I/" in url:
        return re.sub(r"\._[^/]*?_\.(jpg|jpeg|png|gif|webp)$", r".\1", url)
    return url


def _bracket_block(text, start):
    """Return the JSON array starting at text[start] == '['."""
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def parse_main_images(html):
    """Gallery images in page order (MAIN, PT01, PT02 ...). Videos are not included."""
    urls = []
    k = html.find("'colorImages'")
    if k >= 0:
        j = html.find("'initial'", k)
        b = html.find("[", j) if j >= 0 else -1
        if b >= 0:
            block = _bracket_block(html, b)
            if block:
                try:
                    data = json.loads(block.replace("\\'", "'"))
                    for it in data:
                        u = it.get("hiRes") or it.get("large")
                        if u:
                            urls.append(u)
                except ValueError:
                    pass
    if not urls:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for im in soup.select("#altImages li.imageThumbnail img, #altImages li.item img"):
            u = original_image_url(im.get("src"))
            if u and u not in urls:
                urls.append(u)
        if not urls:
            land = soup.find(id="landingImage")
            if land:
                urls.append(land.get("data-old-hires") or original_image_url(land.get("src")))
    seen, res = set(), []
    for u in urls:
        key = re.sub(r"\._[^/]*?_\.", ".", u)
        if key not in seen:
            seen.add(key)
            res.append(u)
    return res


APLUS_CONTAINERS = ("aplus", "aplus_feature_div", "aplusBrandStory_feature_div",
                    "aplus3p_feature_div", "aplusSustainabilityStory_feature_div")


def parse_aplus_images(soup):
    res, seen = [], set()
    in_container = set()
    for cid in APLUS_CONTAINERS:
        box = soup.find(id=cid)
        if box:
            in_container.update(id(im) for im in box.find_all("img"))
    for im in soup.find_all("img"):
        u = im.get("data-src") or im.get("src") or ""
        if not u.startswith("http") or u.endswith(".gif") or "grey-pixel" in u or "transparent-pixel" in u:
            continue
        if "aplus-media" not in u and id(im) not in in_container:
            continue
        # product cards inside A+ (brand-story ASIN grid, comparison-table thumbnails) link to other
        # products: they are not this listing's A+ images
        link = im.find_parent("a")
        if link and re.search(r"/(dp|gp/product)/[A-Z0-9]{10}", link.get("href") or ""):
            continue
        if im.find_parent(class_=re.compile(r"apm-brand-story-image-grid")):
            continue
        m = re.search(r"/([0-9a-fA-F-]{20,}|[A-Za-z0-9+%-]{9,})\.", u)
        key = m.group(1) if m else u
        if key in seen:
            continue
        seen.add(key)
        res.append(original_image_url(u))
    return res


def parse_attributes(soup):
    attrs = {}
    for tr in soup.select('tr[class*="po-"], #productOverview_feature_div tr, #prodDetails tr, '
                          'table[id^=productDetails] tr, #technicalSpecifications_feature_div tr'):
        th = tr.find("th")
        tds = tr.find_all("td")
        if th and tds:
            k, v = _clean(th.get_text(" ")), _clean(tds[-1].get_text(" "))
        elif len(tds) >= 2:
            k, v = _clean(tds[0].get_text(" ")), _clean(tds[-1].get_text(" "))
        else:
            continue
        if k and v and k != v and len(v) < 400:
            attrs.setdefault(k, v)
    for li in soup.select("#detailBullets_feature_div li"):
        b = li.select_one(".a-text-bold")
        if b:
            k = _clean(b.get_text(" "))
            v = _clean(li.get_text(" ").replace(b.get_text(" "), "", 1))
            if k and v and len(v) < 400:
                attrs.setdefault(k, v)
    return attrs


def parse_bsr_categories(soup):
    """Best Sellers Rank categories of a product page (language independent: uses links)."""
    cats, seen = [], set()
    links = soup.select('a[href*="/gp/bestsellers/"]')
    bsr = [a for a in links if "pd_zg_ts" in a.get("href", "") or "pd_zg_hrsr" in a.get("href", "")]
    for a in bsr or links:
        href = a.get("href", "")
        if _clean(a.get_text(" ")).startswith("#"):  # "#1 Best Seller" badge, not a category
            continue
        m = re.search(r"/gp/bestsellers/([^/?]+)(?:/(\d+))?", href)
        if not m:
            continue
        # only links inside the product detail / BSR area, not navigation
        holder = a.find_parent(["li", "td", "span"])
        txt = _clean(holder.get_text(" ")) if holder else ""
        # rank formats: US/UK "#1,234 in", DE "Nr. 1.234 in", IT "n. 12 in", ES "nº 12 en", FR "12 en", JP "- 12位"
        rank = re.search(r"(?:#|Nr\.|n\.|nº|n°|N°)\s?(\d[\d,.]*)", txt) or re.search(r"(\d[\d,.]*)", txt)
        if not rank:
            continue
        path = m.group(1) + (f"/{m.group(2)}" if m.group(2) else "")
        if path in seen:
            continue
        seen.add(path)
        name = _clean(a.get_text(" "))
        name = re.sub(r"^(See Top 100 in|Siehe Top 100 in|Voir les 100 premiers en|Visualizza i Top 100 nella categoria|Ver el Top 100 en)\s*", "", name)
        cats.append({
            "name": name,
            "path": path,
            "rank": int(re.sub(r"[,.]", "", rank.group(1))),
            "is_root": m.group(2) is None,
        })
    return cats


def parse_product(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find(id="productTitle")
    byline = soup.find(id="bylineInfo")
    attrs = parse_attributes(soup)
    brand = attrs.get("Brand") or attrs.get("Marke") or attrs.get("Marque") or attrs.get("Marca") or attrs.get("ブランド")
    if not brand and byline:
        b = _clean(byline.get_text(" "))
        b = re.sub(r"^(Visit the|Besuche den|Visiter la boutique|Visita lo Store di|Visita la tienda de)\s+", "", b)
        b = re.sub(r"\s+(Store|Shop|-Store|Boutique)$", "", b)
        b = re.sub(r"^(Brand|Marke|Marque|Marca|ブランド)\s*[:：]\s*", "", b)
        brand = b
    pt = re.search(r"productType\s*[=:]\s*['\"]([A-Z0-9_]+)['\"]", html)
    return {
        "title": _clean(t.get_text(" ")) if t else None,
        "product_type": pt.group(1) if pt else None,
        "brand": brand or None,
        "attributes": attrs,
        "main_images": parse_main_images(html),
        "aplus_images": parse_aplus_images(soup),
        "bsr_categories": parse_bsr_categories(soup),
    }


# ---------------------------------------------------------------- layout

ROW_MAX_PT = 409  # Excel / WPS row height limit


def text_height_pt(text, width_chars, font_pt=10):
    """Row height (pt) a wrapped text cell needs. CJK chars count ~1.8 width units at 10pt YaHei."""
    import math
    lines = 0
    for para in str(text or "").split("\n"):
        units = sum(1.8 if ord(ch) >= 0x2E80 else 1.0 for ch in para)
        lines += max(1, math.ceil(units / max(1.0, width_chars - 1.5)))
    return lines * font_pt * 1.45 + 12  # small margin: Excel wraps slightly wider than WPS


# ---------------------------------------------------------------- OCR (text-on-image check)

def ocr_images(paths, cache_path):
    """{path: text} via Windows built-in OCR (ocr_images.ps1). Cached in cache_path.
    Returns None when OCR is not available on this machine."""
    import subprocess
    import tempfile
    cache = read_json(cache_path, {}) or {}
    todo = [p for p in paths if p not in cache]
    if todo:
        if os.name != "nt":
            return None
        ps1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_images.ps1")
        with tempfile.TemporaryDirectory() as td:
            lst, res = os.path.join(td, "list.txt"), os.path.join(td, "out.json")
            with open(lst, "w", encoding="utf-8") as f:
                f.write("\n".join(todo))
            try:
                subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, lst, res],
                               capture_output=True, timeout=600, check=True)
                got = read_json(res, None)
            except Exception:
                return None
        if not isinstance(got, dict):
            return None
        cache.update(got)
        write_json(cache_path, cache)
    return {p: cache.get(p) for p in paths}


_CONFUSE = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "5": "s"})


def _norm(s):
    return re.sub(r"[^0-9a-z぀-ヿ一-鿿%]", "", (s or "").lower()).translate(_CONFUSE)


def text_matches(claimed, ocr):
    """Does the text the analyst copied from an image appear in the OCR result?
    Returns (ok, found_tokens, checked_tokens). Tolerant of OCR splitting letters and 0/O, 1/l/I."""
    target = _norm(ocr)
    stop = {"the", "and", "for", "with", "your", "you", "our", "der", "die", "das", "und", "mit", "les", "des"}
    tokens = [_norm(t) for t in re.split(r"[\s,;/|｜、，。:：!！?？()（）\"“”'‘’]+", claimed or "")]
    tokens = [t for t in tokens if len(t) >= 3 and t not in stop]
    if not tokens:
        return True, 0, 0
    # stylised headline fonts are often missed by OCR, and plurals differ: accept a word stem,
    # and pass when a third of the words are found (made-up text usually matches none)
    found = sum(1 for t in tokens if t in target or (len(t) >= 6 and t[:-2] in target))
    return found >= max(1, -(-len(tokens) // 3)), found, len(tokens)


# ---------------------------------------------------------------- images

def save_image(raw, path_orig, path_thumb, long_side=1000):
    """Save the original bytes and a proportionally downscaled JPEG. Returns (w, h, tw, th)."""
    from io import BytesIO
    from PIL import Image
    os.makedirs(os.path.dirname(path_orig), exist_ok=True)
    with open(path_orig, "wb") as f:
        f.write(raw)
    im = Image.open(BytesIO(raw))
    im.load()
    w, h = im.size
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    scale = min(1.0, long_side / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    im.save(path_thumb, "JPEG", quality=85, optimize=True)
    return w, h, im.size[0], im.size[1]
