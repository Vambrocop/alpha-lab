// ═══════════════════════════════════════════════════════
//  预测 vs 实际结果 — 准确率回溯
// ═══════════════════════════════════════════════════════
function renderPredictionAccuracy() {
  if (!SIGNALS || !SIGNALS.daily_signals) return;
  const nDays = parseInt(document.getElementById("accuracy-days-select")?.value || 40);

  // Collect last N days that have actual return data
  const allDays = Object.entries(SIGNALS.daily_signals)
    .filter(([, v]) => v.ret != null)
    .sort(([a], [b]) => a.localeCompare(b));

  const recent = allDays.slice(-nDays);
  if (!recent.length) return;

  // Build result objects
  const DOW_LABELS = vpL(["周一","周二","周三","周四","周五","周六","周日"],
                          ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]);
  const rows = recent.map(([date, v]) => {
    const prob    = v.prob;
    const ret     = v.ret;           // actual % return
    const actualUp = ret > 0;
    const tier    = v.tier;
    // Signal direction: only "call" when signal is in tier 4+ (≥0.60) or tier 1-2 (≤0.40)
    let predicted = "neutral";
    if      (prob >= 0.60) predicted = "up";
    else if (prob <= 0.40) predicted = "down";
    const hasCall = predicted !== "neutral";
    const correct  = hasCall
      ? ((predicted === "up" && actualUp) || (predicted === "down" && !actualUp))
      : null;
    return { date, prob, tier, ret, actualUp, predicted, hasCall, correct, dow: v.dow };
  });

  // ── Summary stats ──────────────────────────────────────────────
  const called   = rows.filter(r => r.hasCall);
  const correct  = called.filter(r => r.correct);
  const tier45   = rows.filter(r => r.tier >= 4);
  const t45ok    = tier45.filter(r => r.correct);
  const tier12   = rows.filter(r => r.tier <= 2);
  const t12ok    = tier12.filter(r => r.correct);
  const overall  = called.length > 0 ? (correct.length / called.length * 100) : null;
  const h4Acc    = tier45.length  > 0 ? (t45ok.length  / tier45.length  * 100) : null;
  const l2Acc    = tier12.length  > 0 ? (t12ok.length  / tier12.length  * 100) : null;

  function accColor(pct) {
    if (pct == null) return "var(--muted)";
    if (pct >= 65) return "#27ae60";
    if (pct >= 55) return "#2ecc71";
    if (pct >= 45) return "#f1c40f";
    return "#e74c3c";
  }

  const summaryEl = document.getElementById("accuracy-summary");
  if (summaryEl) summaryEl.innerHTML = [
    { label: vpL("第4-5档信号准确率","Tier 4-5 signal accuracy"), val:h4Acc, n:tier45.length,
      hint: vpL("概率≥60%时，预测上涨是否正确","Whether the up-call was correct when probability ≥60%") },
    { label: vpL("第1-2档信号准确率","Tier 1-2 signal accuracy"), val:l2Acc, n:tier12.length,
      hint: vpL("概率≤40%时，预测下跌是否正确","Whether the down-call was correct when probability ≤40%") },
    { label: vpL("总体有效信号准确率","Overall active-signal accuracy"), val:overall, n:called.length,
      hint: vpL("所有非中性预测的综合准确率","Combined accuracy across all non-neutral calls") },
    { label: vpL(`近${nDays}天上涨天数`, `Up days (last ${nDays}d)`),
      val: rows.filter(r=>r.actualUp).length / rows.length * 100,
      n:rows.length, hint: vpL("实际市场上涨天数占比","Share of days the market actually rose") },
  ].map(c => `
    <div class="acc-card">
      <div class="acc-card-num" style="color:${accColor(c.val)}">${c.val!=null ? c.val.toFixed(1)+"%" : "—"}</div>
      <div class="acc-card-label">${c.label}<br><span style="opacity:.7">n=${c.n}</span></div>
    </div>`).join("");

  // ── Timeline Plotly chart ───────────────────────────────────────
  const dates  = rows.map(r => r.date);
  const probs  = rows.map(r => +(r.prob * 100).toFixed(1));
  const rets   = rows.map(r => +r.ret.toFixed(2));
  const barColors = rows.map(r => {
    if (!r.hasCall) return "rgba(139,148,158,.35)";
    return r.correct ? "rgba(46,204,113,.75)" : "rgba(231,76,60,.75)";
  });
  const hoverText = rows.map(r => {
    const callStr = r.predicted === "up" ? vpL("📈看多","📈 Bullish") : r.predicted === "down" ? vpL("📉看空","📉 Bearish") : vpL("中性","Neutral");
    const outStr  = r.actualUp ? `+${r.ret.toFixed(2)}%↑` : `${r.ret.toFixed(2)}%↓`;
    const res     = r.hasCall ? (r.correct ? vpL("✓正确","✓ Correct") : vpL("✗错误","✗ Wrong")) : vpL("中性(不计)","Neutral (excluded)");
    return vpL(
      `${r.date}<br>信号: ${callStr} (${(r.prob*100).toFixed(1)}%)<br>实际: ${outStr}<br>${res}`,
      `${r.date}<br>Signal: ${callStr} (${(r.prob*100).toFixed(1)}%)<br>Actual: ${outStr}<br>${res}`
    );
  });

  Plotly.newPlot("chart-accuracy", [
    { type:"bar", name: vpL("预测概率%","Predicted prob %"), x:dates, y:probs,
      marker:{ color: barColors },
      text: hoverText, hovertemplate:"%{text}<extra></extra>",
      width: 0.7 },
    { type:"scatter", name: vpL("实际涨跌%","Actual return %"), x:dates, y:rets,
      mode:"lines+markers", yaxis:"y2",
      line:{ color:"rgba(52,152,219,.8)", width:1.5 },
      marker:{ size:4, color: rets.map(r => r>0?"#2ecc71":"#e74c3c") },
      hovertemplate: vpL("%{x}<br>实际: %{y:.2f}%<extra></extra>","%{x}<br>Actual: %{y:.2f}%<extra></extra>") },
    { type:"scatter", name: vpL("60% 基准线","60% baseline"), x:[dates[0],dates[dates.length-1]], y:[60,60],
      mode:"lines", line:{color:"rgba(46,204,113,.4)",dash:"dot",width:1}, hoverinfo:"skip" },
  ], {
    ...DARK,
    yaxis:  { ...DARK.yaxis, title: vpL("预测概率 %","Predicted probability %"), range:[35,90] },
    yaxis2: { overlaying:"y", side:"right", title: vpL("实际涨跌 %","Actual return %"), zeroline:true,
               zerolinecolor:"#444", gridcolor:"transparent", tickformat:".1f" },
    legend: { orientation:"h", y:1.08, font:{size:10} },
    margin: { t:10, b:55, l:55, r:55 },
    hovermode:"x unified",
    xaxis:  { ...DARK.xaxis, tickangle:-40, tickfont:{size:9} },
  }, { responsive:true });

  // ── Recent rows table (last 14) ───────────────────────────────
  const tableEl = document.getElementById("accuracy-table");
  if (!tableEl) return;
  const last14 = rows.slice(-14).reverse();
  const headerStyle = "color:var(--muted);font-size:0.72rem;padding:.2rem .5rem;";
  const cellStyle   = "padding:.3rem .5rem;white-space:nowrap;";
  tableEl.innerHTML = `
    <table style="width:100%;border-collapse:collapse;min-width:480px;">
      <thead><tr style="border-bottom:1px solid var(--border);">
        <th style="${headerStyle}text-align:left">${vpL("日期","Date")}</th>
        <th style="${headerStyle}text-align:right">${vpL("预测方向","Predicted direction")}</th>
        <th style="${headerStyle}text-align:right">${vpL("概率","Probability")}</th>
        <th style="${headerStyle}text-align:right">${vpL("实际涨跌","Actual return")}</th>
        <th style="${headerStyle}text-align:center">${vpL("结果","Result")}</th>
      </tr></thead>
      <tbody>
      ${last14.map(r => {
        const signalStr = r.predicted === "up"
          ? `<span style="color:#2ecc71">${vpL(`📈 看多(T${r.tier})`, `📈 Bullish (T${r.tier})`)}</span>`
          : r.predicted === "down"
          ? `<span style="color:#e74c3c">${vpL(`📉 看空(T${r.tier})`, `📉 Bearish (T${r.tier})`)}</span>`
          : `<span style="color:var(--muted)">${vpL(`→ 中性(T${r.tier})`, `→ Neutral (T${r.tier})`)}</span>`;
        const retColor  = r.ret > 0 ? "#2ecc71" : r.ret < 0 ? "#e74c3c" : "var(--muted)";
        const retStr    = `<span style="color:${retColor}">${r.ret > 0 ? "+" : ""}${r.ret.toFixed(2)}%</span>`;
        const resultStr = !r.hasCall ? `<span style="color:var(--muted)">—</span>`
          : r.correct ? `<span style="color:#2ecc71;font-weight:700">✓</span>`
          : `<span style="color:#e74c3c;font-weight:700">✗</span>`;
        const todayBg   = r.date === localDateStr() ? "background:rgba(52,152,219,.07);" : "";
        return `<tr style="border-bottom:1px solid var(--border-faint);${todayBg}">
          <td style="${cellStyle}">${r.date} <span style="color:var(--muted);font-size:0.72rem">${DOW_LABELS[r.dow||0]}</span></td>
          <td style="${cellStyle}text-align:right">${signalStr}</td>
          <td style="${cellStyle}text-align:right;font-weight:700">${(r.prob*100).toFixed(1)}%</td>
          <td style="${cellStyle}text-align:right">${retStr}</td>
          <td style="${cellStyle}text-align:center">${resultStr}</td>
        </tr>`;
      }).join("")}
      </tbody>
    </table>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;line-height:1.5;">
      ${vpL(
        "✓/✗ 仅统计信号概率≥60%（看多）或≤40%（看空）的有效预测。中性区间(40-60%)不纳入准确率计算。",
        "✓/✗ only count signals with probability ≥60% (bullish) or ≤40% (bearish). The neutral 40-60% band is excluded from the accuracy calculation."
      )}
      <br>${vpL(
        "注意：本模型预测的是\"统计上有利的入场时机\"，不是逐日涨跌预测——单日准确率参考意义有限，多日累积效果更重要。",
        "Note: this model predicts a \"statistically favorable entry window,\" not day-by-day direction — single-day accuracy has limited meaning; the cumulative multi-day effect matters more."
      )}
    </div>`;
}

