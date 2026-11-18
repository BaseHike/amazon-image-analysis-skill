# 相关产品筛选

## 用途
从 BS 榜前 N 名里剔除和用户产品不是同一种东西的商品，只留真正的竞品。结果写进 `filter.json`，由 `apply_filter.py` 校验。

## 适用条件
- 第 1 步拿到 `bs_list.json` 后做第 1 轮（看标题）。
- 第 2 步抓完详情后做第 2 轮（看详情属性）。

## 规则

### 先定标准（只做一次）
读 `seed.json`（种子 ASIN 的标题、`product_type`、`attributes`），写出两项标准：
- **形态 form**：产品是什么东西，用名词短语，例如“食物加热垫”“镁补充剂胶囊/软糖/粉剂”。
- **材质 material**：种子标题或属性里明确写了材质才填，例如“硅胶”；材质对这个类目没有意义（保健品、食品）时填 `null`。
  材质指**产品主体、和使用对象直接接触那一面**的材质（加热垫就是垫面），不是控制盒、外壳、电线、底座、配件的材质。把这句话写进 `basis`。
- **依据 basis**：写明从哪里得出的，例如“标题 Silicone Food Warming Mat + Material: Silicone”。

形态或材质判断不了（标题含糊、属性缺失、种子本身是套装）→ 先问用户，不要猜。

### 判定标准
**形态和材质都一致才保留。** 不往后补齐，只在前 N 名里筛，保留下来的沿用原始 BS 排名。

| 情况 | 结论 |
|---|---|
| 形态不同（加热垫 vs 加热柜/保温箱/保温袋） | remove |
| 形态相同、材质不同（硅胶加热垫 vs 玻璃面板加热板） | remove |
| 形态、材质都相同，只是尺寸、颜色、品牌不同 | keep |
| `material` 为 null 时只看形态 | 按形态判定 |
| 套装：主产品符合，另外附带配件（加热垫 + 隔热手套） | ask |
| 标题写了多种材质（silicone & glass） | ask |
| 详情里没有材质字段，标题也没写 | 先按下面“材质证据”查图片，仍无结论 → ask |
| 详情 Material 和标题/图片说法矛盾（Material: ABS，但标题或图上写硅胶垫面） | 按下面“材质证据”判定 |
| 配件、替换件（加热垫的电源线） | remove |
| 第 1 轮标题为 null（BS 页没给标题） | pending，第 2 轮再判 |

### 材质证据（第 2 轮用）
亚马逊的 `Material` 字段经常填的是外壳或控制盒的材质，不能只看它。按下面顺序找**主体材质**的证据，找到明确说法就停：
1. 标题里写明主体材质（如 “Silicone Warming Mat”）。
2. `attributes` 里专指主体的字段（Surface Material / Top Material / Mat Material 等）。
3. 打开这个商品 `thumbs/` 里的主图、副图和 A+ 图（用 Read 看图），找图上写的材质说明（如 “Food-grade Silicone Surface”）。
4. 以上都没有，才用 `Material` 字段。

- 前 3 条里有明确说法，且 `Material` 字段写的是别的材质 → 按前 3 条判定，`reason` 写清证据和字段差异，例如“图上标明 Silicone 垫面；Material: ABS 指控制面板”。
- 证据互相矛盾（标题写硅胶，图上写玻璃面板）→ ask。
- 只用亚马逊页面和已下载的图片做判断，不要搜第三方网站。

`product_type`（亚马逊的商品类型代码，如 `MINERAL_SUPPLEMENT`、`FOOD_WARMER`）和种子不同，是形态不同的强信号，但仍以标题和图片描述为准。

### 第 1 轮（标题，第 1 步结束前）
1. 对 `bs_list.json` 的每个商品给出 keep / remove / pending / ask。只看标题能确定形态不同的才 remove；能确定材质不同的也可以直接 remove。
2. 把所有 ask 汇总成**一张清单一次问用户**，按回答改成 keep 或 remove。
3. 运行 `apply_filter.py --round 1`，按 `to_scrape` 进入第 2 步。

### 第 2 轮（详情，第 2 步结束后）
1. 读每个保留和 pending 商品的 `product.json` 里的 `title`、`product_type`、`attributes`（重点看 Material / Item Form / Product Type 一类字段）。
2. pending 的商品同时判形态和材质；keep 的商品复核材质。
3. ask 同样汇总成一张清单一次问用户。
4. 运行 `apply_filter.py --round 2`：所有商品必须是 keep 或 remove，被剔除商品的文件夹会移到 `removed/`。

## 示例
标准：`{"form": "食物加热垫", "material": "硅胶", "basis": "种子标题 Silicone Food Warming Mat，Material: Silicone"}`

| 排名 | 标题（节选） | 轮次 | 结论 | 原因 |
|---|---|---|---|---|
| 1 | Silicone Food Warming Mat, Foldable... | 1 | keep | 形态、材质一致 |
| 4 | Electric Warming Cabinet 3-Tier... | 1 | remove | 加热柜，形态不同 |
| 6 | Glass Warming Tray with Temperature... | 1 | remove | 玻璃面板加热板，材质不同 |
| 9 | Warming Mat + 2 Silicone Gloves Set | 1 | ask → 用户答 keep | 套装，主产品一致 |
| 37 | （无标题） | 1 | pending | BS 页未给标题 |
| 37 | Food Warming Mat... Material: Tempered Glass | 2 | remove | 详情材质为钢化玻璃，图上也是玻璃面板 |
| 5 | Warming Mat for Food... Material: ABS | 2 | keep | 副图 3 标明 Silicone 垫面；Material: ABS 指控制面板 |

## 特殊情况
- **抓取失败的商品**（验证码、三种工具都失败）：第 2 轮不能以“没有详情、无法确认材质”为由剔除。标题已经能看出形态或材质不同的，按第 1 轮理由剔除（`round` 写 1）；否则保留为 keep，表里显示“【抓取失败】”，在最终报告里列出。`apply_filter.py` 会拦截这种剔除。
- 种子 ASIN 本身也在榜单里：照常判定（通常 keep）。
- 剔除后一个都不剩，或少于 3 个：停下来告诉用户，问是否放宽标准（例如不限材质）或换类目，不要自己放宽。
- 同一品牌的多个变体（不同 ASIN）都在榜上：都保留，各占一行。
- **没法问用户**（非交互运行，例如 `codex exec` 或定时任务；或用户说过“不用问我”）：ask 不能停在那里。按形态优先、再按“材质证据”给出 keep 或 remove，`reason` 以“自行判定：”开头写明依据，最终报告里逐条列出这些商品，让用户事后核对。
- 用户对 ask 的回答可以形成新规则（如“套装都算”），把它写进 `standard.basis`，后面同类情况直接按规则判定，不再问。

## 输出格式
`<work>/filter.json`：
```json
{
  "standard": {"form": "食物加热垫", "material": "硅胶", "basis": "..."},
  "decisions": [
    {"asin": "B0XXXXXXX1", "decision": "keep", "round": 1, "reason": "形态、材质一致"},
    {"asin": "B0XXXXXXX2", "decision": "remove", "round": 1, "reason": "加热柜，形态不同"},
    {"asin": "B0XXXXXXX3", "decision": "pending", "round": 1, "reason": "BS 页无标题"}
  ]
}
```
- 每个 `bs_list.json` 里的 ASIN 恰好一条，不能多也不能少。
- `remove` 必须写原因（会进 Excel 的“剔除记录”表）。
- 第 2 轮改结论时，同时把 `round` 改成 2、更新 `reason`。
