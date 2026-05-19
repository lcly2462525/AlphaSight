Translate each Chinese equity-research claim into concise English
KEYWORDS, for retrieval against an English corpus of SEC filings
(10-K/10-Q/8-K), earnings press releases, and financial news. The
English MUST use the exact vocabulary those documents use, not generic
translations — BM25 only matches the corpus wording.

Hard rules:
- Keep ALL numbers, dates, percentages, currency amounts, fiscal
  periods (Q1/Q2/FY2025), and ticker symbols EXACTLY as written.
- Output short English keyword phrases, NOT fluent sentences. No
  explanations. Items already in English: copy unchanged.
- When a term has a standard filing abbreviation, output BOTH the full
  term and the abbreviation (e.g. "Boeing Defense, Space & Security
  (BDS)") so it matches whichever the corpus uses.

Use this standard financial vocabulary:
- Metrics: 营收/收入/销售额 -> revenue / net sales; 净利润/净利 ->
  net income; 营业利润/经营利润 -> operating income; 毛利率 -> gross
  margin; 营业利润率 -> operating margin; 自由现金流 -> free cash flow
  (FCF); 经营性现金流 -> operating cash flow; 每股收益/每股盈利 ->
  earnings per share (EPS); 摊薄每股收益 -> diluted EPS; 同比 ->
  year-over-year (YoY); 环比 -> quarter-over-quarter (QoQ); 资本开支
  -> capital expenditures (capex); 积压订单/在手订单 -> backlog.
- Earnings vs expectations: 一致预期/市场预期/分析师预期 -> consensus
  estimate; 超预期 -> beat; 不及预期/逊于预期 -> miss; 业绩指引/指引
  -> guidance; 上调指引 -> raised guidance; 下调指引 -> cut guidance.
- Filings & events: 年报 -> annual report (10-K); 季报 -> quarterly
  report (10-Q); 临时报告/重大事项公告 -> 8-K; 招股说明书 -> S-1;
  委托书/股东大会材料 -> proxy statement (DEF 14A); 披露 -> disclosed
  / filed; 报道 -> reported.
- Corporate actions: 回购 -> share repurchase / buyback; 股息/分红
  -> dividend; 除息日 -> ex-dividend date; 拆股 -> stock split; 召回
  -> recall; 评级上调 -> upgrade; 评级下调 -> downgrade; 收购/并购
  -> acquisition / merger; 重组 -> restructuring.
- Prices: 收盘价 -> closing price; 开盘价 -> opening price; 52周最高/
  最低 -> 52-week high / low; 年初至今 -> year-to-date (YTD).
- Segments: translate to the issuer's exact reported segment name with
  its filing abbreviation, e.g. 民用飞机/商用飞机部门 -> Commercial
  Airplanes (BCA); 防务/国防部门 -> Defense, Space & Security (BDS);
  全球服务部门 -> Global Services (BGS).

# CLAIMS (JSON array)
{items}

Return JSON only:
{{"t": [{{"idx": 0, "en": "<english keywords>"}}, ...]}}
Every input index must appear exactly once.
