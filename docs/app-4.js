// i18n 安全兜底：vpL(zh,en) 单一来源是 vp_i18n.js。挂到 window 而非 const/let 本地别名——
// 5 个 app-*.js 共享同一全局脚本作用域，多文件各自声明同名会因重复声明抛 SyntaxError（见 app-1.js 同款注释）。
// vp_i18n.js 尚未加载/接线时退化为恒返回 zh，页面纯中文不崩。
if (typeof window.vpL !== "function") window.vpL = function (zh, en) { return zh; };

// ═══════════════════════════════════════════════════════
//  SpaceX SPCX IPO 追踪器
// ═══════════════════════════════════════════════════════
const SPCX_LISTING_DATE = "2026-06-12";
const SPCX_ISSUE_USD    = 135;
const SPCX_MY_SHARES    = 16;   // 站长实际获配股数（localStorage 未填时的默认值）

function renderSPCXTracker() {
  const el = document.getElementById("spcx-tracker");
  if (!el) return;
  const today = localDateStr();
  const hasListed = today >= SPCX_LISTING_DATE;

  // Countdown
  const listDt  = new Date(2026, 5, 12); // June 12 local time
  const daysLeft = Math.max(0, Math.ceil((listDt - new Date()) / 86400000));

  const savedShares = +(localStorage.getItem("spcx_shares") || SPCX_MY_SHARES);
  const savedPrice  = +(localStorage.getItem("spcx_price")  || 0);
  const savedCostAUD= +(localStorage.getItem("spcx_cost_aud")|| 0);

  // AUD value
  const issueAUD = savedShares * SPCX_ISSUE_USD / _portAudRate;
  const currAUD  = savedShares > 0 && savedPrice > 0 ? savedShares * savedPrice / _portAudRate : 0;
  const plAUD    = currAUD - issueAUD;
  const plPct    = issueAUD > 0 ? plAUD / issueAUD * 100 : 0;
  const gainPct  = savedPrice > 0 ? (savedPrice - SPCX_ISSUE_USD) / SPCX_ISSUE_USD * 100 : 0;

  // Pre-listing countdown
  if (!hasListed) {
    el.innerHTML = `
      <div class="spcx-countdown">
        <div class="spcx-big-num">${daysLeft}</div>
        <div class="spcx-big-label">${vpL("天后上市","days until listing")}<br><span style="font-size:0.7rem">${vpL("2026年6月12日 Nasdaq","Jun 12, 2026 · Nasdaq")}</span></div>
      </div>
      <div style="font-size:0.8rem;display:flex;flex-direction:column;gap:.3rem;margin-bottom:.75rem;">
        <div class="spcx-row"><span style="color:var(--muted)">${vpL("发行价","Issue price")}</span><span style="font-weight:700">US$135</span></div>
        <div class="spcx-row"><span style="color:var(--muted)">${vpL("交易所","Exchange")}</span><span>Nasdaq</span></div>
        <div class="spcx-row"><span style="color:var(--muted)">${vpL("澳洲通道","AU channel")}</span><span>CommSec IPO</span></div>
      </div>
      <div style="font-size:0.78rem;color:var(--muted);margin-bottom:.3rem">${vpL("我的申购（股数）","My allocation (shares)")}</div>
      <input class="spcx-input" type="number" min="0" step="1" placeholder="${vpL("等待分配结果后填写","Fill in once allocation is confirmed")}"
        value="${savedShares||""}" data-spcx-save="shares">
      ${savedShares > 0 ? `<div style="font-size:0.75rem;color:var(--muted);margin-top:.35rem">
        ${vpL(`≈ A$${issueAUD.toFixed(0)}（按发行价US$135 · AUD/USD≈${_portAudRate.toFixed(3)}）`, `≈ A$${issueAUD.toFixed(0)} (at issue price US$135 · AUD/USD≈${_portAudRate.toFixed(3)})`)}</div>` : ""}
      <div class="spcx-decision-box" style="background:rgba(155,89,182,.1);border-left:3px solid var(--purple);">
        <strong style="color:var(--purple)">${vpL("🧭 站长个人观点","🧭 Site owner's personal take")}</strong>
        <span style="font-size:0.68rem;color:var(--muted)">${vpL("· 非模型信号 · 仅个人看法","· Not a model signal · personal opinion only")}</span><br>
        ${vpL("1. 分配结果出来后填写实际获得股数","1. Fill in your actual allotted shares once the allocation result is out")}<br>
        ${vpL("2. 高关注度 IPO 上市首日常高于发行价（历史差异极大，见详情面板的首日分布图）","2. High-profile IPOs often trade above issue price on day one (historically highly variable — see the day-1 distribution chart in the detail panel)")}<br>
        ${vpL("3. 我个人会：<strong>卖一半锁利润，留一半长持</strong>","3. My personal plan: <strong>sell half to lock in profit, hold the other half long-term</strong>")}
        <div style="font-size:0.66rem;color:var(--muted);margin-top:.3rem">${vpL("⚠ 这是我的主观判断，不是数据信号；你的剧本可不同","⚠ This is my personal judgment, not a data signal — your plan may differ")}</div>
      </div>`;
    return;
  }

  // Post-listing —— 以下是站长个人剧本（第一人称），非模型信号
  let decisionHtml = "";
  if (savedPrice > 0) {
    if (gainPct > 50)      decisionHtml = `<span style="color:#f1c40f">${vpL(`🔥 溢价${gainPct.toFixed(0)}%：我会卖出至少一半锁利润`, `🔥 Up ${gainPct.toFixed(0)}%: I'd sell at least half to lock in profit`)}</span>`;
    else if (gainPct > 25) decisionHtml = `<span style="color:#2ecc71">${vpL(`溢价${gainPct.toFixed(0)}%：我会卖 1/3–1/2，其余长持`, `Up ${gainPct.toFixed(0)}%: I'd sell 1/3–1/2, hold the rest long-term`)}</span>`;
    else if (gainPct > 10) decisionHtml = `<span style="color:#2ecc71">${vpL(`溢价${gainPct.toFixed(0)}%：我会先持有，等更高位再减`, `Up ${gainPct.toFixed(0)}%: I'd hold for now and trim at a higher level`)}</span>`;
    else if (gainPct > 0)  decisionHtml = `<span style="color:#f1c40f">${vpL("⏸ 小幅溢价：我会持有观察","⏸ Slightly up: I'd hold and watch")}</span>`;
    else if (gainPct > -15)decisionHtml = `<span style="color:#e67e22">${vpL("轻微破发：我会持有等反弹","Slightly below issue: I'd hold and wait for a bounce")}</span>`;
    else                   decisionHtml = `<span style="color:#e74c3c">${vpL("大幅破发：我会重新评估，倾向长期持有","Well below issue: I'd reassess, leaning toward holding long-term")}</span>`;
  }

  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.65rem;">
      <span style="background:#27ae6022;color:#27ae60;border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">${vpL("已上市 ✓","Listed ✓")}</span>
      <span style="color:var(--muted);font-size:0.75rem">2026-06-12 Nasdaq</span>
    </div>
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:.3rem">${vpL("实际获配股数","Actual allotted shares")}</div>
    <input class="spcx-input" type="number" min="0" step="1" placeholder="${vpL("股数","Shares")}"
      value="${savedShares||""}" data-spcx-save="shares">
    <div style="font-size:0.78rem;color:var(--muted);margin:.5rem 0 .3rem">${vpL("当前市价 (USD)","Current price (USD)")}</div>
    <input class="spcx-input" type="number" min="0" step="0.01" placeholder="${vpL("发行价135","Issue price 135")}"
      value="${savedPrice||""}" data-spcx-save="price">
    ${savedShares > 0 && savedPrice > 0 ? `
    <div class="spcx-pl-row" style="margin-top:.65rem;">
      <div class="spcx-pl-val"><span class="u-cap">${vpL("成本","Cost")}</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">${vpL("市值","Value")}</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">${vpL("盈亏","P&L")}</span><br>
        <strong style="color:${plAUD>=0?'#2ecc71':'#e74c3c'}">${plAUD>=0?'+':''}A$${plAUD.toFixed(0)}<br>${plPct>=0?'+':''}${plPct.toFixed(1)}%</strong></div>
    </div>
    <div class="spcx-decision-box" style="background:rgba(155,89,182,.08);border-left:3px solid var(--purple);">
      <strong style="color:var(--purple);font-size:0.72rem">${vpL("🧭 站长个人剧本","🧭 Site owner's personal plan")}</strong>
      <span style="font-size:0.66rem;color:var(--muted)">${vpL("· 非模型信号","· Not a model signal")}</span><br>${decisionHtml}
    </div>` : `<div style="font-size:0.78rem;color:var(--muted);margin-top:.5rem">${vpL("填写股数和价格查看盈亏","Fill in shares and price to see P&L")}</div>`}`;
}

function saveSPCXData(field, val) {
  if (field === 'shares') localStorage.setItem("spcx_shares", val);
  if (field === 'price')  localStorage.setItem("spcx_price",  val);
  renderSPCXTracker();
  updateSPCXCalc();
}

// SPCX right-column detail panel
function renderSPCXDetail() {
  // Historical tech IPO first-day performance data
  const ipoData = [
    { name:"Airbnb\n2020",   gain:113 }, { name:"Snowflake\n2020", gain:112 },
    { name:"Twitter\n2013",  gain:73  }, { name:"Reddit\n2024",    gain:48  },
    { name:"Palantir\n2020", gain:37  }, { name:"ARM\n2023",       gain:25  },
    { name:"Rivian\n2021",   gain:29  }, { name:"Lyft\n2019",      gain:9   },
    { name:"Uber\n2019",     gain:-8  }, { name:"Robinhood\n2021", gain:-8  },
  ];
  const colors = ipoData.map(d => d.gain > 30 ? "#27ae60" : d.gain > 0 ? "#2ecc71" : "#e74c3c");
  Plotly.newPlot("chart-spcx-ipo", [{
    type:"bar", x: ipoData.map(d=>d.name), y: ipoData.map(d=>d.gain),
    marker:{ color: colors },
    text: ipoData.map(d => (d.gain >= 0 ? "+" : "") + d.gain + "%"),
    textposition:"outside", cliponaxis:false,
    hovertemplate: vpL("<b>%{x}</b><br>首日涨幅: %{y}%<extra></extra>", "<b>%{x}</b><br>Day-1 gain: %{y}%<extra></extra>"),
  }], {
    ...DARK, margin:{t:20,b:55,l:35,r:10},
    yaxis:{...DARK.yaxis, title: vpL("首日涨幅 %","Day-1 gain %")},
    xaxis:{...DARK.xaxis, tickfont:{size:9}},
    shapes:[{type:"line",x0:-0.5,x1:9.5,y0:0,y1:0,line:{color:"#555",dash:"dot",width:1}}],
  }, {responsive:true});

  document.getElementById("spcx-decision-detail").innerHTML =
    `<div style="font-size:0.78rem;line-height:1.6;">
       <strong>${vpL("首日历史规律（客观）：","Day-1 historical pattern (objective):")}</strong>${vpL("高关注度科技 IPO 首日涨幅历史上差异极大（-8% 到 +113%，见左图）。","High-profile tech IPO day-1 gains have historically varied hugely (-8% to +113%, see chart at left).")}
       ${vpL("这是历史分布，不代表 SPCX 会怎样。","This is a historical distribution, not a prediction of what SPCX will do.")}
     </div>

     <div style="margin-top:.75rem;background:rgba(155,89,182,.08);border-left:3px solid var(--purple);border-radius:0 6px 6px 0;padding:.6rem .8rem;">
       <strong style="color:var(--purple)">${vpL("🧭 站长个人剧本","🧭 Site owner's personal plan")}</strong>
       <span style="font-size:0.68rem;color:var(--muted)">${vpL("· 非模型信号 · 仅个人看法","· Not a model signal · personal opinion only")}</span><br>
       <span style="font-size:0.8rem;line-height:1.6;">${vpL("溢价 &gt;25% → 我会卖一半锁利润；溢价 &lt;10% → 我会先全持等中期；破发我不恐慌（我个人看好长期）。","Up &gt;25% → I'd sell half to lock in profit; up &lt;10% → I'd hold the full position for the medium term; if it's below issue I won't panic (I'm personally bullish long-term).")}
       <span style="color:var(--muted);font-size:0.7rem;">${vpL("⚠ 这是我的主观判断，不是数据信号，你的剧本可不同。","⚠ This is my personal judgment, not a data signal — your plan may differ.")}</span></span>
     </div>

     <div style="margin-top:.75rem;font-size:0.78rem;line-height:1.65;">
       <strong>${vpL("🧭 纳入与解禁机制（客观）：","🧭 Index-inclusion & lock-up mechanics (objective):")}</strong><br>
       ${vpL(`<b>纳指100 快速纳入</b>：常规在 12 月年度重构纳入（需约 3 个月 seasoning），但纳斯达克
       <b>2026-05 生效的 "Fast Entry" 规则</b>允许总市值排名进前 40（约 ≥$1000 亿）的超大型新股豁免 seasoning，
       公告后约 <b>15 个交易日</b>在年度重构外快速纳入——<b>SpaceX 体量（约 $1.75 万亿）符合，大概率走这条快速通道</b>。
       （研究普遍发现：纳入效应近年减弱、且常在公告时被提前定价，不宜当择时信号。）`,
       `<b>Nasdaq-100 fast entry</b>: normally added at the December annual reconstitution (needs ~3 months seasoning), but Nasdaq's
       <b>"Fast Entry" rule effective 2026-05</b> lets mega-cap new listings ranked in the top 40 by market cap (roughly ≥$100bn) skip seasoning,
       joining within about <b>15 trading days</b> of announcement outside the annual reconstitution — <b>SpaceX's size (~$1.75 trillion) qualifies, so it's likely to take this fast-track route</b>.
       (Research generally finds the inclusion effect has weakened in recent years and is often priced in ahead of the announcement — don't treat it as a timing signal.)`)}<br>
       ${vpL(`<b>标普500</b>：由委员会自由裁量（无"够格即纳入"），硬门槛含 <b>最近季度 GAAP 净利为正且最近四季合计为正 + 流通股≥50% + 市值门槛</b>。
       SpaceX 流通比例低（仅售约 5.56 亿股、马斯克锁 366 天 + 高投票权），<b>短期进标普门槛很高</b>。`,
       `<b>S&amp;P 500</b>: entirely at the index committee's discretion (no "qualify and you're in" rule); hard requirements include <b>positive GAAP earnings in the latest quarter and over the trailing four quarters, ≥50% public float, and a market-cap threshold</b>.
       SpaceX's float is low (only ~556 million shares sold, with Musk locked up for 366 days plus super-voting shares), so <b>the bar for a near-term S&amp;P inclusion is very high</b>.`)}<br>
       ${vpL(`<b>解禁（已披露，分级释放）</b>：S-1（2026-05-20）列明非单一 180 天，而是 <b>分阶段</b>：
       Q2 财报后早期投资者可卖 20%（股价触发条件下再加 10%）；IPO 后第 <b>70/90/105/120/135 天各释放 7%</b>；
       Q3 财报后再 28%；<b>第 180 天后不受限</b>。<b>马斯克及部分核心投资者承诺持有 ≥366 天</b>。这些是真实的供给压力时点。`,
       `<b>Lock-up (disclosed, staged release)</b>: the S-1 (2026-05-20) specifies not a single 180-day cliff but a <b>staged schedule</b>:
       early investors can sell 20% after Q2 earnings (plus 10% more under a price trigger); <b>7% releases each at days 70/90/105/120/135</b> post-IPO;
       another 28% after Q3 earnings; <b>fully unrestricted after day 180</b>. <b>Musk and some core investors have committed to holding ≥366 days</b>. These are real supply-pressure dates.`)}
     </div>
     <div style="color:var(--muted);font-size:0.72rem;margin-top:.5rem;">${vpL("机制为公开规则/已披露文件的客观说明（截至 2026-06）；个人剧本为站长主观看法。均非投资建议。","Mechanics are an objective summary of public rules/disclosed filings (as of 2026-06); the personal plan is the site owner's subjective opinion. Neither is investment advice.")}</div>`;

  updateSPCXCalc();
}

function updateSPCXCalc() {
  const el = document.getElementById("spcx-calc");
  if (!el) return;
  const sharesIn = parseFloat(document.getElementById("spcx-shares-input")?.value || 0) || 0;
  const priceIn  = parseFloat(document.getElementById("spcx-price-input")?.value  || 0) || 0;
  // also sync with left-panel inputs and localStorage
  if (sharesIn) { localStorage.setItem("spcx_shares", sharesIn); renderSPCXTracker(); }
  if (priceIn)  { localStorage.setItem("spcx_price",  priceIn);  renderSPCXTracker(); }

  const shares = sharesIn || +(localStorage.getItem("spcx_shares")||SPCX_MY_SHARES);
  const price  = priceIn  || +(localStorage.getItem("spcx_price") ||0);
  const rate   = _portAudRate || 0.64;

  const issueAUD = shares * SPCX_ISSUE_USD / rate;
  const currAUD  = shares > 0 && price > 0 ? shares * price / rate : 0;
  const plAUD    = currAUD - issueAUD;
  const plPct    = issueAUD > 0 ? plAUD / issueAUD * 100 : 0;
  const gainPct  = price > 0 ? (price - SPCX_ISSUE_USD) / SPCX_ISSUE_USD * 100 : 0;
  const halfAUD  = currAUD / 2;
  const halfProfit = halfAUD - issueAUD / 2;

  if (!shares) { el.innerHTML = `<span style="color:var(--muted)">${vpL("输入申购股数后显示","Enter your allotted shares to see this")}</span>`; return; }

  let recHtml = "";
  if (price > 0) {
    if (gainPct > 25)      recHtml = `<div style="color:#27ae60;font-weight:600">${vpL(`建议：卖出一半 → 锁定 A$${halfProfit.toFixed(0)} 利润，留一半长期持有`, `Suggestion: sell half → lock in A$${halfProfit.toFixed(0)} profit, hold the rest long-term`)}</div>`;
    else if (gainPct > 5)  recHtml = `<div style="color:#2ecc71;font-weight:600">${vpL("建议：持有观察，等待更好的卖出时机","Suggestion: hold and watch, wait for a better exit")}</div>`;
    else if (gainPct >= 0) recHtml = `<div style="color:#f1c40f;font-weight:600">${vpL("建议：持有，SpaceX长期前景强劲","Suggestion: hold — SpaceX's long-term outlook is strong")}</div>`;
    else                   recHtml = `<div style="color:#e67e22;font-weight:600">${vpL("破发：短期持有等待反弹，长期看好","Below issue: hold short-term for a bounce, bullish long-term")}</div>`;
  }

  el.innerHTML = `
    <div class="spcx-pl-row">
      <div class="spcx-pl-val"><span class="u-cap">${vpL("股数","Shares")}</span><br><strong>${shares}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">${vpL("成本(AUD)","Cost (AUD)")}</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      ${currAUD > 0 ? `<div class="spcx-pl-val"><span class="u-cap">${vpL("市值(AUD)","Value (AUD)")}</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">${vpL("盈亏","P&L")}</span><br>
        <strong style="color:${plAUD>=0?'#2ecc71':'#e74c3c'}">${plAUD>=0?'+':''}A$${plAUD.toFixed(0)}<br>${plPct>=0?'+':''}${plPct.toFixed(1)}%</strong></div>` : ""}
    </div>
    ${currAUD > 0 && gainPct > 5 ? `<div style="font-size:0.78rem;color:var(--muted)">${vpL(`卖一半可入袋 <strong style="color:#2ecc71">A$${halfProfit.toFixed(0)}</strong>`, `Selling half would bank <strong style="color:#2ecc71">A$${halfProfit.toFixed(0)}</strong>`)}</div>` : ""}
    ${recHtml}`;
}

