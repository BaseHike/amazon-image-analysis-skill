---
name: amazon-image-analysis
description: 抓取亚马逊竞品的主图、副图和 A+ 图片，整理成图片嵌入单元格的 Excel（WPS 版 + Excel 版），并附每张图的作用分析和新品作图方案。用户给出 ASIN 或 BS 榜链接，说“抓取一下这个 asin 图片”“抓取一下图片”“抓一下 BS 榜前 50 的图”“竞品图片分析”“把竞品主图/A+ 做成表格”“看看竞品图片怎么做的，给我作图建议”时使用。不用于：写 listing、标题、五点、广告文案、关键词研究，直接生成或修改图片，只查价格、评论、销量等非图片数据。
---

# 亚马逊竞品图片分析

`SKILL_DIR` = 本文件所在目录。所有命令用 `python -X utf8 <SKILL_DIR>/scripts/...` 运行。

## 文件清单
| 文件 | 内容 | 什么时候读/运行 |
|---|---|---|
| `references/relevance-filter.md` | 相关产品筛选规则（形态 + 材质） | 第 1 步、第 2 步末尾 |
| `references/scraping.md` | 抓取降级顺序、拦截页处理、抓取子代理模板 | 第 1 步脚本失败时、第 2 步 |
| `references/excel-spec.md` | 表格规范、两种嵌图格式、制表子代理模板 | 第 3 步 |
| `references/image-analysis.md` | 图片类型表、分析写法、分析子代理模板 | 第 4 步 |
| `references/visual-plan.md` | 作图方案写法、方案子代理模板 | 第 5 步 |
| `references/qa-and-retry.md` | 检验项对应步骤、返工提示词、重试上限 | 第 3～6 步检验时 |
| `scripts/init_job.py` | 建工作目录和 job.json | 第 1 步 |
| `scripts/get_bs_list.py` | ASIN → BS 类目 → 前 N 名 | 第 1 步 |
| `scripts/apply_filter.py` | 校验并执行筛选结论 | 第 1、2 步 |
| `scripts/scrape_product.py` | 抓详情、下载图片（含浏览器结果导入） | 第 2 步 |
| `scripts/browser_extract_product.js` / `browser_extract_bs.js` | 浏览器降级时在页面里执行的提取代码 | 第 1、2 步降级时 |
| `scripts/contact_sheet.py` | 每个商品的主副图拼成一张带图位标签的拼图，方便一次看全 | 第 4 步 |
| `scripts/ocr_images.ps1` | Windows 自带文字识别，`check_excel.py` 用它核对分析里的图上文字 | 第 4～6 步（自动调用） |
| `scripts/build_excel.py` | 生成 WPS 版和 Excel 版两个文件 | 第 3、4、5 步 |
| `scripts/summarize_analysis.py` | 统计各图位常用类型 | 第 5 步 |
| `scripts/check_excel.py` | 检验文件、指出出问题的步骤 | 第 3～6 步 |

依赖：`pip install curl_cffi beautifulsoup4 pillow xlsxwriter openpyxl`（缺哪个装哪个）。

## 输入
必需（缺任何一项先问用户，不要猜，一次问完）。**缺必需项时不运行任何脚本、不抓任何东西**：直接回复缺哪几项并结束这一轮。非交互运行（没法追问）也一样，不能自己编站点、前 N 名、新品名或卖点。
1. **ASIN** 或 **类目 BS 链接**（二选一）
2. **站点**：US / UK / DE / FR / IT / ES / JP / CA
3. **榜单前 N 名**：1～100
4. **新品名称**和**核心卖点**（用于第 5 步作图方案）

可选：输出目录（默认 `<当前工作目录>/output/`）。

## 工作流程

### 第 1 步：拿榜单，第 1 轮筛选（主代理）
1. 运行 `init_job.py --site <站点> --top <N> --name "<新品名>" --points "<卖点1>" "<卖点2>" ... --asin <ASIN>`（有 BS 链接时用 `--bs-url <链接>` 代替 `--asin`；指定输出目录时加 `--out-root <目录>`）。记下输出的 `work_dir`，下文写作 `<work>`。
2. 运行 `get_bs_list.py --work <work>`，按退出码处理：
   - **0**：继续。
   - **2（need_choice）**：把输出里的 `categories` 列给用户（名称 + 排名），问用哪个；拿到回答后运行 `get_bs_list.py --work <work> --category <path>`。
   - **1（failed）**：读 `references/scraping.md`，按“浏览器降级的做法 → 榜单页”用内置浏览器，再不行用 Chrome。三种都失败 → 告诉用户原因，请用户提供 BS 链接或稍后重试，停止。
