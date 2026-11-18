// Run on an Amazon product page (/dp/ASIN) with the browser's JavaScript tool.
// Returns a JSON string; save it to a file and pass it to scrape_product.py --from-json.
// Same fields as the script parser: title, brand, product_type, attributes, main_images, aplus_images.
(() => {
  const txt = el => (el ? el.innerText.replace(/\s+/g, ' ').trim() : null);
  const blocked = /validateCaptcha|Access restricted|unauthorized AI agent|Enter the characters you see/i;
  if (blocked.test(document.body.innerText.slice(0, 3000))) {
    return JSON.stringify({ blocked: true, reason: txt(document.body).slice(0, 200) });
  }
  let main = [];
  for (const s of document.querySelectorAll('script')) {
    const t = s.textContent; const k = t.indexOf("'colorImages'"); if (k < 0) continue;
    const j = t.indexOf("'initial'", k); const b = t.indexOf('[', j);
    let d = 0, i = b, inS = false, esc = false;
    for (; i < t.length; i++) {
      const c = t[i];
      if (inS) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inS = false; }
      else if (c === '"') inS = true; else if (c === '[') d++; else if (c === ']') { d--; if (d === 0) break; }
    }
    try { main = JSON.parse(t.slice(b, i + 1).replace(/\\'/g, "'")).map(x => x.hiRes || x.large).filter(Boolean); } catch (e) {}
    if (main.length) break;
  }
  if (!main.length) {
    main = [...document.querySelectorAll('#altImages li.imageThumbnail img')]
      .map(i => i.src.replace(/\._[^/]*?_\.(jpg|png)$/, '.$1'));
  }
  const aplus = [], seen = new Set();
  document.querySelectorAll('#aplus img, #aplus_feature_div img, #aplusBrandStory_feature_div img, ' +
    'img[src*="aplus-media"], img[data-src*="aplus-media"]').forEach(im => {
    const u = im.dataset.src || im.src || '';
    if (!u.startsWith('http') || u.endsWith('.gif') || u.includes('pixel')) return;
    const m = u.match(/\/([0-9a-fA-F-]{20,}|[A-Za-z0-9+%-]{9,})\./); const key = m ? m[1] : u;
    if (!seen.has(key)) { seen.add(key); aplus.push(u); }
  });
  const attributes = {};
  document.querySelectorAll('tr[class*="po-"], #productOverview_feature_div tr, #prodDetails tr, ' +
    'table[id^=productDetails] tr').forEach(tr => {
    const th = tr.querySelector('th'); const tds = tr.querySelectorAll('td');
    const k = txt(th || tds[0]); const v = txt(tds[tds.length - 1]);
    if (k && v && k !== v && !(k in attributes)) attributes[k] = v;
  });
  document.querySelectorAll('#detailBullets_feature_div li').forEach(li => {
    const b = li.querySelector('.a-text-bold'); if (!b) return;
    const k = txt(b).replace(/[\s:\u200e\u200f]+$/, ''); const v = txt(li).replace(txt(b), '').trim();
    if (k && v && !(k in attributes)) attributes[k] = v;
  });
  const pt = document.documentElement.innerHTML.match(/productType\s*[=:]\s*['"]([A-Z0-9_]+)['"]/);
  return JSON.stringify({
    title: txt(document.querySelector('#productTitle')),
    brand: attributes['Brand'] || txt(document.querySelector('#bylineInfo')),
    product_type: pt ? pt[1] : null, attributes, main_images: main, aplus_images: aplus,
  });
})()
