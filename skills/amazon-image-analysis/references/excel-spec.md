# 表格规范

## 用途
规定输出的 Excel 长什么样，以及第 3 步制表子代理怎么做、做不出来怎么办。

## 适用条件
- 第 3 步制表，以及第 4、5 步之后回填文字时（都是重跑同一个脚本）。
- 第 6 步检验时，对照这里判断哪里不合格。

## 规则

### 两个文件，内容完全一样
| 文件 | 图片嵌入方式 | 用什么打开 |
|---|---|---|
| `<新品名>-竞品图片分析-WPS.xlsx` | WPS 单元格图片（`=DISPIMG(...)`） | WPS（用 Excel 打开会显示 #NAME） |
| `<新品名>-竞品图片分析-Excel.xlsx` | Excel“放置在单元格中”图片 | Excel 365 / 2021 及以上；新版 WPS 也能显示 |

两个都在 `<output_dir>` 里，由 `build_excel.py` 一次生成。

### 图片要求
- 图片必须**嵌入单元格**（不是浮在表格上方的图片）。
- **比例不变**：只允许等比缩小（长边 ≤1000px，`scrape_product.py` 已做），表里由单元格等比适配，禁止拉伸或裁切。
- 主图、副图按亚马逊上的顺序放：第 1 张进“主图”列，第 2 张进“副图1”列，依此类推。

### 工作表和列
1. **图片分类总表**：ASIN｜排名｜品牌｜主图｜副图1…副图K｜图片分析｜商品页
   - K = 所有商品里最多的副图数量。
   - 排名为原始 BS 排名（剔除后会有断号）。品牌缺失写“未识别品牌”。
   - 抓取失败的商品也占一行，图片分析列写“【抓取失败】原因”。
2. **A+图片总表**：ASIN｜排名｜品牌｜A+图1…A+图M｜商品页（没有 A+ 的写“无A+”）。
3. **新品视觉方案**：序号｜载体｜画面任务｜用户需求触发｜参考图｜参考链接。
4. **剔除记录**：排名｜ASIN｜标题｜筛选轮次｜剔除原因｜商品页。

### 样式（脚本已固定，不要手改）
表头深青底白字加粗、冻结首行（前两张表另外冻结前 3 列）、图片行高至少 98、图片列宽 27（A+ 列宽 22）、文字自动换行、无网格线。
行高按文字量自动加高，保证图片分析、画面任务、剔除原因等长文字完整显示（单行上限 409；超过时脚本会自动加宽图片分析列）。`check_excel.py` 会检查“文字被截断”。不要另写脚本改行高或列宽。

### 制表工具优先级
1. **脚本**：`python -X utf8 scripts/build_excel.py --work <work>`。
2. 脚本报错时，先看报错能不能修（缺依赖就 `pip install xlsxwriter openpyxl pillow`；文件被占用时脚本会自动另存为 `-v2`）。修好后重跑脚本。
3. 脚本确实做不出来，才**操作电脑**（computer-use，先读 `anthropic-skills:computer-use` Skill）：
   - 先用 `build_excel.py --format excel` 或 `--format wps` 生成能生成的那一个，或让脚本生成不含图片的表。
   - 在 WPS 里打开，选中目标单元格 → 插入 → 图片 → 本地图片，插入 `thumbs/` 里对应的图 → 右键图片 → “切换为嵌入单元格图片”（或插入时直接选“嵌入单元格”）。
   - 在 Excel 里：选中单元格 → 插入 → 图片 → 放置在单元格中 → 此设备。
   - 每做完一个商品保存一次。完成后照常跑第 6 步的 `check_excel.py`。

## 示例：制表子代理提示词模板
```
你负责生成竞品图片 Excel，不做分析。

运行：python -X utf8 <SKILL_DIR>/scripts/build_excel.py --work "<work>"
- 成功：再运行 python -X utf8 <SKILL_DIR>/scripts/check_excel.py --work "<work>" --stage table，
  把输出原样返回。
- 失败：按 <SKILL_DIR>/references/excel-spec.md 的“制表工具优先级”处理，先修脚本问题，实在不行再操作电脑。

最后只回复 JSON：{"files": [...build_excel 输出的 files...], "check": {...check_excel 的输出...}, "method": "script|computer-use", "notes": "..."}
```

## 特殊情况
- **图片很多、文件很大**：每张图约 80KB，每个商品（主图 + A+）约 2.5MB，50 个商品约 120MB，属于正常。超过 200MB 时告诉用户，问是否只保留主图表、不要 A+ 表。
- **文件正在被 WPS/Excel 打开**：脚本自动另存为 `-v2.xlsx`，在最终报告里说明。
- **方案里的参考图找不到**：单元格写“参考图缺失：ASIN 位置”，`check_excel.py` 会报第 5 步错误。

## 输出格式
`build_excel.py` 打印：
```json
{"files": [{"format": "wps", "file": "...-WPS.xlsx", "images": 1280, "size_mb": 104.6},
           {"format": "excel", "file": "...-Excel.xlsx", "images": 1280, "size_mb": 102.3}],
 "products": 41, "removed": 9, "with_analysis": 41, "plan_rows": 8}
```
