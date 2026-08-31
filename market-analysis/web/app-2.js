// ══════════════════════════════════════════════════════
//  多元分析图表
// ══════════════════════════════════════════════════════
// i18n 安全兜底(#5 深度面板双语化 W2b)：vpL(zh,en) 单一来源是 vp_i18n.js（W1a 接线）。
// 挂到 window 而非 const/let 声明本地别名——5 个 app-*.js 共享同一全局脚本作用域，
// 若多文件各自声明同名会因重复声明抛 SyntaxError、整文件失效。
// vp_i18n.js 尚未加载/接线时退化为恒返回 zh，页面纯中文不崩。
if (typeof window.vpL !== "function") window.vpL = function (zh, en) { return zh; };

// dow_cn 来自后端(build_signals.py DOW_CN，固定枚举"周一".."周五")；后端只吐中文，
// EN 模式下用本地映射转英文缩写，避免要求后端再吐一份英文字段。
const DOW_CN_EN = { "周一":"Mon", "周二":"Tue", "周三":"Wed", "周四":"Thu", "周五":"Fri" };
function dowLabel(cn) { return vpL(cn, DOW_CN_EN[cn] || cn); }

// stock_checkup.py TICKER_NAMES：18 支固定枚举，后端只吐中文公司名。
const TICKER_NAME_EN = {
  AAPL:"Apple", MSFT:"Microsoft", GOOGL:"Google", AMZN:"Amazon", NVDA:"Nvidia",
  META:"Meta", TSLA:"Tesla", AVGO:"Broadcom", TSM:"TSMC", COST:"Costco",
  LLY:"Eli Lilly", "BRK-B":"Berkshire Hathaway", KO:"Coca-Cola", SNDK:"SanDisk", MU:"Micron",
  AMD:"AMD", INTC:"Intel", NFLX:"Netflix", HOOD:"Robinhood",
};
function tickerName(code, zhName) { return vpL(zhName, TICKER_NAME_EN[code] || zhName); }

// stock_checkup.py _effect_test：日历效应名固定枚举("星期几"/"月份")，后端只吐中文。
const EFFECT_EN = { "星期几":"Day of week", "月份":"Month" };
function effectLabel(zh) { return vpL(zh, EFFECT_EN[zh] || zh); }

// EVT 尾部描述来自后端(risk_dashboard.py / stock_checkup.py 共享同一枚举值集)，只吐中文。
const TAIL_EN = {
  "厚尾(ξ>0,极端损失比指数更重)": "Fat tail (ξ>0, extreme losses heavier than exponential)",
  "近指数尾(ξ≈0)": "Near-exponential tail (ξ≈0)",
  "薄尾(ξ<0,损失有上界)": "Thin tail (ξ<0, losses are bounded)",
};
function tailLabel(zh) { return vpL(zh, TAIL_EN[zh] || zh); }

// long_history.py presidential_cycle 的 label 是固定 4 值枚举，后端只吐中文括注。
const CYCLE_LABEL_EN = {
  "Year 1 (新任期)": "Year 1 (new term)", "Year 2 (中期选举)": "Year 2 (midterm)",
  "Year 3 (选前)": "Year 3 (pre-election)", "Year 4 (大选年)": "Year 4 (election year)",
};
function cycleLabel(zh) { return vpL(zh, CYCLE_LABEL_EN[zh] || zh); }

// long_history.py _PRESIDENTS：17 位总统固定枚举，后端只吐中文名。
const PRESIDENT_NAME_EN = {
  "胡佛":"Hoover", "罗斯福":"FDR", "杜鲁门":"Truman", "艾森豪威尔":"Eisenhower",
  "肯尼迪":"Kennedy", "约翰逊":"Johnson", "尼克松":"Nixon", "福特":"Ford",
  "卡特":"Carter", "里根":"Reagan", "布什(父)":"Bush Sr.", "克林顿":"Clinton",
  "布什(子)":"Bush Jr.", "奥巴马":"Obama", "特朗普1":"Trump I", "拜登":"Biden", "特朗普2":"Trump II",
};
function presidentName(zh) { return vpL(zh, PRESIDENT_NAME_EN[zh] || zh); }

function renderModelComparison() {
  if (!MV || !MV.model_comparison) return;
  const mc = MV.model_comparison;

  // ML模型：用AUC排序（AUC是分类质量的真实衡量）
  const ml = [...mc.ml_models].sort((a,b) => b.auc - a.auc);
  // 统计模型：用R²排序
  const st = [...mc.stats_models].sort((a,b) => b.r2_pct - a.r2_pct);

  const allNames  = [...ml.map(m=>m.name+vpL("（ML）"," (ML)")), ...st.map(s=>s.name)].reverse();
  const allValues = [...ml.map(m=>+(m.auc*100).toFixed(1)), ...st.map(s=>s.r2_pct)].reverse();
  const allColors = [
    ...st.map(s => s.significant ? "#3498db" : "#555"),
    ...ml.map(m => "#9b59b6"),
  ];
  const allText = [
    ...ml.map(m=>`AUC=${m.auc} Acc=${m.acc}`),
    ...st.map(s=>`R²=${s.r2_pct}% ${s.note}`),
  ].reverse();

  Plotly.newPlot("chart-modelcmp", [{
    type: "bar", orientation: "h",
    x: allValues, y: allNames,
    marker: { color: allColors },
    text: allText,
    textposition: "outside",
    hovertemplate: "<b>%{y}</b><br>%{text}<extra></extra>",
    cliponaxis: false,
  }], {
    ...DARK,
    xaxis: {...DARK.xaxis, title: vpL("解释力 / AUC×100（越大越好）","Explanatory power / AUC×100 (higher = better)"), range: [0, 70]},
    margin: {t:20, b:50, l:200, r:80},
    shapes: [
      {type:"line",x0:50,x1:50,y0:-0.5,y1:allNames.length-0.5,
       line:{color:"#9b59b6",dash:"dot",width:1}},
    ],
    annotations: [
      {x:50, y:allNames.length-0.5, text: vpL("AUC=0.5（随机水平）","AUC=0.5 (random level)"),
       showarrow:false, font:{color:"#9b59b6",size:10}},
    ]
  }, {responsive:true});

  // 找最佳ML和最佳统计
  const bestML  = ml[0];
  const bestStat= st[0];
  document.getElementById("modelcmp-insight").innerHTML = vpL(`
     <strong>核心结论：</strong><br>
     <span style="color:#3498db">统计关系模型</span>（<strong>${bestStat.name}</strong>）解释力最高，R²=<strong style="color:#2ecc71">${bestStat.r2_pct}%</strong>——
     这是"已知X时，Y的方差有多少被解释"。<br>
     <span style="color:#9b59b6">机器学习分类模型</span> AUC 最高仅 <strong style="color:#f1c40f">${(bestML.auc*100).toFixed(1)}</strong>（随机=50）——
     这是"预测明天涨还是跌"，市场半有效，难度极大。<br>
     <span style="color:var(--muted);font-size:0.78rem">解读：VIX和SP500高度相关≠可以用VIX预测未来涨跌。相关是同步的，预测是提前的——两回事。</span>`, `
     <strong>Core takeaway:</strong><br>
     <span style="color:#3498db">The statistical relationship model</span> (<strong>${bestStat.name}</strong>) has the highest explanatory power, R²=<strong style="color:#2ecc71">${bestStat.r2_pct}%</strong> —
     this is "given X, how much of Y's variance is explained."<br>
     <span style="color:#9b59b6">The machine-learning classification model</span>'s best AUC is only <strong style="color:#f1c40f">${(bestML.auc*100).toFixed(1)}</strong> (random = 50) —
     this is "predicting whether tomorrow goes up or down," which the market is semi-efficient against, so it's extremely hard.<br>
     <span style="color:var(--muted);font-size:0.78rem">Interpretation: VIX and the S&amp;P 500 being highly correlated ≠ VIX can predict future moves. Correlation is contemporaneous; prediction is forward-looking — two different things.</span>`);
}

function renderSHAPChart() {
  if (!MV || !MV.shap) return;
  const items = MV.shap.slice(0,12).reverse();
  const colors = items.map(d => d.importance > 0.5 ? "#27ae60" : d.importance > 0.3 ? "#f1c40f" : "#3498db");

  Plotly.newPlot("chart-shap", [{
    type:"bar", orientation:"h",
    x: items.map(d=>d.importance),
    y: items.map(d=>d.feature.replace(/_/g," ")),
    marker:{color: colors},
    text: items.map(d=>d.importance.toFixed(3)),
    textposition:"outside",
    hovertemplate: vpL("<b>%{y}</b><br>SHAP影响: %{x:.4f}<extra></extra>","<b>%{y}</b><br>SHAP impact: %{x:.4f}<extra></extra>")
  }], {...DARK, xaxis:{...DARK.xaxis,title: vpL("平均|SHAP|值（越大=对预测影响越大）","Mean |SHAP| value (larger = more influence on the prediction)")},
    margin:{t:20,b:40,l:160,r:60}}, {responsive:true});

  const sep = vpL("、", ", ");
  const bul = MV.shap_latest?.bullish?.map(d=>`${d.feature.replace(/_/g," ")} <span style="color:#2ecc71">(+${d.shap})</span>`).join(sep) || "";
  const bea = MV.shap_latest?.bearish?.map(d=>`${d.feature.replace(/_/g," ")} <span style="color:#e74c3c">(${d.shap})</span>`).join(sep) || "";
  document.getElementById("shap-insight").innerHTML = vpL(`
     <strong>当前预测解释：</strong><br>
     支持上涨：${bul}<br>
     支持下跌：${bea}<br>
     <span style="color:var(--muted);font-size:0.78rem">SHAP = 每个因子对本次预测的实际推拉量。正值推高预测，负值拖低预测。</span>`, `
     <strong>Current-prediction explanation:</strong><br>
     Bullish support: ${bul}<br>
     Bearish support: ${bea}<br>
     <span style="color:var(--muted);font-size:0.78rem">SHAP = the actual push/pull each factor contributes to this prediction. Positive values push the prediction up, negative values pull it down.</span>`);
}

function renderProphetChart() {
  if (!MV || !MV.prophet || !MV.prophet.length) return;
  const p = MV.prophet;
  Plotly.newPlot("chart-prophet", [
    {x:p.map(d=>d.date), y:p.map(d=>d.upper), name: vpL("上界","Upper bound"), type:"scatter",
     mode:"lines", line:{color:"rgba(52,152,219,.3)",width:1}, showlegend:false},
    {x:p.map(d=>d.date), y:p.map(d=>d.lower), name: vpL("下界","Lower bound"), type:"scatter",
     mode:"lines", fill:"tonexty", fillcolor:"rgba(52,152,219,.15)",
     line:{color:"rgba(52,152,219,.3)",width:1}, showlegend:false},
    {x:p.map(d=>d.date), y:p.map(d=>d.yhat), name: vpL("Prophet预测","Prophet forecast"), type:"scatter",
     mode:"lines+markers", line:{color:"#3498db",width:2.5},
     marker:{size:7}, text:p.map(d=> vpL(`${d.date}<br>预测：${d.yhat.toLocaleString()}`, `${d.date}<br>Forecast: ${d.yhat.toLocaleString()}`)),
     hovertemplate:"%{text}<extra></extra>"},
  ], {...DARK, yaxis:{...DARK.yaxis,title: vpL("S&P 500 预测点位","S&P 500 forecast level")},
    legend:{orientation:"h",y:1.05},
    annotations:[{x:p[p.length-1].date, y:p[p.length-1].yhat, text:`${p[p.length-1].yhat.toLocaleString()}`,
      showarrow:true, arrowhead:2, ax:40, ay:-30, font:{color:"#3498db",size:11}}]
  }, {responsive:true});
}

function renderKalmanChart() {
  if (!MV || !MV.kalman) return;
  const k = MV.kalman;
  Plotly.newPlot("chart-kalman", [
    {x:k.map(d=>d.date), y:k.map(d=>d.observed), name: vpL("实际月收益%","Actual monthly return %"), type:"scatter",
     mode:"lines", line:{color:"#8b949e",width:1}, opacity:.7},
    {x:k.map(d=>d.date), y:k.map(d=>d.trend), name: vpL("卡尔曼趋势信号","Kalman trend signal"), type:"scatter",
     mode:"lines", line:{color:"#f1c40f",width:2.5},
     hovertemplate: vpL("<b>%{x}</b><br>趋势 %{y:.2f}%/月<extra></extra>","<b>%{x}</b><br>Trend %{y:.2f}%/mo<extra></extra>")},
    {x:[k[k.length-1].date], y:[MV.kalman_current], name: vpL("当前趋势","Current trend"), mode:"markers",
     marker:{color:"#2ecc71",size:12,symbol:"diamond"},
     hovertemplate: vpL(`当前趋势：${MV.kalman_current}%/月<extra></extra>`, `Current trend: ${MV.kalman_current}%/mo<extra></extra>`)},
  ], {...DARK, yaxis:{...DARK.yaxis,title: vpL("月收益率 %","Monthly return %"), zeroline:true, zerolinecolor:"#555"},
    legend:{orientation:"h",y:1.05},
    shapes:[{type:"line",x0:k[0].date,x1:k[k.length-1].date,y0:0,y1:0,
      line:{color:"#555",dash:"dash",width:1}}]
  }, {responsive:true});
}

function renderRollingBetaChart() {
  if (!MV || !MV.rolling_betas) return;
  const rb = MV.rolling_betas;
  const colors = {VIX:"#e74c3c",DXY:"#3498db",OIL:"#e67e22",TNX:"#9b59b6"};
  const traces = Object.entries(colors).map(([k,c]) => ({
    x: rb.dates, y: rb[k], name:`SP500 vs ${k}`, type:"scatter", mode:"lines",
    line:{color:c,width:1.8},
    hovertemplate:`<b>SP500 β ${k}</b> %{x}<br>β=%{y:.4f}<extra></extra>`
  }));
  traces.push({x:[rb.dates[0],rb.dates[rb.dates.length-1]],y:[0,0],
    mode:"lines",line:{color:"#555",dash:"dash"},showlegend:false});
  Plotly.newPlot("chart-rolling", traces, {...DARK,
    yaxis:{...DARK.yaxis,title: vpL("滚动β系数（36月窗口）","Rolling β coefficient (36-month window)")},
    legend:{orientation:"h",y:1.05},hovermode:"x unified"}, {responsive:true});
}

