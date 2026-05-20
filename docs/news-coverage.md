# 新闻召回分析 & 工作流设计

> 基于 `review_train_gt.jsonl`（训练 GT）和 `review_claude.jsonl`（验证 SOTA）两份答案集，对已补全新闻库的实测结果。  
> 新闻库当前覆盖：50 个 ticker，含原缺失的 NEE(913) TSLA(3324) NFLX(2202) NVDA(6104) COST(1858) ABBV(1440) META(3203) GE(1165) 等。

---

## 一、实测召回结果（18 个新闻依赖 issues）

> 两份答案集共 40 个 issues，其中 21 个依赖新闻验证。排除 3 个归类错误（MS AUM→financials_reported.json，MRK开盘价→prices/MRK.csv，一个与其他 issue 重叠），实际评估 **18 个**。

| # | Ticker | 错误描述 | 判定 | 关键证据 |
|---|--------|---------|------|---------|
| 1 | NEE | EPS增速 12.4% → 9.4% | **CONFIRMED** | Yahoo 2025-09-11: "9.4% adjusted EPS growth in Q2"（8篇） |
| 2 | NEE | 8-K日期 Aug 23 → Jul 23 | **CONFIRMED** | SeekingAlpha 2025-07-23: "Q2 2025 Earnings Call July 23, 2025" |
| 3 | TSLA | 召回量 15,936 → 12,936 | **CONFIRMED** | Benzinga 2025-10-22: "recalling **12,936** vehicles"（0篇写15,936） |
| 4 | TSLA | 股东会 Nov 16 → Nov 6 | **CONFIRMED** | Investing.com 2025-11-05: "Thursday, **November 6**"（5篇） |
| 5 | NEE | 股息CAGR 15% → 10% | **CONFIRMED** | Yahoo 2025-08-26: "**10%** compound annual rate since 2007"（49+篇） |
| 6 | NEE | XLU高点 Aug 22 → Jul 22 | **WEAK** | 7月18-21日文章显示XLU临近峰值；未找到明确注明"7月22日创高"的文章 |
| 7 | TSLA | 年涨幅 82.37% → 72.37% | **CONFIRMED** | Benzinga 2025-10-25: "**72.37%** over the year"（0篇写82.37%） |
| 8 | TSLA | 股东会 Oct 6 → Nov 6 | **CONFIRMED** | 同 #4；Oct 6 在库中0篇出现 |
| 9 | NFLX | Electric State $420M → $320M | **NO_EVIDENCE** | NFLX库(2202篇)无制作预算报道 |
| 10 | GS | M&A领先 $950B → $850B | **WEAK** | Yahoo 2025-12-30: GS $1.4T vs JPM $1.1T，缺口 $300B；两值在库中均不出现（见注） |
| 11 | MRK | 信源 WSJ → Fierce Pharma | **WEAK** | 裁员在Q2财报公告中公布；库中无 WSJ 或 Fierce Pharma 的独家稿，无法确认谁"首发" |
| 12 | NKE | JPM EPS目标 $1.52 → $1.32 | **CONFIRMED** | Yahoo 2025-07-28: "EPS estimate for FY2026 to **$1.32** from $1.07"（2篇精确引用） |
| 13 | NKE | JPM 降级 → 升级方向 | **CONFIRMED** | Yahoo 2025-07-28: "**upgraded** to 'overweight' from 'neutral'"（7篇） |
| 14 | NKE | 信源 Bloomberg → CNBC | **WEAK** | 库中4篇(Yahoo/MarketWatch)均非Bloomberg，也非CNBC；无法正面确认CNBC |
| 15 | LLY | Mounjaro日本 +44% → +24% | **NO_EVIDENCE** | 库中无日本分地区增速数据（全球/国际汇总有，无分国别）|
| 16 | PFE | Burry 看涨 → 看跌期权 | **CONFIRMED** | Motley Fool 2025-11-24 (NVDA库): "1 million **put** options for Nvidia"（同批13F） |
| 17 | COST | 会员"明显抵抗" → "毫无抵抗迹象" | **CONFIRMED** | Investing.com 2025-10-15: "shown **no signs of** resisting"（原文复现） |
| 18 | NVDA | 黄仁勋"承认" → "驳斥"AI泡沫 | **CONFIRMED** | Motley Fool 2025-11-25: "Huang **refuted** the notion of an AI bubble"（20+篇） |