// ── 回测验证图表 ──
function renderBacktestCharts() {
  // 新格式按指数分组（NASDAQ/SP500），旧格式平铺；面板展示纳指回测
  const bt = SIGNALS?.backtest?.NASDAQ || SIGNALS?.backtest;
  if (!bt) return;

  const tiers = bt.by_tier || [];

  // 2026-07-03：backtest.py 由 fail-closed 改为优雅降级续跑——信号与价格历史
  // 无重叠日期（或前向窗口数据缺失）时不再让整条流水线中止，而是返回
  // degraded=true 的空结构（by_tier=[]、calibration_20d=[]、tier4_strategy 全 NaN）。
  // 这里必须显式识别并给出诚实占位，否则 [] 是 truthy、会静默往下走空数组画图、
  // 渲染出一堆 "?" 和硬编码兜底基准（63.1%），看起来像"分析结果"实则是垃圾。
  if (bt.degraded || tiers.length === 0) {
    const msg = vpL(
      "⚠ 回测数据本轮不可用（信号与价格历史无重叠，或前向窗口数据缺失，疑似上游数据源异常）——本次未产出可评估的统计结果，不代表模型失效，请等待下次数据刷新或核查数据源。",
      "⚠ Backtest data unavailable this run (no overlap between signal and price history, or forward-window data missing — likely an upstream data-source issue). No evaluable statistical result was produced this time; this does not mean the model has failed. Please wait for the next data refresh or check the data source."
    );
    const tierEl = document.getElementById("chart-backtest-tier");
    const calEl  = document.getElementById("chart-backtest-cal");
    const insightEl = document.getElementById("backtest-insight");
    if (tierEl) tierEl.innerHTML = `<div style="color:var(--muted);font-size:0.85rem;padding:1rem 0;">${msg}</div>`;
    if (calEl)  calEl.innerHTML  = "";
    if (insightEl) insightEl.innerHTML = `<span style="color:#e67e22">${msg}</span>`;
    return;
  }
  const base20  = bt.baseline?.["20d"]?.win_rate || 63.1;
  const TIER_COLOR = { 1:"#e74c3c", 2:"#e74c3c", 3:"#f1c40f", 4:"#2ecc71", 5:"#27ae60" };
  const TIER_LABEL = vpL(
    { 1:"第1档", 2:"第2档", 3:"第3档", 4:"第4档", 5:"第5档" },
    { 1:"Tier 1", 2:"Tier 2", 3:"Tier 3", 4:"Tier 4", 5:"Tier 5" }
  );

  // ── 图1：各档位实际20日胜率 ──────────────────────────────────
  const horizons = ["1d","5d","10d","20d","30d"];
  const hLabels  = vpL(["1日","5日","10日","20日","30日"], ["1d","5d","10d","20d","30d"]);
  const traces = tiers.map(t => ({
    type: "scatter", mode: "lines+markers",
    name: TIER_LABEL[t.tier] + vpL(`（n=${t.n}）`, ` (n=${t.n})`),
    x: hLabels,
    y: horizons.map(h => t.horizons[h]?.win_rate ?? null),
    line: { color: TIER_COLOR[t.tier] || "#3498db", width: 2 },
    marker: { size: 7 },
    hovertemplate: vpL(`<b>Tier ${t.tier} %{x}</b><br>胜率: %{y:.1f}%<extra></extra>`,
                        `<b>Tier ${t.tier} %{x}</b><br>Win rate: %{y:.1f}%<extra></extra>`),
  }));
  // 基准线
  traces.push({
    type: "scatter", mode: "lines",
    name: vpL(`基准（全样本 ${base20}%）`, `Baseline (full sample ${base20}%)`),
    x: hLabels, y: hLabels.map(() => base20),
    line: { color: "#8b949e", dash: "dot", width: 1.5 },
    hoverinfo: "skip",
  });

  Plotly.newPlot("chart-backtest-tier", traces, {
    ...DARK,
    yaxis: {...DARK.yaxis, title: vpL("实际上涨胜率 (%)","Actual up-move win rate (%)"), range: [25, 80]},
    xaxis: {...DARK.xaxis, title: vpL("持有天数","Holding days")},
    margin: {t: 20, b: 50, l: 60, r: 20},
    legend: {orientation: "h", y: 1.12},
  }, {responsive: true});

  // ── 图2：校准曲线（模型预测 vs 实际20日胜率）────────────────
  const cal = bt.calibration_20d || [];
  if (cal.length > 0) {
    const calX = cal.map(c => c.bucket);
    const calY = cal.map(c => c.actual_wr_20d);
    const calN = cal.map(c => c.n);
    const calColors = calY.map(y => y >= base20 + 3 ? "#2ecc71" : y >= base20 ? "#f1c40f" : "#e74c3c");
    Plotly.newPlot("chart-backtest-cal", [{
      type: "bar",
      x: calX, y: calY,
      marker: { color: calColors },
      text: cal.map(c => `n=${c.n}`),
      hovertemplate: vpL("<b>预测概率区间: %{x}</b><br>实际20日胜率: %{y:.1f}%<br>%{text}<extra></extra>",
                          "<b>Predicted-probability bucket: %{x}</b><br>Actual 20-day win rate: %{y:.1f}%<br>%{text}<extra></extra>"),
    }, {
      type: "scatter", mode: "lines",
      x: calX, y: calX.map(() => base20),
      line: { color: "#8b949e", dash: "dot", width: 1.5 },
      name: vpL("基准","Baseline"), hoverinfo: "skip",
    }], {
      ...DARK,
      yaxis: {...DARK.yaxis, title: vpL("实际胜率 (%)","Actual win rate (%)"), range: [45, 75]},
      xaxis: {...DARK.xaxis, title: vpL("模型预测概率区间","Model-predicted probability bucket")},
      margin: {t: 10, b: 50, l: 60, r: 20},
      showlegend: false,
    }, {responsive: true});
  }

  // ── Insight 文字 ──────────────────────────────────────────────
  const s4 = bt.tier4_strategy || {};
  const t4 = tiers.find(t => t.tier === 4);
  const t2 = tiers.find(t => t.tier === 2);
  const t3 = tiers.find(t => t.tier === 3);
  const sig4 = t4?.horizons?.["20d"]?.significant;
  const sig2 = t2?.horizons?.["5d"]?.significant;

  const calInsight = (() => {
    if (!cal.length) return vpL("校准曲线：数据不足，暂无法评估单调性。","Calibration curve: insufficient data to assess monotonicity.");
    const calMonotonic = cal.every((c, i) => i === 0 || c.actual_wr_20d >= cal[i - 1].actual_wr_20d);
    return calMonotonic
      ? vpL("校准曲线：模型预测概率越高 → 实际胜率确实更高，信号有单调性。",
            "Calibration curve: higher predicted probability really does mean a higher actual win rate — the signal is monotonic.")
      : vpL("校准曲线：分段胜率非单调（高置信区间 ≠ 更准），需谨慎解读概率区间。",
            "Calibration curve: bucketed win rates are non-monotonic (higher confidence ≠ more accurate) — interpret probability buckets with caution.");
  })();
  const s4SigStr = s4.significant === undefined ? ""
    : s4.significant ? vpL("（<strong>统计显著</strong>）"," (<strong>statistically significant</strong>)")
    : vpL("（<strong>未达显著，纯噪声区间</strong>）"," (<strong>not significant — pure noise range</strong>)");

  document.getElementById("backtest-insight").innerHTML = vpLang() === "en" ? `
     <strong>Historical backtest conclusion (2000-2026, ${SIGNALS.backtest?.NASDAQ?.baseline?.["20d"]?.n ?? Object.values(SIGNALS.daily_signals).length} trading days):</strong><br><br>
     <span style="color:#2ecc71">▲ Tier 4 signal (≥60%, n=${t4?.n||0}d):</span>
     20-day actual win rate <strong style="color:#2ecc71">${t4?.horizons?.["20d"]?.win_rate||"?"}%</strong>,
     above the full-sample baseline of ${base20}% (+${t4?.horizons?.["20d"]?.diff_vs_baseline||"?"}pp),
     <strong>p=${t4?.horizons?.["20d"]?.p_value||"?"}</strong>${sig4?" ✓ statistically significant":""}<br>
     <span style="color:#e74c3c">▼ Tier 2 signal (≤40%, n=${t2?.n||0}d):</span>
     5-day win rate only <strong style="color:#e74c3c">${t2?.horizons?.["5d"]?.win_rate||"?"}%</strong>,
     well below baseline (${t2?.horizons?.["5d"]?.diff_vs_baseline||"?"}pp),
     <strong>p=${t2?.horizons?.["5d"]?.p_value||"?"}</strong>${sig2?" ✓ statistically significant":""}<br>
     <span style="color:#f1c40f">△ Tier 3 signal:</span>
     20-day win rate ${t3?.horizons?.["20d"]?.win_rate||"?"}%, slightly below baseline (essentially neutral)<br><br>
     <span style="color:var(--muted);font-size:0.79rem">
       ${calInsight}<br>
       The "Tier ≥4 entry only" strategy: 20-day win rate ${s4.win_rate_20d||"?"}% vs ${s4.baseline_win_rate||"?"}% for buying anytime,
       p=${s4.p_value||"?"}${s4SigStr}. Absolute gap +${s4.diff||"?"}pp.
     </span>` : `
     <strong>历史回测结论（2000-2026，${SIGNALS.backtest?.NASDAQ?.baseline?.["20d"]?.n ?? Object.values(SIGNALS.daily_signals).length}个交易日）：</strong><br><br>
     <span style="color:#2ecc71">▲ 第4档信号（≥60%，n=${t4?.n||0}天）：</span>
     20日实际胜率 <strong style="color:#2ecc71">${t4?.horizons?.["20d"]?.win_rate||"?"}%</strong>，
     高于全样本基准 ${base20}%（+${t4?.horizons?.["20d"]?.diff_vs_baseline||"?"}pp），
     <strong>p=${t4?.horizons?.["20d"]?.p_value||"?"}</strong>${sig4?" ✓统计显著":""}<br>
     <span style="color:#e74c3c">▼ 第2档信号（≤40%，n=${t2?.n||0}天）：</span>
     5日胜率仅 <strong style="color:#e74c3c">${t2?.horizons?.["5d"]?.win_rate||"?"}%</strong>，
     远低于基准（${t2?.horizons?.["5d"]?.diff_vs_baseline||"?"}pp），
     <strong>p=${t2?.horizons?.["5d"]?.p_value||"?"}</strong>${sig2?" ✓统计显著":""}<br>
     <span style="color:#f1c40f">△ 第3档信号：</span>
     20日胜率 ${t3?.horizons?.["20d"]?.win_rate||"?"}%，略低于基准（几乎中性）<br><br>
     <span style="color:var(--muted);font-size:0.79rem">
       ${calInsight}<br>
       「仅Tier≥4入场」策略 20日胜率 ${s4.win_rate_20d||"?"}% vs 随时买入 ${s4.baseline_win_rate||"?"}%，
       p=${s4.p_value||"?"}${s4SigStr}。绝对差距 +${s4.diff||"?"}pp。
     </span>`;
}