function renderPathChart() {
  if (!MV || !MV.path) return;
  const p = MV.path;
  const colors = p.map(d => d.significant ? "#2ecc71" : "#8b949e");
  Plotly.newPlot("chart-path", [{
    type:"bar", orientation:"h",
    x: p.map(d=>d.beta), y: p.map(d=>d.path),
    marker:{color:colors},
    text: p.map(d=>`β=${d.beta.toFixed(3)} p=${d.pvalue.toFixed(3)} ${d.significant?"✓":"✗"}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>"
  }], {...DARK, xaxis:{...DARK.xaxis,title: vpL("路径系数β（正=正向影响，负=负向影响）","Path coefficient β (positive = positive effect, negative = negative effect)")},
    margin:{t:20,b:40,l:150,r:100},
    shapes:[{type:"line",x0:0,x1:0,y0:-0.5,y1:p.length-0.5,
      line:{color:"#555",dash:"dash",width:1}}]
  }, {responsive:true});

  const sig = p.filter(d=>d.significant);
  document.getElementById("path-insight").innerHTML = vpL(
    `<strong>显著因果路径（p&lt;0.05）：</strong>` +
    sig.map(d=>`<span style="color:#2ecc71">${d.path}</span> β=${d.beta.toFixed(3)} R²=${d.r2.toFixed(3)}`).join(" · ") +
    `<br><span style="color:var(--muted);font-size:0.78rem">灰色=统计上不显著，绿色=已证实的因果链路。VIX→SP500 解释力最强（R²=0.56）。</span>`,
    `<strong>Significant causal paths (p&lt;0.05):</strong>` +
    sig.map(d=>`<span style="color:#2ecc71">${d.path}</span> β=${d.beta.toFixed(3)} R²=${d.r2.toFixed(3)}`).join(" · ") +
    `<br><span style="color:var(--muted);font-size:0.78rem">Gray = not statistically significant, green = a confirmed causal link. VIX→SP500 has the strongest explanatory power (R²=0.56).</span>`
  );
}

function renderCCAChart() {
  if (!MV || !MV.cca || !MV.rda) return;

  // CCA canonical correlations bar + RDA marginal contributions
  const ccaCorrs = MV.cca.canonical_corrs || [];
  const rdaRows  = MV.rda || [];
  const macroLoad = MV.cca.macro_loadings || {};
  const assetLoad = MV.cca.asset_loadings || {};

  const traces = [
    {type:"bar", name: vpL("CCA典型相关系数","CCA canonical correlation"),
     x:ccaCorrs.map((_,i)=> vpL(`第${i+1}典型变量`, `Canonical variate ${i+1}`)), y:ccaCorrs,
     marker:{color:["#2ecc71","#3498db","#9b59b6"]},
     text:ccaCorrs.map(v=>v.toFixed(3)), textposition:"outside",
     hovertemplate:"%{x}<br>r=%{y:.3f}<extra></extra>"},
  ];
  Plotly.newPlot("chart-cca", traces, {...DARK,
    yaxis:{...DARK.yaxis,range:[0,0.8],title: vpL("典型相关系数 r","Canonical correlation r")},
    margin:{t:20,b:50,l:60,r:20}
  }, {responsive:true});

  const sep = vpL("、", ", ");
  const macroTop = Object.entries(macroLoad).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,3)
    .map(([k,v])=>`${k} (${v>0?"+":""}${v.toFixed(2)})`).join(sep);
  const rdaTotal = rdaRows.reduce((s,r)=>s+r.marginal_r2,0).toFixed(1);
  const rdaBest = rdaRows.sort((a,b)=>b.marginal_r2-a.marginal_r2)[0];
  document.getElementById("cca-insight").innerHTML = vpL(
    `<strong>典型相关（CCA）：</strong>宏观因子与资产价格的最强共变组合 r=<span style="color:#2ecc71">${ccaCorrs[0]?.toFixed(3)||"—"}</span>，
     第1宏观载荷主要由 <span style="color:#f1c40f">${macroTop}</span> 驱动。<br>
     <strong>冗余分析（RDA）：</strong>宏观变量合计解释资产方差 <span style="color:#3498db">${rdaTotal}%</span>，
     贡献最大的是 <span style="color:#2ecc71">${rdaBest?.macro}</span>（${rdaBest?.marginal_r2.toFixed(2)}%）。
     其余 ${(100-rdaTotal).toFixed(1)}% 由市场情绪和动量主导——这解释了为什么宏观指标无法完全预测短期行情。`,
    `<strong>Canonical correlation (CCA):</strong> the strongest co-movement combination between macro factors and asset prices is r=<span style="color:#2ecc71">${ccaCorrs[0]?.toFixed(3)||"—"}</span>,
     with the 1st macro loading driven mainly by <span style="color:#f1c40f">${macroTop}</span>.<br>
     <strong>Redundancy analysis (RDA):</strong> macro variables jointly explain <span style="color:#3498db">${rdaTotal}%</span> of asset variance,
     with the largest contribution from <span style="color:#2ecc71">${rdaBest?.macro}</span> (${rdaBest?.marginal_r2.toFixed(2)}%).
     The remaining ${(100-rdaTotal).toFixed(1)}% is dominated by market sentiment and momentum — which is why macro indicators can't fully predict short-term price action.`
  );
}

// ── 30日概率前瞻图 ──
function renderForecastChart() {
  if (!SIGNALS || !SIGNALS.next_opportunities) return;
  const opp = SIGNALS.next_opportunities;
  const all = opp.all_forecast || [];
  if (all.length === 0) return;

  const dates  = all.map(d => d.date);
  const probs  = all.map(d => +(d.prob * 100).toFixed(1));
  const tiers  = all.map(d => d.tier);
  const dows   = all.map(d => dowLabel(d.dow_cn));
  const reasons= all.map(d => d.reasons.join(vpL("、", ", ")) || vpL("普通交易日","Ordinary trading day"));
  const tops   = new Set(opp.top_entry.map(x => x.date));
  const bottoms= new Set(opp.top_exit.map(x => x.date));

  const colors = dates.map((d, i) => {
    if (tops.has(d))    return "#27ae60";
    if (bottoms.has(d)) return "#e74c3c";
    return tiers[i] >= 4 ? "#2ecc71" : tiers[i] <= 2 ? "#e67e22" : "#3498db";
  });

  Plotly.newPlot("chart-forecast", [{
    type: "bar",
    x: dates, y: probs,
    marker: { color: colors, opacity: 0.85 },
    text: dows,
    customdata: reasons,
    hovertemplate: vpL("<b>%{x}</b> (%{text})<br>概率: <b>%{y:.1f}%</b><br>%{customdata}<extra></extra>",
                        "<b>%{x}</b> (%{text})<br>Probability: <b>%{y:.1f}%</b><br>%{customdata}<extra></extra>"),
  }], {
    ...DARK,
    yaxis: {...DARK.yaxis, title: vpL("信号概率 (%)","Signal probability (%)"), range: [45, 80]},
    xaxis: {...DARK.xaxis, tickangle: -45, tickfont: {size: 10}},
    margin: {t:20, b:80, l:60, r:20},
    shapes: [
      {type:"line", x0:dates[0], x1:dates[dates.length-1], y0:60, y1:60,
       line:{color:"#2ecc71", dash:"dot", width:1}},
      {type:"line", x0:dates[0], x1:dates[dates.length-1], y0:55, y1:55,
       line:{color:"#f1c40f", dash:"dot", width:1}},
    ],
    annotations: [
      {x:dates[Math.floor(dates.length*0.9)], y:60.5, text: vpL("60% 参考线","60% reference line"),
       showarrow:false, font:{color:"#2ecc71",size:10}},
      {x:dates[Math.floor(dates.length*0.9)], y:55.5, text: vpL("55% 中性线","55% neutral line"),
       showarrow:false, font:{color:"#f1c40f",size:10}},
    ]
  }, {responsive:true});

  const topDate = opp.top_entry[0];
  const tech = opp.latest_tech || {};
  const maState = tech.nasdaq_ma200 === 1 ? vpL("NASDAQ在200均线上方（偏多）","Nasdaq above its 200-day moving average (bullish-leaning)") : vpL("NASDAQ在200均线下方（偏空）","Nasdaq below its 200-day moving average (bearish-leaning)");
  document.getElementById("forecast-insight").innerHTML = vpL(`
     <strong>未来45交易日概率前瞻</strong><br>
     <span style="color:#27ae60">绿色</span>=历史偏强窗口 &nbsp;
     <span style="color:#e74c3c">红色</span>=历史偏弱窗口 &nbsp;
     <span style="color:#3498db">蓝色</span>=普通日<br>
     最高概率日：<strong style="color:#27ae60">${topDate.date} (${dowLabel(topDate.dow_cn)})</strong>
     — ${topDate.prob*100 > 0 ? (topDate.prob*100).toFixed(1) : "—"}%，原因：${topDate.reasons.join("、") || "日历因子叠加"}<br>
     <span style="color:var(--muted);font-size:0.78rem">
       技术信号已冻结为最新值：${maState}；RSI=${tech.nasdaq_rsi}；BTC动量=${tech.btc_mom20?.toFixed(3) || "—"}。
       日历因子（星期/月份/假日/税季）可精确预测，技术信号近期不确定。
     </span>`, `
     <strong>Next-45-trading-day probability outlook</strong><br>
     <span style="color:#27ae60">Green</span> = historically stronger window &nbsp;
     <span style="color:#e74c3c">Red</span> = historically weaker window &nbsp;
     <span style="color:#3498db">Blue</span> = ordinary day<br>
     Highest-probability day: <strong style="color:#27ae60">${topDate.date} (${dowLabel(topDate.dow_cn)})</strong>
     — ${topDate.prob*100 > 0 ? (topDate.prob*100).toFixed(1) : "—"}%, reason: ${(topDate.reasons_en && topDate.reasons_en.length ? topDate.reasons_en : (topDate.reasons||[])).join(", ") || "Overlapping calendar factors"}<br>
     <span style="color:var(--muted);font-size:0.78rem">
       Technical signals are frozen at their latest value: ${maState}; RSI=${tech.nasdaq_rsi}; BTC momentum=${tech.btc_mom20?.toFixed(3) || "—"}.
       Calendar factors (day-of-week / month / holiday / tax season) can be predicted precisely; technical signals are uncertain in the near term.
     </span>`);
}

// ── 未来操作窗口面板（左栏）──
function renderOppPanel() {
  if (!SIGNALS || !SIGNALS.next_opportunities) return;
  const opp = SIGNALS.next_opportunities;

  const TIER_COLOR = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };
  const TIER_LABEL = vpL(
    { 5:"强势", 4:"适合", 3:"中性", 2:"谨慎", 1:"高险" },
    { 5:"Strong", 4:"Favorable", 3:"Neutral", 2:"Cautious", 1:"High risk" }
  );

  function makeItem(d, cls) {
    const color = TIER_COLOR[d.tier] || "#888";
    const label = TIER_LABEL[d.tier] || "";
    const tags  = d.reasons.length > 0 ? d.reasons.slice(0,2).join(" · ") : vpL("普通日","Ordinary day");
    return `<div class="opp-item ${cls}">
      <span class="opp-date">${d.date}</span>
      <span class="opp-dow">${dowLabel(d.dow_cn)}</span>
      <span class="opp-prob" style="color:${color}">${(d.prob*100).toFixed(1)}%</span>
      <span class="opp-tags">${tags}</span>
      <span class="opp-tier" style="background:${color}22;color:${color}">${label}</span>
    </div>`;
  }

  const entryHTML = opp.top_entry.slice(0,4).map(d => makeItem(d,"entry")).join("");
  const exitHTML  = opp.top_exit.slice(0,3).map(d => makeItem(d,"exit")).join("");

  document.getElementById("opp-entry-list").innerHTML = entryHTML;
  document.getElementById("opp-exit-list").innerHTML  = exitHTML;
  document.getElementById("opp-note").innerHTML = vpL(
    `<span style="color:var(--muted)">技术信号冻结为今日值。买入日排序基于历史<b>日历先验</b>:其中星期/月份/圣诞效应经 placebo 检验成立;节前/税季/月内周等为先验(未通过或未单独检验)——<b>当参考、非已验证边际,不预测方向</b>。</span>`,
    `<span style="color:var(--muted)">Technical signals are frozen at today's value. Buy-day ranking is based on historical <b>calendar priors</b>: day-of-week / month / Christmas effects have passed placebo testing; pre-holiday / tax-season / week-of-month etc. are priors (not yet passed or not separately tested) — <b>treat as reference, not a validated edge; this does not predict direction</b>.</span>`
  );
}
// 旧"事件研究图表"已删除（裸 p 值 + 方向红绿色违反诚实铁律）；
// 事件结论以"今日"标签的"🗓 事件影响一览"(renderEventImpact) 为唯一口径。

// ── 百分位信息 ──
function renderPercentileInfo(todayProb) {
  if (!SIGNALS || !SIGNALS.daily_signals) return;
  // 模型无样本外区分度时，"强于过去X%交易日"是把原始打分当把握度卖——隐藏
  if (SIGNALS.calibration_flat) {
    document.getElementById("signal-percentile").innerHTML =
      `<span style="color:var(--muted);font-size:0.78rem">${vpL('样本外无区分度，不展示强弱百分位（详见"实验"标签的验证）','No out-of-sample discriminative power — the strength percentile is hidden (see the "Exploratory" tab for validation details)')}</span>`;
    return;
  }
  const allProbs = Object.values(SIGNALS.daily_signals).map(d => d.prob);
  const last252  = allProbs.slice(-252);
  const below    = last252.filter(p => p < todayProb).length;
  const pct      = Math.round(below / last252.length * 100);
  const maxForecast = SIGNALS.next_opportunities?.top_entry?.[0];

  // Count days >=60% in next 45
  const forecast = SIGNALS.next_opportunities?.all_forecast || [];
  const strongDays = forecast.filter(d => d.prob >= 0.60).length;

  // pct = 今日概率高于过去一年多少比例的交易日（越高越强；100%=一年内最强）
  const tag = pct >= 80 ? [vpL("历史高位","Historical high"),"#27ae60"] : pct >= 60 ? [vpL("偏强","Leaning strong"),"#2ecc71"]
            : pct >= 40 ? [vpL("中等","Middling"),"#f1c40f"]   : pct >= 20 ? [vpL("偏弱","Leaning weak"),"#e67e22"]
            : [vpL("历史低位","Historical low"),"#e74c3c"];
  let html = vpL(
    `<span style="color:var(--muted)">强于过去一年 </span><strong style="color:${tag[1]}">${pct}%</strong><span style="color:var(--muted)"> 的交易日 · ${tag[0]}</span>`,
    `<span style="color:var(--muted)">Stronger than </span><strong style="color:${tag[1]}">${pct}%</strong><span style="color:var(--muted)"> of trading days over the past year · ${tag[0]}</span>`
  );
  if (maxForecast) {
    html += vpL(
      `<br><span style="color:var(--muted)">未来两个月最高：</span><strong>${(maxForecast.prob*100).toFixed(1)}%</strong><span style="color:var(--muted)"> (${maxForecast.date} ${dowLabel(maxForecast.dow_cn)})</span>`,
      `<br><span style="color:var(--muted)">Highest over the next two months: </span><strong>${(maxForecast.prob*100).toFixed(1)}%</strong><span style="color:var(--muted)"> (${maxForecast.date} ${dowLabel(maxForecast.dow_cn)})</span>`
    );
  }
  if (strongDays > 0) {
    html += vpL(
      `<br><span style="color:var(--muted)">未来两个月中 </span><strong style="color:#2ecc71">${strongDays}</strong><span style="color:var(--muted)"> 天≥60%</span>`,
      `<br><span style="color:var(--muted)">Over the next two months, </span><strong style="color:#2ecc71">${strongDays}</strong><span style="color:var(--muted)"> day(s) are ≥60%</span>`
    );
  }
  document.getElementById("signal-percentile").innerHTML = html;
}

// ── 日历统计标签切换 ──
const CAL_TABS = ["digit","cycle","party","calholiday"];
const _calTabRendered = new Set();
function switchCalTab(name, el) {
  el.closest(".tabs").querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  CAL_TABS.forEach(t => {
    const e = document.getElementById("caltab-"+t);
    if (e) e.classList.remove("active");
  });
  const pane = document.getElementById("caltab-"+name);
  pane?.classList.add("active");
  if (_calTabRendered.has(name)) { setTimeout(() => resizeChartsIn(pane), 0); return; }
  _calTabRendered.add(name);
  // setTimeout 确保浏览器 reflow 完成再让 Plotly 计算尺寸
  if (name==="digit")      setTimeout(() => safeRender(renderDigitChart,      "Digit"),      0);
  if (name==="cycle")      setTimeout(() => safeRender(renderCycleChart,      "Cycle"),      0);
  if (name==="party")      setTimeout(() => safeRender(renderPartyChart,      "Party"),      0);
  if (name==="calholiday") setTimeout(() => safeRender(renderCalHolidayChart, "CalHoliday"), 0);
}

// ── 🔬 规律防伪：placebo 置换检验 + 多重检验校正(FDR) 诚实总览 ──
// 同源消费 placebo_tests.json（placebo_test.py 产出）。被打回/无定论也是诚实结果。
let PLACEBO = null;
async function loadPlacebo() {
  const el = document.getElementById("placebo-overview");
  if (!el) return;
  try {
    const r = await fetch("placebo_tests.json?_=" + Date.now());
    if (r.ok) PLACEBO = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!PLACEBO?.tests) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("placebo 数据尚未生成（下次全量流水线后出现）","Placebo data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const STY = vpL(
    { real:{c:"#2ecc71",t:"✓ 真实"}, rejected:{c:"#e74c3c",t:"✗ 未显现"},
      inconclusive:{c:"#f1c40f",t:"— 无定论"} },
    { real:{c:"#2ecc71",t:"✓ Real"}, rejected:{c:"#e74c3c",t:"✗ Not detected"},
      inconclusive:{c:"#f1c40f",t:"— Inconclusive"} }
  );
  const rows = PLACEBO.tests.map(t => {
    const s = STY[t.status] || STY.inconclusive;
    const fdr = t.status === "inconclusive" ? `<span style="color:var(--muted)">FDR —</span>`
              : t.fdr_significant_05 ? `<span style="color:#2ecc71">FDR✓</span>`
              : `<span style="color:#e67e22">FDR✗</span>`;
    const recAdq = t.recent_min_group_n == null || t.recent_min_group_n >= 30;   // 现代段够检验力才敢说"消失"
    const modern = t.recent_p == null ? ""
      : (t.fdr_significant_05 && !t.recent_significant && recAdq
          ? vpL(`<span style="color:#3498db;font-size:0.78rem">· 现代(2000后) p=${t.recent_p.toFixed(2)} → <b>现代已测不到(很可能被套利)</b></span>`,
                `<span style="color:#3498db;font-size:0.78rem">· Modern (post-2000) p=${t.recent_p.toFixed(2)} → <b>no longer detectable in the modern era (likely arbitraged away)</b></span>`)
          : vpL(`<span style="color:var(--muted);font-size:0.78rem">· 现代 p=${t.recent_p.toFixed(2)}${t.recent_significant ? "(仍在)" : (recAdq ? "" : "(现代样本不足)")}</span>`,
                `<span style="color:var(--muted);font-size:0.78rem">· Modern p=${t.recent_p.toFixed(2)}${t.recent_significant ? " (still holds)" : (recAdq ? "" : " (insufficient modern sample)")}</span>`));
    return `<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;
                 padding:.5rem .2rem .5rem .6rem;border-bottom:1px solid var(--border);border-left:3px solid ${s.c};">
      <strong style="min-width:8.5rem">${t.panel}</strong>
      <span style="color:${s.c};font-weight:700">${s.t}</span>
      <span style="color:var(--muted);font-size:0.78rem">p=${t.p_value.toFixed(3)} · q=${t.q_value.toFixed(3)} ${fdr}</span>
      ${modern}
      <span style="color:var(--muted);font-size:0.73rem;flex-basis:100%">${t.claim}——${t.detail}（${t.scope}）</span>
    </div>`;
  }).join("");
  const cnt = k => PLACEBO.tests.filter(t => t.status === k).length;
  const fdrSurv = PLACEBO.tests.filter(t => t.fdr_significant_05).map(t => t.panel);
  const fadedSurv = PLACEBO.tests.filter(t => t.fdr_significant_05 && t.recent_p != null && !t.recent_significant && (t.recent_min_group_n == null || t.recent_min_group_n >= 30)).map(t => t.panel);
  el.innerHTML = vpL(`
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      把每个"日历规律"的日期标签随机打乱 ${PLACEBO.n_perm} 次生成零分布，真实效应须超 95 分位才算"真"；
      再用 Benjamini-Hochberg 控多重检验假发现率(FDR q 值)。
      <b style="color:var(--text)">被打回 / 无定论也是诚实结果——本站不假装规律都成立。</b>
    </div>
    ${rows}
    <div style="font-size:0.78rem;color:var(--muted);margin-top:.7rem;">
      小结：<b style="color:#2ecc71">${cnt("real")} 真实</b> /
      <b style="color:#f1c40f">${cnt("inconclusive")} 无定论</b>(样本太小,无权下结论) /
      <b style="color:#e74c3c">${cnt("rejected")} 未显现</b>。
      多重检验校正(FDR q&lt;0.05)后仍站得住：<b>${fdrSurv.join("、") || "无"}</b>${fadedSurv.length ? `——但分段揭示 <b style="color:#3498db">${fadedSurv.join("、")}</b> 在 2000 后已测不到(很可能被套利，见 🪦 诚实坟场)，全样本显著多半是 2000 前的遗物` : ""}。
      <br><span style="font-size:0.73rem">分段口径=全样本 vs 现代(2000后)两段;只证"现代段测不到"，不证具体消失机制(套利/结构变迁/检验力下降皆可能)。与个股体检的"分半+近5年"口径不同。</span>
      <br>数据 ${PLACEBO.data?.source} ${PLACEBO.data?.start}–${PLACEBO.data?.end}，种子 ${PLACEBO.seed}（可复现）。
    </div>`, `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      Each "calendar pattern"'s date labels are randomly shuffled ${PLACEBO.n_perm} times to build a null distribution — the real effect must exceed the 95th percentile to count as "real";
      Benjamini-Hochberg then controls the false-discovery rate across multiple tests (FDR q-value).
      <b style="color:var(--text)">Being rejected / inconclusive is also an honest result — this site doesn't pretend every pattern holds.</b>
    </div>
    ${rows}
    <div style="font-size:0.78rem;color:var(--muted);margin-top:.7rem;">
      Summary: <b style="color:#2ecc71">${cnt("real")} real</b> /
      <b style="color:#f1c40f">${cnt("inconclusive")} inconclusive</b> (sample too small to conclude) /
      <b style="color:#e74c3c">${cnt("rejected")} not detected</b>.
      Still standing after multiple-testing correction (FDR q&lt;0.05): <b>${fdrSurv.join(", ") || "none"}</b>${fadedSurv.length ? ` — but the split-sample view shows <b style="color:#3498db">${fadedSurv.join(", ")}</b> is no longer detectable after 2000 (likely arbitraged away — see the 🪦 honest graveyard); the full-sample significance is mostly a pre-2000 relic` : ""}.
      <br><span style="font-size:0.73rem">The split is full sample vs. modern (post-2000) only; it only shows "not detectable in the modern segment," not the specific mechanism of disappearance (arbitrage / structural change / lower test power are all possible). Different split convention from the single-stock check-up's "split-half + last-5-years."</span>
      <br>Data: ${PLACEBO.data?.source} ${PLACEBO.data?.start}–${PLACEBO.data?.end}, seed ${PLACEBO.seed} (reproducible).
    </div>`);
}

// ── 🎯 反事实事件影响（方法B）：同源消费 event_causal.json ──
let EVENT_CAUSAL = null;
async function loadEventCausal() {
  const el = document.getElementById("event-causal");
  if (!el) return;
  try {
    const r = await fetch("event_causal.json?_=" + Date.now());
    if (r.ok) EVENT_CAUSAL = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!EVENT_CAUSAL) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("反事实数据尚未生成（下次全量流水线后出现）","Counterfactual data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const STY = { significant:"#2ecc71", not_significant:"#e67e22",
                inadequate_controls:"#f1c40f", pending:"var(--muted)" };
  const events = (EVENT_CAUSAL.events || []).map(e => {
    const c = STY[e.status] || "var(--muted)";
    return `<div style="padding:.55rem .2rem .55rem .6rem;border-bottom:1px solid var(--border);border-left:3px solid ${c};">
      <div style="display:flex;flex-wrap:wrap;gap:.5rem;align-items:baseline;">
        <strong>${e.name}</strong>
        <span style="color:${c};font-weight:700">${e.verdict || e.status}</span>
        ${e.pre_r2 != null ? `<span style="color:var(--muted);font-size:0.74rem">${vpL(`对照R²=${e.pre_r2} · p=${e.p_value}`, `Control R²=${e.pre_r2} · p=${e.p_value}`)}</span>` : ""}
      </div>
      ${e.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.2rem;">${e.note}</div>` : ""}
    </div>`;
  }).join("");
  const sp = EVENT_CAUSAL.spcx;
  const spcxHtml = sp ? `<div style="padding:.55rem .6rem;border-left:3px solid var(--muted);background:var(--surface2);border-radius:5px;margin-top:.55rem;font-size:0.78rem;">
      <strong>🚀 ${sp.name}</strong>：${sp.status === "pending" ? vpL(`待数据（已上市 ${sp.days_listed} 个交易日，需 ≥${sp.need_post}）`, `Awaiting data (listed ${sp.days_listed} trading days so far, needs ≥${sp.need_post})`) : sp.status}
      ${sp.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.2rem;">${sp.note}</div>` : ""}
    </div>` : "";
  el.innerHTML = vpL(`
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      用事件前的"处理~对照"关系外推一个<b style="color:var(--text)">反事实</b>，实际 − 反事实 = 异常影响，
      block-bootstrap(含系数估计不确定性)做显著性。
      ${EVENT_CAUSAL.caveat ? `<br><span style="font-size:0.74rem">${EVENT_CAUSAL.caveat}</span>` : ""}
    </div>
    ${events}${spcxHtml}`, `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      Extrapolates a <b style="color:var(--text)">counterfactual</b> from the pre-event "treatment ~ control" relationship; actual − counterfactual = the abnormal impact,
      with significance from a block-bootstrap (which also captures coefficient-estimation uncertainty).
      ${EVENT_CAUSAL.caveat ? `<br><span style="font-size:0.74rem">${EVENT_CAUSAL.caveat}</span>` : ""}
    </div>
    ${events}${spcxHtml}`);
}

// ── 📉 风险仪表盘（方法D）：VXN-VIX 价差 + 条件下行风险（测风险不测方向）──
let RISK_DASH = null;
async function loadRiskDashboard() {
  const el = document.getElementById("risk-dashboard");
  if (!el) return;
  try {
    const r = await fetch("risk_dashboard.json?_=" + Date.now());
    if (r.ok) RISK_DASH = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!RISK_DASH) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("风险仪表盘数据尚未生成（下次全量流水线后出现）","Risk-dashboard data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const sp = RISK_DASH.vxn_vix_spread;
  let spreadHtml = "";
  if (sp && sp.status === "ok") {
    const c = sp.percentile >= 70 ? "#e74c3c" : sp.percentile <= 30 ? "#2ecc71" : "#f1c40f";
    spreadHtml = `<div style="border-left:3px solid ${c};padding:.4rem .7rem;margin-bottom:.6rem;">
      <div style="font-size:0.76rem;color:var(--muted)">${vpL("VXN−VIX 价差（纳指 vs 标普 隐含波动率溢价）","VXN−VIX spread (Nasdaq vs S&amp;P implied-volatility premium)")}</div>
      <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
        <span style="font-size:1.4rem;font-weight:800;color:${c}">${sp.current}</span>
        <span style="color:${c};font-weight:700">${sp.regime}</span>
        <span style="color:var(--muted);font-size:0.76rem">${vpL(`历史 ${sp.percentile} 分位 · VXN ${sp.vxn_last} / VIX ${sp.vix_last}`, `Historical ${sp.percentile}th pct · VXN ${sp.vxn_last} / VIX ${sp.vix_last}`)}</span>
      </div>
      <div style="color:var(--muted);font-size:0.72rem;margin-top:.15rem">${vpL(`区间 ${sp.min}~${sp.max}，均值 ${sp.mean}（${sp.start}–${sp.end}，n=${sp.n}）`, `Range ${sp.min}~${sp.max}, mean ${sp.mean} (${sp.start}–${sp.end}, n=${sp.n})`)}</div>
    </div>`;
  }
  // VXSMH 半导体恐慌计——纯描述(指数2025-09才发布·史太短不能回测·不进信号);muted 样式,不做红绿情绪渲染
  const sm = RISK_DASH.vxsmh;
  let smHtml = "";
  if (sm && sm.status === "ok") {
    smHtml = `<div style="border-left:3px solid var(--muted);padding:.4rem .7rem;margin-bottom:.6rem;">
      <div style="font-size:0.76rem;color:var(--muted)">${vpL("VXSMH 半导体恐慌计（SMH 隐含波动率 · Cboe）","VXSMH semiconductor fear gauge (SMH implied vol · Cboe)")}</div>
      <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
        <span style="font-size:1.15rem;font-weight:800">${sm.close}</span>
        <span style="color:var(--muted);font-size:0.76rem">${vpL(`≈ VIX 的 ${sm.vs_vix ?? "—"}× · VXN 的 ${sm.vs_vxn ?? "—"}× · 发布以来 ${sm.pctile_since_launch} 分位（仅 ${sm.n_days} 个交易日）`, `≈ ${sm.vs_vix ?? "—"}× VIX · ${sm.vs_vxn ?? "—"}× VXN · ${sm.pctile_since_launch}th pct since launch (only ${sm.n_days} td)`)}</span>
      </div>
      <div style="font-size:0.7rem;color:var(--muted);margin-top:.15rem">${vpL(`⚠ 指数 ${sm.launch_date} 才发布、历史太短——不能回测/不能检验，纯描述读数、非信号（截至 ${sm.date}）`, `⚠ Launched ${sm.launch_date}; history too short to backtest — descriptive reading only, not a signal (as of ${sm.date})`)}</div>
    </div>`;
  }
  const dd = RISK_DASH.downside_by_vix || [];
  let ddHtml = "";
  if (dd.length) {
    const rows = dd.map(b => `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:.3rem .4rem;color:var(--muted)">VIX ${b.vix_lo}–${b.vix_hi}</td>
      <td style="padding:.3rem .4rem;text-align:right;color:#e74c3c;font-weight:600">${b.downside_q05_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:#e67e22">${b.downside_q10_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:var(--muted)">${b.median_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:var(--muted);font-size:0.72rem">n_eff≈${b.n_eff}</td></tr>`).join("");
    ddHtml = `<div style="margin-top:.5rem;">
      <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.3rem">${vpL(`条件下行风险：不同 VIX 档位之后 ${RISK_DASH.horizon} 日 NASDAQ 收益的下行分位（风险何时更深；n_eff=有效独立样本≈n/${RISK_DASH.horizon}，前瞻窗口重叠故勿过度解读精度）`, `Conditional downside risk: downside percentiles of ${RISK_DASH.horizon}-day Nasdaq returns following different VIX tiers (when risk runs deeper; n_eff=effective independent sample ≈ n/${RISK_DASH.horizon}; forward windows overlap, so don't over-read precision)`)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("VIX 档位","VIX tier")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("5% 分位","5th pct")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("10% 分位","10th pct")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("中位","Median")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("样本","Sample")}</td></tr>
        ${rows}
      </table></div>`;
  }
  const ev = RISK_DASH.evt;
  let evtHtml = "";
  if (ev && ev.status === "ok") {
    const ve = (ev.var_es || []).map(x => `VaR${(x.level * 100).toFixed(x.level >= 0.999 ? 1 : 0)}=${x.var_pct}%·ES${x.es_pct}%`).join("　");
    const rp = (ev.return_periods || []).map(r => `<tr style="border-bottom:1px solid var(--border)"><td style="padding:.25rem .4rem;color:var(--muted)">${vpL(`单日跌 ≥${r.loss_pct}%`, `Single-day drop ≥${r.loss_pct}%`)}</td><td style="padding:.25rem .4rem;text-align:right">${r.return_period_yrs != null ? vpL("约每 " + r.return_period_yrs + " 年", "about every " + r.return_period_yrs + " yr") : "—"}</td></tr>`).join("");
    evtHtml = `<div style="margin-top:.7rem;">
      <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.3rem">${vpL(`极值尾部(EVT/POT)：S&P(${ev.start}–${ev.end}) 日损失拟合广义帕累托 · 尾指数 ξ=<b style="color:#e74c3c">${ev.xi}</b>（${tailLabel(ev.tail)}）· 极值指数 θ=${ev.extremal_index}（越小越聚集）· 日 ${ve}`, `Extreme-value tail (EVT/POT): S&amp;P (${ev.start}–${ev.end}) daily losses fit to a generalized Pareto · tail index ξ=<b style="color:#e74c3c">${ev.xi}</b> (${tailLabel(ev.tail)}) · extremal index θ=${ev.extremal_index} (smaller = more clustered) · daily ${ve}`)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("极端单日跌幅","Extreme single-day drop")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("平均重现期（非规律间隔）","Average return period (not a regular interval)")}</td></tr>
        ${rp}
      </table>
      ${ev.caveat ? `<div style="font-size:0.7rem;color:var(--muted);margin-top:.3rem;line-height:1.5">⚠ ${ev.caveat}</div>` : ""}</div>`;
  }
  const dw = RISK_DASH.drawdown || [];
  let dwHtml = "";
  if (dw.length) {
    const rows = dw.map(d => `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.3rem .4rem;color:var(--muted)">${vpL(`${d.horizon} 日持有`, `${d.horizon}-day hold`)}</td>
      <td style="padding:.3rem .4rem;text-align:right">${d.median_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:#e67e22">${d.p90_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:#e74c3c">${d.worst_pct}%</td></tr>`).join("");
    dwHtml = `<div style="margin-top:.7rem;">
      <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.3rem">${vpL("路径回撤：持有期内峰到谷最深跌幅的历史分布（持有期间最难受跌多深；非重叠窗口；测严重度非方向）","Path drawdown: historical distribution of the deepest peak-to-trough decline within the holding period (how bad it gets while you hold; non-overlapping windows; measures severity, not direction)")}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("持有期","Holding period")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("中位回撤","Median drawdown")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("90分位","90th pct")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("史上最坏","Worst on record")}</td></tr>
        ${rows}
      </table></div>`;
  }
  el.innerHTML = `${spreadHtml}${smHtml}${ddHtml}${evtHtml}${dwHtml}
    <div style="font-size:0.73rem;color:var(--muted);margin-top:.6rem;line-height:1.55">${RISK_DASH.caveat || ""}</div>`;
}

// ── 📐 收益区间（方法E 保形预测）：同源消费 conformal.json ──
let CONFORMAL = null;
async function loadConformal() {
  const el = document.getElementById("conformal");
  if (!el) return;
  try {
    const r = await fetch("conformal.json?_=" + Date.now());
    if (r.ok) CONFORMAL = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!CONFORMAL?.horizons) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("保形预测数据尚未生成（下次全量流水线后出现）","Conformal-prediction data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const HN = vpL(
    { 5: "~1周 (5日)", 20: "~1月 (20日)", 60: "~3月 (60日)" },
    { 5: "~1wk (5d)", 20: "~1mo (20d)", 60: "~3mo (60d)" }
  );
  const rows = CONFORMAL.horizons.map(h => {
    const b90 = (h.bands || []).find(b => b.level === 0.90) || {};
    const b80 = (h.bands || []).find(b => b.level === 0.80) || {};
    const cov = b90.empirical_coverage;
    const cc = (cov != null && Math.abs(cov - 0.90) <= 0.03) ? "#2ecc71" : "#e67e22";
    const fmt = b => b.lower_pct == null ? "—" : `${b.lower_pct}% ~ +${b.upper_pct}%`;
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:.3rem .4rem;color:var(--muted)">${HN[h.horizon_days] || h.horizon_days + vpL("日","d")}</td>
      <td style="padding:.3rem .4rem;text-align:center;color:var(--muted)">${fmt(b80)}</td>
      <td style="padding:.3rem .4rem;text-align:center;font-weight:600">${fmt(b90)}</td>
      <td style="padding:.3rem .4rem;text-align:right;color:${cc}">${cov != null ? (cov * 100).toFixed(0) + "%" : "—"}<span style="color:var(--muted);font-size:0.66rem"> (n=${b90.n_test ?? "?"})</span></td>
    </tr>`;
  }).join("");
  const cond = CONFORMAL.conditional_by_vix || [];
  let condHtml = "";
  if (cond.length) {
    const crows = cond.map(c => `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.3rem .4rem;color:var(--muted)">VIX ${c.vix_lo}–${c.vix_hi}</td>
      <td style="padding:.3rem .4rem;text-align:center">${c.lower_pct}% ~ +${c.upper_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;font-weight:600">${c.width_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;color:var(--muted)">${c.empirical_coverage != null ? (c.empirical_coverage * 100).toFixed(0) + "%" : "—"}</td></tr>`).join("");
    condHtml = `<div style="margin-top:.7rem">
      <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.3rem">${vpL(
        `按 VIX 体制的 20 日 90% 区间——<b>不确定性(宽度)随体制放大</b>(低VIX窄 / 高VIX宽)。实测覆盖<名义 = 该体制样本少 / 出样本外不够稳,<b>勿因区间窄就当更可信</b>;非方向、非"未来必落在内"。${CONFORMAL.conditional_period ? "仅覆盖 VIX 可得期 " + esc(CONFORMAL.conditional_period) + "(与上表全样本期间不同)" : ""}`,
        `20-day 90% interval by VIX regime — <b>uncertainty (width) scales with the regime</b> (narrow in low VIX / wide in high VIX). Measured coverage &lt; nominal = that regime has a small sample / isn't stable out-of-sample; <b>don't treat a narrower interval as more trustworthy</b>; non-directional, not "the future must fall inside." ${CONFORMAL.conditional_period ? "Covers only the period VIX is available: " + esc(CONFORMAL.conditional_period) + " (differs from the full-sample period in the table above)" : ""}`
      )}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("VIX 体制","VIX regime")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("90% 区间","90% interval")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("宽度","Width")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("实测覆盖","Measured coverage")}</td></tr>
        ${crows}
      </table></div>`;
  }
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.5rem">${CONFORMAL.caveat || ""}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("期限","Term")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("80% 区间","80% interval")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("90% 区间","90% interval")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("经验覆盖(名义90%)","Empirical coverage (nominal 90%)")}</td></tr>
      ${rows}
    </table>${condHtml}
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.4rem">${vpL(
      `${CONFORMAL.source} ${CONFORMAL.data_start}–${CONFORMAL.data_end}；旧${(CONFORMAL.cal_frac * 100).toFixed(0)}%校准/新${(100 - CONFORMAL.cal_frac * 100).toFixed(0)}%测试。经验覆盖≈名义 → 区间可信。`,
      `${CONFORMAL.source} ${CONFORMAL.data_start}–${CONFORMAL.data_end}; earlier ${(CONFORMAL.cal_frac * 100).toFixed(0)}% calibration / later ${(100 - CONFORMAL.cal_frac * 100).toFixed(0)}% test. Empirical coverage ≈ nominal → intervals are trustworthy.`
    )}</div>`;
}

// ── 🌀 周期检验（方法F 谱 + 红噪声）：同源消费 cycles.json ──
let CYCLES = null;
async function loadCycles() {
  const el = document.getElementById("cycles-spectral");
  if (!el) return;
  try {
    const r = await fetch("cycles.json?_=" + Date.now());
    if (r.ok) CYCLES = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  const res = CYCLES?.result;
  if (!res || res.status !== "ok") {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("周期检验数据尚未生成（下次全量流水线后出现）","Cycle-test data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const sig = res.significant, vc = sig ? "#e74c3c" : "#2ecc71";
  const head = `<div style="border-left:3px solid ${vc};padding:.4rem .7rem;margin-bottom:.6rem;">
    <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
      <span style="font-size:1.05rem;font-weight:800;color:${vc}">${sig ? vpL("✓ 检出超红噪声的周期","✓ Detected a cycle exceeding red noise") : vpL("✗ 无显著周期","✗ No significant cycle")}</span>
      <span style="color:var(--muted);font-size:0.78rem">${vpL(`全局检验 p=${res.p_global}（最强峰≈${res.top_period_years}年 vs 红噪声最强峰）`, `Global test p=${res.p_global} (strongest peak≈${res.top_period_years}yr vs. red-noise strongest peak)`)}</span>
    </div>
    <div style="color:var(--muted);font-size:0.73rem;margin-top:.2rem">${vpL(`AR(1) ρ=${res.ar1_rho}（≈0 即近白噪声）· ${CYCLES.source} ${CYCLES.data_start}–${CYCLES.data_end}（${res.years}年/${res.n_months}月）· ${CYCLES.n_surrogate} 条 surrogate`, `AR(1) ρ=${res.ar1_rho} (≈0 means near-white-noise) · ${CYCLES.source} ${CYCLES.data_start}–${CYCLES.data_end} (${res.years}yr/${res.n_months}mo) · ${CYCLES.n_surrogate} surrogates`)}</div>
  </div>`;
  const STAT = vpL(
    { no:{t:"未见超噪声功率",c:"#2ecc71"}, pt:{t:"⚠ 仅逐频率穿线",c:"#e67e22"}, lo:{t:"分辨率边缘·信息有限",c:"var(--muted)"}, na:{t:"数据不足·无法检验",c:"var(--muted)"} },
    { no:{t:"No above-noise power",c:"#2ecc71"}, pt:{t:"⚠ Pointwise-only crossing",c:"#e67e22"}, lo:{t:"Resolution edge · limited info",c:"var(--muted)"}, na:{t:"Insufficient data · untestable",c:"var(--muted)"} }
  );
  const rows = (res.named_cycles || []).map(nc => {
    const s = !nc.testable ? STAT.na : (nc.exceeds_red_noise_95 ? STAT.pt : (nc.low_resolution ? STAT.lo : STAT.no));
    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:.3rem .4rem">${nc.cycle}</td>
      <td style="padding:.3rem .4rem;text-align:center;color:var(--muted)">${vpL(`${nc.band_years[0]}–${nc.band_years[1]}年`, `${nc.band_years[0]}–${nc.band_years[1]}yr`)}</td>
      <td style="padding:.3rem .4rem;text-align:right;color:${s.c};font-weight:600">${s.t}</td></tr>`;
  }).join("");
  const named = `<div style="margin-top:.3rem">
    <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.3rem">${vpL('民间常引用的经济周期（实体经济：库存/投资/基建/科技，<b>非股市收益周期</b>），在 S&P 月收益谱上对照：', 'Commonly-cited economic cycles (the real economy: inventory / investment / infrastructure / tech — <b>not stock-return cycles</b>), checked against the S&amp;P monthly-return spectrum:')}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("周期（学说）","Cycle (theory)")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("周期带","Period band")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("谱检验","Spectral test")}</td></tr>
      ${rows}
    </table></div>`;
  const warn = (res.named_cycles || []).some(nc => nc.testable && nc.exceeds_red_noise_95)
    ? `<div style="font-size:0.72rem;color:#e67e22;margin-top:.4rem;line-height:1.5">${vpL('⚠ 个别周期带"逐频率穿 95% 线"是检验上百个频率的<b>预期偶然假阳性(~5%)</b>，不构成真周期证据——以<b>上方全局检验</b>为准（控多重比较，结论：无显著周期）。', '⚠ A given period band "pointwise-crossing the 95% line" is the <b>expected false-positive rate (~5%)</b> from testing hundreds of frequencies — it is not evidence of a real cycle. Defer to the <b>global test above</b> (which controls for multiple comparisons; conclusion: no significant cycle).')}</div>`
    : "";
  el.innerHTML = `${head}${named}${warn}
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;line-height:1.55">${CYCLES.caveat || ""}</div>`;
}

// ── 🧮 诚实总账（#5 跨检验族 FDR）：同源消费 fdr_crossfamily.json ──
let FDRCF = null;
async function loadFdrCrossfamily() {
  const el = document.getElementById("fdr-crossfamily");
  if (!el) return;
  try { const r = await fetch("fdr_crossfamily.json?_=" + Date.now()); if (r.ok) FDRCF = await r.json(); } catch (e) { /* 尚未生成 */ }
  if (!FDRCF?.claims) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("跨检验族 FDR 数据尚未生成（下次全量流水线后出现）","Cross-family FDR data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const d = FDRCF;
  // FC/FAMILY_EN 按后端 fdr_crossfamily.py 硬编码的中文 family 值做键——数据本身只吐中文，
  // 键必须保持原样才能命中颜色查找；FAMILY_EN 只管显示文案，不改查找逻辑。
  const FAMILY_EN = { "日历效应":"Calendar effects", "事件因果":"Event causality", "路径/Granger":"Path/Granger", "因子AUC":"Factor AUC" };
  const famLabel = f => vpL(f, FAMILY_EN[f] || f);
  const head = `<div style="border-left:3px solid var(--yellow);padding:.4rem .7rem;margin-bottom:.6rem;">
    <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
      <span style="font-size:1.6rem;font-weight:800;color:var(--yellow)">${d.n_survive_by_10} / ${d.m_total}</span>
      <span style="font-weight:700">${vpL("项经得起跨族 BY 校正（q=0.10）","items survive cross-family BY correction (q=0.10)")}</span>
    </div>
    <div style="color:var(--muted);font-size:0.73rem;margin-top:.2rem">${vpL(`把"试过的所有显著性主张"汇到一起算多重比较 · BH(乐观)留 ${d.n_survive_bh_10} · Bonferroni 留 ${d.n_survive_bonferroni_05} · BY 调和数 c(m)=${d.by_c_m}`, `Pools "every significance claim ever tried" into one multiple-comparison correction · BH (optimistic) keeps ${d.n_survive_bh_10} · Bonferroni keeps ${d.n_survive_bonferroni_05} · BY harmonic number c(m)=${d.by_c_m}`)}</div>
  </div>`;
  const fam = (d.by_family || []).map(f => {
    const pct = f.n ? Math.round(f.n_survive_by_10 / f.n * 100) : 0;
    return `<div style="display:flex;align-items:center;gap:.5rem;font-size:0.78rem;margin:.2rem 0;">
      <span style="min-width:88px;color:var(--muted)">${famLabel(f.family)}</span>
      <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden;"><div style="height:100%;width:${pct}%;background:var(--yellow);"></div></div>
      <span style="min-width:46px;text-align:right">${f.n_survive_by_10}/${f.n}</span></div>`;
  }).join("");
  const FC = { "日历效应": "#3498db", "事件因果": "#9b59b6", "路径/Granger": "#e67e22", "因子AUC": "#2ecc71" };
  const rows = d.claims.map(c => {
    const ok = c.survive_by_10;
    return `<tr style="border-top:1px solid var(--border-faint);${ok ? "" : "opacity:.55"}">
      <td style="padding:.25rem .4rem"><span style="color:${FC[c.family] || "var(--muted)"};font-size:0.7rem">${famLabel(c.family)}</span></td>
      <td style="padding:.25rem .4rem">${vpD(c,"label") || "—"}</td>
      <td style="padding:.25rem .4rem;text-align:right;font-variant-numeric:tabular-nums">${c.p.toFixed(4)}</td>
      <td style="padding:.25rem .4rem;text-align:center;color:${ok ? "#2ecc71" : "var(--muted)"};font-weight:600">${ok ? "✓" : "✗"}</td></tr>`;
  }).join("");
  el.innerHTML = `${head}
    <div style="margin:.5rem 0;">${fam}</div>
    <div style="font-size:0.76rem;color:var(--muted);margin:.5rem 0 .3rem">${vpL(`全部 ${d.m_total} 项（按 p 排序；✓ = 过 BY q=0.10）：`, `All ${d.m_total} items (sorted by p; ✓ = passes BY q=0.10):`)}</div>
    <div style="max-height:340px;overflow-y:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:0.8rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("族","Family")}</td><td style="padding:.2rem .4rem">${vpL("主张","Claim")}</td><td style="padding:.2rem .4rem;text-align:right">p</td><td style="padding:.2rem .4rem;text-align:center">BY</td></tr>
      ${rows}
    </table></div>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;line-height:1.55">${d.caveat}</div>`;
}

// 同源拉取 JSON（带 cache-buster），失败/非 200 返 null —— 登记簿/坟场/探索区共用
async function _fetchJson(f) {
  try { const r = await fetch(f + "?_=" + Date.now()); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

// ── 🧾 诚实总览（登记簿首屏）：从各方法 JSON 实时抓 verdict，含空/否结果 ──
async function loadHonestRegistry() {
  const el = document.getElementById("honest-registry");
  if (!el) return;
  const get = _fetchJson;
  const [pl, fx, ev, cy, cf, cv, sc] = await Promise.all([
    get("placebo_tests.json"), get("fdr_crossfamily.json"), get("event_causal.json"),
    get("cycles.json"), get("conformal.json"), get("cpcv.json"), get("stock_checkup.json"),
  ]);
  const rows = [];
  if (pl?.tests) {
    const c = s => pl.tests.filter(t => t.status === s).length;
    rows.push([vpL("日历效应","Calendar effects"), vpL("placebo 置换 + FDR","Placebo permutation + FDR"),
      vpL(`${c("real")} 真 / ${c("inconclusive")} 无定论 / ${c("rejected")} 未显现（FDR 校正后更少）`, `${c("real")} real / ${c("inconclusive")} inconclusive / ${c("rejected")} not detected (fewer survive FDR correction)`),
      "placebo-overview", c("real") ? "real" : "null"]);
  }
  if (fx) rows.push([vpL("跨族总账","Cross-family ledger"), "BY / BH / Bonferroni",
    vpL(`${fx.m_total} 项主张 → 跨族 BY 仅 ${fx.n_survive_by_10} 项扛得住（多为机械/验证）`, `${fx.m_total} claims → only ${fx.n_survive_by_10} survive cross-family BY (mostly mechanical/validation)`),
    "fdr-crossfamily", "null"]);
  if (ev?.events) {
    const sig = ev.events.filter(e => e.status === "significant").length;
    rows.push([vpL("事件因果 (DiD)","Event causality (DiD)"), vpL("反事实 + bootstrap","Counterfactual + bootstrap"),
      sig ? vpL(`${sig} 个验证事件显著（如 SVB→KRE −30%）`, `${sig} verified event(s) significant (e.g. SVB→KRE −30%)`) : vpL("暂无显著（或样本不足）","None significant yet (or insufficient sample)"),
      "event-causal", sig ? "real" : "null"]);
  }
  if (cy?.result) rows.push([vpL("市场周期","Market cycles"), vpL("谱 + AR1 红噪声","Spectral + AR(1) red noise"),
    cy.result.significant ? vpL("检出超红噪声周期","Detected a cycle exceeding red noise") : vpL("无超红噪声周期（民间周期被否）","No cycle exceeds red noise (folk cycles rejected)"),
    "cycles-spectral", cy.result.significant ? "real" : "null"]);
  if (cf?.horizons) {
    const b90 = cf.horizons.flatMap(h => (h.bands || []).filter(b => b.level === 0.90));
    const okCov = b90.length && b90.every(b => b.empirical_coverage != null && Math.abs(b.empirical_coverage - 0.90) <= 0.05);
    rows.push([vpL("收益区间","Return interval"), "split-conformal",
      okCov ? vpL("实测覆盖≈名义；给区间、不给方向","Measured coverage ≈ nominal; gives a range, not a direction") : vpL("实测覆盖偏离名义(见详情)；给区间、不给方向","Measured coverage deviates from nominal (see details); gives a range, not a direction"),
      "conformal", okCov ? "real" : "null"]);
  }
  if (fx?.by_family) {
    const fam = fx.by_family.find(f => f.family === "因子AUC");
    if (fam) rows.push([vpL("因子 alpha","Factor alpha"), vpL("OOS 拼接 + DSR deflation","OOS splicing + DSR deflation"),
      vpL(`${fam.n} 个因子 → 跨族稳健 ${fam.n_survive_by_10} 个`, `${fam.n} factors → ${fam.n_survive_by_10} robust across families`),
      "factor-audit", fam.n_survive_by_10 ? "real" : "null"]);
  }
  if (cv?.result?.pbo != null) {
    const p = cv.result.pbo;
    rows.push([vpL("因子过拟合 (PBO)","Factor overfitting (PBO)"), vpL("CSCV 组合对称CV","CSCV combinatorial symmetric CV"),
      vpL(`PBO=${(p * 100).toFixed(0)}% —— 挑"最佳"因子${p >= 0.3 ? "过拟合风险显著" : "较稳健"}`, `PBO=${(p * 100).toFixed(0)}% — picking the "best" factor ${p >= 0.3 ? "carries significant overfitting risk" : "is fairly robust"}`),
      "cpcv", p >= 0.3 ? "null" : "real"]);
  }
  const cdr = (typeof SIGNALS !== "undefined" && SIGNALS) ? SIGNALS.calibration_drift : null;
  if (cdr?.status === "ok") {
    const txt = cdr.verdict === "stable" ? vpL(`平均|缺口| ${cdr.mean_abs_gap_pct}pp —— 跨时段自报把握度与现实一致`, `Mean |gap| ${cdr.mean_abs_gap_pct}pp — self-reported confidence matches reality across periods`)
              : cdr.verdict === "drifting" ? vpL(`校准随时间恶化（ρ=${cdr.trend_rho}，峰值 ${cdr.max_abs_gap_pct}pp）—— 见详情`, `Calibration worsens over time (ρ=${cdr.trend_rho}, peak ${cdr.max_abs_gap_pct}pp) — see details`)
              : vpL(`无定论：单期最大|缺口| ${cdr.max_abs_gap_pct}pp（区制误差大，无系统漂移 ≠ 校准良好）`, `Inconclusive: largest single-period |gap| ${cdr.max_abs_gap_pct}pp (large per-regime error; no systematic drift ≠ good calibration)`);
    rows.push([vpL("校准漂移","Calibration drift"), vpL("逐折 OOS 校准 + Spearman 趋势","Per-fold OOS calibration + Spearman trend"), txt, "calibration-drift", cdr.verdict === "stable" ? "real" : "null"]);
  }
  if (sc?.summary) {
    const s = sc.summary;
    const lead = s.pattern_real ? vpL(`${s.pattern_real} 例疑似持续规律(待验证)`, `${s.pattern_real} case(s) of a suspected persistent pattern (unverified)`) : vpL("未发现可持续日历规律","No persistent calendar pattern found");
    const extra = (s.pattern_faded ? vpL(`${s.pattern_faded} 例曾有、已被套利`, `${s.pattern_faded} case(s) once held, now arbitraged away`) : "")
      + (s.pattern_data_snoop ? vpL(`；${s.pattern_data_snoop} 例数据窥探`, `; ${s.pattern_data_snoop} case(s) of data snooping`) : "");
    rows.push([vpL("个股诚实体检","Single-stock honest check-up"), vpL("风险画像 + 规律真伪(三关)","Risk profile + real-vs-fake patterns (3 gates)"),
      vpL(`${s.n_ok} 票风险画像；${lead}${extra ? "（" + extra + "）" : ""} —— 非荐股非预测`, `${s.n_ok} ticker risk profile(s); ${lead}${extra ? " (" + extra + ")" : ""} — not a stock tip, not a forecast`),
      "stock-checkup", s.pattern_real ? "real" : "null"]);
  }
  rows.push([vpL("短期方向预测","Short-term direction forecast"), vpL("（红线）","(off-limits)"), vpL("不可靠预测 → 主动不做","Not reliably predictable → deliberately not attempted"), null, "redline"]);
  rows.push([vpL("v3 稀疏模型","v3 sparse model"), vpL("L1 正则实验","L1-regularization experiment"), vpL("假设被否（诚实 null，见 git 历史）","Hypothesis rejected (honest null result, see git history)"), null, "null"]);
  rows.push([vpL("指数纳入效应 (RDD)","Index-inclusion effect (RDD)"), vpL("断点回归 · Russell 1000/2000 阈值","Regression discontinuity · Russell 1000/2000 threshold"),
    vpL("排名运行变量为 Russell/WRDS 专有，免费拿不到（2007后 banding 又使阈值模糊）→ 诚实不做，不用劣质代理硬凑", "The ranking running variable is Russell/WRDS proprietary and unavailable for free (post-2007 banding also blurs the threshold) → honestly not attempted, rather than forcing a low-quality proxy"),
    null, "infeasible"]);

  const TAG = vpL(
    { real: { t: "有信号", c: "#2ecc71" }, null: { t: "空/否", c: "#e67e22" }, redline: { t: "红线", c: "#e74c3c" }, infeasible: { t: "数据不可行", c: "#8b949e" } },
    { real: { t: "Has signal", c: "#2ecc71" }, null: { t: "Null/rejected", c: "#e67e22" }, redline: { t: "Off-limits", c: "#e74c3c" }, infeasible: { t: "Data infeasible", c: "#8b949e" } }
  );
  const tr = rows.map(([name, method, verdict, anchor, kind]) => {
    const tg = TAG[kind] || TAG.null;
    const jump = anchor ? `<a href="#" data-scroll-target="${anchor}" style="color:var(--blue);text-decoration:none">${vpL("展开 ↓","Expand ↓")}</a>` : "—";
    return `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.35rem .4rem;font-weight:600">${name}</td>
      <td style="padding:.35rem .4rem;color:var(--muted);font-size:0.76rem">${method}</td>
      <td style="padding:.35rem .4rem">${verdict}</td>
      <td style="padding:.35rem .4rem;text-align:center"><span style="color:${tg.c};font-weight:600;font-size:0.74rem">${tg.t}</span></td>
      <td style="padding:.35rem .4rem;text-align:center;font-size:0.76rem">${jump}</td></tr>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem">${vpL('这张表自动汇总各方法的真实结论——<b>包括空结果、被否、无定论</b>。诚实统计的价值不在"找到规律"，而在<b>分清真规律与幻觉</b>。', 'This table auto-summarizes each method\'s real conclusion — <b>including null results, rejections, and inconclusive ones</b>. The value of honest statistics isn\'t "finding a pattern," it\'s <b>telling real patterns apart from illusions</b>.')}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.84rem">
      <tr class="u-cap"><td style="padding:.25rem .4rem">${vpL("实验","Experiment")}</td><td style="padding:.25rem .4rem">${vpL("方法","Method")}</td><td style="padding:.25rem .4rem">${vpL("诚实结论","Honest conclusion")}</td><td style="padding:.25rem .4rem;text-align:center">${vpL("判定","Verdict")}</td><td style="padding:.25rem .4rem;text-align:center">${vpL("详情","Details")}</td></tr>
      ${tr}
    </table>`;
}

// ── 🎲 过拟合概率 PBO（方法G CSCV）：同源消费 cpcv.json ──
let CPCV = null;
async function loadCpcv() {
  const el = document.getElementById("cpcv");
  if (!el) return;
  try { const r = await fetch("cpcv.json?_=" + Date.now()); if (r.ok) CPCV = await r.json(); } catch (e) { /* 尚未生成 */ }
  const res = CPCV?.result;
  if (!res || res.pbo == null) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("PBO 数据尚未生成（下次全量流水线后出现）","PBO data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const pbo = res.pbo, pct = (pbo * 100).toFixed(0);
  const c = pbo >= 0.5 ? "#e74c3c" : pbo >= 0.3 ? "#e67e22" : "#2ecc71";   // 高PBO=过拟合=红
  el.innerHTML = `
    <div style="border-left:3px solid ${c};padding:.4rem .7rem;margin-bottom:.6rem;">
      <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
        <span style="font-size:1.6rem;font-weight:800;color:${c}">PBO ${pct}%</span>
        <span style="color:var(--muted);font-size:0.78rem">${vpL('挑"最佳"因子在样本外低于中位的概率','Probability that the "best" factor falls below the median out-of-sample')}</span>
      </div>
      <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin:.45rem 0;">
        <div style="height:100%;width:${pct}%;background:${c};"></div></div>
      <div style="color:var(--muted);font-size:0.72rem">${vpL(`${res.n_combos} 个 CSCV 组合 · ${res.n_factors} 因子 · 0%=完全稳健 / 50%≈抛硬币(过拟合) / &gt;50%=系统性失效`, `${res.n_combos} CSCV combinations · ${res.n_factors} factors · 0%=fully robust / 50%≈coin flip (overfit) / &gt;50%=systematic failure`)}</div>
    </div>
    <div style="font-size:0.82rem;line-height:1.55;margin-bottom:.4rem">${res.verdict}</div>
    <div style="font-size:0.72rem;color:var(--muted);line-height:1.55">${CPCV.caveat || ""}</div>`;
}

// ── 📉 校准漂移（#3 逐折校准随时间）：同源消费 SIGNALS.calibration_drift ──
function loadCalibrationDrift() {
  const el = document.getElementById("calibration-drift");
  if (!el) return;
  const cd = (typeof SIGNALS !== "undefined" && SIGNALS) ? SIGNALS.calibration_drift : null;
  if (!cd || cd.status !== "ok") {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("校准漂移数据尚未生成（下次重跑 walk_forward 后出现）","Calibration-drift data not generated yet (will appear after the next walk_forward run)")}</span>`;
    return;
  }
  const vmap = vpL(
    { stable: ["#2ecc71", "校准稳定"], drifting: ["#e74c3c", "校准漂移"], inconclusive: ["#f1c40f", "无定论"] },
    { stable: ["#2ecc71", "Calibration stable"], drifting: ["#e74c3c", "Calibration drifting"], inconclusive: ["#f1c40f", "Inconclusive"] }
  );
  const [c, vlabel] = vmap[cd.verdict] || ["#f1c40f", esc(cd.verdict)];
  const frows = (cd.folds || []).map(f => {
    const g = f.gap, gc = Math.abs(g) < 0.05 ? "var(--muted)" : "#e67e22";
    return `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.25rem .4rem;color:var(--muted)">${esc(f.period)}</td>
      <td style="padding:.25rem .4rem;text-align:right;font-variant-numeric:tabular-nums">${(f.mean_pred * 100).toFixed(1)}%</td>
      <td style="padding:.25rem .4rem;text-align:right;font-variant-numeric:tabular-nums">${(f.actual_wr * 100).toFixed(1)}%</td>
      <td style="padding:.25rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:${gc}">${g > 0 ? "+" : ""}${(g * 100).toFixed(1)}pp</td>
      <td style="padding:.25rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:var(--muted)">${(f.ece * 100).toFixed(1)}</td></tr>`;
  }).join("");
  el.innerHTML = `
    <div style="border-left:3px solid ${c};padding:.4rem .7rem;margin-bottom:.6rem;">
      <div style="display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;">
        <span style="font-size:1.2rem;font-weight:800;color:${c}">${vlabel}</span>
        <span style="color:var(--muted);font-size:0.78rem">${vpL(`平均|缺口| ${cd.mean_abs_gap_pct}pp · 最大 ${cd.max_abs_gap_pct}pp · 趋势 ρ=${cd.trend_rho} (p=${cd.trend_p})`, `Mean |gap| ${cd.mean_abs_gap_pct}pp · max ${cd.max_abs_gap_pct}pp · trend ρ=${cd.trend_rho} (p=${cd.trend_p})`)}</span>
      </div>
      <div style="font-size:0.8rem;line-height:1.5;margin-top:.35rem">${esc(cd.note)}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:0.8rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("时段(测试折)","Period (test fold)")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("平均预测","Mean predicted")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("实际胜率","Actual win rate")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("缺口","Gap")}</td><td style="text-align:right;padding:.2rem .4rem">ECE</td></tr>
      ${frows}
    </table>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.45rem;line-height:1.5">${vpL('缺口=平均预测−实际胜率(&gt;0=偏乐观);ECE=分箱内|预测−实际|样本加权均。逐折=walk-forward 各前向时间窗(naive 部署打分)。折数少→趋势检验力低,故多落"无定论"——这是<b>校准质量</b>诊断,非方向预测。', 'Gap = mean predicted − actual win rate (&gt;0 = overly optimistic); ECE = sample-weighted mean of |predicted − actual| within bins. Per-fold = each walk-forward forward-looking window (scored as a naive deployment would be). Fewer folds → lower power for the trend test, so it often lands on "inconclusive" — this is a <b>calibration-quality</b> diagnostic, not a directional forecast.')}</div>`;
}

// ── 🩺 个股诚实体检（块0 基础风险画像）：同源消费 stock_checkup.json ──
let STOCK_CHECKUP = null;
async function loadStockCheckup() {
  const el = document.getElementById("stock-checkup");
  if (!el) return;
  try { const r = await fetch("stock_checkup.json?_=" + Date.now()); if (r.ok) STOCK_CHECKUP = await r.json(); } catch (e) { /* 尚未生成 */ }
  const tks = STOCK_CHECKUP?.tickers;
  if (!tks || !Object.keys(tks).length) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("个股体检数据尚未生成（下次全量流水线后出现）","Single-stock check-up data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const codes = Object.keys(tks);
  const opts = codes.map(c => `<option value="${esc(c)}">${esc(c)} ${esc(tickerName(c, tks[c].name || ""))}</option>`).join("");
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem">${esc(STOCK_CHECKUP.caveat || "")}</div>
    <div style="margin-bottom:.6rem"><select id="sc-select" onchange="renderStockCheckup(this.value)" aria-label="${vpL('选择股票','Choose a stock')}"
       style="background:var(--card);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:.35rem .6rem;font-size:0.9rem">${opts}</select></div>
    <div id="sc-body"></div>`;
  renderStockCheckup(codes[0]);
}

function renderStockCheckup(code) {
  const t = STOCK_CHECKUP?.tickers?.[code];
  const body = document.getElementById("sc-body");
  if (!body || !t) return;
  if (t.status !== "ok") {
    body.innerHTML = `<div style="color:var(--muted);font-size:0.85rem">${vpL(`${esc(code)} ${esc(tickerName(code, t.name || ""))}：数据不足/不可得（${esc(t.status)}${t.n_days != null ? "，n=" + t.n_days : ""}），诚实不给画像。`, `${esc(code)} ${esc(tickerName(code, t.name || ""))}: insufficient/unavailable data (${esc(t.status)}${t.n_days != null ? ", n=" + t.n_days : ""}) — honestly withholding a risk profile.`)}</div>`;
    return;
  }
  const betaTxt = t.beta_nasdaq == null ? "—" : t.beta_nasdaq + vpL(t.beta_nasdaq >= 1 ? "（对纳指涨跌更敏感）" : "（对纳指涨跌不敏感）", t.beta_nasdaq >= 1 ? " (more sensitive to Nasdaq swings)" : " (less sensitive to Nasdaq swings)");
  const row = (label, val, hint) => `<tr style="border-top:1px solid var(--border-faint)">
    <td style="padding:.35rem .4rem;color:var(--muted)">${label}</td>
    <td style="padding:.35rem .4rem;text-align:right;font-weight:600;font-variant-numeric:tabular-nums">${val}</td>
    <td style="padding:.35rem .4rem;color:var(--muted);font-size:0.74rem">${hint}</td></tr>`;
  const ev = t.evt;
  let evtHtml = "";
  if (ev && ev.status === "ok") {
    const v99 = (ev.var_es || []).find(x => x.level === 0.99) || {};
    evtHtml = `<div style="margin-top:.75rem">
      <div style="color:var(--muted);font-size:0.74rem;margin-bottom:.2rem">${vpL(`极值尾部（EVT/GPD，日损失）：${esc(ev.tail || "")}`, `Extreme-value tail (EVT/GPD, daily losses): ${esc(tailLabel(ev.tail || ""))}`)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem">
        ${row(vpL("尾部指数 ξ","Tail index ξ"), ev.xi, vpL("尾部越厚极端日跌越狠；≈0 近指数、&lt;0 有上界","Thicker tail = harsher extreme-day drops; ≈0 near-exponential, &lt;0 has an upper bound"))}
        ${row(vpL("日 VaR 99%","Daily VaR 99%"), (v99.var_pct ?? "—") + "%", vpL("约百日一遇的单日跌幅量级","Roughly a once-in-100-days single-day drop magnitude"))}
        ${row(vpL("日 ES 99%","Daily ES 99%"), (v99.es_pct ?? "—") + "%", vpL("跌破 VaR 时的平均损失（更惨那部分）","Average loss when VaR is breached (the worse tail)"))}
      </table>
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.3rem;line-height:1.5">${vpL('⚠ 历史尾部严重度——长期平均频率、<b>非规律间隔</b>（极端日常成簇连发、之后多年沉寂），<b>不预测哪天发生</b>。', '⚠ Historical tail severity — a long-run average frequency, <b>not a regular interval</b> (extreme days often cluster in bursts, then go quiet for years); <b>this does not predict which day it happens</b>.')}</div></div>`;
  } else if (ev) {
    evtHtml = `<div style="margin-top:.6rem;color:var(--muted);font-size:0.76rem">${vpL("极值尾部：数据不足（需 ~1000+ 天），诚实不给。","Extreme-value tail: insufficient data (needs ~1000+ days) — honestly withheld.")}</div>`;
  }
  const md = t.market_dep;
  let mdHtml = "";
  if (md && md.status === "ok") {
    const tag = md.r2_pct >= 60 ? vpL("——大盘主导"," — market-dominated") : md.r2_pct <= 30 ? vpL("——以自身因素为主"," — mostly idiosyncratic") : "";
    mdHtml = vpL(`<div style="margin-top:.7rem;font-size:0.82rem;color:var(--muted);line-height:1.55">
      市场依赖度：<b style="color:var(--fg)">${md.r2_pct}%</b> 的波动可由纳指解释（相关 ${md.corr}），其余
      <b style="color:var(--fg)">${md.idiosyncratic_pct}%</b> 是个股特质。${tag}</div>`,
      `<div style="margin-top:.7rem;font-size:0.82rem;color:var(--muted);line-height:1.55">
      Market dependence: <b style="color:var(--fg)">${md.r2_pct}%</b> of the volatility can be explained by the Nasdaq (correlation ${md.corr}); the remaining
      <b style="color:var(--fg)">${md.idiosyncratic_pct}%</b> is stock-specific.${tag}</div>`);
  }
  const pat = t.patterns;
  let patHtml = "";
  if (pat && pat.status === "ok") {
    const vmap = vpL(
      { real: ["#e67e22", "疑似持续规律(待验证)"], faded: ["#3498db", "历史有·近年消失(被套利)"],
        hist_robust: ["#8b949e", "历史稳健·近期样本不足未验证"],
        data_snoop: ["#f1c40f", "数据窥探(分半不稳)"], rejected: ["#2ecc71", "未检出规律"],
        inconclusive: ["#8b949e", "无定论(检验力不足)"] },
      { real: ["#e67e22", "Suspected persistent pattern (unverified)"], faded: ["#3498db", "Once real · faded in recent years (arbitraged)"],
        hist_robust: ["#8b949e", "Historically robust · unverified (recent sample too small)"],
        data_snoop: ["#f1c40f", "Data snooping (unstable split-half)"], rejected: ["#2ecc71", "No pattern detected"],
        inconclusive: ["#8b949e", "Inconclusive (insufficient power)"] }
    );
    const sig = p => p == null ? "—" : (p < 0.05 ? `<b style="color:var(--fg)">${p}*</b>` : `${p}`);
    const prows = pat.tests.map(t2 => {
      const [c, lbl] = vmap[t2.verdict] || ["#8b949e", esc(t2.verdict || "")];
      const hp = t2.split_half_p || [null, null];
      return `<tr style="border-top:1px solid var(--border-faint)">
        <td style="padding:.3rem .4rem;color:var(--muted)">${effectLabel(t2.effect)}</td>
        <td style="padding:.3rem .4rem;text-align:center;color:${c};font-size:.76rem">${lbl}</td>
        <td style="padding:.3rem .4rem;text-align:right;font-size:.76rem;font-variant-numeric:tabular-nums">${sig(t2.p_value)}</td>
        <td style="padding:.3rem .4rem;text-align:right;font-size:.76rem;font-variant-numeric:tabular-nums">${sig(hp[0])}/${sig(hp[1])}</td>
        <td style="padding:.3rem .4rem;text-align:right;font-size:.76rem;font-variant-numeric:tabular-nums">${sig(t2.recent_p)}</td></tr>`;
    }).join("");
    patHtml = `<div style="margin-top:.75rem">
      <div style="color:var(--muted);font-size:0.74rem;margin-bottom:.25rem">${vpL("日历规律真伪（置换检验 + 跨票 FDR + 分段稳健；* = p&lt;0.05）：","Real vs. fake calendar patterns (permutation test + cross-ticker FDR + split robustness; * = p&lt;0.05):")}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("效应","Effect")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("判定","Verdict")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("全样本","Full sample")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("前半/后半","1st half/2nd half")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("近5年","Last 5yr")}</td></tr>
        ${prows}
      </table>
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.3rem;line-height:1.5">${vpL('只问"是真是噪声"、<b>不预测涨跌</b>。<b>历史有·近年消失</b>=典型被套利(如 AAPL 星期效应:全史显著、近5年 p≈0.57 已无)。单股日历效应极易过拟合，故跨票 FDR + 分半 + 近期三关从严。', 'This only asks "real or noise" — <b>it does not predict direction</b>. <b>Once real, faded in recent years</b> = a textbook arbitraged-away pattern (e.g. AAPL\'s day-of-week effect: significant over the full history, gone by recent-5yr p≈0.57). Single-stock calendar effects overfit very easily, so cross-ticker FDR + split-half + recency form three strict gates.')}</div></div>`;
  }
  const cf = t.conformal;
  let cfHtml = "";
  if (cf && cf.status === "ok") {
    const covC = Math.abs((cf.empirical_coverage || 0) - 0.9) <= 0.07 ? "var(--muted)" : "#e67e22";
    const sgn = x => (x >= 0 ? "+" : "") + x + "%";
    const _sp = (Math.max(Math.abs(cf.lower_pct), Math.abs(cf.upper_pct)) * 1.1) || 1;   // 对称跨度,0 居中
    const _x = v => (v + _sp) / (2 * _sp) * 100;
    const bar = `<div style="position:relative;height:12px;background:var(--border);border-radius:6px;margin:.35rem 0;overflow:hidden" title="${vpL('0=今日水平，蓝条=历史90%区间(范围非方向)','0=today\'s level, blue bar=historical 90% interval (a range, not a direction)')}">
      <div style="position:absolute;left:${_x(cf.lower_pct).toFixed(1)}%;width:${(_x(cf.upper_pct) - _x(cf.lower_pct)).toFixed(1)}%;top:0;bottom:0;background:var(--blue);opacity:.35"></div>
      <div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--fg);opacity:.6"></div></div>`;
    cfHtml = `<div style="margin-top:.7rem;font-size:0.82rem;line-height:1.55">
      <span style="color:var(--muted)">${vpL(`${cf.horizon}日 ${Math.round(cf.level * 100)}% 区间：`, `${cf.horizon}d ${Math.round(cf.level * 100)}% interval: `)}</span><b style="color:var(--fg)">${sgn(cf.lower_pct)} ~ ${sgn(cf.upper_pct)}</b>
      <span style="color:var(--muted)">${vpL(`（宽 ${cf.width_pct}%）· 实测覆盖 <span style="color:${covC}">${(cf.empirical_coverage * 100).toFixed(0)}%</span>（${cf.n_test} 个出样本窗口）`, `(width ${cf.width_pct}%) · measured coverage <span style="color:${covC}">${(cf.empirical_coverage * 100).toFixed(0)}%</span> (${cf.n_test} out-of-sample windows)`)}</span>
      ${bar}
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.2rem">${vpL('这是<b>不确定性区间</b>(历史 N 日收益多少比例落在内)，<b>给范围不给方向、不预测涨跌</b>。此为<b>历史无条件</b>区间、非对当下行情的预测，<b>不等于未来一定落在内</b>;覆盖偏离名义 90% = 该票非平稳或样本少。', 'This is an <b>uncertainty interval</b> (what share of historical N-day returns fell inside it) — <b>it gives a range, not a direction; it does not predict up or down</b>. It is a <b>historical, unconditional</b> interval, not a forecast for right now, <b>and does not mean the future must fall inside it</b>; coverage deviating from the nominal 90% means this ticker is non-stationary or has too small a sample.')}</div></div>`;
  }
  const an = t.anomaly;
  let anHtml = "";
  if (an && an.status === "ok") {
    const flags = [];
    if (an.high_vol) flags.push(vpL("波动处历史高位(≥95 分位)","Volatility at a historical high (≥95th pct)"));
    if (an.decoupled) flags.push(vpL("与大盘异常脱钩(走自己的、相关处历史低位 → 特质风险占比升高，无关好坏方向)","Unusually decoupled from the market (moving on its own, correlation at a historical low → idiosyncratic-risk share is up, regardless of direction)"));
    const sC = flags.length ? "#e67e22" : "var(--muted)";   // 正常=中性灰,不用绿(避免"绿灯=可买"误读);橙仅引起注意
    const sT = flags.length ? flags.join(vpL("、", "; ")) : vpL("无异常（波动/相关均在常态区间）","No anomaly (both volatility and correlation are in the normal range)");
    const vpBar = `<div style="position:relative;height:10px;background:var(--border);border-radius:5px;margin:.3rem 0;overflow:hidden" title="${vpL('当前波动在该票历史的分位(0–100)，红线=95','Current volatility percentile in this ticker\'s history (0–100); red line = 95')}">
      <div style="position:absolute;left:0;width:${an.vol_percentile}%;top:0;bottom:0;background:${an.high_vol ? "#e67e22" : "var(--blue)"};opacity:.4"></div>
      <div style="position:absolute;left:95%;top:0;bottom:0;width:1px;background:#e67e22;opacity:.7"></div></div>`;
    anHtml = `<div style="margin-top:.7rem;font-size:0.82rem;line-height:1.55">
      <span style="color:var(--muted)">${vpL(`当前风险状态（${an.win}日滚动，截至 ${esc(an.asof)}）：`, `Current risk state (${an.win}-day rolling, as of ${esc(an.asof)}): `)}</span><span style="color:${sC}">${sT}</span>
      <div style="color:var(--muted);font-size:0.74rem;margin-top:.2rem">${vpL(`波动 ${an.vol_now_pct}%（历史第 ${an.vol_percentile} 分位）${an.corr_now != null ? "、与纳指相关 " + an.corr_now + "（第 " + an.corr_percentile + " 分位）" : ""}`, `Volatility ${an.vol_now_pct}% (historical ${an.vol_percentile}th pct)${an.corr_now != null ? `, correlation with Nasdaq ${an.corr_now} (${an.corr_percentile}th pct)` : ""}`)}</div>
      ${vpBar}
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.2rem">${vpL('⚠ 异动 = <b>风险升高、请重新审视你的仓位风险</b>，<b>不是交易信号/机会</b>；本页不择时、不预测方向。', '⚠ An anomaly flag = <b>elevated risk — reconsider your position sizing</b>, <b>not a trading signal or opportunity</b>; this page does not time the market or predict direction.')}</div></div>`;
  }
  const dd = t.dip_distribution;
  let dipHtml = "";
  if (dd && dd.status === "ok" && (dd.distribution || []).length) {
    const dn = vpL({ 1: "次日", 5: "次 5 日", 20: "次 20 日" }, { 1: "Next day", 5: "Next 5d", 20: "Next 20d" });
    const dpr = dd.distribution.map(x => `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.3rem .4rem;color:var(--muted)">${dn[x.horizon] || x.horizon + vpL("日","d")}</td>
      <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums">${x.median_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e74c3c">${x.p10_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e74c3c;font-weight:600">${x.worst_pct}%</td>
      <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e67e22">${x.pct_negative}%</td></tr>`).join("");
    dipHtml = `<div style="margin-top:.75rem">
      <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.2rem">${vpL(`这只票<b>大跌日(收益≤第 ${dd.q} 百分位)之后</b>历史发生过什么——<b>完整分布(含灾难路径)</b>，不只看平均：`, `What historically happened <b>after this ticker's big-drop days (return ≤ ${dd.q}th pct)</b> — <b>the full distribution (including disaster paths)</b>, not just the average:`)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.8rem">
        <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("区间","Window")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("中位","Median")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("p10(差)","p10 (bad)")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("最坏","Worst")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("继续亏比例","% still losing")}</td></tr>
        ${dpr}
      </table>
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.25rem">${vpL('⚠ 相当比例(见"继续亏"列)大跌后<b>继续亏</b>、最坏可深至表中"最坏"列——<b>这是历史全貌、不是抄底信号,不预测、不可交易</b>。', '⚠ A substantial share (see the "% still losing" column) <b>kept losing</b> after the big drop, and the worst case can go as deep as the "Worst" column shows — <b>this is the full historical picture, not a buy-the-dip signal; it does not predict, and is not tradable</b>.')}</div></div>`;
  }
  const volTier = t.ann_vol_pct >= 45 ? vpL("高波动","High volatility") : t.ann_vol_pct >= 28 ? vpL("中等波动","Moderate volatility") : vpL("低波动","Low volatility");
  const betaDesc = t.beta_nasdaq == null ? "" : (t.beta_nasdaq >= 1.2 ? vpL("、对大盘涨跌更敏感",", more sensitive to market swings") : t.beta_nasdaq <= 0.6 ? vpL("、对大盘涨跌不敏感",", less sensitive to market swings") : vpL("、敏感度与大盘相当",", sensitivity in line with the market"));
  const betaClause = t.beta_nasdaq == null ? "" : `${betaDesc}${vpL(`（β=${t.beta_nasdaq}）`, ` (β=${t.beta_nasdaq})`)}`;
  const patMap = vpL(
    { has_real: "出现疑似持续规律(见下，待验证)", faded: "曾有日历规律、近年已消失(被套利)", hist_robust: "历史稳健但近期样本不足无法验证", data_snoop: "疑似规律经查为数据窥探", no_pattern: "未检出日历规律", inconclusive: "日历规律无定论(检验力不足)" },
    { has_real: "a suspected persistent pattern appears (see below, unverified)", faded: "once had a calendar pattern, now faded in recent years (arbitraged away)", hist_robust: "historically robust but recent sample too small to verify", data_snoop: "the suspected pattern turned out to be data snooping", no_pattern: "no calendar pattern detected", inconclusive: "calendar pattern inconclusive (insufficient power)" }
  );
  const patTxt = (t.patterns && t.patterns.status === "ok") ? (patMap[t.patterns.overall] || "") : "";
  const cardHtml = vpL(`<div style="border-left:3px solid var(--blue);padding:.4rem .7rem;margin-bottom:.7rem;font-size:0.85rem;line-height:1.6">
    <b>${esc(code)} ${esc(tickerName(code, t.name || ""))}</b> 风险画像综述：${volTier}（年化 ${t.ann_vol_pct}%）${betaClause}${md && md.status === "ok" ? "、" + md.r2_pct + "% 波动随大盘" : ""}。${patTxt ? "日历规律：" + patTxt + "。" : ""}
    <div style="color:var(--muted);font-size:0.74rem;margin-top:.25rem">这是<b>风险与真伪的客观画像，不是评级、不荐股、不预测方向</b>（'敏感'指随大盘摆动幅度，非安全或收益高低）。</div></div>`,
    `<div style="border-left:3px solid var(--blue);padding:.4rem .7rem;margin-bottom:.7rem;font-size:0.85rem;line-height:1.6">
    <b>${esc(code)} ${esc(tickerName(code, t.name || ""))}</b> risk-profile summary: ${volTier} (annualized ${t.ann_vol_pct}%)${betaClause}${md && md.status === "ok" ? `, ${md.r2_pct}% of volatility moves with the market` : ""}. ${patTxt ? "Calendar pattern: " + patTxt + "." : ""}
    <div style="color:var(--muted);font-size:0.74rem;margin-top:.25rem">This is an <b>objective profile of risk and real-vs-fake patterns — not a rating, not a stock tip, not a directional forecast</b> ('sensitive' means the amplitude of swings with the market, not safety or return level).</div></div>`);
  body.innerHTML = `${cardHtml}
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:.4rem">${vpL(`${esc(code)} ${esc(tickerName(code, t.name || ""))} · 日线 ${esc(t.start)}→${esc(t.end)}（${t.n_days} 天）`, `${esc(code)} ${esc(tickerName(code, t.name || ""))} · daily bars ${esc(t.start)}→${esc(t.end)} (${t.n_days} days)`)}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.85rem">
      ${row(vpL("年化波动","Annualized volatility"), t.ann_vol_pct + "%", vpL("历史日收益波动，越高越颠","Historical daily-return volatility — higher means bumpier"))}
      ${row(vpL("历史最深回撤","Deepest historical drawdown"), t.max_drawdown_pct + "%", vpL("峰到谷最大跌幅——提示风险，非机会","Largest peak-to-trough decline — flags risk, not an opportunity"))}
      ${row(vpL("对纳指 β","β vs. Nasdaq"), betaTxt, vpL("对大盘的敏感度，是风险特征非收益承诺","Sensitivity to the broad market — a risk characteristic, not a return promise"))}
    </table>${mdHtml}${evtHtml}${cfHtml}${patHtml}${anHtml}${dipHtml}`;
}

// ── 🌡️ 当前市场风险体制(R1)：同源消费 market_regime.json,描述非预测 ──
async function loadMarketRegime() {
  const el = document.getElementById("market-regime");
  if (!el) return;
  let MR = null;
  try { const r = await fetch("market_regime.json?_=" + Date.now()); if (r.ok) MR = await r.json(); } catch (e) { /* 尚未生成 */ }
  if (!MR || MR.status !== "ok") {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("市场体制数据尚未生成（下次全量流水线后出现）","Market-regime data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  const rows = (MR.components || []).map(c => {
    const lc = (c.inverted || c.backwardation) ? "#e67e22" : "var(--muted)";   // 倒挂=橙仅引起注意,非红绿灯
    return `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.35rem .4rem;color:var(--muted)">${esc(c.name)}</td>
      <td style="padding:.35rem .4rem;text-align:right;font-weight:600;font-variant-numeric:tabular-nums">${c.value}${c.percentile != null ? `<span style="color:var(--muted);font-size:.72rem"> ${vpL(`(第${c.percentile}分位${c.history_start ? "·" + c.history_start.slice(0, 4) + "+起" : ""})`, `(${c.percentile}th pct${c.history_start ? " · since " + c.history_start.slice(0, 4) : ""})`)}</span>` : ""}${c.asof ? `<span style="color:var(--muted);font-size:.68rem;display:block;font-weight:400">${vpL(`截至 ${esc(c.asof)}`, `as of ${esc(c.asof)}`)}</span>` : ""}${c.percentile != null ? `<span class="vp-posbar" data-pct="${+c.percentile}" style="display:block;margin-top:3px;font-weight:400"></span>` : ""}</td>
      <td style="padding:.35rem .4rem;text-align:center;color:${lc};font-size:.8rem">${esc(c.label)}</td>
      <td style="padding:.35rem .4rem;color:var(--muted);font-size:.72rem">${esc(c.note)}</td></tr>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.86rem;font-weight:600;margin-bottom:.5rem">${esc(MR.composite)} <span style="color:var(--muted);font-size:.74rem;font-weight:400">${vpL("— 描述当前环境，非预测、非操作建议（各指标截至日期见下，部分月频会滞后）","— describes the current environment; not a forecast or trading advice (each indicator's as-of date is shown below; some monthly-frequency ones lag)")}</span></div>
    <table style="width:100%;border-collapse:collapse;font-size:0.83rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("指标","Indicator")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("现值","Current")}</td><td style="text-align:center;padding:.2rem .4rem">${vpL("体制","Regime")}</td><td style="padding:.2rem .4rem">${vpL("含义","Meaning")}</td></tr>
      ${rows}
    </table>
    <div style="font-size:0.7rem;color:var(--muted);margin-top:.3rem">${vpL("● 位置=历史分位", "● position = historical pct (0–100)")}</div>
    <div style="font-size:0.74rem;color:var(--muted);line-height:1.6;margin-top:.6rem">${esc(MR.caveat || "")}</div>`;
  // D2 微图表:每成分"现值落在自家历史哪个分位"的位置条(0-100 位置,非时间序列)。
  // 极端分位(≥90/≤10)游标用 --amb 引起注意——与上面"倒挂=橙"同款语义(注意≠红绿灯),其余中性 --acc。
  if (typeof vpPosBar === "function") {
    el.querySelectorAll(".vp-posbar").forEach(sp => {
      const p = parseFloat(sp.dataset.pct);
      vpPosBar(sp, p, { color: (p >= 90 || p <= 10) ? "var(--amb)" : "var(--acc)", w: 84,
                        label: vpL(`历史分位 ${Math.round(p)}/100`, `historical percentile ${Math.round(p)}/100`) });
    });
  }
}

// ── 🔁 短期反转(过度反应 R3)：大跌次日是否系统性反弹——描述历史规律,非抄底建议、不可交易 ──
async function loadOverreaction() {
  const el = document.getElementById("overreaction");
  if (!el) return;
  let OV = null;
  try { const r = await fetch("overreaction.json?_=" + Date.now()); if (r.ok) OV = await r.json(); } catch (e) { /* 尚未生成 */ }
  if (!OV || OV.status !== "ok") {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${vpL("短期反转数据尚未生成（下次全量流水线后出现）","Short-term reversal data not generated yet (will appear after the next full pipeline run)")}</span>`;
    return;
  }
  // real 用蓝(描述性历史规律),不用绿(避免读成"可交易信号")
  const vmap = vpL(
    { real: ["#3498db", "统计上可见 · 经济上不可用"], faded: ["#3498db", "历史有·现代已消失(被套利)"],
      real_recent_untested: ["#8b949e", "全样本有·现代样本不足未验证"], rejected: ["#2ecc71", "未检出系统反弹"],
      inconclusive: ["#8b949e", "无定论"] },
    { real: ["#3498db", "Statistically visible · economically unusable"], faded: ["#3498db", "Once real · faded in the modern era (arbitraged)"],
      real_recent_untested: ["#8b949e", "Real full-sample · unverified (recent sample too small)"], rejected: ["#2ecc71", "No systematic bounce detected"],
      inconclusive: ["#8b949e", "Inconclusive"] }
  );
  const [c, lbl] = vmap[OV.verdict] || ["#8b949e", esc(OV.verdict || "")];
  const f = OV.full, rc = OV.recent;
  const hn = vpL({ 1: "次日", 5: "次 5 日", 20: "次 20 日" }, { 1: "Next day", 5: "Next 5d", 20: "Next 20d" });
  const dist = OV.distribution || [];
  const drows = dist.map(x => `<tr style="border-top:1px solid var(--border-faint)">
    <td style="padding:.3rem .4rem;color:var(--muted)">${hn[x.horizon] || x.horizon + vpL("日","d")}</td>
    <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums">${x.median_pct}%</td>
    <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e74c3c">${x.p10_pct}%</td>
    <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e74c3c;font-weight:600">${x.worst_pct}%</td>
    <td style="padding:.3rem .4rem;text-align:right;font-variant-numeric:tabular-nums;color:#e67e22">${x.pct_negative}%</td></tr>`).join("");
  const distHtml = dist.length ? `<div style="margin-top:.6rem">
    <div style="font-size:0.76rem;color:var(--muted);margin-bottom:.2rem">${vpL('大跌后历史上发生过什么——<b>完整分布(含灾难路径)</b>，不只看平均：', 'What historically happened after a big drop — <b>the full distribution (including disaster paths)</b>, not just the average:')}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.8rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("区间","Window")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("中位","Median")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("p10(差)","p10 (bad)")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("最坏","Worst")}</td><td style="text-align:right;padding:.2rem .4rem">${vpL("继续亏比例","% still losing")}</td></tr>
      ${drows}
    </table>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.25rem">${vpL('看清没：大跌后约 <b style="color:#e67e22">40–46% 的情况继续亏</b>、最坏跌到 <b style="color:#e74c3c">-20%~-31%</b>。"平均小幅反弹"把这些灾难路径藏起来了——<b>这就是为什么我们不喊抄底：把全貌给你，你自己判断</b>。', 'Look closely: about <b style="color:#e67e22">40–46% of the time it kept losing</b> after the drop, worst case down to <b style="color:#e74c3c">-20%~-31%</b>. The "small average bounce" hides these disaster paths — <b>this is exactly why we don\'t call a dip-buy: we give you the full picture, you decide</b>.')}</div></div>` : "";
  el.innerHTML = `
    <div style="border-left:3px solid ${c};padding:.4rem .7rem;margin-bottom:.6rem">
      <div style="font-weight:700;color:${c}">${lbl}</div>
      <div style="font-size:0.82rem;margin-top:.3rem;line-height:1.55">${vpL(`极端下跌日(收益≤第 ${OV.q} 百分位)的<b>次日</b>平均 ${f.bounce_next_pct}% vs 其余 ${f.other_next_pct}%（差 ${f.diff_pct}pp，全样本 p=${f.p_value}，n=${f.n_down}）${rc ? `<br>现代(2000后)：差 ${rc.diff_pct}pp，p=${rc.p_value}` : ""}`, `On extreme down days (return ≤ ${OV.q}th pct), the <b>next day</b> averages ${f.bounce_next_pct}% vs ${f.other_next_pct}% otherwise (diff ${f.diff_pct}pp, full-sample p=${f.p_value}, n=${f.n_down})${rc ? `<br>Modern era (post-2000): diff ${rc.diff_pct}pp, p=${rc.p_value}` : ""}`)}
      <span style="color:#e67e22;font-size:0.74rem">　${vpL('← 这点均差远小于当日波动与交易成本，统计可见 ≠ 能赚钱', '← This average gap is far smaller than same-day volatility and trading costs — statistically visible ≠ profitable')}</span></div>
    </div>
    ${distHtml}
    <div style="font-size:0.74rem;color:var(--muted);line-height:1.6;margin-top:.5rem">${vpL('⚠ <b>这是历史描述，不是抄底建议、不预测明天</b>。每天零点几 pp 的均差会被<b>波动 / 交易成本 / 滑点</b>吃掉，且极端下跌日多发生在 2008/2020 这类危机中(反弹伴随剧烈波动)——<b>不可交易</b>。', '⚠ <b>This is a historical description, not a dip-buy recommendation, and it does not predict tomorrow</b>. A few-tenths-of-a-percentage-point average gap gets eaten by <b>volatility / trading costs / slippage</b>, and extreme down days mostly cluster in crises like 2008/2020 (bounces come with violent volatility) — <b>not tradable</b>.')} ${esc(OV.caveat || "")}</div>`;
}

// ── 🔬 探索区：未验证/猜测性假设(露了苗头但没过稳健检验)——怀疑训练场,非预测非可交易 ──
async function loadExploratory() {
  const el = document.getElementById("exploratory");
  if (!el) return;
  const get = _fetchJson;
  const [pl, cy, sc] = await Promise.all([
    get("placebo_tests.json"), get("cycles.json"), get("stock_checkup.json"),
  ]);
  const items = [];   // [类别, 名称, 说明, 没过哪一关]
  const ncs = cy?.result?.named_cycles || [];
  for (const c of ncs) {
    if (c.testable === false) items.push([vpL("长周期猜测·无法检验","Long-cycle guess · untestable"), c.cycle, c.note || vpL("超出可检验范围","Beyond the testable range"), vpL("数据跨不了一个完整周期","Data doesn't span a full cycle")]);
    else if (c.low_resolution) items.push([vpL("周期·分辨率边缘","Cycle · resolution edge"), c.cycle, vpL("频带内频点太少、谱分辨率不足，结论不稳","Too few frequency bins in the band; spectral resolution is insufficient, conclusion unstable"), vpL("样本/分辨率","Sample/resolution")]);
    else if (c.exceeds_red_noise_95 && cy?.result?.significant === false) items.push([vpL("周期·逐点超但全局不显著","Cycle · pointwise-exceeds but not globally significant"), c.cycle, vpL("逐频率超红噪声 95% 线，但控多重比较的全局检验后不显著","Exceeds the red-noise 95% line frequency-by-frequency, but not significant after the multiple-comparison-controlled global test"), vpL("全局 max-stat","Global max-stat")]);
  }
  if (pl?.tests) for (const t of pl.tests) {
    if (t.status === "real" && !t.fdr_significant_05) items.push([vpL("日历·裸显著但没过FDR","Calendar · naively significant but fails FDR"), t.panel, vpL(`单看 p=${t.p_value} 显著，多重比较校正后站不住`, `Significant alone at p=${t.p_value}, but doesn't survive multiple-comparison correction`), "FDR"]);
    else if (t.status === "inconclusive") items.push([vpL("日历·无定论(检验力不足)","Calendar · inconclusive (insufficient power)"), t.panel, vpL(`p=${t.p_value}，每组样本太少、无权下结论`, `p=${t.p_value}, each group's sample is too small to conclude anything`), vpL("样本量","Sample size")]);
  }
  if (sc?.summary) items.push([vpL("个股层面","Single-stock level"), vpL("个股日历规律","Single-stock calendar patterns"), vpL("13 票多为无定论(详见个股体检);疑似数据窥探/已消失的见 🪦 坟场","Most of the 13 tickers are inconclusive (see the single-stock check-up); suspected data-snooping/faded ones are in the 🪦 graveyard"), vpL("分半 / 近期","Split-half / recency")]);

  const cats = [...new Set(items.map(d => d[0]))];
  const body = cats.map(c => {
    const rows = items.filter(d => d[0] === c).map(d =>
      `<tr style="border-top:1px solid var(--border-faint)"><td style="padding:.3rem .4rem;font-weight:600">${esc(d[1])}</td><td style="padding:.3rem .4rem;color:var(--muted)">${esc(d[2])}</td><td style="padding:.3rem .4rem;text-align:right;color:#e67e22;font-size:.72rem;white-space:nowrap">${vpL("没过","Failed")}:${esc(d[3])}</td></tr>`).join("");
    return `<div style="margin-bottom:.7rem"><div style="font-size:0.8rem;color:#f1c40f;font-weight:600;margin-bottom:.2rem">🔬 ${esc(c)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">${rows}</table></div>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.7rem;border-left:3px solid #e67e22;padding-left:.6rem">
      ${vpL(
        '⚠ 这里是<b>未通过稳健检验的探索性/猜测性假设</b>——露了点苗头(甚至"有一两次 ok")，但没过 FDR / 分半 / 全局多重比较，<b>极可能是噪声或即将被套利。不是规律、不是预测、不可交易</b>。我们保留并<b>逐次重验</b>：哪天真过了稳健检验 → 升入 🧾 登记簿；证伪 → 进 🪦 坟场。隔壁坟场就是这类东西的大多数归宿——看看就好，别拿来下注。',
        '⚠ This zone holds <b>exploratory/speculative hypotheses that haven\'t passed robust testing</b> — they show a hint of something (even "worked once or twice"), but haven\'t passed FDR / split-half / global multiple-comparison tests, so they\'re <b>very likely noise or about to be arbitraged away. Not a pattern, not a forecast, not tradable</b>. We keep them and <b>re-test every cycle</b>: the day one truly passes robust testing → it graduates to the 🧾 registry; falsified → it goes to the 🪦 graveyard. The graveyard next door is where most of these end up — look, don\'t bet on them.'
      )}</div>
    ${body || `<span style="color:var(--muted);font-size:0.8rem">${vpL("暂无未定论候选(数据尚未生成)","No inconclusive candidates yet (data not generated)")}</span>`}`;
}

// ── 🪦 诚实坟场：聚合死掉的模型 + 消失/被刷掉的规律(同源消费各 JSON) ──
async function loadGraveyard() {
  const el = document.getElementById("honest-graveyard");
  if (!el) return;
  const get = _fetchJson;
  const [pl, fx, cy, sc] = await Promise.all([
    get("placebo_tests.json"), get("fdr_crossfamily.json"), get("cycles.json"), get("stock_checkup.json"),
  ]);
  const dead = [];   // [类别, 名称, 说明]
  dead.push([vpL("模型/假设被否","Model/hypothesis rejected"), vpL("v3 稀疏模型(L1 正则)","v3 sparse model (L1 regularization)"), vpL("加正则未带来样本外增益，假设被否(诚实 null，见 git 历史)","Adding regularization brought no out-of-sample gain — hypothesis rejected (honest null result, see git history)")]);
  dead.push([vpL("模型/假设被否","Model/hypothesis rejected"), vpL("指数纳入效应 RDD","Index-inclusion effect (RDD)"), vpL("断点回归需 Russell 浮动市值排名(专有不可得)，拒用劣质代理硬凑 → 诚实不做","Regression discontinuity needs the Russell float-market-cap ranking (proprietary, unavailable) — refused to force a low-quality proxy → honestly not attempted")]);
  dead.push([vpL("模型/假设被否","Model/hypothesis rejected"), vpL("Fed model(盈利收益率 vs 债券收益率)","Fed model (earnings yield vs. bond yield)"), vpL("流行但学术已证伪(Asness 2003):它相关的是通胀、非真实价值;不预测股市回报","Popular but academically debunked (Asness 2003): it correlates with inflation, not real value; it doesn't predict stock returns")]);
  if (pl?.tests) for (const t of pl.tests) if (t.status === "rejected")
    dead.push([vpL("曾认为有效·现已测不到","Once thought real · now undetectable"), t.panel, vpL(`充分样本下不显著(p=${t.p_value})——很可能已被套利`, `Not significant even with a full sample (p=${t.p_value}) — very likely already arbitraged away`)]);
  if (pl?.tests) for (const t of pl.tests) if (t.fdr_significant_05 && t.recent_p != null && !t.recent_significant && (t.recent_min_group_n == null || t.recent_min_group_n >= 30))
    dead.push([vpL("曾有效·现已消失(指数级)","Once real · now faded (index-level)"), t.panel, vpL(`全样本 FDR 显著(q=${t.q_value})但 2000 后 p=${t.recent_p.toFixed(2)} 已测不到——全样本显著多半是 2000 前遗物，很可能被套利`, `Full-sample FDR-significant (q=${t.q_value}) but undetectable post-2000 (p=${t.recent_p.toFixed(2)}) — the full-sample significance is mostly a pre-2000 relic, very likely arbitraged away`)]);
  if (sc?.tickers) for (const k of Object.keys(sc.tickers)) {
    const p = sc.tickers[k].patterns, nm = tickerName(k, sc.tickers[k].name || "");
    if (p && p.overall === "faded") dead.push([vpL("曾有效·现已消失(个股)","Once real · now faded (single-stock)"), vpL(`${k} ${nm} 日历规律`, `${k} ${nm} calendar pattern`), vpL("全史显著但近年消失——经典被套利(详见个股体检)","Significant over the full history but faded in recent years — a textbook arbitraged-away case (see the single-stock check-up)")]);
    else if (p && p.overall === "data_snoop") dead.push([vpL("伪规律(数据窥探)","Fake pattern (data snooping)"), vpL(`${k} ${nm} 日历规律`, `${k} ${nm} calendar pattern`), vpL("in-sample 显著但分半不稳 = 数据窥探","Significant in-sample but unstable across split-half = data snooping")]);
  }
  if (pl?.tests) for (const t of pl.tests) if (t.status === "real" && !t.fdr_significant_05)
    dead.push([vpL("被多重比较(FDR)刷掉","Killed by multiple-comparison (FDR) correction"), t.panel, vpL(`裸 p 显著(${t.p_value})但 FDR 校正后掉出(q≥0.05)`, `Naively significant (p=${t.p_value}) but drops out after FDR correction (q≥0.05)`)]);
  if (fx && fx.m_total != null) dead.push([vpL("被多重比较(FDR)刷掉","Killed by multiple-comparison (FDR) correction"), vpL("跨检验族总账","Cross-family ledger"), vpL(`全站 ${fx.m_total} 项显著性主张 → 跨族 BY 后仅 ${fx.n_survive_by_10} 项扛住(${fx.m_total - fx.n_survive_by_10} 项是噪声)`, `${fx.m_total} significance claims site-wide → only ${fx.n_survive_by_10} survive cross-family BY (${fx.m_total - fx.n_survive_by_10} are noise)`)]);
  if (cy?.result && cy.result.significant === false) dead.push([vpL("民间说法被否","Folk claim rejected"), vpL("市场周期(基钦/朱格拉等)","Market cycles (Kitchin/Juglar etc.)"), vpL("未检出超过红噪声的显著周期","No cycle exceeding red noise was detected")]);

  const cats = [...new Set(dead.map(d => d[0]))];
  const body = cats.map(c => {
    const items = dead.filter(d => d[0] === c).map(d =>
      `<tr style="border-top:1px solid var(--border-faint)"><td style="padding:.3rem .4rem;font-weight:600">${esc(d[1])}</td><td style="padding:.3rem .4rem;color:var(--muted)">${esc(d[2])}</td></tr>`).join("");
    return `<div style="margin-bottom:.7rem"><div style="font-size:0.8rem;color:#e67e22;font-weight:600;margin-bottom:.2rem">🪦 ${esc(c)}</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.82rem">${items}</table></div>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.7rem">${vpL('这页专收<b>死掉的东西</b>——试过没用、曾有效现已消失、被多重比较刷掉。诚实统计的价值，一半在于敢把<b>坟</b>立出来：这些"否定结果"和"找到规律"同样重要，且能防你去追一个早已被套利的幻觉。', 'This page collects <b>the things that died</b> — tried and useless, once real and now faded, killed by multiple-comparison correction. Half the value of honest statistics is having the nerve to put up the <b>graveyard</b>: these "null results" matter just as much as "found a pattern," and they keep you from chasing an illusion that\'s already been arbitraged away.')}</div>
    ${body}`;
}

function renderDigitChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.decade_digit) return;
  const items = [...yp.decade_digit].sort((a,b) => a.digit - b.digit);
  const colors = items.map(d => d.digit===5 ? "#f1c40f" : d.avg_return>0 ? "#2ecc71" : "#e74c3c");
  Plotly.newPlot("chart-digit",[{
    type:"bar",
    x: items.map(d => vpL(d.label, d.label.replace("年",""))),
    y: items.map(d => d.avg_return),
    marker:{color:colors},
    text: items.map(d=> vpL(`胜率${d.win_rate}% n=${d.n}`, `Win rate ${d.win_rate}% n=${d.n}`)),
    hovertemplate: vpL("<b>%{x}</b><br>年均回报: %{y:.1f}%<br>%{text}<extra></extra>","<b>%{x}</b><br>Avg annual return: %{y:.1f}%<br>%{text}<extra></extra>"),
  }],{
    ...DARK,
    yaxis:{...DARK.yaxis,title: vpL("S&P500年均回报 (%)","S&P 500 average annual return (%)")},
    xaxis:{...DARK.xaxis,title: vpL("年份个位数","Year's last digit")},
    margin:{t:20,b:60,l:60,r:20},
    shapes:[{type:"line",x0:-0.5,x1:9.5,y0:0,y1:0,line:{color:"#555",width:1}}]
  },{responsive:true});
  const d5 = yp.decade_digit.find(d=>d.digit==5);
  document.getElementById("digit-highlight").innerHTML = vpL(
    `<span style="color:#f1c40f">★ ×5年（如1995、2005、2015、2025）：均值 <strong>+${d5?.avg_return||"?"}%</strong>，胜率 <strong>${d5?.win_rate||"?"}%</strong>，历史最强十年位</span>`,
    `<span style="color:#f1c40f">★ Years ending in 5 (e.g. 1995, 2005, 2015, 2025): mean <strong>+${d5?.avg_return||"?"}%</strong>, win rate <strong>${d5?.win_rate||"?"}%</strong> — the strongest position in the decade historically</span>`
  );
}

function renderCycleChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.presidential_cycle) return;
  const items = yp.presidential_cycle;
  const colors = items.map(d => d.label.includes("选前") ? "#f1c40f" : "#3498db");
  Plotly.newPlot("chart-cycle",[
    {type:"bar", name: vpL("年均回报%","Avg annual return %"),
     x:items.map(d=>cycleLabel(d.label)), y:items.map(d=>d.avg_return),
     marker:{color:colors},
     text:items.map(d=> vpL(`胜率${d.win_rate}% n=${d.n}`, `Win rate ${d.win_rate}% n=${d.n}`)),
     hovertemplate:"<b>%{x}</b><br>%{y:.1f}%<br>%{text}<extra></extra>"},
    {type:"scatter",mode:"lines+markers", name: vpL("胜率%","Win rate %"),
     x:items.map(d=>cycleLabel(d.label)), y:items.map(d=>d.win_rate),
     yaxis:"y2", line:{color:"#9b59b6",width:2},
     marker:{color:"#9b59b6",size:7}}
  ],{
    ...DARK,
    yaxis:{...DARK.yaxis,title: vpL("年均回报 (%)","Avg annual return (%)")},
    yaxis2:{title: vpL("胜率 (%)","Win rate (%)"),overlaying:"y",side:"right",range:[40,90],gridcolor:"transparent"},
    xaxis:{...DARK.xaxis},
    margin:{t:20,b:60,l:60,r:60},
    legend:{orientation:"h",y:1.05}
  },{responsive:true});
  const best = items.find(d=>d.label.includes("选前")) || items[0];
  document.getElementById("cycle-insight").innerHTML = vpL(
    `<strong>总统任期四年周期：</strong>选前年（Year 3）历史均值 <strong style="color:#f1c40f">+${best.avg_return}%</strong>，胜率 <strong>${best.win_rate}%</strong>——总统在大选前一年倾向刺激经济。<br>
     中期选举年（Year 2）最弱，均值 ${items.find(d=>d.label.includes("中期"))?.avg_return||"?"}%，不确定性最大。<br>
     <span style="color:var(--muted);font-size:0.78rem">2025年=Year 1（新任期），历史均值+7.0%，胜率60%。</span>`,
    `<strong>The four-year presidential cycle:</strong> the pre-election year (Year 3) historically averages <strong style="color:#f1c40f">+${best.avg_return}%</strong>, win rate <strong>${best.win_rate}%</strong> — presidents tend to stimulate the economy the year before an election.<br>
     The midterm-election year (Year 2) is weakest, averaging ${items.find(d=>d.label.includes("中期"))?.avg_return||"?"}%, with the most uncertainty.<br>
     <span style="color:var(--muted);font-size:0.78rem">2025 = Year 1 (new term), historical average +7.0%, win rate 60%.</span>`
  );
}

function renderPartyChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.party_effect) return;
  const parties = yp.party_effect;
  const R = parties.find(p=>p.party==="R");
  const D = parties.find(p=>p.party==="D");
  const presidents = (yp.president_detail||[]).sort((a,b)=>a.start-b.start);

  Plotly.newPlot("chart-party",[
    {type:"bar",name: vpL("共和党","Republican"),
     x:[vpL("年均回报(%)","Avg annual return (%)"),vpL("胜率(%)","Win rate (%)")],
     y:[R?.avg_return||0, R?.win_rate||0],
     marker:{color:"#e74c3c"},
     text:[vpL(`n=${R?.n}年`,`n=${R?.n}yr`),vpL(`n=${R?.n}年`,`n=${R?.n}yr`)],
     hovertemplate: vpL("共和党 %{x}: %{y:.1f}<extra></extra>","Republican %{x}: %{y:.1f}<extra></extra>")},
    {type:"bar",name: vpL("民主党","Democratic"),
     x:[vpL("年均回报(%)","Avg annual return (%)"),vpL("胜率(%)","Win rate (%)")],
     y:[D?.avg_return||0, D?.win_rate||0],
     marker:{color:"#3498db"},
     text:[vpL(`n=${D?.n}年`,`n=${D?.n}yr`),vpL(`n=${D?.n}年`,`n=${D?.n}yr`)],
     hovertemplate: vpL("民主党 %{x}: %{y:.1f}<extra></extra>","Democratic %{x}: %{y:.1f}<extra></extra>")},
  ],{...DARK,barmode:"group",margin:{t:20,b:40,l:60,r:20},legend:{orientation:"h",y:1.05}},{responsive:true});

  if (presidents.length > 0) {
    Plotly.newPlot("chart-presidents",[{
      type:"bar", orientation:"h",
      x: presidents.map(p=>p.avg_return),
      y: presidents.map(p=>`${presidentName(p.name)}(${p.start}-${p.end})`),
      marker:{color: presidents.map(p=>p.party==="R"?"#e74c3c":"#3498db"), opacity:0.8},
      text: presidents.map(p=> vpL(`${p.avg_return>0?"+":""}${p.avg_return}%  胜率${p.win_rate}%`, `${p.avg_return>0?"+":""}${p.avg_return}%  win rate ${p.win_rate}%`)),
      textposition:"outside", cliponaxis:false,
      hovertemplate: vpL("<b>%{y}</b><br>年均: %{x:.1f}%<extra></extra>","<b>%{y}</b><br>Avg annual: %{x:.1f}%<extra></extra>"),
    }],{
      ...DARK,
      xaxis:{...DARK.xaxis,title: vpL("年均回报 (%)","Avg annual return (%)"), zeroline:true, zerolinecolor:"#444"},
      margin:{t:10,b:40,l:150,r:100},
      height:280,
    },{responsive:true});
  }

  // 执政党效应长句：英文语序与中文相反(民主党在前→保留原意但改写主谓结构)，整句双写、数字全经插值。
  document.getElementById("party-insight").innerHTML = vpL(
    `<strong>执政党效应（1928-2026）：</strong>民主党执政年均 <strong style="color:#3498db">+${D?.avg_return}%</strong>（胜率${D?.win_rate}%，n=${D?.n}年）；共和党 <strong style="color:#e74c3c">+${R?.avg_return}%</strong>（胜率${R?.win_rate}%，n=${R?.n}年）。<br>
     <span style="color:var(--muted);font-size:0.78rem">⚠ 相关≠因果：差异主要来自经济周期的巧合（胡佛遇大萧条，克林顿遇科技繁荣），而非政策直接驱动。不建议据此做选党投资决策。</span>`,
    `<strong>Ruling-party effect (1928-2026):</strong> under Democratic presidents, the market averaged <strong style="color:#3498db">+${D?.avg_return}%</strong> a year (win rate ${D?.win_rate}%, n=${D?.n}yr); under Republican presidents, <strong style="color:#e74c3c">+${R?.avg_return}%</strong> (win rate ${R?.win_rate}%, n=${R?.n}yr).<br>
     <span style="color:var(--muted);font-size:0.78rem">⚠ Correlation ≠ causation: the gap mainly reflects coincidences of the economic cycle (Hoover caught the Great Depression, Clinton caught the tech boom), not direct policy effects. Not a recommendation to invest based on which party wins.</span>`
  );
}

function renderCalHolidayChart() {
  const hd = SIGNALS?.holiday_detail;
  if (!hd) return;
  const items = vpL(
    [
      {label:"感恩节前夕", wr: hd.thanksgiving_eve?.win_rate, n: hd.thanksgiving_eve?.n},
      {label:"黑色星期五", wr: hd.thanksgiving_friday?.win_rate, n: hd.thanksgiving_friday?.n},
      {label:"节前3天内",  wr: hd.pre_holiday?.win_rate, n: hd.pre_holiday?.n},
      {label:"节后3天内",  wr: hd.post_holiday?.win_rate, n: hd.post_holiday?.n},
      {label:"圣诞行情",   wr: hd.santa_claus_rally?.win_rate, n: hd.santa_claus_rally?.n},
      {label:"1月效应",    wr: hd.january_effect?.win_rate, n: hd.january_effect?.n},
      {label:"普通交易日", wr: hd.normal?.win_rate, n: hd.normal?.n},
    ],
    [
      {label:"Thanksgiving eve", wr: hd.thanksgiving_eve?.win_rate, n: hd.thanksgiving_eve?.n},
      {label:"Black Friday", wr: hd.thanksgiving_friday?.win_rate, n: hd.thanksgiving_friday?.n},
      {label:"Within 3d pre-holiday",  wr: hd.pre_holiday?.win_rate, n: hd.pre_holiday?.n},
      {label:"Within 3d post-holiday",  wr: hd.post_holiday?.win_rate, n: hd.post_holiday?.n},
      {label:"Santa Claus rally",   wr: hd.santa_claus_rally?.win_rate, n: hd.santa_claus_rally?.n},
      {label:"January effect",    wr: hd.january_effect?.win_rate, n: hd.january_effect?.n},
      {label:"Ordinary trading day", wr: hd.normal?.win_rate, n: hd.normal?.n},
    ]
  ).filter(d=>d.wr!=null).sort((a,b)=>b.wr-a.wr);

  const colors = items.map(d => d.wr>=65?"#f1c40f": d.wr>=58?"#2ecc71": d.wr>=54?"#3498db":"#8b949e");
  Plotly.newPlot("chart-cal-holiday",[{
    type:"bar", orientation:"h",
    x: items.map(d=>d.wr),
    y: items.map(d=>d.label),
    marker:{color:colors},
    text: items.map(d=> vpL(`${d.wr}%  n=${d.n}`, `${d.wr}%  n=${d.n}`)),
    textposition:"outside", cliponaxis:false,
    hovertemplate: vpL("<b>%{y}</b><br>胜率: %{x:.1f}%<extra></extra>","<b>%{y}</b><br>Win rate: %{x:.1f}%<extra></extra>"),
  }],{
    ...DARK,
    xaxis:{...DARK.xaxis, title: vpL("上涨胜率 (%)","Up-move win rate (%)"), range:[44,84]},
    margin:{t:20,b:50,l:110,r:90},
    shapes:[{type:"line",x0:hd.normal?.win_rate||52.4,x1:hd.normal?.win_rate||52.4,
             y0:-0.5,y1:items.length-0.5,
             line:{color:"#555",dash:"dot",width:1}}]
  },{responsive:true});

  document.getElementById("cal-holiday-insight").innerHTML = vpL(
    `<strong>假日效应（1950-2026日频）：</strong>感恩节前夕胜率 <strong style="color:#f1c40f">${hd.thanksgiving_eve?.win_rate}%</strong>（n=${hd.thanksgiving_eve?.n}），是全年单日最强规律之一。节前节后均显著高于普通日（基准${hd.normal?.win_rate}%）。`,
    `<strong>Holiday timing effect (1950-2026, daily frequency):</strong> Thanksgiving eve has a win rate of <strong style="color:#f1c40f">${hd.thanksgiving_eve?.win_rate}%</strong> (n=${hd.thanksgiving_eve?.n}), one of the strongest single-day patterns all year. Both pre- and post-holiday windows are significantly above the ordinary-day baseline of ${hd.normal?.win_rate}%.`
  );
}