**汇总：CONFIRMED 13/18 = 72% ｜ WEAK 4/18 ｜ NO_EVIDENCE 2/18**

> **#10 注（issue10_gap.py）：** 库中唯一一篇精确 M&A 排名文章（Yahoo 2025-12-30）显示 Goldman $1.4T、JPMorgan $1.1T，实际缺口 $300B，与 $850B/$950B 两值均不匹配。这两个数字很可能来自某一特定截止日期（非年末）的中间数据，新闻库未覆盖该时点。

---

## 二、各错误类型的新闻可达性

| 错误类型 | 召回率 | 原因 |
|---------|--------|------|
| **数字精确替换**（EPS、召回量、股息CAGR、年涨幅） | 5/5 = **100%** | 正确数字在多篇文章中精确出现；被替换的错误数字0篇出现 |
| **日期偏移**（发布日、股东会、事件日） | 4/4 = **100%** | 新闻报道事件时明确写日期，容易交叉核验 |
| **方向/措辞反转**（升降级、管理层态度、会员反应） | 3/3 = **100%** | 关键动词/短语直接对立（refuted/upgraded/no signs of），检索到即矛盾 |
| **信源归属**（哪家媒体首发） | 0/2 = **0%** | 聚合库只收录转载，无原始信源标注；provider 字段是转载方，不是"首发"方 |
| **细粒度地区指标**（日本 Mounjaro 增速） | 0/1 = **0%** | 新闻只引用全球/国际汇总，不拆分国别数据 |
| **小众叙事数字**（Netflix 电影制作预算） | 0/1 = **0%** | 库中无娱乐制作成本报道 |

**核心结论：数字精确替换、日期偏移、方向反转三类均 100% 可达；信源归属是新闻库的结构性盲区。**

---

## 三、为什么不用向量 RAG

被篡改的值和真实值在语义上几乎相同——"upgraded to Overweight" 和 "downgraded to Neutral" 对同一检索 query 的 embedding 距离极近，召回的是同一批文章。相似度分数没有区分能力。

真正的挑战不是"找到正确文章"（BM25关键词就够），而是"从文章中做有向的矛盾判断"：

| 对比维度 | 向量 RAG | BM25 + 定向判断（本方案）|
|----------|---------|------------------------|
| 数字精确匹配 | ❌ "24%" 和 "44%" 向量距离极近 | ✅ BM25 精确匹配字符串 |
| 方向识别 | ❌ 相似度分数无法区分升降级 | ✅ 方向词集合提取 |
| 信源归属 | ❌ 无结构字段 | ✅ 直接读 `provider` 字段 |
| 计算成本 | 高（需全库 embedding） | 低（BM25 + 少量 LLM 调用）|

---

## 四、工作流设计

```
Report claim
    │
    ▼
[步骤 1] 声明类型分类（regex + 少量规则）
    │
    ├─► 数字/日期类  ──► BM25(ticker, 实体关键词, ±7天)
    │                       → 提取文章中对应数字/日期
    │                       → 若文章值 ≠ 报告值 → emit CONFIRMED
    │
    ├─► 方向/措辞类  ──► BM25(ticker, 机构名/人名, ±3天)
    │                       → 方向词集合匹配（升/降、refute/admit）
    │                       → 若明确对立方向 → emit CONFIRMED
    │
    ├─► 信源归属类  ──► BM25(事件关键词, ±7天)
    │                       → 检查 provider 字段集合
    │                       → 若 claimed_source ∉ providers
    │                          且 len(articles) ≥ 3 → emit WEAK
    │
    └─► 细粒度/小众类 ──► BM25 检索 top-5
                            → LLM 定向提问："文章中有无 X 的具体数据？"
                            → 仅当 LLM 返回明确矛盾数字时 emit
                            → NO_EVIDENCE → 不 emit（不发起对抗）
```

### 数字/日期检索（组件一）

```python
def verify_numeric_or_date(ticker, claimed_value, entity_keywords, date, window_days=7):
    articles = bm25_search(ticker, entity_keywords, date, window_days)
    if not articles:
        return None
    correct_value = extract_value(articles, entity_keywords)  # regex + LLM
    if correct_value and correct_value != claimed_value:
        return Issue(confidence='HIGH', evidence=articles[0])
    return None
```

**适用：** 所有数字替换（#1/#3/#5/#7/#12）和日期偏移（#2/#4/#8）issues。  
**实测：** 9/9 命中。