// ── 信号解读 ──
// adjustedProb: pass event-adjusted probability from updateSignal so the box stays in sync
function renderTodayRec(adjustedProb) {
  const el = document.getElementById("today-rec");
  if (!el || !SIGNALS) return;
  const dateStr = selectedDate || localDateStr();
  const isFuture = dateStr > localDateStr();
  let prob, tierNum, isForecast = false;

  if (isFuture) {
    const allFc = SIGNALS.next_opportunities?.all_forecast || [];
    const fc = allFc.find(d => d.date === dateStr) ||
               (allFc.length ? allFc.reduce((best, d) =>
                 Math.abs(new Date(d.date) - new Date(dateStr)) <
                 Math.abs(new Date(best.date) - new Date(dateStr)) ? d : best, allFc[0]) : null);
    if (!fc) { el.innerHTML = ""; return; }
    prob = adjustedProb !== undefined ? adjustedProb : fc.prob;
    isForecast = true;
  } else {
    const rec = SIGNALS.daily_signals?.[dateStr];
    if (!rec) { el.innerHTML = ""; return; }
    prob = adjustedProb !== undefined ? adjustedProb : rec.prob;
  }

  // 模型无样本外区分度时，不输出"档位/买卖"建议——否则与中性信号环自相矛盾
  if (SIGNALS.calibration_flat) {
    const br = Math.round((SIGNALS.base_rate_20d ?? 0.62) * 100);
    el.innerHTML = vpLang() === "en" ? `
      <div style="background:rgba(241,196,15,.07);border:1px solid #f1c40f44;border-radius:8px;padding:.85rem 1rem;">
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.3rem;">Signal read</div>
        <div style="font-size:1.05rem;font-weight:700;color:#f1c40f">⏸ No out-of-sample edge · tier suppressed</div>
        <div style="font-size:0.8rem;color:var(--text);margin-top:.4rem;line-height:1.55">
          Walk-forward block-bootstrap validation found no out-of-sample discriminative power for this signal — the 20-day up-probability on any given day is ≈ the base rate of ${br}%.
          This is an experimental research tool and does not constitute market-timing advice.</div>
      </div>` : `
      <div style="background:rgba(241,196,15,.07);border:1px solid #f1c40f44;border-radius:8px;padding:.85rem 1rem;">
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.3rem;">信号解读</div>
        <div style="font-size:1.05rem;font-weight:700;color:#f1c40f">⏸ 无样本外优势 · 不输出档位</div>
        <div style="font-size:0.8rem;color:var(--text);margin-top:.4rem;line-height:1.55">
          walk-forward 块自助验证未发现该信号有样本外区分度——任意一天的 20 日上涨概率都≈基率 ${br}%。
          这是实验性研究工具，不构成择时建议。</div>
      </div>`;
    return;
  }

  tierNum = tier(prob);

  const map = {
    5: { color:"#27ae60", bg:"rgba(39,174,96,.12)", icon:"🟢",
         action: vpL("倾向积极（信号偏多）","Leaning positive (bullish tilt)"),
         desc: vpL("多重指标全面支撑，历史最强信号组合。当前处于信号最强档。",
                    "Broad support across multiple indicators — historically the strongest signal combination. Currently in the strongest tier.") },
    4: { color:"#2ecc71", bg:"rgba(46,204,113,.09)", icon:"✅",
         action: vpL("偏向乐观","Leaning optimistic"),
         desc: vpL("信号偏多，多数支撑指标指向正面。属信号偏强档。",
                    "Signal tilts bullish; most supporting indicators point positive. A stronger-than-average tier.") },
    3: { color:"#f1c40f", bg:"rgba(241,196,15,.09)", icon:"⏸",
         action: vpL("中性观望","Neutral / wait-and-see"),
         desc: vpL("信号中性，多空力量大致均衡、方向性不明确。历史上此档位缺乏统计优势。",
                    "Signal is neutral — bullish and bearish forces are roughly balanced with no clear direction. Historically this tier has shown no statistical edge.") },
    2: { color:"#e67e22", bg:"rgba(230,126,34,.09)", icon:"⚠️",
         action: vpL("偏向谨慎","Leaning cautious"),
         desc: vpL("偏空信号，负面因素略占上风。属信号偏弱档。",
                    "Signal tilts bearish; negative factors slightly outweigh positive ones. A weaker-than-average tier.") },
    1: { color:"#e74c3c", bg:"rgba(231,76,60,.09)", icon:"🔴",
         action: vpL("信号偏防御","Defensive-leaning signal"),
         desc: vpL("信号极弱，多重负面因素叠加，历史最弱信号组合。属信号最弱档。",
                    "Signal is very weak, with multiple negative factors stacking up — historically the weakest signal combination. Currently in the weakest tier.") },
  };
  const c = map[tierNum] || map[3];
  const tag = isForecast ? `<span style="color:var(--muted);font-size:0.72rem">${vpL("（预测）"," (forecast)")}</span>` : "";
  el.innerHTML = `
    <div style="background:${c.bg};border:1px solid ${c.color}55;border-radius:8px;padding:.85rem 1rem;">
      <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.3rem;">${vpL("信号解读","Signal read")}${tag}</div>
      <div style="font-size:1.05rem;font-weight:700;color:${c.color}">${c.icon} ${vpL(`第${tierNum}档`, `Tier ${tierNum}`)} · ${c.action}</div>
      <div style="font-size:0.8rem;color:var(--text);margin-top:.4rem;line-height:1.55">${c.desc}</div>
      <div style="font-size:0.72rem;color:var(--muted);margin-top:.4rem">${vpL(`上涨概率 ${Math.round(prob*100)}% · 仅供参考，不构成投资建议`, `Up-probability ${Math.round(prob*100)}% · reference only, not investment advice`)}</div>
    </div>`;
}

