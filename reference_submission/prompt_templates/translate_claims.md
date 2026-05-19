Translate each Chinese equity-research claim into concise English
KEYWORDS, for retrieval against an English corpus of SEC filings
(10-K/10-Q/8-K), earnings press releases, and financial news. The
English MUST use the exact vocabulary those documents use, not generic
translations — BM25 only matches the corpus wording.

Hard rules:
- NORMALIZE Chinese number units into a standard English magnitude so
  the value is machine-comparable. Convert: 万 -> ×10^4 (ten-thousand),
  百万 -> million, 亿 -> ×10^8 (hundred-million), 十亿 -> billion,
  万亿 -> trillion. Examples: 224.9亿美元 -> $22.49 billion;
  9.13亿美元 -> $913 million; 净利润913百万美元 -> net income
  $913 million; 1.2万亿美元 -> $1.2 trillion. Keep the digits faithful
  to the converted magnitude; never drop the unit.
- Keep all OTHER numbers, percentages, fiscal periods (Q1/Q2/FY2025),
  and ticker symbols EXACTLY as written. Keep dates in ISO
  (YYYY-MM-DD) or "Month D, YYYY" form so they stay machine-parseable.
- Output short English keyword phrases, NOT fluent sentences. No
  explanations. Items already in English: copy unchanged.
- When a term has a standard filing abbreviation, output BOTH the full
  term and the abbreviation (e.g. "Boeing Defense, Space & Security
  (BDS)") so it matches whichever the corpus uses.

The English equity reports in this task use a fixed structural
vocabulary — translate to THESE exact words:
- 营收/收入/顶线 -> top-line / revenue / net sales; 业绩快照/财报概览
  -> earnings snapshot; 业绩序列 -> earnings sequence; 股价表现/股价
  走势 -> stock action; 可比公司/同业 -> peer set / peers; 前九个月/
  前三季度累计 -> nine months ended <date> (use this exact phrasing for
  fiscal-YTD cumulative figures); 季度截至 -> quarter ending <date>;
  净利息收入 -> net interest income (NII).
- Metrics: 净利润/净利 -> net income; 营业利润/经营利润 -> operating
  income; 毛利率 -> gross margin; 营业利润率 -> operating margin;
  自由现金流 -> free cash flow (FCF); 经营性现金流 -> operating cash
  flow; 每股收益/每股盈利 -> earnings per share (EPS); 摊薄每股收益 ->
  diluted EPS; 同比 -> year-over-year (YoY); 环比 ->
  quarter-over-quarter (QoQ); 资本开支 -> capital expenditures
  (capex); 积压订单/在手订单 -> backlog.
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
- Segments / business lines: translate to the issuer's EXACT reported
  segment name as it appears in that company's 10-K/10-Q (e.g. for a
  datacenter chipmaker 数据中心业务 -> Data Center segment; for a bank
  净息差 -> net interest margin (NIM)). Do not invent a generic name;
  use the standard segment label the filing would use, and include any
  common abbreviation in parentheses so BM25 matches either form.

# CLAIMS (JSON array)
{items}

Return JSON only:
{{"t": [{{"idx": 0, "en": "<english keywords>"}}, ...]}}
Every input index must appear exactly once.