// ── 盘中轻量报价（quotes.json，CI 每10分钟产出；页面每5分钟自动重拉）──
let QUOTES = null;
async function loadQuotes() {
  try {
    const r = await fetch("quotes.json?_=" + Date.now());
    if (r.ok) QUOTES = await r.json();
  } catch(e) { /* 文件可能尚未生成，靠 stocks.json 兜底 */ }
  renderSPCXMonitor();
}
setInterval(loadQuotes, 5 * 60 * 1000);   // IPO 首笔成交等场景：无需手动刷新自动上墙

// ── SPCX 监视卡：盘中报价(10分钟) > 流水线收盘价(30分钟) + 解禁/税务倒计时 ──
function _spcxDaysFrom(listDt, days) {
  const d = new Date(listDt.getTime() + days * 86400000);
  return d;
}
function renderSPCXMonitor() {
  const el = document.getElementById("spcx-monitor");
  if (!el) return;
  const sp = STOCKS?.spcx;
  const listDt = new Date(2026, 5, 12);
  const now = new Date();
  const daysListed = Math.max(1, Math.floor((now - listDt) / 86400000) + 1);  // 上市日=第1天

  // ① 价格卡：盘中报价(quotes.json, ~10分钟) 优先，流水线收盘(stocks.json) 兜底。同源数据，国内访客可用。
  const q = QUOTES?.quotes?.SPCX;
  let priceHtml, autoPrice = null;
  // 占位价识别：成交量为 0，或"最后成交时间"早于今天且价格还钉在发行价
  // ——大型 IPO 开盘竞价常持续 1-3 小时，期间行情源只有发行价占位，不是真成交
  const tradeMs = q?.ts ? q.ts * 1000 : null;
  const tradeStale = tradeMs != null && (Date.now() - tradeMs > 20 * 3600 * 1000);
  const awaitingFirstTrade = q && q.price === SPCX_ISSUE_USD &&
        ((q.vol === 0) || tradeStale || q.prev_close == null);
  if (q && q.price && awaitingFirstTrade && daysListed <= 1) {
    // 有活的订单簿时展示 bid/ask 中值指示价（明确标注非成交价）
    const mid = q.bid && q.ask ? (q.bid + q.ask) / 2 : null;
    const midHtml = mid ? `
        <span style="font-size:1.25rem;font-weight:800;">≈US$${mid.toFixed(2)}</span>
        <span style="font-weight:700;color:${mid>=SPCX_ISSUE_USD?'#2ecc71':'#e74c3c'}">${mid>=SPCX_ISSUE_USD?'+':''}${((mid/SPCX_ISSUE_USD-1)*100).toFixed(1)}% ${vpL("vs 发行价","vs issue price")}</span>
        <span style="color:var(--muted);font-size:0.72rem">${vpL(`订单簿指示价（bid ${q.bid} / ask ${q.ask} 中值）· 非成交价`, `Order-book indicative price (bid ${q.bid} / ask ${q.ask} midpoint) · not a traded price`)}</span>` : "";
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        ${midHtml}
        <span style="font-size:0.95rem;font-weight:700;color:#f1c40f;">${vpL("⏳ 等待首笔成交确认","⏳ Waiting for first trade confirmation")}</span>
        <span style="color:var(--muted);font-size:0.74rem">${vpL("超大型 IPO 首笔成交常在开盘后 1–3 小时进入公开行情源；确认后此处自动切换为成交价。","For mega-cap IPOs the first trade often only reaches public quote feeds 1–3 hours after the open; this panel auto-switches to the traded price once confirmed.")}</span>
      </div>`;
  } else if (q && q.price) {
    const vsIssue = (q.price / SPCX_ISSUE_USD - 1) * 100;
    const up = vsIssue >= 0;
    const tradeT = tradeMs
      ? new Date(tradeMs).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
      : (QUOTES.generated ? new Date(QUOTES.generated).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "");
    autoPrice = q.price;
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        <span style="font-size:1.3rem;font-weight:800;">US$${q.price.toFixed(2)}</span>
        <span style="font-weight:700;color:${up?'#2ecc71':'#e74c3c'}">${up?'+':''}${vsIssue.toFixed(1)}% ${vpL("vs 发行价","vs issue price")}</span>
        ${q.chg_pct != null ? `<span style="color:${q.chg_pct>=0?'#2ecc71':'#e74c3c'};font-size:0.8rem">${vpL("日内","Intraday")} ${q.chg_pct>=0?'+':''}${q.chg_pct}%</span>` : ""}
        <span style="color:var(--muted);font-size:0.72rem">${vpL(`盘中报价 · 成交 ${tradeT}`, `Intraday quote · traded ${tradeT}`)}</span>
      </div>`;
  } else if (sp && sp.last) {
    const up = sp.vs_issue_pct >= 0;
    autoPrice = sp.last;
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        <span style="font-size:1.3rem;font-weight:800;">US$${sp.last.toFixed(2)}</span>
        <span style="font-weight:700;color:${up?'#2ecc71':'#e74c3c'}">${up?'+':''}${sp.vs_issue_pct.toFixed(1)}% ${vpL("vs 发行价","vs issue price")}</span>
        ${sp.chg_1d != null ? `<span style="color:${sp.chg_1d>=0?'#2ecc71':'#e74c3c'};font-size:0.8rem">${vpL("日","Day")} ${sp.chg_1d>=0?'+':''}${sp.chg_1d}%</span>` : ""}
        <span style="color:var(--muted);font-size:0.72rem">${vpL(`收盘数据 ${sp.date} · 区间 ${sp.low}–${sp.high}`, `Close data ${sp.date} · range ${sp.low}–${sp.high}`)}</span>
      </div>`;
  } else {
    priceHtml = `<span style="color:var(--muted);font-size:0.8rem">${vpL("尚无 SPCX 数据（上市首个交易时段后出现；盘中可点上方\"获取价格\"手动取）","No SPCX data yet (appears after the first trading session; during market hours you can click \"Fetch price\" above to fetch manually)")}</span>`;
  }
  // 用户没手填过价格时，自动用最新价算盈亏
  if (autoPrice != null) {
    const inp = document.getElementById("spcx-price-input");
    if (inp && !inp.value && !+(localStorage.getItem("spcx_price") || 0)) {
      inp.value = autoPrice.toFixed(2);
      updateSPCXCalc();
    }
  }

  // ② 解禁/里程碑倒计时（S-1 披露的分级释放 + CGT 12个月折扣日）
  const milestones = [
    { d: 70,  label: vpL("解禁 7%（第70天）","7% unlock (day 70)") },
    { d: 90,  label: vpL("解禁 7%（第90天）","7% unlock (day 90)") },
    { d: 105, label: vpL("解禁 7%（第105天）","7% unlock (day 105)") },
    { d: 120, label: vpL("解禁 7%（第120天）","7% unlock (day 120)") },
    { d: 135, label: vpL("解禁 7%（第135天）","7% unlock (day 135)") },
    { d: 180, label: vpL("全面解禁（第180天）","Full unlock (day 180)") },
    { d: 366, label: vpL("马斯克持有承诺到期","Musk's lock-up commitment expires") },
    { d: 367, label: vpL("🇦🇺 CGT 50%折扣生效（持有满12个月后卖出）","🇦🇺 CGT 50% discount kicks in (sell after 12-month hold)") },
  ].map(m => {
    const dt = _spcxDaysFrom(listDt, m.d);
    const left = Math.ceil((dt - now) / 86400000);
    return { ...m, dt, left };
  });
  const next = milestones.find(m => m.left > 0);
  const rows = milestones.map(m => {
    const passed = m.left <= 0;
    const isNext = m === next;
    const dateStr = `${m.dt.getFullYear()}-${String(m.dt.getMonth()+1).padStart(2,"0")}-${String(m.dt.getDate()).padStart(2,"0")}`;
    return `<div style="display:flex;justify-content:space-between;gap:.5rem;padding:.18rem 0;font-size:0.78rem;
                 ${passed ? "color:var(--muted);text-decoration:line-through;" : ""}
                 ${isNext ? "font-weight:700;" : ""}">
      <span>${isNext ? "→ " : ""}${m.label}</span>
      <span style="white-space:nowrap;${isNext ? "color:#f1c40f;" : "color:var(--muted);"}">${dateStr}${passed ? "" : ` · ${vpL(`${m.left}天`, `${m.left}d`)}`}</span>
    </div>`;
  }).join("");

  el.innerHTML = `
    <div style="background:var(--surface2);border-radius:7px;padding:.75rem .9rem;margin-bottom:1rem;">
      <div style="font-size:0.75rem;color:var(--muted);margin-bottom:.35rem;">${vpL(`📡 SPCX 监视 · 上市第 ${daysListed} 天 · 流水线自动更新（盘中约30分钟一次）`, `📡 SPCX watch · day ${daysListed} since listing · pipeline auto-updates (~every 30 min during market hours)`)}</div>
      ${priceHtml}
      <div style="margin-top:.65rem;border-top:1px solid var(--border);padding-top:.5rem;">
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.25rem;">${vpL("⏳ 供给压力与税务时点（S-1 披露 + 澳洲 CGT）","⏳ Supply pressure & tax dates (S-1 disclosure + Australian CGT)")}</div>
        ${rows}
      </div>
      ${sp?.supply ? `
      <div style="margin-top:.55rem;border-top:1px solid var(--border);padding-top:.5rem;font-size:0.76rem;">
        <span style="color:var(--muted)">${vpL("📦 供给面：","📦 Supply side: ")}</span>
        ${vpL("IPO 实际新发 ≈5.56亿股（<b>占总股本仅 ~7.5%</b>，筹码稀缺的来源）","The IPO actually issued ≈556 million shares (<b>only ~7.5% of total shares outstanding</b>, the source of the scarcity)")}
        ${sp.supply.float_pct != null ? ` · ${vpL(`Yahoo 流通口径 ${sp.supply.float_pct}%<span style="color:var(--muted);font-size:0.68rem">（含锁定股，勿当可交易量）</span>`, `Yahoo float basis ${sp.supply.float_pct}%<span style="color:var(--muted);font-size:0.68rem"> (includes locked-up shares — don't treat as tradable float)</span>`)}` : ""}
        ${sp.supply.short_pct_float != null ? ` · ${vpL(`做空占流通 <b>${sp.supply.short_pct_float}%</b>`, `Short interest as % of float <b>${sp.supply.short_pct_float}%</b>`)}` : ""}
        ${sp.supply.inst_held_pct != null ? ` · ${vpL(`机构持仓 <b>${sp.supply.inst_held_pct}%</b>`, `Institutional ownership <b>${sp.supply.inst_held_pct}%</b>`)}` : ""}
      </div>` : ""}
      <div style="margin-top:.55rem;background:var(--surface);border-radius:6px;padding:.5rem .7rem;font-size:0.74rem;line-height:1.6;color:var(--muted);">
        ${vpL(`<b style="color:var(--text)">解禁怎么读（解禁 ≠ 必然抛售）：</b>解禁只是"可以卖"，会不会卖看持有人结构——
        <b>早期 VC 基金</b>有结构性卖出动机（基金到期要回收资金分给 LP）；<b>员工</b>有分散化动机（财富集中单一股票）；
        <b>马斯克</b>承诺持 366 天且为保控制权基本不会卖。学术证据（Field &amp; Hanka，约2,000家IPO样本）：
        解禁日平均异常收益约 <b style="color:#e74c3c">-1.5%</b>，幅度不大但方向稳定；SpaceX 的<b>分级解禁</b>（5×7%）
        正是为了把冲击摊平。真正值得盯的信号：每波解禁前后的<b>成交量放大</b>与<b>借券费率变化</b>，而非解禁日本身。`,
        `<b style="color:var(--text)">How to read unlocks (unlock ≠ automatic selling):</b> an unlock only means shares "can" be sold — whether they actually are depends on the holder structure:
        <b>early VC funds</b> have a structural incentive to sell (funds nearing maturity need to return capital to LPs); <b>employees</b> have a diversification incentive (wealth concentrated in one stock);
        <b>Musk</b> has committed to holding for 366 days and, to keep control, is unlikely to sell regardless. Academic evidence (Field &amp; Hanka, ~2,000-IPO sample):
        average abnormal return around unlock day is about <b style="color:#e74c3c">-1.5%</b> — modest but directionally consistent; SpaceX's <b>staged unlock</b> (5×7%)
        is designed precisely to spread out the impact. The signal actually worth watching is <b>volume spikes</b> and <b>stock-borrow fee changes</b> around each unlock wave, not the unlock date itself.`)}
      </div>
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.45rem;">
        ${vpL("CGT 日期按上市日申购计，实际以你的成交日为准。非投资建议。","CGT dates assume allocation on the listing date; use your own trade date for actual tax purposes. Not investment advice.")}
      </div>
    </div>`;
}

// 拉取 SPCX 最新报价并填入盈亏计算器。
// 注：旧版直连 query1.finance.yahoo.com，浏览器跨域(CORS)必被拦截 → 永远"获取失败"；
// 且属境外第三方运行时依赖（国内访客打不开、违反本项目"同源自托管"原则）。
// 改为重拉同源 quotes.json（服务端流水线每~10分钟抓好的报价），无 CORS、国内可用。
async function fetchSPCXPrice() {
  const btn = document.getElementById("spcx-price-btn");
  const old = btn ? btn.textContent : "";
  if (btn) btn.textContent = vpL("⏳ 获取中...","⏳ Fetching...");
  try {
    await loadQuotes();                              // 重拉 quotes.json 并重渲染监视卡
    const q = QUOTES?.quotes?.SPCX;
    const price = (q && q.price) ? q.price
                : (STOCKS?.spcx?.last || null);      // 报价缺失时退用收盘数据
    if (price) {
      const inp = document.getElementById("spcx-price-input");
      if (inp) { inp.value = price.toFixed(2); updateSPCXCalc(); }
      localStorage.setItem("spcx_price", price);
    } else {
      alert(vpL("报价暂未刷新（流水线约每10分钟更新 quotes.json）。请稍后再试，或在下方手动输入当前价。","Quote hasn't refreshed yet (the pipeline updates quotes.json roughly every 10 minutes). Try again later, or enter the current price manually below."));
    }
  } catch(e) {
    alert(vpL("刷新失败，请在下方手动输入当前价格。","Refresh failed — please enter the current price manually below."));
  } finally {
    if (btn) btn.textContent = old || vpL("📡 获取价格","📡 Fetch price");
  }
}

// ═══════════════════════════════════════════════════════
//  加密恐惧贪婪指数
// ═══════════════════════════════════════════════════════
function fgMeta(score) {
  if (score <= 24) return { color:"#e74c3c", cn: vpL("极度恐惧","Extreme fear"),  advice: vpL("📈 历史最佳逆向买入时机（别人恐惧时贪婪）","📈 Historically the best contrarian buying window (be greedy when others are fearful)") };
  if (score <= 44) return { color:"#e67e22", cn: vpL("恐惧","Fear"),      advice: vpL("可考虑分批建仓，情绪偏负面但未极端","Could consider building a position in tranches — sentiment is negative but not extreme") };
  if (score <= 55) return { color:"#f1c40f", cn: vpL("中性","Neutral"),      advice: vpL("市场情绪中性，结合其他指标综合判断","Sentiment is neutral — weigh it alongside other indicators") };
  if (score <= 74) return { color:"#2ecc71", cn: vpL("贪婪","Greed"),      advice: vpL("⚠️ 注意追高风险，短期回调概率上升","⚠️ Watch chasing risk — odds of a short-term pullback are rising") };
  return                  { color:"#27ae60", cn: vpL("极度贪婪","Extreme greed"),  advice: vpL("🔴 历史规律：此区间后续往往回调，适量减仓","🔴 Historical pattern: this zone is often followed by a pullback — consider trimming") };
}

async function fetchFearAndGreed() {
  const el = document.getElementById("fear-greed-section");
  if (!el) return;
  el.innerHTML = `<span style="color:var(--muted);font-size:0.78rem">${vpL("加载中...","Loading...")}</span>`;
  try {
    // 优先用同源 quotes.json(服务端 quick_quotes 抓的恐惧贪婪)——中国访客不必直连境外 API
    if (typeof loadQuotes === "function") { try { await loadQuotes(); } catch (e) { /* 用已有 QUOTES */ } }
    let data = QUOTES?.fear_greed;
    if (!data || !data.length) {
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 4000);   // 兜底直连境外，境内易卡→4s 上限，免长 TCP 超时
      try {
        const r = await fetch("https://api.alternative.me/fng/?limit=7&format=json", { signal: ctrl.signal });
        if (!r.ok) throw new Error("HTTP " + r.status);
        data = (await r.json()).data || [];
      } finally { clearTimeout(to); }
    }
    renderFearGreed(data);
  } catch(e) {
    el.innerHTML = `<div style="font-size:0.78rem;color:var(--muted)">
      ${vpL("恐惧贪婪指数暂时无法加载","Fear & Greed index temporarily unavailable")}
      <button data-fear-greed-retry
        style="margin-left:.5rem;background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:2px 8px;border-radius:4px;font-size:0.72rem;cursor:pointer;">${vpL("重试","Retry")}</button>
    </div>`;
  }
}

function renderFearGreed(data) {
  const el = document.getElementById("fear-greed-section");
  if (!el || !data.length) return;
  const cur = data[0];
  const score = parseInt(cur.value);
  const m = fgMeta(score);

  // D2 微图表:7点走势(oldest first)改用 vpSpark 折线——语义纪律:趋势线中性 --mut,
  // 不按恐贪档位染色(装饰不造信号感);50=中性参考线。档位色仅留给大数字/游标(自带现状 label)。
  const spark = data.slice(0,7).reverse().map(d => parseInt(d.value)).filter(v => isFinite(v));

  const nextUpdate = cur.time_until_update
    ? vpL(`· ${Math.round(+cur.time_until_update/3600)}h后更新`, `· updates in ${Math.round(+cur.time_until_update/3600)}h`)
    : "";

  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.5rem;">
      <div>
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.15rem">
          ${vpL("加密恐惧&贪婪指数","Crypto Fear &amp; Greed index")} <span style="opacity:.6">(alternative.me${nextUpdate})</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:.45rem;">
          <span style="font-size:2rem;font-weight:800;line-height:1;color:${m.color}">${score}</span>
          <span style="font-size:0.9rem;font-weight:700;color:${m.color}">${m.cn}</span>
        </div>
      </div>
      <div style="text-align:right;min-width:70px;">
        <div style="font-size:0.68rem;color:var(--muted);margin-bottom:.3rem;">${vpL("7天走势","7-day trend")}</div>
        <div id="fg-spark" title="${spark.join(" → ")}"></div>
      </div>
    </div>
    <div class="fg-gauge-track">
      <div class="fg-needle" style="left:${score}%;background:${m.color}"></div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--muted);margin-bottom:.45rem;">
      <span>0 ${vpL("极度恐惧","Extreme fear")}</span><span>50 ${vpL("中性","Neutral")}</span><span>100 ${vpL("极度贪婪","Extreme greed")}</span>
    </div>
    <div style="font-size:0.78rem;color:${m.color};line-height:1.4">${m.advice}</div>
  `;
  const fgSp = document.getElementById("fg-spark");
  if (fgSp && typeof vpSpark === "function") {
    vpSpark(fgSp, spark, { color: "var(--mut)", fill: true, w: 96, h: 26, refLine: 50 });
  }
}

// ═══════════════════════════════════════════════════════
//  澳洲 CGT 税务计算器
// ═══════════════════════════════════════════════════════
// ──「显示货币」切换（AUD / USD / CNY）─────────────────────────────
// ⚠ 税务红线：calculateCGT 永远在 AUD 里算（澳洲 CGT 法定货币）。
//   货币切换【只换显示】，绝不改税务计算本身。输入框仍按 AUD 单价填。
const CGT_CURRENCIES = {
  AUD: { symbol: "A$", label: "AUD 澳元", locale: "en-AU" },
  USD: { symbol: "US$", label: "USD 美元", locale: "en-US" },
  CNY: { symbol: "¥",  label: "CNY 人民币", locale: "zh-CN" },
};
// 渲染时按当前语言取显示用币种名——不改 CGT_CURRENCIES 结构本身（symbol/locale 是计算/格式化依据，不动）。
function _cgtCurLabel(cur) {
  const en = { AUD: "AUD (A$)", USD: "USD (US$)", CNY: "CNY (¥)" };
  return vpL(CGT_CURRENCIES[cur].label, en[cur] || cur);
}
let _cgtFX = null;                  // { aud_usd, usd_cny, asof, generated } 来自 fx_rates.json
let _cgtDisplayCur = (typeof localStorage !== "undefined" &&
                      localStorage.getItem("cgt_display_cur")) || "AUD";
if (!CGT_CURRENCIES[_cgtDisplayCur]) _cgtDisplayCur = "AUD";

// 1 AUD = ? 目标币。AUD 优先用盘中实时 aud_rate（quotes.json），fx_rates.json 兜底。
function _cgtRateFromAUD(cur) {
  if (cur === "AUD") return 1;
  // AUD→USD：优先实时 QUOTES.aud_rate（≈0.70），否则 fx_rates.json
  const audUsd = (typeof QUOTES !== "undefined" && QUOTES && QUOTES.aud_rate)
    ? QUOTES.aud_rate : (_cgtFX && _cgtFX.aud_usd);
  if (cur === "USD") return audUsd || null;
  if (cur === "CNY") {            // AUD→USD→CNY 两段相乘
    const usdCny = _cgtFX && _cgtFX.usd_cny;
    return (audUsd && usdCny) ? audUsd * usdCny : null;
  }
  return null;
}
// 把 AUD 金额格式化成所选显示币种（带正负号/小数位）。换算不可得时回退 AUD 并标注。
function _cgtFmt(audAmount, { sign = false, decimals = 2 } = {}) {
  let cur = _cgtDisplayCur;
  let rate = _cgtRateFromAUD(cur);
  if (rate == null) { cur = "AUD"; rate = 1; }   // 汇率缺失：诚实回退 AUD，不瞎换
  const v = audAmount * rate;
  const c = CGT_CURRENCIES[cur];
  const num = Math.abs(v).toLocaleString(c.locale,
    { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const pre = sign ? (v >= 0 ? "+" : "−") : (v < 0 ? "−" : "");
  return `${pre}${c.symbol}${num}`;
}

// 拉取 fx_rates.json（同源，国内访客可用）。失败不阻塞——AUD 始终可算。
async function loadCgtFXRates() {
  try {
    const r = await fetch("fx_rates.json?_=" + Date.now());
    if (r.ok) _cgtFX = await r.json();
  } catch (e) { /* 文件可能尚未生成；切 USD/CNY 时会提示并回退 AUD */ }
  renderCgtCurrencySelector();
  // 若结果已算过，按新汇率重渲染
  if (document.getElementById("cgt-result")?.innerHTML.trim()) calculateCGT();
}

function setCgtDisplayCur(cur) {
  if (!CGT_CURRENCIES[cur]) return;
  _cgtDisplayCur = cur;
  try { localStorage.setItem("cgt_display_cur", cur); } catch (e) {}
  renderCgtCurrencySelector();
  if (document.getElementById("cgt-result")?.innerHTML.trim()) calculateCGT();
}

// 把货币选择器 + 税务红线提示注入到计算器区域（结果容器上方）。纯 JS 渲染，不动 HTML。
function renderCgtCurrencySelector() {
  const result = document.getElementById("cgt-result");
  if (!result) return;
  let host = document.getElementById("cgt-currency-switch");
  if (!host) {
    // 用字面 id="..." 注入（也便于前端审计的 id 正则识别这个动态容器）
    result.insertAdjacentHTML("beforebegin", '<div id="cgt-currency-switch"></div>');
    host = document.getElementById("cgt-currency-switch");
  }
  if (!host) return;
  const btns = Object.keys(CGT_CURRENCIES).map(cur => {
    const active = cur === _cgtDisplayCur;
    const avail = cur === "AUD" || _cgtRateFromAUD(cur) != null;
    const style = active
      ? "background:rgba(52,152,219,.18);border:1px solid #3498db;color:#3498db;font-weight:700;"
      : "background:var(--surface2);border:1px solid var(--border);color:var(--muted);";
    const dis = avail ? "" : "opacity:.45;cursor:not-allowed;";
    return `<button type="button" data-cgt-cur="${cur}" ${avail ? "" : "disabled"}
      title="${avail ? "" : vpL("汇率暂不可用（fx_rates.json 未生成）","Exchange rate unavailable (fx_rates.json not yet generated)")}"
      style="${style}${dis}padding:.28rem .7rem;border-radius:5px;font-size:0.76rem;cursor:pointer;">${esc(_cgtCurLabel(cur))}</button>`;
  }).join("");
  // 当前换算口径（让人看清用了哪条汇率），AUD 不显示
  let rateNote = "";
  if (_cgtDisplayCur !== "AUD") {
    const rate = _cgtRateFromAUD(_cgtDisplayCur);
    const sym = CGT_CURRENCIES[_cgtDisplayCur].symbol;
    rateNote = rate != null
      ? `<span style="color:var(--muted);font-size:0.7rem;">${vpL(`当前：1 AUD ≈ ${sym}${rate.toFixed(4)}${_cgtFX && _cgtFX.asof ? "（汇率 " + esc(_cgtFX.asof) + "）" : ""}`, `Current: 1 AUD ≈ ${sym}${rate.toFixed(4)}${_cgtFX && _cgtFX.asof ? " (rate as of " + esc(_cgtFX.asof) + ")" : ""}`)}</span>`
      : `<span style="color:#e67e22;font-size:0.7rem;">${vpL("该币种汇率暂不可用，已回退按 AUD 显示","This currency's exchange rate is unavailable — falling back to AUD display")}</span>`;
  }
  host.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:.4rem;margin:.6rem 0 .35rem;">
      <span style="font-size:0.76rem;color:var(--muted);">${vpL("显示货币：","Display currency: ")}</span>
      ${btns}
      ${rateNote}
    </div>
    <div style="background:rgba(231,126,34,.08);border:1px solid rgba(231,126,34,.3);border-radius:6px;
                padding:.5rem .7rem;font-size:0.72rem;line-height:1.55;color:var(--muted);margin-bottom:.5rem;">
      ${vpL(`⚠️ <b>税务红线</b>：澳洲 CGT 法定按 <b>AUD</b> 计税，且买入/卖出各按<b>成交日汇率</b>计税。
      本货币切换<b>仅方便查看/估算</b>，<b>不能替代</b>按成交日 AUD 记账报税；用单一当前汇率换算会让税额失真。
      输入框仍请按 <b>AUD 单价</b>填写。`,
      `⚠️ <b>Tax red line</b>: Australian CGT is legally assessed in <b>AUD</b>, with buy/sell each converted at the <b>exchange rate on the trade date</b>.
      This currency toggle is <b>for viewing/estimation convenience only</b> — it <b>cannot replace</b> proper AUD record-keeping at trade-date rates for tax purposes; converting with a single current rate will distort the tax figure.
      Please keep entering the input fields in <b>AUD per-unit price</b>.`)}
    </div>`;
}

function prefillCGT() {
  const asset = document.getElementById("cgt-asset")?.value;
  if (!asset || asset === "custom") return;
  const port = loadPortfolio();
  const item = port.find(p => p.ticker === asset);
  if (!item) return;
  // Pre-fill quantity
  const qtyEl = document.getElementById("cgt-qty");
  if (qtyEl && item.qty) qtyEl.value = item.qty;
  // Pre-fill sell price from live prices (convert USD→AUD)
  const liveUSD = portfolioPrices[asset] || item.priceUSD;
  const sellEl = document.getElementById("cgt-sell-aud");
  if (sellEl && liveUSD) sellEl.value = (liveUSD / _portAudRate).toFixed(4);
  // Pre-fill buy price from cost basis
  const costEl = document.getElementById("cgt-buy-aud");
  if (costEl && item.costUSD) costEl.value = (item.costUSD / _portAudRate).toFixed(4);
}

function calculateCGT() {
  const qty     = parseFloat(document.getElementById("cgt-qty")?.value) || 0;
  const buyAUD  = parseFloat(document.getElementById("cgt-buy-aud")?.value) || 0;
  const sellAUD = parseFloat(document.getElementById("cgt-sell-aud")?.value) || 0;
  const buyDate = document.getElementById("cgt-buy-date")?.value || "";
  const taxRate = parseFloat(document.getElementById("cgt-tax-rate")?.value) || 32.5;
  const el = document.getElementById("cgt-result");
  if (!el) return;

  if (!qty || !buyAUD || !sellAUD) {
    el.innerHTML = `<div style="color:var(--muted);font-size:0.82rem;padding:.5rem 0;">${vpL("请填写数量、买入价和卖出价。","Please fill in quantity, buy price and sell price.")}</div>`;
    return;
  }

  const totalCost     = qty * buyAUD;
  const totalProceeds = qty * sellAUD;
  const rawGain       = totalProceeds - totalCost;
  const isGain        = rawGain > 0;

  // 12-month CGT discount
  let heldMonths = 0, eligible50 = false;
  if (buyDate) {
    heldMonths = Math.round((new Date() - new Date(buyDate)) / (1000*60*60*24*30.44));
    eligible50 = isGain && heldMonths >= 12;
  }

  const taxableGain = eligible50 ? rawGain * 0.5 : rawGain;
  const taxOnGain   = taxableGain > 0 ? taxableGain * (taxRate / 100) : 0;
  const medicare    = taxableGain > 0 ? taxableGain * 0.02 : 0;
  const totalTax    = taxOnGain + medicare;
  const netGain     = rawGain - totalTax;
  const netPct      = totalCost > 0 ? netGain / totalCost * 100 : 0;

  // Break-even sell price (where net gain = 0)
  const effectiveTaxRate = eligible50 ? (taxRate/100 + 0.02) * 0.5 : (taxRate/100 + 0.02);
  const breakEvenAUD = totalCost / qty / (1 - effectiveTaxRate);

  const gain_color = rawGain >= 0 ? "#2ecc71" : "#e74c3c";
  const assetName = document.getElementById("cgt-asset")?.value || vpL("资产","asset");

  // ⚠ 以上全部在 AUD 里算（税务红线）。下面只把【显示】换算到所选货币：_cgtFmt(aud)。
  const curMeta = CGT_CURRENCIES[_cgtRateFromAUD(_cgtDisplayCur) == null ? "AUD" : _cgtDisplayCur];
  const curTag = curMeta.symbol === "A$" ? ""
    : `<span style="color:var(--muted);font-weight:400;font-size:0.7rem;margin-left:.3rem;">${vpL(`· 显示币种 ${esc(curMeta.label.split(" ")[0])}（仅换算显示，税仍按 AUD）`, `· Display currency ${esc(curMeta.label.split(" ")[0])} (display only — tax still assessed in AUD)`)}</span>`;

  el.innerHTML = `
    <div style="background:var(--surface2);border-radius:8px;padding:1rem;margin-top:.5rem;">
      <div style="font-size:0.8rem;font-weight:600;color:var(--muted);margin-bottom:.5rem;">
        ${assetName !== "custom" && assetName ? assetName : ""}  ${vpL(`${qty} 个 · 持有${heldMonths ? heldMonths+"个月" : "未知"}`, `${qty} units · held ${heldMonths ? heldMonths+" months" : "unknown"}`)}
        ${eligible50 ? `<span style="background:rgba(46,204,113,.2);color:#2ecc71;border-radius:3px;padding:1px 6px;font-size:0.7rem;margin-left:.3rem;">${vpL("✓ 12月折扣","✓ 12-month discount")}</span>` : ""}${curTag}
      </div>
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL("买入总成本","Total cost basis")}</span><span>${_cgtFmt(totalCost)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL("卖出总收入","Total proceeds")}</span><span>${_cgtFmt(totalProceeds)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL("资本利得（税前）","Capital gain (pre-tax)")}</span><span style="color:${gain_color};font-weight:700">${_cgtFmt(rawGain, {sign:true})}</span></div>
      ${eligible50 ? `<div class="cgt-result-row"><span style="color:var(--muted)">${vpL("50%折扣（持有>12月）","50% discount (held &gt;12 months)")}</span><span style="color:#2ecc71">−${_cgtFmt(rawGain*0.5)}</span></div>` : ""}
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL("应税金额","Taxable amount")}</span><span>${_cgtFmt(Math.max(0,taxableGain))}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL(`个税（${taxRate}%）`, `Income tax (${taxRate}%)`)}</span><span style="color:#e74c3c">−${_cgtFmt(taxOnGain)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">${vpL("Medicare征费（2%）","Medicare levy (2%)")}</span><span style="color:#e74c3c">−${_cgtFmt(medicare)}</span></div>
      <div class="cgt-result-row cgt-highlight"><span>${vpL("税后净盈亏","Net P&L after tax")}</span>
        <span style="color:${netGain >= 0 ? '#2ecc71' : '#e74c3c'}">${_cgtFmt(netGain, {sign:true})} (${netPct >= 0 ? '+' : ''}${netPct.toFixed(1)}%)</span></div>
      ${isGain && !eligible50 && heldMonths > 0 && heldMonths < 12 ? `
      <div style="background:rgba(241,196,15,.1);border:1px solid rgba(241,196,15,.3);border-radius:5px;padding:.5rem .75rem;margin-top:.5rem;font-size:0.78rem;">
        ${vpL(`💡 再持有 <strong style="color:#f1c40f">${12 - heldMonths} 个月</strong>即可享受50%折扣，届时预计少缴税 <strong style="color:#2ecc71">${_cgtFmt(rawGain*0.5*(taxRate/100+0.02), {decimals:0})}</strong>`,
              `💡 Hold for <strong style="color:#f1c40f">${12 - heldMonths} more months</strong> to qualify for the 50% discount, saving an estimated <strong style="color:#2ecc71">${_cgtFmt(rawGain*0.5*(taxRate/100+0.02), {decimals:0})}</strong> in tax`)}
      </div>` : ""}
      <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;">
        ${vpL(`保本卖出价（税后回本）≈ <strong>${_cgtFmt(breakEvenAUD, {decimals:4})}/个</strong>`, `Break-even sell price (after tax) ≈ <strong>${_cgtFmt(breakEvenAUD, {decimals:4})}/unit</strong>`)}
      </div>
    </div>`;
}

// ── CGT 货币切换的初始化（自给自足，不依赖 app-5.js）──────────────
// 委派点击：货币按钮由 renderCgtCurrencySelector 动态生成，用委托绑一次即可。
function _cgtInitCurrencySwitch() {
  if (_cgtInitCurrencySwitch._done) return;
  if (!document.getElementById("cgt-result")) return;   // 不在「我的」视图的页面就跳过
  _cgtInitCurrencySwitch._done = true;
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-cgt-cur]");
    if (b && !b.disabled) setCgtDisplayCur(b.dataset.cgtCur);
  });
  renderCgtCurrencySelector();   // 先用已有/缺省汇率渲染出选择器
  loadCgtFXRates();              // 再异步拉 fx_rates.json，到了重渲染
}
// app-4.js 在 <body> 末尾加载，DOM 通常已就绪；兼容偶发未就绪的情况。
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _cgtInitCurrencySwitch);
  } else {
    _cgtInitCurrencySwitch();
  }
}

// ── 自动刷新持仓价格 ──
let _priceRefreshTimer = null;
function toggleAutoRefresh(el) {
  if (_priceRefreshTimer) {
    clearInterval(_priceRefreshTimer);
    _priceRefreshTimer = null;
    el.textContent = vpL("⏱ 自动","⏱ Auto");
    el.style.cssText = "background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:.3rem .8rem;border-radius:5px;font-size:0.78rem;cursor:pointer;";
  } else {
    fetchPortfolioPrices();
    _priceRefreshTimer = setInterval(fetchPortfolioPrices, 30000);
    el.textContent = vpL("⏱ 30s·开","⏱ 30s · on");
    el.style.cssText = "background:rgba(46,204,113,.15);border:1px solid var(--green);color:var(--green);padding:.3rem .8rem;border-radius:5px;font-size:0.78rem;cursor:pointer;font-weight:700;";
  }
}

// Portfolio cost basis editor —— 支持两种输入：单价，或买入总价(前缀"=")
function setPortfolioCost(i, ticker) {
  const port = loadPortfolio();
  const item = port[i];
  if (!item) return;
  const qty = item.qty;
  const raw = prompt(vpL(
    `输入 ${ticker} 的成本（USD）：\n` +
    `· 知道单价 → 直接填每股/每枚价格（例：BTC填95000，DOGE填0.15）\n` +
    `· 只知买入总价 → 数字前加「=」（例：=1500 表示总共花US$1500，按持有 ${qty} 份自动折算单价）`,
    `Enter the cost basis for ${ticker} (USD):\n` +
    `· Know the unit price → enter price per share/coin directly (e.g. BTC → 95000, DOGE → 0.15)\n` +
    `· Only know total cost → prefix the number with "=" (e.g. =1500 means US$1500 total, auto-divided by your ${qty} units)`
  ));
  if (raw == null) return;
  const t = String(raw).trim();
  let unit;
  if (t.startsWith("=")) {
    const totalCost = parseFloat(t.slice(1));
    if (isNaN(totalCost) || totalCost < 0) { alert(vpL("请输入有效金额","Please enter a valid amount")); return; }
    if (!qty || qty <= 0) { alert(vpL("该持仓数量为 0，无法用总价折算单价——请先设好数量，或直接填单价","This holding has 0 units, so total cost can't be divided into a unit price — set the quantity first, or enter the unit price directly")); return; }
    unit = totalCost / qty;
  } else {
    unit = parseFloat(t);
    if (isNaN(unit) || unit < 0) { alert(vpL("请输入有效价格","Please enter a valid price")); return; }
  }
  item.costUSD = unit;
  savePortfolio(port);
  renderPortfolioTable(_portAudRate);
}

// ── 启动 ──
// ═══════════════════════════════════════════════════════
//  双指数信号对比（纳指 vs 标普，含校准概率）
// ═══════════════════════════════════════════════════════
function renderIndicesCompare() {
  const el = document.getElementById("indices-compare");
  if (!el || !SIGNALS?.indices) return;
  const TC = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };
  const NAMES = { NASDAQ: vpL("纳斯达克","Nasdaq"), SP500: vpL("标普500","S&P 500") };
  const flat = SIGNALS.calibration_flat;
  const br = Math.round((SIGNALS.base_rate_20d ?? 0.62) * 100);
  el.innerHTML = Object.entries(SIGNALS.indices).map(([idx, s]) => {
    // 无样本外区分度：中性卡片，只显示原始打分（不给档位/校准概率，避免假把握度）
    if (flat) {
      const c = "#f1c40f";
      return `<div style="flex:1;text-align:center;padding:.6rem .4rem;border:1px solid ${c}33;border-radius:8px;background:${c}0d;">
        <div style="font-size:0.78rem;color:var(--muted);">${NAMES[idx]||idx}</div>
        <div style="font-size:1.35rem;font-weight:800;color:${c};">≈${br}%</div>
        <div style="font-size:0.66rem;color:var(--muted);">${vpL("基率·无区分度","Base rate · no discriminative power")}</div>
        <div style="font-size:0.68rem;color:var(--muted);margin-top:.1rem;">${vpL(`原始打分 ${(s.prob*100).toFixed(1)}%`, `Raw score ${(s.prob*100).toFixed(1)}%`)}</div>
        <div style="font-size:0.65rem;color:var(--muted);margin-top:.2rem;">${vpL(`截至 ${s.date||""}`, `As of ${s.date||""}`)}</div>
      </div>`;
    }
    // 主显示：校准概率（prob_cal）与 tier_cal；校准值缺失时回退原始
    const calProb = s.prob_cal != null ? s.prob_cal : s.prob;
    const calTier = s.tier_cal != null ? s.tier_cal : s.tier;
    const c = TC[calTier] || "#f1c40f";
    const rawNote = s.prob_cal != null
      ? `<div style="font-size:0.68rem;color:var(--muted);margin-top:.1rem;" title="${vpL("模型原始输出（未校准）","Raw model output (uncalibrated)")}">${vpL(`原始 ${(s.prob*100).toFixed(1)}%`, `Raw ${(s.prob*100).toFixed(1)}%`)}</div>`
      : "";
    return `<div style="flex:1;text-align:center;padding:.6rem .4rem;border:1px solid ${c}44;border-radius:8px;background:${c}11;">
      <div style="font-size:0.78rem;color:var(--muted);">${NAMES[idx]||idx}</div>
      <div style="font-size:1.35rem;font-weight:800;color:${c};">${(calProb*100).toFixed(1)}%</div>
      <div style="font-size:0.72rem;color:${c};">${vpL(`第${calTier}档`, `Tier ${calTier}`)}</div>
      ${rawNote}
      <div style="font-size:0.65rem;color:var(--muted);margin-top:.2rem;">${vpL(`截至 ${s.date||""}`, `As of ${s.date||""}`)}</div>
    </div>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════
//  模型实盘追踪（append-only 预测日志，无法事后美化）
// ═══════════════════════════════════════════════════════
function renderLiveTracking() {
  const el = document.getElementById("live-tracking");
  if (!el) return;
  const lt = SIGNALS?.live_tracking;
  if (!lt || !lt.n_logged) {
    el.innerHTML = `<div style="font-size:0.75rem;color:var(--muted);">
      ${vpL(`🧪 实盘追踪已启动（${SIGNALS?.model_version ? "模型 v"+SIGNALS.model_version : ""}）：
      每天记录模型预测，之后用真实行情回填对账。约一周后这里会出现第一批成绩。`,
      `🧪 Live tracking is running (${SIGNALS?.model_version ? "model v"+SIGNALS.model_version : ""}): the model's predictions are logged daily and later reconciled against real market outcomes. The first results should appear here in about a week.`)}</div>`;
    return;
  }
  const rows = Object.entries(lt.by_index || {}).map(([idx, s]) => {
    const hit5 = s.hit_rate_5d != null ? `${s.hit_rate_5d}%` : vpL("待回填","pending");
    const hit1 = s.hit_rate_1d != null ? `${s.hit_rate_1d}%` : vpL("待回填","pending");
    return `<tr><td style="padding:.25rem .5rem;">${idx}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${s.n}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${hit1}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${hit5}</td></tr>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.78rem;font-weight:600;margin-bottom:.4rem;">
      ${vpL("🧪 模型实盘成绩单","🧪 Model live track record")} <span style="color:var(--muted);font-weight:400;">${vpL(`自 ${lt.since||"—"} · 当日预测当日记录，无法事后修改`, `Since ${lt.since||"—"} · predictions are logged same-day and can't be edited after the fact`)}</span>
    </div>
    <table style="width:100%;font-size:0.75rem;border-collapse:collapse;">
      <tr style="color:var(--muted);"><th style="text-align:left;padding:.25rem .5rem;">${vpL("指数","Index")}</th>
        <th>${vpL("已记录","Logged")}</th><th>${vpL("1日方向命中","1-day hit rate")}</th><th>${vpL("5日方向命中","5-day hit rate")}</th></tr>
      ${rows}
    </table>`;
}

// ═══════════════════════════════════════════════════════
//  个股观察池（七姐妹 + 优质龙头）
// ═══════════════════════════════════════════════════════
let STOCKS = null;
async function loadStocksPanel() {
  try {
    const r = await fetch("stocks.json?_=" + Date.now());
    if (!r.ok) throw new Error("HTTP " + r.status);   // 404 返 HTML 会让 r.json() 抛错→面板静默不渲染；显式判
    STOCKS = await r.json();
  } catch(e) {
    console.warn("stocks.json 未找到", e);
    const el = document.getElementById("stocks-table");
    if (el) el.innerHTML = `<div style="color:var(--muted);font-size:0.8rem;padding:.5rem">${vpL("个股数据暂不可用（稍后自动重试或刷新页面）","Stock data unavailable right now (will auto-retry, or refresh the page)")}</div>`;
    return;
  }
  renderStocksTable();
  const first = Object.keys(STOCKS.stocks)[0];
  if (first) renderStockChart(first);
  renderGamePanel();   // 用户模拟盘需要最新股价
  renderSPCXMonitor(); // SPCX 监视卡依赖 STOCKS.spcx
  if (typeof renderHorizonStocks === "function") renderHorizonStocks();  // 长期页质量表
}

// ═══════════════════════════════════════════════════════
//  个股表行 → 展开体检摘要（D3任务2：手风琴，同源消费 stock_checkup.json）
// ═══════════════════════════════════════════════════════
// STOCK_CHECKUP 是全局共享变量（app-2.js 已声明，供"🩺个股诚实体检"登记簿面板用）——
// 这里复用同一个缓存，谁先请求谁写入，避免同一份 stock_checkup.json 被拉两次。
let _expandedStockSym = null;   // 当前展开的股票代码；null=全部收起（手风琴，同时只展开一行）

async function ensureStockCheckup() {
  if (STOCK_CHECKUP) return STOCK_CHECKUP;
  try {
    const r = await fetch("stock_checkup.json?_=" + Date.now());
    if (r.ok) STOCK_CHECKUP = await r.json();
  } catch (e) { /* 尚未生成/网络失败 —— 保持 null，展开卡诚实显示"暂无体检数据" */ }
  return STOCK_CHECKUP;
}

// 展开/收起某一行；数据未就绪时先渲染占位再补渲染，不让用户觉得卡住。
async function toggleStockRowExpand(sym) {
  _expandedStockSym = _expandedStockSym === sym ? null : sym;
  renderStocksTable();
  if (_expandedStockSym === sym && !STOCK_CHECKUP) {
    await ensureStockCheckup();
    if (_expandedStockSym === sym) renderStocksTable();   // 异步返回时用户可能已切到别行/收起，别强行拉回
  }
}

// 规律真伪判定 → 双语文案（措辞与"🩺个股诚实体检"面板一致，见 app-2.js renderStockCheckup 的 patMap）
function _patVerdictLabel(v) {
  const map = vpL(
    { has_real:"出现疑似持续规律(待验证)", faded:"曾有、近年已消失(被套利)", hist_robust:"历史稳健但近期样本不足", data_snoop:"疑似数据窥探", no_pattern:"未检出", inconclusive:"无定论(检验力不足)" },
    { has_real:"suspected persistent pattern (unverified)", faded:"once real, now faded (arbitraged away)", hist_robust:"historically robust, recent sample too small", data_snoop:"suspected data snooping", no_pattern:"none detected", inconclusive:"inconclusive (low power)" }
  );
  return map[v] || v;
}

// 跳到本页"🩺个股诚实体检"完整面板并选中该票（同一批 19 只观察池股票，比 ticker.html 的
// 第三方"任意代码快查"更权威——ticker.html 不接受 ?t= 参数、也非同一数据源，故不链去那里）。
async function goToStockCheckup(sym) {
  const scEl = document.getElementById("stock-checkup");
  if (!scEl) return;
  // 该面板挂在"📋登记簿"视图里（切视图前是 display:none，直接 scrollIntoView 不生效）——先切视图
  const registryBtn = document.querySelector('.view-btn[data-view="registry"]');
  if (typeof switchView === "function") switchView("registry", registryBtn || undefined);
  if (!document.getElementById("sc-select") && typeof loadStockCheckup === "function") {
    await loadStockCheckup();   // 面板首次尚未渲染（懒渲染门未触发）：主动补一次，fetch 已缓存不重复拉网络
  }
  const sel = document.getElementById("sc-select");
  if (sel && [...sel.options].some(o => o.value === sym)) {
    sel.value = sym;
    if (typeof renderStockCheckup === "function") renderStockCheckup(sym);
  }
  (scEl.closest(".chart-wrap") || scEl).scrollIntoView({ behavior: "smooth", block: "start" });
}

// 展开卡内容：诚实分支——status!=ok 或缺失都直说"暂无体检数据"，不硬凑
function renderStockCheckupExpandRow(sym, colspan) {
  let body;
  if (!STOCK_CHECKUP) {
    body = `<span style="color:var(--muted);font-size:0.8rem">${vpL("加载中…","Loading…")}</span>`;
  } else {
    const t = STOCK_CHECKUP.tickers?.[sym];
    if (!t || t.status !== "ok") {
      body = `<span style="color:var(--muted);font-size:0.8rem">${vpL("暂无体检数据","No check-up data available")}</span>`;
    } else {
      const an = t.anomaly || {};
      const highVolTag   = an.high_vol   ? vpL(" ⚠高波动区"," ⚠ elevated-volatility zone") : "";
      const decoupledTag = an.decoupled  ? vpL(" · ⚠与大盘异常脱钩"," · ⚠ unusually decoupled from the market") : "";
      const patTxt = (t.patterns && t.patterns.status === "ok") ? _patVerdictLabel(t.patterns.overall) : vpL("数据不足","insufficient data");
      body = `
        <div style="font-size:0.82rem;line-height:1.7;">
          ${vpL("年化波动","Ann. volatility")} <b>${t.ann_vol_pct}%</b> ·
          ${vpL("最大回撤","Max drawdown")} <b>${t.max_drawdown_pct}%</b> ·
          β(${vpL("纳指","Nasdaq")}) <b>${t.beta_nasdaq ?? "—"}</b> ·
          ${vpL("当前波动分位","Current vol percentile")} <b>${an.vol_percentile != null ? an.vol_percentile + "%" : "—"}</b>${highVolTag}${decoupledTag} ·
          ${vpL("规律真伪","Pattern verdict")}: ${esc(patTxt)}
          <button type="button" onclick="goToStockCheckup('${sym}')"
            style="margin-left:.5rem;background:none;border:none;padding:0;color:var(--blue);cursor:pointer;
                   font:inherit;text-decoration:underline;">${vpL("完整体检 →","Full check-up →")}</button>
        </div>
        <div style="font-size:0.7rem;color:var(--muted);margin-top:.35rem;">${vpL("风险画像·非荐股非预测","Risk profile · not a recommendation, not a forecast")}</div>`;
    }
  }
  return `<tr class="stx-expand-row" data-stock-expand="${sym}">
    <td colspan="${colspan}" style="padding:.6rem .8rem;background:var(--surface2);border-bottom:1px solid var(--border-faint);">${body}</td>
  </tr>`;
}

function renderStocksTable() {
  const el = document.getElementById("stocks-table");
  if (!el || !STOCKS) return;
  const COLSPAN = 9;   // 股票/现价/1日/20日/YTD/距52周高/RSI14/>MA200/β —— 与表头列数对齐
  const fmt = (v, suffix="%") => v == null ? "—"
    : `<span style="color:${v >= 0 ? "#2ecc71" : "#e74c3c"}">${v > 0 ? "+" : ""}${v}${suffix}</span>`;
  const rows = Object.entries(STOCKS.stocks).map(([sym, s]) => {
    const st = s.stats;
    const ma = st.above_ma200
      ? `<span style="color:#2ecc71">✓</span>` : `<span style="color:#e74c3c">✗</span>`;
    const rsiColor = st.rsi14 > 70 ? "#e74c3c" : st.rsi14 < 30 ? "#2ecc71" : "var(--text)";
    const tag = s.is_mag7 ? `<span style="font-size:0.6rem;background:#9b59b633;color:#9b59b6;border-radius:3px;padding:0 3px;margin-left:3px;">M7</span>` : "";
    const expanded = _expandedStockSym === sym;
    const caret = `<span class="stx-caret" aria-hidden="true">${expanded ? "▾" : "▸"}</span>`;
    const rowHtml = `<tr data-stock-symbol="${sym}" tabindex="0" aria-expanded="${expanded}"
        style="cursor:pointer;border-bottom:1px solid var(--border-faint);">
      <td style="padding:.35rem .5rem;font-weight:600;">${caret}${sym}${tag}<br><span style="font-size:0.68rem;color:var(--muted);margin-left:1.1em;">${vpD(s,"label")}</span></td>
      <td style="padding:.35rem .5rem;text-align:right;">$${st.last}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.chg_1d)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.chg_20d)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.ytd)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.from_high_52w)}</td>
      <td style="padding:.35rem .5rem;text-align:center;color:${rsiColor};">${st.rsi14}</td>
      <td style="padding:.35rem .5rem;text-align:center;">${ma}</td>
      <td style="padding:.35rem .5rem;text-align:center;">${st.beta_nasdaq_1y ?? "—"}</td>
    </tr>`;
    return rowHtml + (expanded ? renderStockCheckupExpandRow(sym, COLSPAN) : "");
  }).join("");
  el.innerHTML = `<table style="width:100%;font-size:0.78rem;border-collapse:collapse;min-width:640px;">
    <tr style="color:var(--muted);font-size:0.72rem;">
      <th style="text-align:left;padding:.35rem .5rem;">${vpL("股票","Stock")}</th><th style="text-align:right;">${vpL("现价","Price")}</th>
      <th style="text-align:right;">${vpL("1日","1d")}</th><th style="text-align:right;">${vpL("20日","20d")}</th>
      <th style="text-align:right;">YTD</th><th style="text-align:right;">${vpL("距52周高","From 52w high")}</th>
      <th>RSI14</th><th>&gt;MA200</th><th>${vpL("β(纳指)","β(Nasdaq)")}</th>
    </tr>${rows}</table>`;
  // D3：手风琴展开卡（β/年化波动/分位等术语）在页面自动双扫窗口(载入+2000ms)之后才可能
  // 首次出现在 DOM 里——vp_gloss.js 的固定双扫不会回头再扫，这里在每次重画表格后主动补扫
  // 一次（vpGlossScan 幂等，全页每词只注一次，重复调用零副作用，开销也只在这一个子树内）。
  if (typeof vpGlossScan === "function") vpGlossScan(el);
}

// ── 个股分析卡（可复用模板：趋势/动量/波动/回撤/系统性，描述性非预测）──
function renderStockScorecard(sym) {
  const el = document.getElementById("stock-scorecard");
  if (!el || !STOCKS?.stocks?.[sym]) return;
  const s = STOCKS.stocks[sym], st = s.stats;
  // 每个维度：标签 + 值 + 解读带（颜色+一句话），全部基于历史统计，不预测
  const band = (cond, txt, color) => `<span style="color:${color}">${txt}</span>`;
  const trend = st.dist_ma200 == null ? ["—", "var(--muted)", vpL("数据不足","Insufficient data")]
    : st.dist_ma200 > 15 ? [`+${st.dist_ma200}%`, "#e67e22", vpL("强多头但偏离均线远，回踩风险升高","Strongly bullish but far above the moving average — pullback risk is elevated")]
    : st.dist_ma200 > 0 ? [`+${st.dist_ma200}%`, "#2ecc71", vpL("站上200日线，多头趋势","Above the 200-day line — bullish trend")]
    : [`${st.dist_ma200}%`, "#e74c3c", vpL("跌破200日线，趋势转弱","Below the 200-day line — trend weakening")];
  const rsiB = st.rsi14 > 70 ? [vpL("超买","Overbought"), "#e74c3c"] : st.rsi14 < 30 ? [vpL("超卖","Oversold"), "#2ecc71"] : [vpL("中性","Neutral"), "var(--text)"];
  const volB = st.vol_pctile_1y == null ? ["—", "var(--muted)"]
    : st.vol_pctile_1y > 80 ? [vpL(`第${st.vol_pctile_1y}百分位·异常高`, `${st.vol_pctile_1y}th pctile · unusually high`), "#e74c3c"]
    : st.vol_pctile_1y < 20 ? [vpL(`第${st.vol_pctile_1y}百分位·异常平静`, `${st.vol_pctile_1y}th pctile · unusually calm`), "#3498db"]
    : [vpL(`第${st.vol_pctile_1y}百分位·常态`, `${st.vol_pctile_1y}th pctile · normal`), "var(--text)"];
  const r2 = st.r2_nasdaq_1y;
  const r2B = r2 == null ? ["—", "var(--muted)", ""]
    : r2 > 0.5 ? [`${Math.round(r2*100)}%`, "#3498db", vpL("波动主要由大盘驱动（系统性，分散作用小）","Volatility mostly driven by the broad market (systematic — diversification helps little)")]
    : [`${Math.round(r2*100)}%`, "#9b59b6", vpL("波动多为个股特有（独立逻辑，需看公司基本面）","Volatility is mostly stock-specific (idiosyncratic — look at company fundamentals)")];
  const rv = st.ret_vol_1y;
  const cell = (label, valHtml, note) => `
    <div style="background:var(--surface2);border-radius:7px;padding:.55rem .7rem;">
      <div style="font-size:0.68rem;color:var(--muted);">${label}</div>
      <div style="font-size:0.95rem;font-weight:700;margin:.1rem 0;">${valHtml}</div>
      <div style="font-size:0.68rem;color:var(--muted);line-height:1.4;">${note}</div>
    </div>`;
  el.innerHTML = `
    <div style="font-size:0.82rem;font-weight:700;margin-bottom:.5rem;">${vpL(`📊 ${sym} ${s.label} · 个股分析卡`, `📊 ${sym} ${vpD(s,"label")} · Stock scorecard`)}
      <span style="font-size:0.66rem;color:var(--muted);font-weight:400;">${vpL(`截至 ${st.date}`, `As of ${st.date}`)}</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;">
      ${cell(vpL("趋势（距200日线）","Trend (vs. 200-day line)"), band(0, trend[0], trend[1]), trend[2])}
      ${cell(vpL("动量 RSI14 / 距52周高","Momentum RSI14 / from 52w high"), `${st.rsi14} <span style="font-size:0.7rem;color:${rsiB[1]}">${rsiB[0]}</span> · ${st.from_high_52w}%`,
             st.range_pctile_52w!=null?vpL(`位于52周区间第 ${st.range_pctile_52w} 百分位`, `${st.range_pctile_52w}th percentile of the 52-week range`):"")}
      ${cell(vpL("波动率状态","Volatility regime"), `${st.vol20_ann}% · <span style="font-size:0.7rem;color:${volB[1]}">${volB[0]}</span>`,
             vpL("年化20日波动 vs 自身近一年","Annualized 20-day volatility vs. its own trailing year"))}
      ${cell(vpL("最大回撤 / 风险调整","Max drawdown / risk-adjusted"), `${st.max_dd}% · ${rv!=null?vpL("性价比","Sharpe-like ")+rv:"—"}`,
             rv!=null?(rv>1?vpL("近1年收益/波动>1，性价比尚可","Past-year return/volatility &gt;1 — decent risk-adjusted profile"):vpL("近1年风险调整后一般","Past-year risk-adjusted profile is unremarkable")):"")}
      ${cell(vpL("β / 系统性占比 R²","β / systematic share R²"), `β ${st.beta_nasdaq_1y ?? "—"} · R² ${r2B[0]}`, r2B[2])}
      ${cell(vpL("收益（YTD / 1年）","Return (YTD / 1y)"), `${st.ytd!=null?st.ytd+"%":"—"} / ${st.chg_1y!=null?st.chg_1y+"%":"—"}`, "")}
    </div>
    <div style="font-size:0.68rem;color:var(--muted);margin-top:.5rem;line-height:1.5;">
      ${vpL(`⚠ 这是<b>描述性</b>分析卡（趋势/动量/波动/回撤/系统性现状），不预测涨跌——
      与本站结论一致：个股方向同样不可靠预测。用它快速体检一只股的<b>当前状态与风险画像</b>，不当买卖信号。`,
      `⚠ This is a <b>descriptive</b> scorecard (current trend/momentum/volatility/drawdown/systematic exposure) — it does not predict direction.
      Consistent with this site's conclusions elsewhere: individual-stock direction is just as unreliable to predict. Use it as a quick <b>current-state and risk-profile</b> check on a stock, not a buy/sell signal.`)}
    </div>`;
  // D3 术语注解补扫：分析卡(β/年化波动/百分位等术语密集)由 stocks.json fetch 后直渲，
  // 常错过 vp_gloss 固定双扫窗口；每次重画后补扫本容器（vpGlossScan 幂等，零副作用）。
  if (typeof vpGlossScan === "function") vpGlossScan(el);
}

function renderStockChart(sym) {
  if (!STOCKS?.stocks?.[sym]) return;
  renderStockScorecard(sym);
  const s = STOCKS.stocks[sym];
  const traces = [{
    x: s.series.dates, y: s.series.values, name: `${sym} ${vpD(s,"label")}`,
    type: "scatter", mode: "lines", line: { color: "#9b59b6", width: 2.5 },
  }];
  for (const [idx, col] of [["NASDAQ", "#3498db"], ["SP500", "#95a5a6"]]) {
    const ser = STOCKS.indices?.[idx];
    if (ser) traces.push({
      x: ser.dates, y: ser.values, name: idx,
      type: "scatter", mode: "lines", line: { color: col, width: 1.4, dash: "dot" },
    });
  }
  Plotly.newPlot("chart-stock", traces, {...DARK, hovermode: "x unified",
    title: { text: vpL(`${sym}（${s.label}）vs 指数 · 归一化=100`, `${sym} (${vpD(s,"label")}) vs. indices · normalized=100`), font: { size: 13 } }},
    {displayModeBar: false, responsive: true});
  // D3：外部零依赖切换条替代旧的 Plotly 原生 rangeselector（见判断点①）；每次换股都会
  // Plotly.newPlot 到同一个 div，vpRangeBar 在兄弟节点上"保活"，这里调用即原地刷新。
  if (typeof vpRangeBar === "function") vpRangeBar("chart-stock", { dates: s.series.dates });
}

// ═══════════════════════════════════════════════════════
//  操作计划：对未来选定日期给出 买入时段/持有期/卖出提醒
// ═══════════════════════════════════════════════════════
// 把美东 h:m 换算成访问者本地时间字符串（自动适配任何时区+夏令时）
// 时间显示时区：默认 ET（美东统一），可随时切换到 LOCAL（访问者本地）。
let TZ_MODE = (typeof localStorage !== "undefined" && localStorage.getItem("tz_mode")) || "ET";
function toggleTZMode() {
  TZ_MODE = TZ_MODE === "ET" ? "LOCAL" : "ET";
  try { localStorage.setItem("tz_mode", TZ_MODE); } catch (e) {}
  renderMarketClock();
  if (selectedDate) updateSignal(selectedDate);   // 刷新操作计划里的时段
}
function _pad2(n) { return String(n).padStart(2, "0"); }
// 把美东 h:m 换算成访问者本地时间（同一瞬间两时区钟面差固定，自动含夏令时）
function etToLocalConv(h, m) {
  const now = new Date();
  const etNow = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const offsetMs = now - etNow;
  const t = new Date(etNow); t.setHours(h, m, 0, 0);
  return new Date(t.getTime() + offsetMs)
    .toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
// 模式感知的"美东时段"字符串：ET 模式只显示美东；LOCAL 模式附带本地换算
function tzRange(h1, m1, h2, m2) {
  const et = vpL(`美东 ${_pad2(h1)}:${_pad2(m1)}–${_pad2(h2)}:${_pad2(m2)}`, `ET ${_pad2(h1)}:${_pad2(m1)}–${_pad2(h2)}:${_pad2(m2)}`);
  return TZ_MODE === "ET" ? et : `${et}${vpL(`（你的 ${etToLocalConv(h1, m1)}–${etToLocalConv(h2, m2)}）`, ` (yours ${etToLocalConv(h1, m1)}–${etToLocalConv(h2, m2)})`)}`;
}

// ═══════════════════════════════════════════════════════
//  每日盘后简报（brief.json，云端规则化生成）
// ═══════════════════════════════════════════════════════
async function loadBriefPanel() {
  const el = document.getElementById("brief-content");
  if (!el) return;
  try {
    const r = await fetch("brief.json?_=" + Date.now());
    const b = await r.json();
    const up = document.getElementById("brief-updated");
    if (up && b.generated) up.textContent = vpL(`生成于 ${b.generated} · 模型v${b.model_version||""}`, `Generated ${b.generated} · model v${b.model_version||""}`);
    // 🚦 关键指标红绿灯（直接看的状态层）
    const LC = { green: "#2ecc71", yellow: "#f1c40f", red: "#e74c3c" };
    const lights = (b.lights || []).map(l =>
      `<div title="${esc(l.note)}" style="flex:1;min-width:96px;text-align:center;padding:.35rem .2rem;
           border:1px solid ${LC[l.status]}55;border-radius:7px;background:${LC[l.status]}11;cursor:help;">
        <div style="font-size:0.62rem;color:var(--muted);">${esc(l.name)}</div>
        <div style="font-size:0.78rem;font-weight:700;color:${LC[l.status]};">●&nbsp;${esc(l.value)}</div>
      </div>`).join("");
    const lightsHtml = lights
      ? `<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.55rem;">${lights}</div>` : "";
    el.innerHTML = lightsHtml + (b.lines || []).map(l => {
      const m = l.match(/^【(.+?)】(.*)$/);
      if (!m) return `<div>${esc(l)}</div>`;
      const warn = m[2].includes("⚠");
      return `<div style="padding:.18rem 0;">
        <span style="color:var(--muted);font-size:0.72rem;">【${esc(m[1])}】</span>
        <span style="${warn ? "color:#e67e22;" : ""}">${esc(m[2])}</span></div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">${vpL("简报未生成（跑一次流水线即可）","Brief not generated yet (run the pipeline once)")}</div>`;
  }
}

// ═══════════════════════════════════════════════════════
//  我的模拟盘（用户游戏，localStorage，按最近收盘价成交）
// ═══════════════════════════════════════════════════════
const GAME_KEY = "alpha_game_v1";
function gameState() {
  try { return JSON.parse(localStorage.getItem(GAME_KEY)) ||
    { cash: 10000, holdings: {}, trades: [], started: new Date().toISOString().slice(0,10) }; }
  catch { return { cash: 10000, holdings: {}, trades: [], started: "" }; }
}
function gameSave(g) { localStorage.setItem(GAME_KEY, JSON.stringify(g)); }
function gamePx() {
  const m = {};
  if (STOCKS) for (const [s, v] of Object.entries(STOCKS.stocks)) m[s] = v.stats.last;
  return m;
}

function renderGamePanel() {
  const el = document.getElementById("game-content");
  if (!el || !STOCKS) return;
  const g = gameState(), px = gamePx();
  let mv = 0;
  const holdRows = Object.entries(g.holdings).map(([s, h]) => {
    const p = px[s] || h.cost;
    mv += h.units * p;
    const pl = (p / h.cost - 1) * 100;
    const c = pl >= 0 ? "#2ecc71" : "#e74c3c";
    return `<tr>
      <td style="padding:.25rem .4rem;font-weight:600;">${s}</td>
      <td style="padding:.25rem .4rem;text-align:right;">$${(h.units*p).toFixed(0)}</td>
      <td style="padding:.25rem .4rem;text-align:right;">${vpL("成本","cost")}$${h.cost.toFixed(2)}</td>
      <td style="padding:.25rem .4rem;text-align:right;color:${c};">${pl>0?"+":""}${pl.toFixed(1)}%</td>
      <td style="padding:.25rem .4rem;"><button class="period-btn" data-game-sell="${s}">${vpL("卖出","Sell")}</button></td>
    </tr>`;
  }).join("");
  const eq = g.cash + mv, ret = (eq / 10000 - 1) * 100;
  const rc = ret >= 0 ? "#2ecc71" : "#e74c3c";
  const opts = Object.keys(STOCKS.stocks).map(s =>
    `<option value="${s}">${s} ${vpD(STOCKS.stocks[s],"label")} $${px[s]}</option>`).join("");
  const recent = (g.trades || []).slice(-6).reverse().map(t => {
    const sideDisp = t.side === "买" ? vpL("买","Buy") : t.side === "卖" ? vpL("卖","Sell") : t.side;
    return `<div style="color:var(--muted);font-size:0.7rem;">${t.t} ${sideDisp} ${t.sym} $${t.amt.toFixed(0)} @${t.px}</div>`;
  }).join("");
  el.innerHTML = `
    <div style="margin-bottom:.5rem;">${vpL("净值","Equity")} <b style="font-size:1.1rem;">$${eq.toFixed(0)}</b>
      <b style="color:${rc};">（${ret>0?"+":""}${ret.toFixed(2)}%）</b>
      · ${vpL("现金","Cash")} $${g.cash.toFixed(0)} <span style="color:var(--muted);font-size:0.7rem;">${vpL(`自 ${g.started||"—"}`, `Since ${g.started||"—"}`)}</span></div>
    <div style="display:flex;gap:.4rem;margin-bottom:.5rem;flex-wrap:wrap;">
      <select id="game-sym" class="cgt-input" style="flex:2;min-width:140px;">${opts}</select>
      <input id="game-amt" class="cgt-input" type="number" placeholder="${vpL("金额$","Amount $")}" value="1000" style="flex:1;min-width:70px;">
      <button class="cgt-btn" style="flex:0;padding:.4rem .8rem;" data-game-buy>${vpL("买入","Buy")}</button>
    </div>
    ${holdRows ? `<table style="width:100%;font-size:0.74rem;border-collapse:collapse;">${holdRows}</table>` : ""}
    ${recent ? `<div style="margin-top:.4rem;">${recent}</div>` : ""}
    <div style="display:flex;justify-content:space-between;margin-top:.45rem;align-items:center;">
      <span style="color:var(--muted);font-size:0.66rem;">${vpL(`按最近收盘价成交（${STOCKS.generated}）· 存在本浏览器`, `Fills at the latest close (${STOCKS.generated}) · saved in this browser`)}</span>
      <button class="period-btn" data-game-reset>${vpL("重置","Reset")}</button>
    </div>`;
}

function gameBuy() {
  const sym = document.getElementById("game-sym").value;
  const amt = parseFloat(document.getElementById("game-amt").value);
  const g = gameState(), px = gamePx()[sym];
  if (!px || !(amt > 0)) return;
  if (amt > g.cash) { alert(vpL(`现金不足（剩 $${g.cash.toFixed(0)}）`, `Insufficient cash (remaining $${g.cash.toFixed(0)})`)); return; }
  const units = amt / px;
  const h = g.holdings[sym] || { units: 0, cost: 0 };
  h.cost = (h.cost * h.units + px * units) / (h.units + units);   // 加权平均成本
  h.units += units;
  g.holdings[sym] = h;
  g.cash -= amt;
  g.trades.push({ t: new Date().toISOString().slice(0,16).replace("T"," "),
                  side: "买", sym, px, amt });
  gameSave(g); renderGamePanel();
}

function gameSell(sym) {
  const g = gameState(), px = gamePx()[sym];
  const h = g.holdings[sym];
  if (!h || !px) return;
  const amt = h.units * px;
  g.cash += amt;
  delete g.holdings[sym];
  g.trades.push({ t: new Date().toISOString().slice(0,16).replace("T"," "),
                  side: "卖", sym, px, amt });
  gameSave(g); renderGamePanel();
}

function gameReset() {
  if (!confirm(vpL("清空我的模拟盘，重新从 $10,000 开始？","Clear your paper portfolio and restart from $10,000?"))) return;
  localStorage.removeItem(GAME_KEY);
  renderGamePanel();
}

// ═══════════════════════════════════════════════════════
//  模拟盘（paper.json）
// ═══════════════════════════════════════════════════════
async function loadPaperPanel() {
  const el = document.getElementById("paper-content");
  if (!el) return;
  let p;
  try {
    const r = await fetch("paper.json?_=" + Date.now());
    p = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">${vpL("模拟盘等待首个交易日启动（自 2026-06-10 起前向实验）","Paper portfolio awaiting its first trading day (forward experiment starts 2026-06-10)")}</div>`;
    return;
  }
  const strats = Object.values(p.strategies || {})
    .sort((a, b) => b.ret_pct - a.ret_pct);
  if (!strats.length) {
    el.innerHTML = `<div style="color:var(--muted)">${vpL("模拟盘等待首个交易日","Paper portfolio awaiting its first trading day")}</div>`;
    return;
  }
  el.innerHTML = strats.map((s, i) => {
    const rc = s.ret_pct > 0 ? "#2ecc71" : s.ret_pct < 0 ? "#e74c3c" : "var(--muted)";
    const medal = i === 0 && s.ret_pct > 0 ? "👑 " : "";
    return `<div style="display:flex;justify-content:space-between;align-items:center;gap:.5rem;
        padding:.45rem .55rem;border:1px solid var(--border);border-radius:8px;margin-bottom:.4rem;">
      <div>
        <div style="font-weight:700;">${medal}${s.label}
          <span style="color:${rc};font-weight:800;margin-left:.4rem;">${s.ret_pct>0?"+":""}${s.ret_pct}%</span>
          <span style="color:var(--muted);font-size:0.72rem;margin-left:.3rem;">$${Math.round(s.equity).toLocaleString()}</span>
        </div>
        <div style="color:var(--muted);font-size:0.68rem;margin-top:.1rem;">${s.desc}</div>
        <div style="font-size:0.7rem;margin-top:.1rem;">${vpL("仓位：","Position: ")}<b>${s.position}</b>
          <span style="color:var(--muted)">· ${vpL(`${s.n_trades}次交易`, `${s.n_trades} trades`)} · ${s.last_action}</span></div>
      </div>
    </div>`;
  }).join("") + `<div style="color:var(--muted);font-size:0.68rem;margin-top:.2rem;">
    ${vpL(`每个 $${p.start_capital.toLocaleString()} · 自 ${p.start_date} 同日起跑 · ${p.note}`, `$${p.start_capital.toLocaleString()} each · all started on ${p.start_date} · ${p.note}`)}</div>`;

  // 净值曲线（数据来自各策略 curve，积累几个交易日后才有形状）
  const eqEl = document.getElementById("chart-equity");
  if (!eqEl) return;
  if (strats.some(s => (s.curve?.dates || []).length > 1)) {
    // 各策略 curve 起跑日相同但长度可能因当日是否已结算略有差异——取最长的一条作为
    // vpRangeBar 的数据末日/首日来源（最能代表"实验至今覆盖了多久"）。
    const eqDates = strats.map(s => s.curve?.dates || []).sort((a, b) => b.length - a.length)[0] || [];
    Plotly.newPlot("chart-equity", strats.map(s => ({
      x: s.curve.dates, y: s.curve.equity, type: "scatter", mode: "lines",
      name: s.label,
    })), {...DARK, yaxis:{...DARK.yaxis, title: vpL("净值 $","Equity $")}, hovermode:"x unified",
      legend:{orientation:"h", y:1.1}}, {responsive:true});
    if (typeof vpRangeBar === "function") vpRangeBar("chart-equity", { dates: eqDates });
  } else {
    eqEl.innerHTML = `<div style="color:var(--muted);font-size:0.78rem;display:flex;align-items:center;justify-content:center;height:100%;">${vpL("📈 净值曲线将在实验积累几个交易日后出现","📈 The equity curve will appear once the experiment accumulates a few trading days")}</div>`;
  }
}

// ═══════════════════════════════════════════════════════
//  模型体检报告（report.json）
// ═══════════════════════════════════════════════════════
async function loadReportPanel() {
  const el = document.getElementById("report-content");
  if (!el) return;
  let rep;
  try {
    const r = await fetch("report.json?_=" + Date.now());
    rep = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">${vpL("报告未生成（跑一次流水线即可）","Report not generated yet (run the pipeline once)")}</div>`;
    return;
  }
  el.innerHTML = (rep.sections || []).map(s => {
    const cols = s.table?.length ? Object.keys(s.table[0]) : [];
    const head = cols.map(c => `<th style="text-align:left;padding:.3rem .6rem;color:var(--muted);font-size:0.72rem;">${esc(c)}</th>`).join("");
    const rows = (s.table || []).map(r =>
      `<tr>${cols.map(c => `<td style="padding:.3rem .6rem;border-top:1px solid var(--border-faint);">${esc(r[c])}</td>`).join("")}</tr>`).join("");
    return `<div style="margin-bottom:1.1rem;">
      <div style="font-weight:700;margin-bottom:.35rem;">${esc(s.title)}</div>
      <table style="border-collapse:collapse;min-width:50%;">${head ? `<tr>${head}</tr>` : ""}${rows}</table>
      ${s.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.3rem;line-height:1.5;">${esc(s.note)}</div>` : ""}
    </div>`;
  }).join("") + `<div style="color:var(--muted);font-size:0.68rem;">${vpL(`生成于 ${esc(rep.generated)} · 模型 v${esc(rep.model_version)}`, `Generated ${esc(rep.generated)} · model v${esc(rep.model_version)}`)}</div>`;
}

// ═══════════════════════════════════════════════════════
//  今日市场要闻（news.json，由 AI 监控循环 / 手工更新）
// ═══════════════════════════════════════════════════════
// HTML 转义：RSS 标题来自外部源，必须当不可信数据处理（防 XSS）
function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// 相对时间（"3小时前"）——免去 UTC/ET/本地 多时区困惑；解析 "YYYY-MM-DD HH:MM" 当 UTC
function relTime(t) {
  const m = String(t || "").match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (!m) return "";
  const mins = Math.round((Date.now() - Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])) / 60000);
  if (mins < 0) return "";
  if (mins < 60) return mins <= 1 ? vpL("刚刚","just now") : vpL(`${mins}分钟前`, `${mins}m ago`);
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? vpL(`${hrs}小时前`, `${hrs}h ago`) : vpL(`${Math.round(hrs / 24)}天前`, `${Math.round(hrs / 24)}d ago`);
}

async function loadNewsPanel() {
  const el = document.getElementById("news-list");
  if (!el) return;
  let news;
  try {
    const r = await fetch("news.json?_=" + Date.now());
    news = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">${vpL("暂无要闻数据","No news data available")}</div>`;
    return;
  }
  const up = document.getElementById("news-updated");
  if (up && news.updated) up.textContent = vpL(`更新 ${relTime(news.updated) || news.updated}`, `Updated ${relTime(news.updated) || news.updated}`);
  const IC = { positive: ["▲", "#2ecc71"], negative: ["▼", "#e74c3c"], neutral: ["●", "#f1c40f"] };
  el.innerHTML = (news.items || []).map(n => {
    const [sym, color] = IC[n.impact] || IC.neutral;
    return `<div style="padding:.4rem 0;border-bottom:1px solid var(--border-faint);">
      <div style="display:flex;gap:.45rem;align-items:flex-start;">
        <span style="color:${color};flex-shrink:0;">${sym}</span>
        <div>
          <div style="font-weight:600;line-height:1.4;">${esc(n.title)}</div>
          ${n.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.15rem;line-height:1.5;">${esc(n.note)}</div>` : ""}
          <div style="color:var(--muted);font-size:0.65rem;margin-top:.15rem;">${relTime(n.time) ? esc(relTime(n.time)) + " · " : ""}${esc(n.time)}${n.source ? " · " + esc(n.source) : ""}</div>
        </div>
      </div>
    </div>`;
  }).join("") || `<div style="color:var(--muted)">${vpL("暂无要闻","No headlines available")}</div>`;
}

// 日历格点击 → 联动日期选择器并滚到信号表盘
function selectForecastDay(dateStr) {
  const dp = document.getElementById("date-picker");
  if (dp) dp.value = dateStr;
  updateSignal(dateStr);
  document.querySelector(".signal-meter")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderTradePlan(fc, allFc) {
  const el = document.getElementById("trade-plan");
  if (!el || !fc) return;
  const t = fc.tier;
  const action = t >= 4 ? [vpL("✅ 建议买入窗口","✅ Suggested buy window"), "#2ecc71"]
               : t === 3 ? [vpL("⏸ 中性 · 小仓试探或观望","⏸ Neutral · small test position or wait"), "#f1c40f"]
               : [vpL("🚫 偏弱 · 回避新仓/考虑减仓","🚫 Weak · avoid new positions / consider trimming"), "#e74c3c"];

  // 持有期内（后续20个交易日）的弱势日和宏观事件提醒
  const idx = allFc.findIndex(d => d.date === fc.date);
  const horizon = idx >= 0 ? allFc.slice(idx + 1, idx + 21) : [];
  const weakDays  = horizon.filter(d => d.tier <= 2).slice(0, 3);
  const macroDays = horizon.filter(d => d.macro).slice(0, 3);

  let html = `<div style="border:1px solid var(--border);border-radius:8px;padding:.7rem .8rem;font-size:0.78rem;line-height:1.65;">
    <div style="font-weight:700;color:${action[1]};margin-bottom:.3rem;">${fc.date}（${fc.dow_cn}）${action[0]}</div>`;

  if (t >= 3) {
    html += vpL(`🕐 <b>买入时段</b>：尾盘 <b>${tzRange(15,0,16,0)}</b><br>
      <span style="color:var(--muted)">依据隔夜收益异象（QQQ隔夜段年化+11%，日内段-2%）：避免开盘追高，接近收盘买入以捕获隔夜段。</span><br>
      📦 <b>持有期</b>：信号验证窗口为20个交易日（约1个月），短于此噪音大于信号。<br>
      🕐 <b>卖出时段</b>：如需卖出，开盘后首小时（${tzRange(9,30,10,30)}）历史上更有利（隔夜涨幅已落袋）。<br>`,
      `🕐 <b>Buy window</b>: late session <b>${tzRange(15,0,16,0)}</b><br>
      <span style="color:var(--muted)">Based on the overnight-return anomaly (QQQ overnight leg +11% annualized, intraday leg -2%): avoid chasing at the open, buy near the close to capture the overnight leg.</span><br>
      📦 <b>Holding period</b>: the signal's validation window is 20 trading days (~1 month) — shorter than that and noise dominates signal.<br>
      🕐 <b>Sell window</b>: if you need to sell, the first hour after the open (${tzRange(9,30,10,30)}) has historically been more favorable (the overnight gain is already banked).<br>`);
  } else {
    html += `<span style="color:var(--muted)">${vpL(`该日日历因子偏弱。如已持仓且计划减仓，开盘时段（${tzRange(9,30,10,30)}）通常优于尾盘。`, `The calendar factor is weak on this day. If you already hold a position and plan to trim, the opening session (${tzRange(9,30,10,30)}) is usually preferable to the close.`)}</span><br>`;
  }
  if (weakDays.length) {
    html += vpL(`⚠ 持有期内偏弱日：${weakDays.map(d => `${d.date.slice(5)}(${d.dow_cn})`).join("、")} —— 临近时复查信号<br>`,
                `⚠ Weak days within the holding period: ${weakDays.map(d => `${d.date.slice(5)}(${d.dow_cn})`).join(", ")} — re-check the signal as these approach<br>`);
  }
  if (macroDays.length) {
    html += vpL(`📊 持有期内宏观事件：${macroDays.map(d => `${d.date.slice(5)} ${d.macro}`).join("、")} —— 当日波动放大<br>`,
                `📊 Macro events within the holding period: ${macroDays.map(d => `${d.date.slice(5)} ${d.macro}`).join(", ")} — expect elevated volatility that day<br>`);
  }
  html += `<span class="u-cap">${vpL("以上为历史统计规律的机械应用，非投资建议；越远的日期技术因子失效越多，临近时以当日信号为准。","The above is a mechanical application of historical statistical patterns, not investment advice; the further out the date, the more the technical factors decay — rely on that day's signal as it approaches.")}</span></div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════
//  市场时钟：美东开收盘 ↔ 本地时间对照（自动处理夏令时）
// ═══════════════════════════════════════════════════════
// ── 时钟工具：美东秒级状态 + 任意时区 HH:MM:SS（Intl 自动处理夏令时，本地时区由浏览器自带，无需 IP）──
const _CLOCK_CN_DOW = { Mon:"周一", Tue:"周二", Wed:"周三", Thu:"周四", Fri:"周五", Sat:"周六", Sun:"周日" };
function _clockState(now) {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
    hour: "numeric", minute: "numeric", second: "numeric", weekday: "short", hour12: false })
    .formatToParts(now).reduce((a, x) => (a[x.type] = x.value, a), {});
  const etSec = (parseInt(p.hour) % 24) * 3600 + parseInt(p.minute) * 60 + parseInt(p.second);
  const isWeekday = !["Sat", "Sun"].includes(p.weekday);
  const openSec = (9 * 60 + 30) * 60, closeSec = 16 * 3600;
  const isOpen = isWeekday && etSec >= openSec && etSec < closeSec;
  let countdown = "";
  const fmtLeft = s => vpLang() === "en"
    ? (s >= 3600 ? Math.floor(s / 3600) + "h " : "") + Math.floor((s % 3600) / 60) + "m " + String(s % 60).padStart(2, "0") + "s"
    : (s >= 3600 ? Math.floor(s / 3600) + "小时" : "") + Math.floor((s % 3600) / 60) + "分" + String(s % 60).padStart(2, "0") + "秒";
  if (isOpen) countdown = vpL("距收盘 ","Closes in ") + fmtLeft(closeSec - etSec);
  else if (isWeekday && etSec < openSec) countdown = vpL("距开盘 ","Opens in ") + fmtLeft(openSec - etSec);
  return { p, etSec, isWeekday, isOpen, openSec, closeSec, countdown };
}
function _fmtHMS(tz, now) {
  return new Intl.DateTimeFormat("zh-CN", { timeZone: tz,
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now);
}
const _LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
const _LOCAL_CITY = (_LOCAL_TZ.split("/").pop() || vpL("本地","Local")).replace(/_/g, " ");

function renderMarketClock() {
  const el = document.getElementById("market-clock");
  if (!el) return;
  const now = new Date();
  const st = _clockState(now);

  const status = st.isOpen
    ? `<span style="color:#2ecc71;font-weight:700;">${vpL("● 开盘中","● Market open")}</span>`
    : `<span style="color:var(--muted);font-weight:700;">${vpL("○ 休市","○ Closed")}</span>`;
  const tzBtn = `<button data-tz-toggle title="${vpL("切换页面时间显示：美东统一 / 你的本地","Toggle displayed time: unified ET / your local time")}"
    style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);
    padding:1px 7px;border-radius:5px;font-size:0.68rem;cursor:pointer;">
    🕐 ${vpL(TZ_MODE === "ET" ? "美东" : "本地", TZ_MODE === "ET" ? "ET" : "Local")}${vpL("时间 ⇄"," time ⇄")}</button>`;
  // 本地时区与美东一致时（美国东部访客）不重复显示第二个钟
  const localClock = _LOCAL_TZ === "America/New_York" ? "" :
    ` · ${_LOCAL_CITY} <b style="color:var(--text);font-variant-numeric:tabular-nums;" id="clock-local">${_fmtHMS(_LOCAL_TZ, now)}</b>`;
  // en 模式:星期用 Intl 给的英文缩写键本身(Mon/Tue...)；zh 模式:查 _CLOCK_CN_DOW 映射中文
  const dowDisplay = vpLang() === "en" ? (st.p.weekday || "") : (_CLOCK_CN_DOW[st.p.weekday] || "");
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.3rem;">
      <span>${status} <span style="color:var(--muted);font-variant-numeric:tabular-nums;" id="clock-countdown">${st.countdown}</span></span>
      <span style="color:var(--muted)">${vpL("美东","ET")} ${dowDisplay} <b style="color:var(--text);font-variant-numeric:tabular-nums;" id="clock-et">${_fmtHMS("America/New_York", now)}</b>${localClock} ${tzBtn}</span>
    </div>
    <div style="color:var(--muted);margin-top:.25rem;">
      ${vpL("常规时段","Regular session")} <b style="color:var(--text)">${tzRange(9,30,16,0)}</b>
      <span style="font-size:0.68rem">${TZ_MODE === "ET" ? vpL("（页面时间已统一为美东·含夏令时）","(page time is unified to ET · DST-aware)") : vpL("（已换算为你的本地·含夏令时）","(converted to your local time · DST-aware)")}</span>
    </div>
    ${sessionTip()}`;

  // 盘中情境建议（基于隔夜收益异象）
  function sessionTip() {
    let tip = "";
    const etMin = Math.floor(st.etSec / 60), openMin = st.openSec / 60, closeMin = st.closeSec / 60;
    if (st.isOpen && etMin < openMin + 45) {
      tip = vpL("🔔 开盘初段（首45分钟）波动最大，历史上不宜追高——日内段长期收益≈0","🔔 The opening stretch (first 45 minutes) has the highest volatility — historically not a good time to chase; the intraday leg's long-run return is ≈0");
    } else if (st.isOpen && etMin >= closeMin - 60) {
      tip = vpL("🔔 尾盘时段——按信号执行买入的优选窗口（捕获隔夜段收益）","🔔 Late session — the preferred window for executing signal-based buys (captures the overnight-leg return)");
    } else if (st.isOpen) {
      tip = vpL("🔔 盘中：当日数据为临时价，正式信号以收盘后刷新为准","🔔 Market open: today's data is provisional — the official signal refreshes after the close");
    } else if (st.isWeekday && etMin < openMin) {
      tip = vpL("🔔 未开盘。如计划买入，统计上尾盘买入优于开盘追高","🔔 Market not yet open. If you plan to buy, buying near the close has historically outperformed chasing at the open");
    }
    return tip ? `<div style="color:#f1c40f;font-size:0.72rem;margin-top:.3rem;">${tip}</div>` : "";
  }
}
// 每秒只更新时间/倒计时文本（不重建 DOM，按钮可正常点击）；开/收盘状态翻转由 30 秒全量重渲染兜底
function _marketClockTick() {
  const et = document.getElementById("clock-et");
  if (!et) return;
  const now = new Date();
  et.textContent = _fmtHMS("America/New_York", now);
  const lt = document.getElementById("clock-local");
  if (lt) lt.textContent = _fmtHMS(_LOCAL_TZ, now);
  const cd = document.getElementById("clock-countdown");
  if (cd) cd.textContent = _clockState(now).countdown;
}
setInterval(renderMarketClock, 30000);
setInterval(_marketClockTick, 1000);

// ═══════════════════════════════════════════════════════
//  今日时间线（页头醒目位置）：今日日期(访客本地·完整含星期) ·
//  美东精确时间(自动含夏令时+开/休市) · 阿德莱德精确时间。
//  复用上面的 _clockState/_CLOCK_CN_DOW/_LOCAL_TZ——不重造第二套时区换算，每分钟自刷新。
// ═══════════════════════════════════════════════════════
function _isoDate(tz, now) {
  // en-CA 的日期格式恰好是 YYYY-MM-DD，借用它免去手拼补零
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
function _mdhm(tz, now) {   // 美式 MM/DD HH:MM（Intl 自动处理夏令时）
  const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(now).reduce((a, x) => (a[x.type] = x.value, a), {});
  return `${p.month}/${p.day} ${p.hour}:${p.minute}`;
}
function _dmhm(tz, now) {   // 澳式 DD/MM HH:MM
  const p = new Intl.DateTimeFormat("en-GB", { timeZone: tz, day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(now).reduce((a, x) => (a[x.type] = x.value, a), {});
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
}
function renderTodayLine() {
  const el = document.getElementById("vp-todayline");
  if (!el) return;
  const now = new Date();
  const wdKey = new Intl.DateTimeFormat("en-US", { timeZone: _LOCAL_TZ, weekday: "short" }).format(now);
  const wd = vpLang() === "en" ? wdKey : (_CLOCK_CN_DOW[wdKey] || wdKey);
  const etOpen = _clockState(now).isOpen;
  const etStatus = vpL(etOpen ? "开盘中" : "休市", etOpen ? "open" : "closed");
  el.innerHTML = vpL(
    `📅 ${_isoDate(_LOCAL_TZ, now)} ${wd} · 美东 ${_mdhm("America/New_York", now)} ET(${etStatus}) · 阿德莱德 ${_dmhm("Australia/Adelaide", now)}`,
    `📅 ${_isoDate(_LOCAL_TZ, now)} ${wd} · ET ${_mdhm("America/New_York", now)} (${etStatus}) · Adelaide ${_dmhm("Australia/Adelaide", now)}`
  );
}
setInterval(renderTodayLine, 60000);

// ═══════════════════════════════════════════════════════
//  隔夜 vs 日内收益分解
// ═══════════════════════════════════════════════════════
let OVERNIGHT = null, _ovCur = null;
async function loadOvernightPanel() {
  try {
    const r = await fetch("overnight.json?_=" + Date.now());
    OVERNIGHT = await r.json();
  } catch(e) { console.warn("overnight.json 未找到", e); return; }
  const names = Object.keys(OVERNIGHT.indices || {});
  if (!names.length) return;
  const btns = document.getElementById("overnight-btns");
  if (btns) btns.innerHTML = names.map((n, i) =>
    `<button class="period-btn ${i === 0 ? "active" : ""}" data-overnight="${n}">${n.split("_")[0]}</button>`
  ).join("");
  renderOvernight(names[names.length - 1]);
}

function renderOvernight(name, btn) {
  const d = OVERNIGHT?.indices?.[name];
  if (!d) return;
  _ovCur = name;
  if (btn) {
    document.querySelectorAll("#overnight-btns .period-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  }
  const series = [
    ["overnight", vpL("隔夜持有（收盘买→次日开盘卖）","Overnight hold (buy at close → sell next open)"), "#9b59b6"],
    ["intraday",  vpL("日内持有（开盘买→收盘卖）","Intraday hold (buy at open → sell at close)"),     "#e67e22"],
    ["total",     vpL("买入持有","Buy &amp; hold"), "#3498db"],
  ];
  const traces = series.map(([k, label, color]) => ({
    x: d[k].cum.dates, y: d[k].cum.values, name: label,
    type: "scatter", mode: "lines", line: { color, width: k === "total" ? 1.4 : 2.2,
      dash: k === "total" ? "dot" : "solid" },
  }));
  Plotly.newPlot("chart-overnight", traces, {...DARK, hovermode: "x unified",
    yaxis: {...DARK.yaxis, title: vpL("累计净值（起点=1）","Cumulative value (start=1)"), type: "log"},
    legend: { orientation: "h", y: 1.08 }},
    {displayModeBar: false, responsive: true});

  const ins = document.getElementById("overnight-insight");
  if (ins) {
    const ov = d.overnight.stats, intr = d.intraday.stats, r10 = d.recent10y;
    ins.innerHTML = vpL(`<b>${name}（2000–2026）：</b>隔夜段年化 <b style="color:#9b59b6">${ov.ann_return}%</b>（胜率${ov.win_rate}%），
      日内段年化 <b style="color:#e67e22">${intr.ann_return}%</b>（胜率${intr.win_rate}%）。
      近10年：隔夜 ${r10.overnight.ann_return}% vs 日内 ${r10.intraday.ann_return}%。
      <br><span style="color:var(--muted);font-size:0.75rem">⚠ 这是著名的「隔夜收益异象」（Lou/Polk/Skouras 2019）。注意：若实际执行需每天两笔交易，
      点差+手续费+税会吞掉大部分优势，更适合用来「选择入场时间」（如尽量收盘前买入而非开盘追高），而非高频策略。</span>`,
      `<b>${name} (2000–2026):</b> overnight leg annualized <b style="color:#9b59b6">${ov.ann_return}%</b> (win rate ${ov.win_rate}%),
      intraday leg annualized <b style="color:#e67e22">${intr.ann_return}%</b> (win rate ${intr.win_rate}%).
      Past 10 years: overnight ${r10.overnight.ann_return}% vs. intraday ${r10.intraday.ann_return}%.
      <br><span style="color:var(--muted);font-size:0.75rem">⚠ This is the well-known "overnight return anomaly" (Lou/Polk/Skouras 2019). Note: executing it in practice requires two trades a day —
      spread + fees + taxes would eat most of the edge, so it's better used to "pick an entry time" (e.g. buying near the close instead of chasing at the open) than as a high-frequency strategy.</span>`);
  }
}

// ═══════════════════════════════════════════════════════
//  语言切换收尾：重画"不在 renderAll 里"的持久 app-4 面板
// ═══════════════════════════════════════════════════════
// 背景：renderAll()（app-5.js:177）已覆盖 renderSPCXTracker/renderIndicesCompare/renderLiveTracking/
// loadStocksPanel(→renderStocksTable)/fetchFearAndGreed(→renderFearGreed)/loadQuotes(→renderSPCXMonitor)/
// renderMarketClock——切语言调 renderAll() 时这几个已自动用新语言重画，无需在此重复。
// 但下列面板不在 renderAll 里，若不额外重画，切语言后会留旧语言直到用户手动触发（点计算/点获取价格等）：
//   · CGT 计算器：货币选择器 + 已显示的计算结果
//   · SPCX 明细/计算：chart-spcx-ipo 历史分布图 + 盈亏计算器
//   · 我的模拟盘：持仓/净值展示
// 幂等 + 不碰用户数据（均已逐一核实，非猜测）：
//   - calculateCGT/updateSPCXCalc 只读当前 DOM 输入框的值和 localStorage 已存的值，从不写入/清空输入框；
//     不会新增 fetch，唯一"写"是 updateSPCXCalc 在输入框有值时把同一个值原样存回 localStorage（非新数据）。
//   - renderGamePanel 只读 gameState()（localStorage），不写、不重置模拟盘持仓/现金/交易记录。
//   - renderSPCXDetail 只用页面内静态历史数组作图，无 fetch/无副作用。
//   - chart-spcx-ipo 所在的"我的"视图默认 display:none；Plotly 在隐藏容器画图算不出宽度，
//     但 switchView()（app-5.js）在视图变为可见时已调用 resizeChartsIn()——按代码里的注释，
//     这个函数就是专门"修复曾在隐藏状态下渲染的图"（app-1.js:1018），所以这里无需按 offsetParent
//     可见性门槛跳过：用户下次切到该视图时尺寸会自动修好，文字这次已经是新语言。
//   - calculateCGT 只在 #cgt-result 已经有内容（用户之前点过"计算税务"）时才重跑，避免对着
//     从未用过的空面板凭空生成一条"请填写数量…"提示；货币选择器本身与是否算过无关，随时重画。
// 主脑将在 dashboard.html 的语言 toggle 处理器里加一行：
//   try{ if(typeof reRenderAppTools==="function") reRenderAppTools(); }catch(e){}
// 本文件只定义函数，不接线 dashboard.html。
function reRenderAppTools() {
  try { if (typeof renderCgtCurrencySelector === "function") renderCgtCurrencySelector(); }
  catch (e) { console.warn("reRenderAppTools renderCgtCurrencySelector failed", e); }
  try {
    const cgtResult = document.getElementById("cgt-result");
    if (cgtResult && cgtResult.innerHTML.trim() && typeof calculateCGT === "function") calculateCGT();
  } catch (e) { console.warn("reRenderAppTools calculateCGT failed", e); }

  try { if (typeof renderSPCXDetail === "function") renderSPCXDetail(); }
  catch (e) { console.warn("reRenderAppTools renderSPCXDetail failed", e); }
  try { if (typeof updateSPCXCalc === "function") updateSPCXCalc(); }
  catch (e) { console.warn("reRenderAppTools updateSPCXCalc failed", e); }

  try { if (typeof renderGamePanel === "function") renderGamePanel(); }
  catch (e) { console.warn("reRenderAppTools renderGamePanel failed", e); }
}