// ── 未来40天信号热力横带（D3任务1：原40格大网格 → 单行紧凑热带）──────
// 数据/交互状态：按 date 索引缓存最新一次 all_forecast，供 tooltip/键盘/点击复用。
let _fcDataByDate = {};
let _fcTipOpenDate = null;   // 当前打开 tooltip 的日期；null=未打开
let _fcTipEl = null;         // 单例 tooltip div（复用，不每次新建）

function _fcTooltip() {
  if (_fcTipEl && document.body.contains(_fcTipEl)) return _fcTipEl;
  _fcTipEl = document.createElement("div");
  _fcTipEl.id = "fc-tooltip";
  _fcTipEl.setAttribute("role", "tooltip");
  _fcTipEl.style.cssText = "position:fixed;z-index:400;display:none;background:var(--surface2);"
    + "border:1px solid var(--border);border-radius:7px;padding:.5rem .75rem;font-size:0.76rem;"
    + "line-height:1.5;max-width:260px;box-shadow:0 4px 16px rgba(0,0,0,.4);color:var(--text);pointer-events:none;";
  document.body.appendChild(_fcTipEl);
  return _fcTipEl;
}

// 宏观事件/入场理由字符串 → 英文。数据来自 build_signals.py 固定的几类模式（正则匹配日期/月份变量，
// 不是硬编码某一天）；未识别的新事件类型诚实展示原文，好过瞎译。
const _FC_DOW_EN = { "周一":"Mon","周二":"Tue","周三":"Wed","周四":"Thu","周五":"Fri","周六":"Sat","周日":"Sun" };
function _fcMacroEN(zh) {
  if (!zh) return zh;
  let m;
  if ((m = zh.match(/^CPI发布\((\d+)月\)$/)))     return `CPI release (month ${m[1]})`;
  if ((m = zh.match(/^非农就业\((\d+)月\)$/)))     return `Non-farm payrolls (month ${m[1]})`;
  if ((m = zh.match(/^FOMC决议(\(含SEP\))?$/)))    return m[1] ? "FOMC decision (with SEP)" : "FOMC decision";
  return zh;
}
function _fcReasonEN(zh) {
  let m;
  if ((m = zh.match(/^(周[一二三四五六日])效应$/)))  return `${_FC_DOW_EN[m[1]] || m[1]} effect`;
  if ((m = zh.match(/^月内第(\d)周最强$/)))          return `Week ${m[1]} of month historically strongest`;
  if ((m = zh.match(/^月内第(\d)周偏弱$/)))          return `Week ${m[1]} of month tends weak`;
  if (zh === "假日效应")                              return "Holiday effect";
  if (zh === "税季/季初建仓")                         return "Tax season / quarter-start positioning";
  if (zh === "税损收割期")                            return "Tax-loss harvesting period";
  if ((m = zh.match(/^(\d+)月胜率高$/)))             return `Month ${m[1]} historically high win rate`;
  if ((m = zh.match(/^(\d+)月胜率低$/)))             return `Month ${m[1]} historically low win rate`;
  if ((m = zh.match(/^⚠ (.+?)·波动放大$/)))          return `⚠ ${_fcMacroEN(m[1])} · volatility likely elevated`;
  return zh;
}
function _fcTooltipText(d) {
  const [y, mo, day] = d.date.split("-").map(Number);
  const dow = new Date(y, mo - 1, day).getDay();
  const DOW = vpL(["周日","周一","周二","周三","周四","周五","周六"], ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]);
  const TIER_NAME = vpL({5:"第5档",4:"第4档",3:"第3档",2:"第2档",1:"第1档"}, {5:"Tier 5",4:"Tier 4",3:"Tier 3",2:"Tier 2",1:"Tier 1"});
  const isEN = vpLang() === "en";
  let line1 = `${d.date} ${DOW[dow]} · ${vpL("概率","Prob")} ${Math.round(d.prob*100)}% · ${TIER_NAME[d.tier]}`;
  if (d.macro) line1 += ` · ${isEN ? _fcMacroEN(d.macro) : d.macro}`;
  let line2 = "";
  if (d.reasons && d.reasons.length) {
    // 优先用后端 reasons_en(单一来源、随条件同步);无则退回前端正则翻译 _fcReasonEN(旧兜底)
    const joined = (isEN && d.reasons_en && d.reasons_en.length)
      ? d.reasons_en.join(", ")
      : d.reasons.map(r => isEN ? _fcReasonEN(r) : r).join(isEN ? ", " : "、");
    line2 = joined.length > 60 ? joined.slice(0, 60) + "…" : joined;
  }
  return { line1, line2 };
}

