# 抓取：榜单和商品详情

## 用途
规定第 1 步（榜单）和第 2 步（商品详情 + 图片）怎么抓、抓不到怎么换工具、子代理怎么分配和回报。

## 适用条件
- 第 1 步：`get_bs_list.py` 失败（exit 1）时，用这里的浏览器降级办法。
- 第 2 步：主代理给子代理派抓取任务时，用这里的提示词模板。

## 规则

### 工具降级顺序（不能跳过，也不能乱序）
1. **脚本**：`get_bs_list.py` / `scrape_product.py`。
2. **内置浏览器**（Claude Code：`mcp__Claude_Browser__*`，先读 `anthropic-skills:built-in-browser` Skill；其他代理用自己的内置浏览器工具）。
3. **外置浏览器 Chrome**（Claude Code：`mcp__claude-in-chrome__*`，先读 `anthropic-skills:chrome-browser` Skill；其他代理用自己的 Chrome 控制工具）。

当前环境没有某种浏览器工具时，这一级记为“不可用”，直接试下一级。三级都失败或不可用，就记为失败。不要自己写新的抓取脚本代替，也不要用榜单页缩略图顶替详情页图片。

前一种工具对某个 ASIN 失败，才对**这个 ASIN** 换下一种；成功的 ASIN 不重抓。三种都失败，记为失败并写明每种工具的失败原因，交给主代理。

### 拦截页：不要绕过
页面出现以下任何一种，当前工具对这个 ASIN 判为失败，直接换下一种工具：
- 验证码（“Enter the characters you see”/`validateCaptcha`）
- “Access restricted … unauthorized AI agent …”提示页
- 机器人检查、登录墙

**不要点“Continue”、不要输入验证码、不要换 IP、不要伪装身份、不要反复刷新。** 浏览器提取脚本遇到这些页面会返回 `{"blocked": true}`。

实测（2026-11）：亚马逊会给内置浏览器显示“Access restricted … unauthorized AI agent”页面，所以浏览器降级经常也会失败。这种情况照常记为失败，不要想办法绕过。脚本请求过于频繁时也会遇到验证码，这时先停几分钟、放慢节奏，再整批重跑一次。

### 浏览器降级的做法
商品页：
1. 打开 `https://<站点域名>/dp/<ASIN>`，等页面加载完。
2. 读取 `scripts/browser_extract_product.js` 的全部内容，原样作为 JavaScript 执行。
3. 返回 `blocked: true` → 换下一种工具。返回正常 JSON → 用 Write 存到 `<work>/browser/<ASIN>.json`。
4. 运行：`python -X utf8 scripts/scrape_product.py --work <work> --asins <ASIN> --from-json <work>/browser/<ASIN>.json --method builtin-browser`（Chrome 用 `--method chrome`）。图片由脚本下载，格式和脚本模式完全一样。

榜单页：
0. 还不知道类目时（脚本在种子商品页就失败了）：先打开种子商品页 `/dp/<ASIN>`，用 find 搜 “Best Sellers Rank”，读出其中带 `/gp/bestsellers/` 的类目链接。“See Top 100 in …”是大类，不用；剩下的细分类目只有一个就用它，有多个就列给用户选。
1. 打开类目 BS 链接，滚动到底部让 50 个商品都加载出来；需要第 51～100 名时，再打开 `?pg=2` 重复一次。
2. 每页执行 `scripts/browser_extract_bs.js`，把各页的 `items` 合并，写成：
   `{"category": {...第1页的category...}, "items": [...], "method": "builtin-browser"}`，存到 `<work>/browser/bs_list.json`。
3. 运行：`python -X utf8 scripts/get_bs_list.py --work <work> --from-json <work>/browser/bs_list.json`。

### 子代理分配（第 2 步）
- 每个子代理负责 **10 个 ASIN**，同时最多 **3 个**子代理（太多会被亚马逊限流）。
- 用 `general-purpose` 类型的子代理。
- 子代理只负责抓取，不做相关性判断、不做图片分析。

## 示例：子代理提示词模板
```
你负责抓取亚马逊商品详情和图片。不要做其他事。

工作目录：<work>
站点：<site>
脚本目录：<SKILL_DIR>/scripts
你负责的 ASIN（共 n 个）：B0..., B0..., ...

步骤：
1. 运行 python -X utf8 <SKILL_DIR>/scripts/scrape_product.py --work "<work>" --asins <逗号分隔的 ASIN>
2. 看输出的 results：status 为 ok 的完成。status 为 failed 或 partial 的，逐个改用内置浏览器（先读 anthropic-skills:built-in-browser Skill），
   按 <SKILL_DIR>/references/scraping.md 的“浏览器降级的做法”提取并运行 --from-json。
3. 内置浏览器也失败的，改用 Chrome（先读 anthropic-skills:chrome-browser Skill），做法相同，--method chrome。
4. 遇到验证码或“Access restricted / unauthorized AI agent”页面：不要点继续、不要输入验证码，直接换下一种工具；三种都失败就记为失败。
5. 不要跳过任何 ASIN。

最后只回复一个 JSON（不要别的文字）：
{"done": [{"asin": "...", "method": "script|builtin-browser|chrome", "main_count": 7, "aplus_count": 12,
           "title": "...", "product_type": "...", "material": "..."}],
 "failed": [{"asin": "...", "tried": {"script": "原因", "builtin-browser": "原因", "chrome": "原因"}}]}
```

## 特殊情况
- **整批脚本都失败**（例如全部遇到验证码）：子代理不用对每个 ASIN 都试浏览器，先用内置浏览器试 1 个；也被拦截就再用 Chrome 试 1 个；都被拦截则整批记为失败，回报主代理，由主代理告诉用户。
- **种子页找不到 Best Sellers Rank**（`get_bs_list.py` exit 1，reason 为 “no Best Sellers Rank found”）：按“浏览器降级的做法 → 榜单页”第 0 步，用浏览器读出类目后，运行 `get_bs_list.py --category <path>`。
- **partial**（部分图片下载失败）：先用脚本对这个 ASIN 重跑一次（图片 CDN 偶尔超时），仍失败再走浏览器。
- **主图数量很多**（超过 9 张）：正常，保留全部，表格会自动加列。
- **没有 A+**：正常，`aplus_count` 为 0，表里显示“无A+”。
- **变体商品**：抓取的是 ASIN 当前变体的图片，不切换变体。

## 输出格式
- 每个 ASIN：`<work>/products/<ASIN>/product.json`，原图在 `images/`，等比缩小的副本在 `thumbs/`（长边 ≤1000px）。
- `product.json` 关键字段：`asin, rank, url, method, status(ok|partial|failed), title, brand, product_type, attributes, main_images[], aplus_images[], errors[]`；每张图有 `index, url, file, thumb, width, height, thumb_width, thumb_height`。
- 子代理的回复：上面模板里的 JSON。