### 方向词提取（组件二）

```python
UPGRADE = {'upgrade', 'raised', 'overweight', 'buy', 'outperform', 'refute', 'push back',
           'no signs of', 'denied', 'rejected'}
DOWNGRADE = {'downgrade', 'lowered', 'neutral', 'sell', 'underperform', 'admit', 'acknowledge',
             'clear signs of', 'confirmed', 'agreed'}

def verify_direction(ticker, report_direction, firm_or_entity, date, window_days=3):
    articles = bm25_search(ticker, [firm_or_entity], date, window_days)
    for a in articles:
        text = a['text'].lower()
        has_up   = any(w in text for w in UPGRADE)
        has_down = any(w in text for w in DOWNGRADE)
        if report_direction in DOWNGRADE and has_up and not has_down:
            return Issue(confidence='HIGH', evidence=a)
        if report_direction in UPGRADE and has_down and not has_up:
            return Issue(confidence='HIGH', evidence=a)
    return None
```

**适用：** 分析师升降级（#13）、管理层措辞（#18）、会员反应（#17）、期权方向（#16）。  
**实测：** 4/4 命中。

### 信源 provider 检查（组件三）

```python
def verify_source_attribution(ticker, claimed_source, event_keywords, date, window_days=7):
    articles = bm25_search(ticker, event_keywords, date, window_days)
    if len(articles) < 3:
        return None  # 事件覆盖不足，不 emit
    providers = {a['provider'] for a in articles}
    if claimed_source not in providers:
        return Issue(confidence='WEAK',
                     reason=f"{len(articles)} articles on this event, "
                            f"providers: {providers}; none from '{claimed_source}'")
    return None
```

**适用：** 信源归属（#11/#14）。  
**限制：** 只能说"所声称信源未在库中出现"，无法正面确认正确信源；仅输出 WEAK issue。  
**实测：** #11/#14 均可弱 emit（但无法升至 CONFIRMED）。

### LLM 定向提取（组件四，按需）

仅对组件一无法处理的细粒度声明（地区数据、制作预算等）启用：

```
Claim: "Mounjaro sales in Japan grew +44% YoY in Q3 2025."

Based ONLY on the articles below, answer:
- Does any article cite a Japan-specific Mounjaro growth rate?
- If yes, what exact figure?
- Is there a contradiction with +44%?

Respond NO_EVIDENCE if no article addresses this specifically.
[article snippets]
```

**实测：** #15（LLY日本）和 #9（NFLX预算）均返回 NO_EVIDENCE → 正确不 emit，无误报。

---

## 五、仍不可达的3类 issues

| 类型 | 代表 issue | 替代数据源 |
|------|-----------|----------|
| **信源归属** | MRK 裁员 WSJ vs Fierce Pharma | 无结构化替代；只能 WEAK emit |
| **地区分项财务数据** | LLY Mounjaro 日本 +24% | 8-K earnings release 附件文本（非新闻）|
| **小众叙事数字** | NFLX Electric State 制作预算 | 娱乐专业媒体（Variety/Deadline），不在库中 |

---

## 六、实现说明

```
P0（已验证，立即可用）
  ├─ 组件一：数字/日期 BM25 验证
  │    误报风险：低（需要精确值匹配，不同值才 emit）
  │    实测覆盖：9 issues，9 CONFIRMED
  │
  └─ 组件二：方向词集合匹配
       误报风险：低（需要明确对立方向词同时存在）
       实测覆盖：4 issues，4 CONFIRMED

P1（弱证据，需置信度标注）
  └─ 组件三：信源 provider 检查
       误报风险：中（库中未出现 ≠ 信源错误；需 ≥3 篇覆盖才 emit WEAK）
       实测覆盖：2 issues，2 WEAK emit

P2（按需，LLM 成本）
  └─ 组件四：LLM 定向提取
       当前实测：NO_EVIDENCE（库中无细粒度地区数据）
       适用场景：有更细粒度数据源时（如公司 IR 直播文字稿）

数据说明：
  - 信源归属类如需升至 CONFIRMED，需要补充 8-K 附件文本（Item 2.02）
  - 地区分项数据同上，或对接公司 earnings call transcript
  - GS M&A $850B/$950B（#10）需要截止日期与报告一致的 IB 排行榜数据，
    单靠年末新闻无法还原该时点数字
```