function _fcTipShow(cellEl, d) {
  if (!d) return;
  const tip = _fcTooltip();
  const { line1, line2 } = _fcTooltipText(d);
  tip.innerHTML = `<div>${esc(line1)}</div>${line2 ? `<div style="color:var(--muted);margin-top:.2rem;">${esc(line2)}</div>` : ""}`;
  tip.style.visibility = "hidden";
  tip.style.display = "block";
  const r = cellEl.getBoundingClientRect();
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let left = r.left + r.width / 2 - tw / 2;
  left = Math.max(6, Math.min(left, window.innerWidth - tw - 6));
  let top = r.top - th - 8;
  if (top < 4) top = r.bottom + 8;   // 上方放不下(靠近视口顶部)→翻到下方，防溢出
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
  tip.style.visibility = "visible";
  _fcTipOpenDate = d.date;
  cellEl.setAttribute("aria-expanded", "true");
}
function _fcTipHide() {
  if (_fcTipEl) _fcTipEl.style.display = "none";
  if (_fcTipOpenDate) {
    document.querySelector(`.fc-cell[data-fc-date="${_fcTipOpenDate}"]`)?.removeAttribute("aria-expanded");
  }
  _fcTipOpenDate = null;
}
// 点击/回车激活一个热带 cell：
//   首次激活 → 只显示 tooltip 预览(不跳转，桌面 hover 已先显示过，此时视为"已打开")
//   已打开时再次激活(桌面：hover 后单击一次即触发；移动：再 tap 一次) → 收起 tooltip + 复用原
//   "选中该日→今日建议面板并滚动" 功能(原 data-forecast-date 单击行为，保留不丢)
function _fcCellActivate(cellEl) {
  const date = cellEl.dataset.fcDate;
  if (_fcTipOpenDate === date) {
    _fcTipHide();
    if (typeof selectForecastDay === "function") selectForecastDay(date);
  } else {
    _fcTipShow(cellEl, _fcDataByDate[date]);
  }
}
// 用 Pointer Events(按 pointerType 过滤) 而非 mouseover/mouseout：触屏 tap 时浏览器会在真正
// 派发 click 之前合成一次 mouseover 做兼容("鬼影 hover")，若监听 mouseover 会导致 tap 还没
// 落地 tooltip 就已"预打开"——第一下 tap 的 click 因此误判成"已打开"，直接收起+跳转，
// 出现"tap一下tooltip一闪就没了"。pointerType==="mouse" 只让真鼠标触发预览，触屏交互交给
// click 委托的 _fcCellActivate(首tap开·再tap关)独立处理，互不干扰。
document.addEventListener("pointerover", e => {
  if (e.pointerType !== "mouse") return;
  const cell = e.target.closest(".fc-cell");
  if (cell) _fcTipShow(cell, _fcDataByDate[cell.dataset.fcDate]);
});
document.addEventListener("pointerout", e => {
  if (e.pointerType !== "mouse") return;
  if (e.target.closest(".fc-cell")) _fcTipHide();
});
document.addEventListener("click", e => {
  const cell = e.target.closest(".fc-cell");
  if (cell) { _fcCellActivate(cell); return; }
  if (_fcTipOpenDate) _fcTipHide();   // 点击热带外部 → 收起(不 return，不影响其它委托点击逻辑)
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { if (_fcTipOpenDate) _fcTipHide(); return; }
  if (e.key !== "Enter" && e.key !== " ") return;
  const cell = e.target.closest(".fc-cell");
  if (cell) { e.preventDefault(); _fcCellActivate(cell); }
});

function renderForecastCalendar() {
  const el = document.getElementById("forecast-calendar");
  if (!el || !SIGNALS) return;
  const allFc = SIGNALS.next_opportunities?.all_forecast || [];
  if (!allFc.length) { el.innerHTML = `<span style="color:var(--muted);font-size:0.82rem">${vpL("暂无预测数据","No forecast data yet")}</span>`; return; }

  const TC = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };

  // 档位分布（顶部结论 + 底部统计条共用，别算两遍）
  const strong = allFc.filter(d => d.tier >= 4).length;
  const weak   = allFc.filter(d => d.tier <= 2).length;
  const neut   = allFc.length - strong - weak;

  const sorted = [...allFc].sort((a, b) => a.date.localeCompare(b.date));
  _fcDataByDate = {};
  sorted.forEach(d => { _fcDataByDate[d.date] = d; });

  const today = localDateStr();
  let html = "";
  // 结论抬头：仅当 40 天全落中性档（无强/弱分化，即 calibration_flat 的数据表现）才加——
  // 区间从 min/max prob 四舍五入算出，不硬编码，档位有分化时不写这句（别写死判断）
  if (strong === 0 && weak === 0) {
    const probs = allFc.map(d => d.prob);
    const lo = Math.round(Math.min(...probs) * 100);
    const hi = Math.round(Math.max(...probs) * 100);
    html += `<div class="insight" style="margin-bottom:.75rem;">
      <strong>${vpL("结论：","Conclusion: ")}</strong>${vpL(
        `未来 ${allFc.length} 天没有统计上更该买的某一天——概率全挤在 ${lo}–${hi}%（样本外校准平坦，无择时优势）。这本身就是结果：别靠"挑日子"。`,
        `None of the next ${allFc.length} trading days is statistically more worth buying — probabilities all cluster in ${lo}–${hi}% (out-of-sample calibration is flat, no timing edge). That itself is the finding: don't try to "pick the day."`
      )}</div>`;
  }
  // Legend
  html += `<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:.5rem;font-size:0.72rem;">
    <span style="color:var(--muted)">${vpL("颜色说明：","Color key:")}</span>
    <span><span style="color:#2ecc71">■</span> ${vpL("偏强信号(T4-5)","Strong-leaning (T4-5)")}</span>
    <span><span style="color:#f1c40f">■</span> ${vpL("中性观望(T3)","Neutral (T3)")}</span>
    <span><span style="color:#e74c3c">■</span> ${vpL("偏弱谨慎(T1-2)","Weak-leaning (T1-2)")}</span>
    <span style="color:var(--muted)">${vpL("· 今日有发光边框 · 悬停/点按查看详情","· Today has a glowing border · hover/tap for details")}</span>
  </div>`;

  // 热力横带：40 个 cell 等分一行，不放文字(拥挤放不下)，靠 tooltip 传递细节
  html += `<div class="fc-band" style="display:flex;gap:2px;width:100%;">`;
  sorted.forEach(d => {
    const isToday = d.date === today;
    const color = TC[d.tier] || "#8b949e";
    const border = isToday ? `2px solid ${color}` : `1px solid ${color}66`;
    const { line1, line2 } = _fcTooltipText(d);
    const ariaLabel = line2 ? `${line1} · ${line2}` : line1;
    html += `<div class="fc-cell" role="button" tabindex="0" data-fc-date="${d.date}"
      aria-label="${esc(ariaLabel)}"
      style="flex:1;min-width:0;height:26px;border-radius:3px;background:${color};border:${border};cursor:pointer;
             ${isToday ? `box-shadow:0 0 0 3px ${color}66;` : ""}"></div>`;
  });
  html += `</div>`;

  html += `<div style="font-size:0.75rem;color:var(--muted);margin-top:.6rem;display:flex;gap:1rem;flex-wrap:wrap;">
    <span>${vpL(`共 ${allFc.length} 个交易日`, `${allFc.length} trading days total`)}</span>
    <span style="color:#2ecc71">${vpL(`强势: ${strong}天`, `Strong: ${strong}d`)}</span>
    <span style="color:#f1c40f">${vpL(`中性: ${neut}天`, `Neutral: ${neut}d`)}</span>
    <span style="color:#e74c3c">${vpL(`偏弱: ${weak}天`, `Weak: ${weak}d`)}</span>
  </div>`;

  el.innerHTML = html;
  if (_fcTipOpenDate) _fcTipHide();   // 重渲染(如切语言/刷新)时旧 tooltip 引用的 DOM 节点已失效，先收起防悬空
}

