// Run on an Amazon Best Sellers page (/gp/bestsellers/...) after scrolling to the bottom.
// Returns a JSON string with this page's items; merge pages 1 and 2 into one file
// {"category": {...}, "items": [...], "method": "builtin-browser|chrome"} for get_bs_list.py --from-json.
(() => {
  const blocked = /validateCaptcha|Access restricted|unauthorized AI agent|Enter the characters you see/i;
  if (blocked.test(document.body.innerText.slice(0, 3000))) {
    return JSON.stringify({ blocked: true, reason: document.body.innerText.slice(0, 200) });
  }
  const items = {};
  const holder = document.querySelector('[data-client-recs-list]');
  if (holder) {
    JSON.parse(holder.getAttribute('data-client-recs-list')).forEach(x => {
      const r = x.metadataMap && x.metadataMap['render.zg.rank'];
      if (x.id && r) items[x.id] = { asin: x.id, rank: +r, title: null };
    });
  }
  document.querySelectorAll('#gridItemRoot').forEach(g => {
    const a = g.querySelector('[data-asin]')?.getAttribute('data-asin'); if (!a) return;
    const t = g.querySelector("div[class*='line-clamp']")?.innerText || g.querySelector('img')?.alt || null;
    const b = g.querySelector('.zg-bdg-text')?.innerText.replace(/\D/g, '');
    items[a] = items[a] || { asin: a, rank: b ? +b : null, title: null };
    items[a].title = items[a].title || t;
  });
  const path = location.pathname.replace(/^.*\/gp\/bestsellers\//, '').split('/ref=')[0].replace(/\/$/, '');
  return JSON.stringify({
    category: { name: ([...document.querySelectorAll('h1, h2')].map(h => h.innerText.trim())
                  .find(t => /^(Best Sellers in|Bestseller in|Meilleures ventes en|Più venduti in|Más vendidos en|売れ筋ランキング)/i.test(t)) || '')
                  .replace(/^(Best Sellers in|Bestseller in|Meilleures ventes en|Più venduti in|Más vendidos en|売れ筋ランキング[:：]?)\s*/i, '') || null,
                path, url: location.origin + '/gp/bestsellers/' + path },
    items: Object.values(items).filter(x => x.rank),
  });
})()
