# amazon-image-analysis · 亚马逊竞品图片分析 Skill

给 AI 编程助手（Claude Code、Codex 等支持 Agent Skills 的工具）用的 Skill：输入一个 ASIN 或类目 BS 榜链接，自动抓取榜单前 N 名竞品的**主图、副图和 A+ 图片**，整理成**图片嵌入单元格、比例不变**的 Excel，并附上**逐图作用分析**和**新品作图方案**。

> An Agent Skill that scrapes the gallery and A+ images of Amazon Best Sellers competitors into an Excel workbook (images embedded in cells, aspect ratio kept), with a per-image role analysis and a visual plan for your new product. Instructions are written in Chinese.

## 能做什么

- 从 ASIN 自动找到所属细分类目的 BS 榜，取前 1～100 名；有多个类目时会问你用哪个。
- **相关性筛选**：只保留形态和材质都和你的产品一致的竞品（例如硅胶加热垫会剔除加热柜、玻璃加热板），拿不准的汇总后问你。
- 抓取每个竞品的全部主图、副图和 A+ 图片（自动过滤品牌故事里链到别的商品的卡片图）。
- 同时输出两个文件：
  - `…-WPS.xlsx`：WPS 单元格图片，用 WPS 打开；
  - `…-Excel.xlsx`：Excel“放置在单元格中”图片，用 Excel 365 / 2021 及以上打开。
- 四张工作表：图片分类总表、A+ 图片总表、新品视觉方案、剔除记录。
- 逐张图标注类型（16 种）和“传达什么 + 靠什么画面”，再按你的卖点生成主图 + 副图的作图方案（只写要表达什么，不写设计细节）。
- 自带检验脚本：31 项检查，每个问题都标明出在哪一步，并按步骤返工。

## 安装

### Claude Code（推荐：插件方式）

在 Claude Code 里运行：

```
/plugin marketplace add BaseHike/amazon-image-analysis-skill
/plugin install amazon-image-analysis@amazon-image-analysis-skill
```

### Claude Code（手动）

把 `skills/amazon-image-analysis` 文件夹复制到：

- 所有项目可用：`~/.claude/skills/amazon-image-analysis`
- 只在某个项目可用：`<项目>/.claude/skills/amazon-image-analysis`

### Codex 及其他支持 Agent Skills 的工具

把 `skills/amazon-image-analysis` 复制到 `~/.codex/skills/`，或项目里的 `.agents/skills/`。

### Python 依赖（必需）

需要 Python 3.10+：

```
pip install -r requirements.txt
```

## 使用

直接对助手说，例如：

- “抓取一下这个 asin 图片 B0XXXXXXXX，美国站，BS 前 20，新品是硅胶食物加热垫，卖点是可折叠收纳、快速均匀加热”
- “抓取一下图片，类目 BS 链接 https://www.amazon.com/gp/bestsellers/…，前 30，新品叫 XX，卖点是……”
- “看看德国站这个 ASIN 的竞品主图和 A+ 怎么做的，整理成表格，给我作图建议”

必需信息：**ASIN 或 BS 链接**、**站点**（US/UK/DE/FR/IT/ES/JP/CA）、**前 N 名**（1～100）、**新品名称和卖点**。缺任何一项，助手会先问你，不会自己猜。

不会触发：写 listing / 五点 / 广告文案、关键词研究、生成或修改图片、只查价格评论销量。

输出默认在当前工作目录的 `output/<新品名>-竞品图片分析-<日期>/`。

## 文件结构

```
skills/amazon-image-analysis/
├── SKILL.md                      主流程（第 1～6 步）和规则
├── references/                   各步骤的详细规则和子代理提示词模板
│   ├── relevance-filter.md       相关性筛选（形态 + 材质）
│   ├── scraping.md               抓取、换工具、拦截页处理
│   ├── excel-spec.md             表格规范
│   ├── image-analysis.md         图片类型表和分析写法
│   ├── visual-plan.md            作图方案写法
│   └── qa-and-retry.md           检验和返工
└── scripts/                      所有可脚本化的工作
    ├── init_job.py / get_bs_list.py / apply_filter.py / scrape_product.py
    ├── contact_sheet.py          每个商品的图拼成一张，方便一次看全
    ├── build_excel.py            生成 WPS 版和 Excel 版
    ├── summarize_analysis.py     统计各图位常用类型
    ├── check_excel.py            检验并定位出问题的步骤
    ├── ocr_images.ps1            Windows 自带文字识别，核对分析是否真的看过图
    └── browser_extract_*.js      浏览器兜底时在页面里执行的提取代码
```

## 限制和注意事项

- **请遵守亚马逊的使用条款**，控制抓取频率和数量，仅用于自己的竞品研究。
- 本 Skill **不绕过**任何拦截：遇到验证码、机器人检查或 “Access restricted” 页面，只会换下一种工具（脚本 → 内置浏览器 → Chrome），都不行就记为“抓取失败”。请求太频繁时会触发验证码，过一会儿再跑即可。
- 浏览器兜底依赖助手自带的浏览器工具（Claude Code 的内置浏览器 / Claude in Chrome）；环境里没有时这一级直接跳过。
- “分析是否真的看过图”的文字核对依赖 **Windows 自带 OCR**；在 macOS / Linux 上这一项会跳过并给出提示，其他检查照常。
- Excel 版需要 Excel 365 / 2021 及以上才能显示单元格内图片；旧版 Excel 请用 WPS 版。
- 图片会缩到长边 1000px 再嵌入，前 50 名的文件大约 100MB 以上，属于正常。

## License

[MIT](LICENSE)