// ── 今日页前瞻小条（紧凑条，指向📅买卖时机页完整日历）──
// 数据同源 renderForecastCalendar：SIGNALS.next_opportunities.all_forecast。
// 缺数据→整条隐藏，不显示空壳；全中性(calibration_flat 的数据表现)时不装作有档位差异。
function renderForecastStrip() {
  const el = document.getElementById("forecast-strip");
  if (!el) return;
  const allFc = SIGNALS?.next_opportunities?.all_forecast || [];
  if (!SIGNALS || !allFc.length) { el.style.display = "none"; return; }

  const strong = allFc.filter(d => d.tier >= 4).length;
  const weak   = allFc.filter(d => d.tier <= 2).length;
  const neut   = allFc.length - strong - weak;

  let msg;
  if (strong === 0 && weak === 0) {
    // 区间从 min/max prob 四舍五入算出，别硬编码
    const probs = allFc.map(d => d.prob);
    const lo = Math.round(Math.min(...probs) * 100);
    const hi = Math.round(Math.max(...probs) * 100);
    msg = vpL(
      `未来${allFc.length}个交易日买入概率全在中性档（${lo}–${hi}%）——没有统计上更该买的某一天`,
      `All ${allFc.length} upcoming trading days sit in the neutral tier (${lo}–${hi}%) — no single day is statistically more worth buying`
    );
  } else {
    const best = SIGNALS.next_opportunities?.top_entry?.[0] ||
                 allFc.reduce((b, d) => d.prob > b.prob ? d : b, allFc[0]);
    msg = vpL(
      `未来${allFc.length}个交易日：${strong}天强势 / ${neut}天中性 / ${weak}天偏弱 · 最高 ${best.date} ${Math.round(best.prob*100)}%`,
      `Next ${allFc.length} trading days: ${strong}d strong / ${neut}d neutral / ${weak}d weak · peak ${best.date} ${Math.round(best.prob*100)}%`
    );
  }

  el.style.display = "";
  el.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;">
      <div style="font-size:0.82rem;color:var(--text);">📅 ${msg}</div>
      <button type="button" onclick="switchView('plan')"
        style="background:var(--surface2);border:1px solid var(--border);color:var(--blue);
               padding:.35rem .85rem;border-radius:16px;font-size:0.78rem;cursor:pointer;
               white-space:nowrap;font-family:inherit;">${vpL("看完整日历 →","See full calendar →")}</button>
    </div>`;
}

// ── 重要经济日历 ──
function renderEconCalendar() {
  const el = document.getElementById("econ-calendar-list");
  if (!el) return;
  const today = localDateStr();
  // 特殊事件（手工维护）
  const events = [
    { date:"2026-06-11", emoji:"⚽", label: vpL("世界杯开幕","World Cup opening"), type:"event",
      note: vpL("美/加/墨主办，Fox Corp受益","Hosted by US/Canada/Mexico; Fox Corp benefits") },
    { date:"2026-06-12", emoji:"🚀", label: vpL("SpaceX SPCX 上市","SpaceX (SPCX) IPO"), type:"ipo",
      note: vpL("Nasdaq，发行价US$135，通过CommSec","Nasdaq, IPO price US$135, via CommSec") },
    { date:"2026-07-02", emoji:"📊", label: vpL("6月非农就业数据","June non-farm payrolls"), type:"nfp",
      note: vpL("超预期→加息压力→短期利空","Beat expectations → rate-hike pressure → short-term headwind") },
    { date:"2026-07-19", emoji:"⚽", label: vpL("世界杯决赛","World Cup final"), type:"event",
      note: vpL("冠军国股市往往短暂上涨","Champion nation's stock market often sees a brief rally") },
  ];
  // 官方宏观日历（CPI/FOMC，来自 signals.json，由 BLS/Fed 日程生成）
  (SIGNALS?.macro_calendar || []).forEach(m => {
    const isCpi = m.label.includes("CPI");
    events.push({
      date: m.date,
      emoji: isCpi ? "📊" : "🏦",
      label: m.label,
      type: isCpi ? "cpi" : "fed",
      note: isCpi ? vpL("美东8:30发布·当日波动放大","Released 8:30am ET · intraday volatility spikes")
                   : vpL("美东14:00决议·当日波动放大","Decision at 2:00pm ET · intraday volatility spikes"),
    });
  });
  events.sort((a, b) => a.date.localeCompare(b.date));
  const typeColor = { ipo:"#2ecc71", fed:"#3498db", nfp:"#e67e22", cpi:"#e67e22", event:"#9b59b6" };
  const upcoming = events.filter(e => e.date >= today).slice(0, 6);
  el.innerHTML = upcoming.map(e => {
    const diff = Math.round((new Date(e.date) - new Date(today)) / 86400000);
    const urgency = diff <= 3 ? "#e74c3c" : diff <= 7 ? "#e67e22" : "var(--muted)";
    const diffLabel = diff === 0 ? vpL("今天","Today") : diff === 1 ? vpL("明天","Tomorrow") : vpL(`${diff}天后`, `in ${diff}d`);
    return `<div style="display:flex;align-items:flex-start;gap:.6rem;padding:.4rem 0;border-bottom:1px solid var(--border-faint);">
      <span style="font-size:1rem;flex-shrink:0">${e.emoji}</span>
      <div style="flex:1;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:600;color:${typeColor[e.type]||"var(--text)"}">${e.label}</span>
          <span style="color:${urgency};font-size:0.72rem;font-weight:700;flex-shrink:0">${diffLabel}</span>
        </div>
        <div style="color:var(--muted);font-size:0.72rem">${e.date}${e.note ? " · " + e.note : ""}</div>
      </div>
    </div>`;
  }).join("") || `<div style="color:var(--muted);font-size:0.8rem">${vpL("近期无重要事件","No major events upcoming")}</div>`;
}

// ── 我的持仓计算器 ──
const PORTFOLIO_KEY = "alpha_portfolio_v2";
const COIN_IDS = { BTC:"bitcoin", ETH:"ethereum", XLM:"stellar", DOGE:"dogecoin", HOME:"home", SOL:"solana", BNB:"binancecoin" };
let portfolioPrices = {};
function escPortfolio(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function loadPortfolio() {
  try { return JSON.parse(localStorage.getItem(PORTFOLIO_KEY)) || defaultPortfolio(); }
  catch { return defaultPortfolio(); }
}
function savePortfolio(p) { localStorage.setItem(PORTFOLIO_KEY, JSON.stringify(p)); }
function defaultPortfolio() {
  return [
    { ticker:"BTC",  qty:0.002,    priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"ETH",  qty:0.0103,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"XLM",  qty:503.78,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"DOGE", qty:1360.5,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"HOME", qty:100,      priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"SPCX", qty:0,        priceUSD:135,  costUSD:135,   type:"stock",  note: vpL("IPO发行价US$135","IPO price US$135") },
  ];
}

let _portAudRate = 0.71;

function renderPortfolioTable(audRate) {
  if (audRate && audRate > 0) _portAudRate = audRate;
  const port = loadPortfolio();
  const body = document.getElementById("portfolio-body");
  const foot = document.getElementById("portfolio-foot");
  if (!body) return;
  let total = 0, totalCost = 0;
  body.innerHTML = port.map((item, i) => {
    const rawPrice = portfolioPrices[item.ticker] ?? item.priceUSD;
    const p = Number.isFinite(Number(rawPrice)) ? Number(rawPrice) : null;
    const qty = Number.isFinite(Number(item.qty)) ? Number(item.qty) : 0;
    const pAUD = p && _portAudRate ? p / _portAudRate : null;
    const val = pAUD ? qty * pAUD : null;
    if (val) total += val;
    // P&L
    const costUSD = Number.isFinite(Number(item.costUSD)) ? Number(item.costUSD) : null;
    const costAUD = (costUSD && _portAudRate) ? (costUSD / _portAudRate * qty) : null;
    if (costAUD) totalCost += costAUD;
    const plAUD = (val && costAUD) ? val - costAUD : null;
    const plPct = (plAUD != null && costAUD > 0) ? plAUD / costAUD * 100 : null;
    const plStr = qty <= 0 ? "" :
      plAUD != null
      ? `<br><span class="${plAUD >= 0 ? 'pl-up' : 'pl-dn'}">${plAUD >= 0 ? '+' : ''}A$${plAUD.toFixed(0)} (${plPct >= 0 ? '+' : ''}${(plPct||0).toFixed(1)}%)</span>`
      : `<br><span class="cost-link" role="button" tabindex="0" data-cost-index="${i}">${vpL("设置成本价","Set cost basis")}</span>`;
    const valStr = val ? `A$${val.toFixed(2)}` : "—";
    const pStr  = p   ? `$${p < 1 ? p.toFixed(4) : p.toFixed(2)}` : "—";
    const ticker = escPortfolio(item.ticker);
    const note = item.note ? escPortfolio(item.note) : "";
    return `<tr style="border-bottom:1px solid var(--border-faint);">
      <td style="padding:.35rem .4rem;font-weight:600;color:var(--text)">${ticker}${note?`<br><span style="font-size:0.68rem;color:var(--muted);font-weight:400">${note}</span>`:""}</td>
      <td style="text-align:right;padding:.35rem .4rem;color:var(--muted)">${qty}</td>
      <td style="text-align:right;padding:.35rem .4rem">${pStr}</td>
      <td style="text-align:right;padding:.35rem .4rem;font-weight:600;color:${val?'var(--green)':'var(--muted)'}">${valStr}${plStr}</td>
    </tr>`;
  }).join("");
  const plTotal = (total > 0 && totalCost > 0) ? total - totalCost : null;
  const plTotalPct = plTotal != null && totalCost > 0 ? plTotal / totalCost * 100 : null;
  const plTotalStr = plTotal != null
    ? `<span class="${plTotal >= 0 ? 'pl-up' : 'pl-dn'}" style="font-size:0.8rem;margin-left:.5rem">${plTotal >= 0 ? '+' : ''}A$${plTotal.toFixed(0)} (${plTotalPct >= 0 ? '+' : ''}${(plTotalPct||0).toFixed(1)}%)</span>` : "";
  foot.innerHTML = total > 0 ? `<tr style="border-top:1px solid var(--border);">
    <td colspan="3" style="padding:.4rem;font-weight:700;color:var(--muted)">${vpL("总计","Total")}</td>
    <td style="text-align:right;padding:.4rem;font-weight:800;font-size:1rem;color:var(--green)">A$${total.toFixed(2)}${plTotalStr}</td>
  </tr>` : "";

  // Signal overlay
  const sigEl = document.getElementById("portfolio-signal");
  if (sigEl && SIGNALS) {
    const t = SIGNALS.latest_tier || 3;
    const tColor = {5:"#27ae60",4:"#2ecc71",3:"#f1c40f",2:"#e67e22",1:"#e74c3c"};
    const tText  = vpL(
      {5:"信号最强档",4:"信号偏强",3:"中性观望",2:"信号偏弱",1:"信号最弱档"},
      {5:"Strongest tier",4:"Signal tilts strong",3:"Neutral / wait-and-see",2:"Signal tilts weak",1:"Weakest tier"}
    );
    sigEl.innerHTML = `<div style="font-size:0.78rem;color:var(--muted);">${vpL(`当前信号第${t}档 →`, `Current signal: Tier ${t} →`)}
      <strong style="color:${tColor[t]||"#f1c40f"}">${tText[t]||vpL("观望","Neutral")}</strong></div>`;
  }
}