3. 读 `references/relevance-filter.md`，根据 `<work>/seed.json` 定出形态和材质标准（定不了就问用户），按标题做第 1 轮筛选，写 `<work>/filter.json`。
4. 有 ask：汇总成一张清单一次问用户，按回答改写。没法问用户（非交互运行）→ 按 `references/relevance-filter.md` 的“没法问用户”自行判定。
5. 运行 `apply_filter.py --work <work> --round 1`。exit 1 → 按 `problems` 修 filter.json 再跑。exit 0 → 拿 `to_scrape` 进入第 2 步。

### 第 2 步：抓取详情和图片（子代理），第 2 轮筛选（主代理）
1. 读 `references/scraping.md`。把 `to_scrape` 按每 10 个分一批，用“子代理提示词模板”派 `general-purpose` 子代理，同时最多 3 个。
2. 收齐所有子代理的 JSON。`failed` 里的 ASIN 必须写明三种工具各自的失败原因；缺哪种工具没试，就把这些 ASIN 退回给子代理补试（不要跳过）。
3. 按 `references/relevance-filter.md` 的“第 2 轮”和“材质证据”读各 `product.json`（材质矛盾时看图）判形态和材质，更新 filter.json；有 ask 就汇总问用户，没法问时按“没法问用户”处理。
4. 运行 `apply_filter.py --work <work> --round 2`，exit 0 后进入第 3 步。

### 第 3 步：制表（子代理）
1. 读 `references/excel-spec.md`，用其中的“制表子代理提示词模板”派一个子代理。
2. 子代理返回的 `check` 里有第 3 步的 error → 读 `references/qa-and-retry.md` 写返工说明重派；有第 2 步的 error → 回到第 2 步补抓对应 ASIN。

### 第 4 步：图片分析（子代理）
1. 读 `references/image-analysis.md`。把保留且抓取成功的 ASIN 按每 5 个分一批，用其中的模板派子代理（可以同时派多个）。分析必须先运行 `contact_sheet.py` 看拼图，每张图都要照抄图上文字（`text`）；没看过的图不能写。
2. 全部完成后运行 `build_excel.py --work <work>` 回填分析列，再运行 `check_excel.py --work <work> --stage analysis`。有第 4 步的 error → 按 `references/qa-and-retry.md` 返工。

### 第 5 步：作图方案（主代理汇总 → 子代理）
1. 运行 `summarize_analysis.py --work <work>`，读输出，确认统计覆盖了所有已分析商品。
2. 读 `references/visual-plan.md`，用其中的模板派一个子代理写 `<work>/plan.json`。
3. 运行 `build_excel.py --work <work>` 写入方案表。

### 第 6 步：检验（主代理）
1. 读 `references/qa-and-retry.md`，运行 `check_excel.py --work <work> --stage final`。
2. exit 0 → 进入“最后”。exit 1 → 找出最早出问题的步骤，写返工说明（上次做了什么 / 哪里不合格 / 原因 / 这次怎么做），只重做那一步及其后续的 `build_excel.py`，再检验。每步最多返工 2 次，超过就停下，带着剩余问题进入“最后”。

### 最后：交付
按 `references/qa-and-retry.md` 的“输出格式”回复用户：两个 Excel 的路径（WPS 版用 WPS 打开，Excel 版用 Excel 365 打开）、类目、保留/剔除/失败数量、返工记录和未解决的问题。

## 规则
- **类目**：ASIN 属于多个细分类目时，必须问用户用哪个。
- **相关性**：形态和材质都一致才保留；只在前 N 名里筛，不往后补；拿不准的汇总后问用户。
- **图片**：必须嵌入单元格，比例不变；只允许脚本做等比缩小。
- **表格样式**：只由 `build_excel.py` 决定（行高已按文字量自动加高）。觉得样式有问题，写进最终报告，不要另写脚本改表。
- **工具**：抓取按“脚本 → 内置浏览器 → Chrome”逐级换；制表按“脚本 → 操作电脑”逐级换。抓不到就换工具，不能跳过 ASIN。
- **拦截页**：遇到验证码、“Access restricted / unauthorized AI agent”页面，不点继续、不输验证码、不绕过，直接按失败处理换下一种工具。
- **计算交给脚本**：排名、计数、比例、统计、文件路径都以脚本输出为准，不自己算。
- **中间数据只由脚本写**：`bs_list.json`、`products/*/product.json` 只能由脚本生成。不要手改或删减里面的图片，不要用榜单缩略图顶替详情页图片，不要另写脚本包装或替换 `build_excel.py` 的输出。发现脚本抓错（例如 A+ 混入了别的商品），照原样交付，并在最终报告里写明是哪个 ASIN、什么问题。
- **规则覆盖不到的情况**：停下来问用户，说清楚卡在哪一步、有哪几个选择。必需输入齐全、但运行中没法问用户时，选最保守的做法继续，并在最终报告里单独列出（缺必需输入不适用这一条，见“输入”）。