function setPortfolioCost(i) {
  const port = loadPortfolio();
  const item = port[i];
  if (!item) return;
  const fallback = item.costUSD ?? item.priceUSD ?? portfolioPrices[item.ticker] ?? "";
  const input = prompt(vpL(`设置 ${item.ticker || "资产"} 的 USD 成本价`, `Set USD cost basis for ${item.ticker || "asset"}`), fallback);
  if (input === null) return;
  const cost = Number(input);
  if (!Number.isFinite(cost) || cost <= 0) {
    alert(vpL("请输入有效的正数成本价。","Please enter a valid positive cost price."));
    return;
  }
  item.costUSD = cost;
  savePortfolio(port);
  renderPortfolioTable(_portAudRate);
}

async function fetchPortfolioPrices() {
  const btn = document.getElementById("portfolio-refresh-btn");
  if (btn) btn.textContent = vpL("⏳ 获取中...","⏳ Fetching...");
  try {
    // 优先用同源 quotes.json（服务端 quick_quotes 抓的 CoinGecko）——中国访客不必直连境外 API
    if (typeof loadQuotes === "function") { try { await loadQuotes(); } catch (e) { /* 用已有 QUOTES */ } }
    let crypto = QUOTES?.crypto, audRate = QUOTES?.aud_rate, src = vpL("同源","same-origin");
    if (!crypto || !Object.keys(crypto).length) {
      // 兜底：直连 CoinGecko（境外，可能 CORS/被墙；仅当同源缺失时）
      const ids = Object.values(COIN_IDS).join(",");
      const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd,aud`);
      const data = await r.json();
      crypto = {}; src = vpL("直连","direct");
      Object.entries(COIN_IDS).forEach(([ticker, id]) => {
        if (data[id]?.usd) crypto[ticker] = data[id].usd;
        if (!audRate && data[id]?.usd && data[id]?.aud) audRate = data[id].usd / data[id].aud;
      });
    }
    Object.assign(portfolioPrices, crypto);
    const updEl = document.getElementById("portfolio-updated");
    if (updEl) updEl.textContent = `1 AUD ≈ US$${audRate ? audRate.toFixed(4) : "?"}${vpL(`（${src}报价）`, ` (${src} quote)`)}`;
    renderPortfolioTable(audRate || 0.71);
    renderSPCXTracker();
    updateSPCXCalc();
  } catch (e) {
    console.warn("Portfolio price fetch failed:", e);
    renderPortfolioTable(0.71);
  } finally {
    if (btn) btn.textContent = vpL("🔄 更新价格","🔄 Update prices");
  }
}

// ── 大跌抄底指南 ──
function renderDipGuide() {
  const dipEl = document.getElementById("chart-dip-recovery");
  const vixEl = document.getElementById("chart-vix-entry");
  if (!dipEl || !vixEl) return;

  // S&P 500历史跌幅→恢复天数（1928-2026统计）
  const dipData = [
    { drop:"-5%",   days:22,  n:94 }, { drop:"-10%",  days:115, n:47 },
    { drop:"-15%",  days:130, n:28 }, { drop:"-20%",  days:280, n:19 },
    { drop:"-30%",  days:450, n:11 }, { drop:"-40%+", days:700, n:6  },
  ];
  const dipColors = dipData.map(d => d.days < 100 ? "#2ecc71" : d.days < 300 ? "#f1c40f" : "#e74c3c");
  Plotly.newPlot(dipEl, [{
    type:"bar", x:dipData.map(d=>d.drop), y:dipData.map(d=>d.days),
    marker:{color:dipColors},
    text:dipData.map(d=> vpL(`${d.days}天<br>n=${d.n}次`, `${d.days}d<br>n=${d.n}`)),
    textposition:"outside", cliponaxis:false,
    hovertemplate: vpL("<b>%{x}</b><br>平均恢复 %{y} 天<extra></extra>","<b>%{x}</b><br>avg recovery %{y} days<extra></extra>"),
  }], {
    ...DARK, margin:{t:10,b:40,l:45,r:10},
    // y 轴顶部留 18% 余量，给最高柱(700天)的 outside 文字留位置
    yaxis:{...DARK.yaxis, title: vpL("平均恢复天数","Average recovery days"), range:[0, 700*1.18]},
    // 必须强制分类轴："-5%" 会被 Plotly 自动当数字解析（parseFloat 截断），
    // "-40%+" 解析失败 → 整根柱子凭空消失 + translate(NaN) 报错
    xaxis:{...DARK.xaxis, type:"category"},
  }, {responsive:true});

  // VIX水平→未来3个月胜率
  const vixData = [
    { range:"< 15",   wr:52, label:"过度乐观" }, { range:"15-20", wr:58, label:"正常" },
    { range:"20-30",  wr:65, label:"担忧"     }, { range:"30-40", wr:78, label:"恐慌" },
    { range:"> 40",   wr:89, label:"极度恐慌" },
  ];
  const vixColors = vixData.map(d => d.wr >= 75 ? "#27ae60" : d.wr >= 65 ? "#2ecc71" : d.wr >= 58 ? "#f1c40f" : "#e67e22");
  Plotly.newPlot(vixEl, [{
    type:"bar", x:vixData.map(d=>d.range), y:vixData.map(d=>d.wr),
    marker:{color:vixColors},
    text:vixData.map(d=>`${d.wr}%`),
    textposition:"outside", cliponaxis:false,
    hovertemplate: vpL("<b>VIX %{x}</b><br>3月胜率 %{y}%<extra></extra>","<b>VIX %{x}</b><br>3-month win rate %{y}%<extra></extra>"),
  }], {
    ...DARK, margin:{t:10,b:40,l:40,r:10},
    yaxis:{...DARK.yaxis, title: vpL("3个月胜率%","3-month win rate %"), range:[45,100]},
    xaxis:{...DARK.xaxis, type:"category"},   // "15-20" 会被自动解析成数字 15，同 dip 图
    shapes:[{type:"line",x0:-0.5,x1:4.5,y0:58,y1:58,line:{color:"#555",dash:"dot",width:1}}],
  }, {responsive:true});

  document.getElementById("dip-insight").innerHTML = vpL(
    `<div style="color:var(--muted);font-size:0.72rem;margin-bottom:.35rem">以下为历史统计描述 · 非操作建议 · 见🪦坟场</div>
     <strong>历史统计规律：</strong>跌幅越大、VIX越高，历史胜率越高，但恢复时间也越长。<br>
     <span style="color:#27ae60">VIX > 30</span>（历史高恐慌区），3个月胜率达 <strong>78%+</strong>；
     <span style="color:#f1c40f">VIX < 15</span>（现在）市场过于乐观，历史该区间胜率较低，属<strong>偏弱窗口</strong>。<br>
     <span style="color:var(--muted);font-size:0.78rem">数据来源：S&P 500 1928-2026历史统计，非投资建议。</span>`,
    `<div style="color:var(--muted);font-size:0.72rem;margin-bottom:.35rem">The following is a historical statistical description · not a trading recommendation · see the 🪦 graveyard</div>
     <strong>Historical statistical pattern:</strong> the bigger the drop and the higher the VIX, the higher the historical win rate — but the longer the recovery time too.<br>
     <span style="color:#27ae60">VIX > 30</span> (historically extreme panic), 3-month win rate reaches <strong>78%+</strong>;
     <span style="color:#f1c40f">VIX < 15</span> (current) the market is overly optimistic — historically this range shows a lower win rate, a <strong>weak-leaning window</strong>.<br>
     <span style="color:var(--muted);font-size:0.78rem">Data source: S&P 500, 1928-2026 historical stats — not investment advice.</span>`
  );
}

// ── 市场情绪仪表盘 ──
function renderSentimentPanel() {
  const el = document.getElementById("sentiment-gauges");
  if (!el || !SIGNALS) return;
  const tech = SIGNALS.next_opportunities?.latest_tech || {};

  // VIX: use VIX from daily_signals (latest available) or fallback
  const allDays = SIGNALS.daily_signals || {};
  const latestKey = Object.keys(allDays).sort().pop();
  // nasdaq_vol is annualized realized vol; derive a rough VIX proxy
  // We store actual VIX in prices.json; use latest_tech nasdaq_vol as proxy if no direct VIX
  const nasVol  = tech.nasdaq_vol;  // e.g. 0.0916 = 9.16% 20-day realized vol
  const rsi     = tech.nasdaq_rsi;  // e.g. 77.1
  const btcMom  = tech.btc_mom20;   // e.g. -0.1946

  function gauge(label, val, min, max, zones, unit, note) {
    if (val == null) return "";
    const pct = Math.max(0, Math.min(100, (val - min) / (max - min) * 100));
    let color = "#8b949e", zoneLabel = "";
    for (const z of zones) {
      if (val >= z.from && val < z.to) { color = z.color; zoneLabel = z.label; break; }
    }
    return `<div>
      <div style="display:flex;justify-content:space-between;margin-bottom:.25rem;">
        <span style="color:var(--muted)">${label}</span>
        <span style="font-weight:700;color:${color}">${typeof val==="number"?val.toFixed(1):val}${unit}
          <span style="font-size:0.72rem;font-weight:400"> ${zoneLabel}</span></span>
      </div>
      <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:3px;transition:width .4s"></div>
      </div>
      ${note ? `<div style="font-size:0.7rem;color:var(--muted);margin-top:.2rem">${note}</div>` : ""}
    </div>`;
  }

  // nasdaq_vol 在 build_signals 里已经年化过（std*sqrt252），这里只换百分比
  // ——之前重复年化导致显示 276 并永远"极度恐慌"
  const vixProxy = nasVol ? +(nasVol * 100).toFixed(1) : null;
  const vixZones = [
    {from:0,   to:15,  color:"#f1c40f", label: vpL("过度乐观 ⚠️","Overly optimistic ⚠️")},
    {from:15,  to:20,  color:"#2ecc71", label: vpL("正常","Normal")},
    {from:20,  to:30,  color:"#e67e22", label: vpL("担忧","Concern")},
    {from:30,  to:999, color:"#e74c3c", label: vpL("极度恐慌区(历史反弹样本)","Extreme panic zone (historical bounce sample)")},
  ];
  const rsiZones = [
    {from:0,  to:30,  color:"#e74c3c", label: vpL("超卖 → 可能反弹","Oversold → possible bounce")},
    {from:30, to:50,  color:"#e67e22", label: vpL("弱势","Weak")},
    {from:50, to:70,  color:"#2ecc71", label: vpL("正常偏多","Normal, tilting bullish")},
    {from:70, to:100, color:"#f1c40f", label: vpL("超买 ⚠️","Overbought ⚠️")},
  ];
  const btcPct = btcMom != null ? +(btcMom * 100).toFixed(1) : null;
  const btcZones = [
    {from:-100, to:-20, color:"#e74c3c", label: vpL("极度疲弱","Extremely weak")},
    {from:-20,  to:-5,  color:"#e67e22", label: vpL("偏弱","Weak-leaning")},
    {from:-5,   to:5,   color:"#8b949e", label: vpL("横盘","Flat / sideways")},
    {from:5,    to:20,  color:"#2ecc71", label: vpL("偏强","Strong-leaning")},
    {from:20,   to:999, color:"#27ae60", label: vpL("强势","Strong")},
  ];
  // 💵 美元强弱(DXY 趋势)——与美股通常负相关；颜色按"对股市的含义"上色(走强=承压)
  const dxyPct = tech.dxy_trend != null ? +(tech.dxy_trend * 100).toFixed(1) : null;
  const dxyZones = [
    {from:-100, to:-1, color:"#2ecc71", label: vpL("美元走弱 → 股市顺风","Dollar weakening → tailwind for stocks")},
    {from:-1,   to:1,  color:"#8b949e", label: vpL("美元横盘","Dollar flat")},
    {from:1,    to:100, color:"#e67e22", label: vpL("美元走强 → 股市承压","Dollar strengthening → headwind for stocks")},
  ];

  el.innerHTML = [
    gauge(vpL("VIX（波动率/恐慌指数）","VIX (volatility / fear index)"), vixProxy, 10, 50, vixZones, "",
      vixProxy ? vpL(`>30=恐慌区(历史反弹样本) · <15=过度乐观需谨慎 · 数据截至 ${SIGNALS.generated}`,
                     `>30 = panic zone (historical bounce sample) · <15 = overly optimistic, caution · data as of ${SIGNALS.generated}`) : ""),
    gauge(vpL("纳指RSI（超买超卖）","Nasdaq RSI (overbought/oversold)"), rsi, 0, 100, rsiZones, "",
      vpL("RSI>70超买，<30超卖；现在","RSI>70 = overbought, <30 = oversold; currently ") +
      (rsi>70 ? vpL("偏高，注意回调","elevated, watch for a pullback")
       : rsi<30 ? vpL("极度超卖，反弹概率大","deeply oversold, high odds of a bounce")
       : vpL("正常区间","in the normal range"))),
    gauge(vpL("BTC 20日动量","BTC 20-day momentum"), btcPct, -50, 50, btcZones, "%",
      vpL("BTC往往领先美股科技股1-2周，负值代表近期加密偏弱","BTC often leads US tech stocks by 1-2 weeks; a negative value means crypto has been weak recently")),
    gauge(vpL("💵 美元强弱 (DXY趋势)","💵 Dollar strength (DXY trend)"), dxyPct, -5, 5, dxyZones, "%",
      vpL("美元指数与美股通常负相关：美元强→外资回流美债、股市承压；美元弱→股市常受益。统计相关、非因果铁律",
          "The dollar index is usually negatively correlated with US stocks: a strong dollar → foreign capital flows back into Treasuries, pressuring stocks; a weak dollar → stocks often benefit. Statistical correlation, not a causal law.")),
  ].filter(Boolean).join("");

  // Summary line
  const warning = (vixProxy && vixProxy < 15) || (rsi && rsi > 75);
  const bullish  = (vixProxy && vixProxy > 30) || (rsi && rsi < 30);
  const summary = bullish
    ? `<div style="color:#2ecc71;font-size:0.78rem;margin-top:.4rem">${vpL("📈 恐慌信号出现 → 历史上此后多为逆向反弹样本","📈 Panic signal detected → historically often followed by a contrarian bounce")}</div>`
    : warning
    ? `<div style="color:#f1c40f;font-size:0.78rem;margin-top:.4rem">${vpL("⚠️ 市场情绪偏乐观，短线注意回调风险","⚠️ Sentiment is skewing optimistic — watch short-term pullback risk")}</div>`
    : `<div style="color:var(--muted);font-size:0.78rem;margin-top:.4rem">${vpL("情绪中性，无极端信号","Sentiment neutral, no extreme signal")}</div>`;
  el.innerHTML += summary;
}

