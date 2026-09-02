// ═══════════════════════════════════════════════════════
//  全局状态
// ═══════════════════════════════════════════════════════
// i18n 安全兜底(#5 深度面板双语化 W1b)：vpL(zh,en) 单一来源是 vp_i18n.js（W1a 并行任务接线）。
// 挂到 window 而非用 const/let 声明本地别名——5 个 app-*.js 共享同一全局脚本作用域(见
// dashboard.html 注释)，若多文件各自 const/let 同名会因重复声明抛 SyntaxError、整文件失效；
// 装到 window 上 + 裸标识符引用是本文件既有范式(对照下方 DARK 的 globalThis.defineProperty)。
// vp_i18n.js 尚未加载/接线时退化为恒返回 zh，页面纯中文不崩。
if (typeof window.vpL !== "function") window.vpL = function (zh, en) { return zh; };

let SIGNALS = null;
let PRICES  = null;
let MV      = null;  // multivariate analysis results
let selectedDate = null;

// label/short/desc 用 getter（非静态字符串）：TIER_META 只在脚本加载时构造一次，
// 若烘成静态值，语言切换后再次调用 renderTierLegend()/renderSignalMeter() 也读不到新语言；
// getter 让每次访问都重新读 vpL()，语言状态永远新鲜（对象形状/消费方零改动）。
const TIER_META = {
  5: { get label(){ return vpL("信号最强档","Strongest signal tier"); }, stars:"★★★★★", color:"#27ae60",
       get short(){ return vpL("季节 + 技术 + 宏观全面支撑","Seasonal + technical + macro all aligned"); },
       get desc(){ return vpL("季节性、技术面、宏观全面支撑，历史上此类信号后20天平均涨幅最大",
                               "Seasonal, technical, and macro factors all aligned — historically this tier has been followed by the largest average 20-day gain"); } },
  4: { get label(){ return vpL("信号偏强","Signal leans strong"); }, stars:"★★★★☆", color:"#2ecc71",
       get short(){ return vpL("多数指标偏多","Most indicators lean bullish"); },
       get desc(){ return vpL("多数指标偏多，历史上此档位偏正面","Most indicators lean bullish — historically this tier has skewed positive"); } },
  3: { get label(){ return vpL("中性观望","Neutral / wait-and-see"); }, stars:"★★★☆☆", color:"#f1c40f",
       get short(){ return vpL("信号混合，方向不明","Mixed signals, no clear direction"); },
       get desc(){ return vpL("信号混合、方向性不明确，历史上此档位缺乏统计优势",
                               "Mixed signals with no clear direction — historically this tier has shown no statistical edge"); } },
  2: { get label(){ return vpL("信号偏弱","Signal leans weak"); }, stars:"★★☆☆☆", color:"#e67e22",
       get short(){ return vpL("偏空信号为主","Mostly bearish-leaning signals"); },
       get desc(){ return vpL("偏空信号为主，负面因素略占上风","Mostly bearish-leaning signals — negative factors slightly outweigh positive ones"); } },
  1: { get label(){ return vpL("极高风险","Very high risk"); }, stars:"★☆☆☆☆", color:"#e74c3c",
       get short(){ return vpL("多重负面因素叠加","Multiple negative factors stacking"); },
       get desc(){ return vpL("多重负面因素叠加，历史上此类时期平均亏损","Multiple negative factors stacking — historically periods like this have averaged a loss"); } },
};

// 档位阈值：唯一来源是 signals.json（build_signals 从 signal_model.TIER_THRESHOLDS 下发）
const TIER_FALLBACK = { 5:0.80, 4:0.60, 3:0.40, 2:0.20 };
function tierThresholds() { return SIGNALS?.tier_thresholds || TIER_FALLBACK; }

function renderTierLegend() {
  const el = document.getElementById("tier-legend");
  if (!el) return;
  const th = tierThresholds();
  const bounds = { 5:"100%", 4:Math.round(th[5]*100)+"%", 3:Math.round(th[4]*100)+"%",
                   2:Math.round(th[3]*100)+"%", 1:Math.round(th[2]*100)+"%" };
  el.innerHTML = [5,4,3,2,1].map(t => {
    const m = TIER_META[t];
    const lo = t === 1 ? "0%" : Math.round(th[t]*100)+"%";
    return `<div class="tier-row" style="background:${m.color}10">
      <div class="tier-badge" style="background:${m.color};color:${t===3?"#000":"#fff"}">${t}</div>
      <div><strong style="color:${m.color}">${m.label}</strong> ${lo}–${bounds[t]}<br>
        <span style="color:var(--muted);font-size:0.75rem">${m.short}</span></div>
    </div>`;
  }).join("");
}


// ═══════════════════════════════════════════════════════
//  初始化
// ═══════════════════════════════════════════════════════
async function init() {
  // 直接双击打开 HTML（file:// 协议）时 fetch 全部失败，页面会大面积空白
  if (location.protocol === "file:") {
    const w = document.createElement("div");
    w.style.cssText = "background:#e74c3c;color:#fff;padding:.6rem 1rem;font-size:0.85rem;text-align:center;";
    w.innerHTML = vpL(
      "⚠ 检测到直接打开文件（file://）——浏览器会拦截数据加载，大部分面板将空白。请双击 <b>启动网站.bat</b> 或访问线上页面。",
      "⚠ Direct file open detected (file://) — the browser will block data loading and most panels will be blank. Please double-click <b>启动网站.bat</b> (the start script) or visit the live site."
    );
    document.body.prepend(w);
  }
  try {
    const r = await fetch("signals.json?_=" + Date.now());
    const txt = await r.text();
    SIGNALS = JSON.parse(txt);   // 后端已保证严格合法 JSON（_clean + allow_nan=False）
    const genDate = new Date(SIGNALS.generated);
    const daysDiff = Math.floor((Date.now() - genDate) / 86400000);
    const staleHtml = daysDiff > 3
      ? `<span style="color:#e67e22">⚠ ${vpL(`数据${daysDiff}天前`, `Data ${daysDiff}d old`)}</span>`
      : `<span style="color:var(--muted)">${vpL(`更新：${SIGNALS.generated}`, `Updated: ${SIGNALS.generated}`)}</span>`;
    document.getElementById("updated-time").innerHTML = staleHtml;
  } catch(e) {
    console.warn("signals.json 未找到，使用演示数据", e);
    SIGNALS = buildDemoSignals();
  }

  try {
    const r2 = await fetch("multivariate.json");
    MV = await r2.json();
  } catch(e) {
    console.warn("multivariate.json 未找到", e);
  }

  renderEventRefToday();   // ⑦ 真事件研究参考（替代原 buildEventGrid 主观勾选玩具）
  renderTierLegend();
  initDatePicker();
  // 研究视图的图表全部懒渲染（lazyRender 定义在 app-5.js；init 由 app-5 调用，此时已就绪）
  lazyRender("chart-price", renderPriceChart, "PriceChart");
  lazyRender("chart-signal-history", renderSignalHistory, "SignalHistory");

  if (MV) {
    // 默认标签页懒渲染；其余 MV 标签页首次点击时再渲染
    lazyRender("chart-modelcmp", renderModelComparison, "ModelCmp");
  }

  // loadLongHistory 渲染 3 张图：任意一张接近视口即触发（观察器按批去重，只跑一次）
  ["chart-longmonthly", "chart-holiday", "chart-bearmarkets"]
    .forEach(id => lazyRender(id, loadLongHistory, "LongHistory"));
}

// ═══════════════════════════════════════════════════════
//  演示数据（当 signals.json 不存在时）
// ═══════════════════════════════════════════════════════
function buildDemoSignals() {
  const daily = {};
  const start = new Date("2015-01-01");
  const end   = new Date();
  const PRIOR = [0,0.62,0.54,0.62,0.80,0.58,0.40,0.80,0.54,0.45,0.62,0.80,0.74];
  for(let d = new Date(start); d <= end; d.setDate(d.getDate()+1)) {
    const k = d.toISOString().slice(0,10);
    const m = d.getMonth()+1;
    const p = PRIOR[m] * (0.85 + Math.random()*0.3);
    const prob = Math.min(0.97, Math.max(0.03, p));
    daily[k] = { prob, tier: tier(prob), month: m,
      prior: PRIOR[m], nasdaq_ma200: 1, btc_mom20: 0.02,
      dxy_trend: -0.005, nasdaq_vol: 0.15, nasdaq_rsi: 55 };
  }
  return { generated: new Date().toISOString().slice(0,10),
    latest_prob: 0.392, latest_tier: 2,
    daily_signals: daily };
}

function tier(p) {
  const th = tierThresholds();
  for (const t of [5,4,3,2]) if (p >= th[t]) return t;
  return 1;
}

// 样本外校准插值：模型原始概率 → 历史同档位实际胜率（OOS）
// 点列来自 SIGNALS.calibration_points（按 prob 升序），端点夹紧
function calibrateProb(p) {
  const pts = SIGNALS?.calibration_points;
  if (!pts || !pts.length || p == null) return null;
  const xs = pts.map(d => d.prob);
  const ys = pts.map(d => d.actual_wr);
  if (p <= xs[0]) return Math.round(ys[0] * 100) / 100;
  if (p >= xs[xs.length - 1]) return Math.round(ys[xs.length - 1] * 100) / 100;
  for (let i = 0; i < xs.length - 1; i++) {
    if (p >= xs[i] && p <= xs[i + 1]) {
      const t = (p - xs[i]) / (xs[i + 1] - xs[i]);
      return Math.round((ys[i] + t * (ys[i + 1] - ys[i])) * 10000) / 10000;
    }
  }
  return null;
}

// ── 历史信号按需加载（signals.json 只发布近两年，更早在 signals_history.json）──
let _historyPromise = null;
function ensureHistory() {
  if (_historyPromise) return _historyPromise;
  _historyPromise = fetch("signals_history.json")
    .then(r => r.json())
    .then(h => {
      SIGNALS.daily_signals = { ...h.daily_signals, ...SIGNALS.daily_signals };
      if (h.daily_signals_sp500 && SIGNALS.daily_signals_sp500)
        SIGNALS.daily_signals_sp500 = { ...h.daily_signals_sp500, ...SIGNALS.daily_signals_sp500 };
      SIGNALS._historyTried = true;
    })
    .catch(e => { console.warn("signals_history.json 加载失败", e); SIGNALS._historyTried = true; });
  return _historyPromise;
}

// ═══════════════════════════════════════════════════════
//  日期选择器
// ═══════════════════════════════════════════════════════
// 交易日的「今天」一律以美东为准：澳洲/亚洲访问者本地日期比美国快一天，
// 用本地日期会把还没发生的交易日当成今天（en-CA 格式正好是 YYYY-MM-DD）
function localDateStr(d) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit" }).format(d || new Date());
}

function initDatePicker() {
  const dp = document.getElementById("date-picker");
  const today = localDateStr();
  const maxDate = new Date(); maxDate.setDate(maxDate.getDate() + 60);  // 前瞻40个交易日≈2个月
  dp.value = today;
  dp.max   = localDateStr(maxDate);
  dp.min   = "2015-01-01";
  dp.addEventListener("change", () => updateSignal(dp.value));
  updateSignal(today);
}

function updateSignal(dateStr) {
  selectedDate = dateStr;
  const today = localDateStr();
  const isFuture = dateStr > today;

  // ── 未来日期：从 next_opportunities 前瞻数据中取 ──
  if (isFuture) {
    const allFc = SIGNALS.next_opportunities?.all_forecast || [];
    let forecast = allFc.find(d => d.date === dateStr);
    // 如果不是交易日（节假日/周末），找最近的交易日
    if (!forecast && allFc.length > 0) {
      const target = new Date(dateStr).getTime();
      forecast = allFc.reduce((best, d) => {
        return Math.abs(new Date(d.date).getTime() - target) <
               Math.abs(new Date(best.date).getTime() - target) ? d : best;
      });
    }
    if (!forecast) {
      const ring = document.getElementById("signal-ring");
      ring.className = "signal-ring tier-3";
      document.getElementById("signal-pct").textContent  = "—";
      document.getElementById("signal-label").textContent = vpL("超出预测范围","Out of forecast range");
      document.getElementById("signal-stars").textContent = "—";
      document.getElementById("insight-box").innerHTML = vpL(
        `<strong>${dateStr}</strong><br>该日期超出预测范围（至 ${allFc[allFc.length-1]?.date||"—"}）。<br>
         <span style="color:var(--muted);font-size:0.78rem">"最佳操作窗口"显示未来40个交易日的高/低概率窗口；再往后技术因子外推不可靠，不提供数字。</span>`,
        `<strong>${dateStr}</strong><br>This date is beyond the forecast range (through ${allFc[allFc.length-1]?.date||"—"}).<br>
         <span style="color:var(--muted);font-size:0.78rem">The "best action window" panel shows probability windows for the next 40 trading days; beyond that, extrapolating technical factors is unreliable, so no numbers are shown.</span>`
      );
      document.getElementById("factor-list").innerHTML = "";
      document.getElementById("signal-percentile").innerHTML = "";
      return;
    }
    // 如果找到的是最近交易日而非选定日期本身，给 forecast 加一个标记
    if (forecast.date !== dateStr) forecast = {...forecast, _nearestDate: forecast.date};
    // 用预测数据合成一个 rec，技术因子用最新值
    const tech = SIGNALS.next_opportunities?.latest_tech || {};
    const synRec = {
      prob: forecast.prob, tier: forecast.tier, month: forecast.month,
      // dow_cn 是后端 JSON 字段值(中文星期名)，此处在做数据解析(indexOf 匹配)非展示——不翻译，
      // 翻译会让匹配恒失败(forecast.dow_cn 永远是中文)。
      prior: forecast.prior, dow: forecast.dow_cn ? ["周一","周二","周三","周四","周五"].indexOf(forecast.dow_cn) : 0,
      wom: forecast.wom, cal_lr: forecast.cal_lr || 1.0, holiday_lr: forecast.hol_lr || 1.0,
      nasdaq_ma200: tech.nasdaq_ma200 ?? 1, btc_mom20: tech.btc_mom20 ?? 0,
      dxy_trend: tech.dxy_trend ?? 0, nasdaq_rsi: tech.nasdaq_rsi ?? 50,
      nasdaq_vol: tech.nasdaq_vol ?? 0.15,
      _isForecast: true, _reasons: forecast.reasons || [],
    };
    const prob = forecast.prob;
    renderSignalMeter(prob, synRec);
    renderFactors(synRec, prob);
    renderPercentileInfo(prob);
    renderTodayRec(prob);
    renderTradePlan(forecast, allFc);
    return;
  }

  // ── 历史日期：从 daily_signals 取（瘦身后早于 cutoff 的按需加载）──
  const daily = SIGNALS.daily_signals;
  let key = dateStr;
  if (!daily[key]) {
    const d = new Date(dateStr);
    for(let i=0;i<7;i++) { d.setDate(d.getDate()-1); key=d.toISOString().slice(0,10); if(daily[key]) break; }
  }
  const rec = daily[key];
  if (!rec && SIGNALS.history_cutoff && dateStr < SIGNALS.history_cutoff && !SIGNALS._historyTried) {
    document.getElementById("signal-pct").textContent = "…";
    document.getElementById("signal-label").textContent = vpL("加载历史数据","Loading historical data");
    ensureHistory().then(() => updateSignal(dateStr));
    return;
  }
  if (!rec) { document.getElementById("signal-pct").textContent = vpL("无数据","No data"); return; }

  const prob = rec.prob;
  renderSignalMeter(prob, rec);
  renderFactors(rec, prob);
  renderPercentileInfo(prob);
  renderTodayRec(prob);
  const tp = document.getElementById("trade-plan");
  if (tp) tp.innerHTML = "";   // 历史日期不显示操作计划
}

function renderSignalMeter(prob, rec) {
  const rawPct = Math.round(prob * 100);
  const baseRate = SIGNALS?.base_rate_20d;
  const ring = document.getElementById("signal-ring");

  // 校准曲线被 PAV 压平 = 模型无样本外区分度。此时不显示"档位/星级"这种
  // 暗示把握度的标签，改为中性"基率框架"——这是当前证据下唯一诚实的展示。
  if (SIGNALS?.calibration_flat) {
    // 大数字用无条件基率（base_rate_20d），不是 PAV 压平值（那是测试窗均值，会偏高几个点）
    const flatPct = baseRate ?? 0.62;
    ring.className = "signal-ring tier-3";   // 黄=中性，不绿不红
    document.getElementById("signal-pct").textContent  = Math.round(flatPct * 100) + "%";
    document.getElementById("signal-label").textContent = vpL("≈基率","≈base rate");
    document.getElementById("signal-stars").textContent = "—";
    document.getElementById("signal-desc").innerHTML = vpL(
      `<span style="color:var(--muted);font-size:0.72rem">模型原始打分 ${rawPct}%，但样本外无区分度：` +
      `无论打分高低，未来20日上涨概率都≈基率 ${Math.round(flatPct*100)}%。当温度计看，别当把握度。</span>`,
      `<span style="color:var(--muted);font-size:0.72rem">Raw model score ${rawPct}%, but it has no out-of-sample discriminative power: ` +
      `regardless of the score, the 20-day up-probability is always ≈ the base rate of ${Math.round(flatPct*100)}%. Read it as a thermometer, not a confidence level.</span>`
    );
    renderSignalMeterTail(prob, rec, { color: "#f1c40f",
      desc: vpL("walk-forward 块自助验证未发现样本外优势，故不显示档位。",
                "Walk-forward block-bootstrap validation found no out-of-sample edge, so no tier is shown.") });
    return;
  }

  // 用校准概率决定档位、颜色、星级、标签；回退到原始概率
  const calProb = calibrateProb(prob);
  const displayProb = calProb !== null ? calProb : prob;
  const t = tier(displayProb);
  const meta = TIER_META[t];

  ring.className = "signal-ring tier-" + t;
  document.getElementById("signal-pct").textContent   = Math.round(displayProb*100) + "%";
  document.getElementById("signal-label").textContent  = meta.label;
  document.getElementById("signal-stars").textContent  = meta.stars;

  // 小字说明：原始输出、20日窗口、基率
  const baseRatePart = baseRate != null ? ` · ${vpL(`基率 ${Math.round(baseRate * 100)}%`, `base rate ${Math.round(baseRate * 100)}%`)}` : "";
  document.getElementById("signal-desc").innerHTML = vpL(
    `<span style="color:var(--muted);font-size:0.72rem">原始模型输出 ${rawPct}% · 未来20日窗口${baseRatePart}</span>`,
    `<span style="color:var(--muted);font-size:0.72rem">Raw model output ${rawPct}% · next-20-day window${baseRatePart}</span>`
  );

  renderSignalMeterTail(prob, rec, { color: meta.color, desc: meta.desc });
}

// 信号环以下的解释区（日期徽章/季节先验/事件叠加/模型状态），档位与基率两种展示共用
function renderSignalMeterTail(prob, rec, opts) {
  const MONTH = ["", vpL("1月","Jan"), vpL("2月","Feb"), vpL("3月","Mar"), vpL("4月","Apr"), vpL("5月","May"),
                 vpL("6月","Jun"), vpL("7月","Jul"), vpL("8月","Aug"), vpL("9月","Sep"), vpL("10月","Oct"),
                 vpL("11月","Nov"), vpL("12月","Dec")];
  const today = localDateStr();
  const isToday = selectedDate === today;
  const isForecast = rec._isForecast;
  const nearestNote = rec._nearestDate
    ? ` <span style="color:var(--muted);font-size:0.75rem">${vpL(`（非交易日，显示最近交易日 ${rec._nearestDate}）`, `(not a trading day, showing nearest trading day ${rec._nearestDate})`)}</span>`
    : "";
  const dateBadge = isToday
    ? `<span style="background:#2ecc7122;color:#2ecc71;border-radius:4px;padding:1px 6px;font-size:0.78rem">${vpL("今天","Today")}</span>`
    : isForecast
    ? `<span style="background:#3498db22;color:#3498db;border-radius:4px;padding:1px 6px;font-size:0.78rem">${vpL("📡 预测","📡 Forecast")}</span>`
    : "";
  const evText = "";   // 事件叠加玩具已移除(原 activeEvents);保留空串兼容下方模板
  // rec._reasons 是后端(build_signals.py)生成的中文短语数组，超出本文件(JS)翻译范围——
  // EN 模式下"日历因子："标签会译，但拼接的具体原因短语仍是中文(已知缺口，见交付说明)。
  const forecastReasons = isForecast && rec._reasons?.length
    ? vpL(`<br>日历因子：${rec._reasons.join("、")}`, `<br>Calendar factors: ${rec._reasons.join(", ")}`)
    : "";
  const techNote = isForecast
    ? `<br><span style="color:var(--muted);font-size:0.76rem">${vpL("技术因子冻结为最新值","Technical factors frozen at latest value")}</span>`
    : "";

  document.getElementById("insight-box").innerHTML = vpL(`
    <strong>${selectedDate}</strong>${nearestNote} ${dateBadge}（${MONTH[rec.month]}）<br>
    季节先验：${Math.round(rec.prior*100)}%${forecastReasons}
    ${evText}${techNote}<br>
    ${opts.desc}
  `, `
    <strong>${selectedDate}</strong>${nearestNote} ${dateBadge} (${MONTH[rec.month]})<br>
    Seasonal prior: ${Math.round(rec.prior*100)}%${forecastReasons}
    ${evText}${techNote}<br>
    ${opts.desc}
  `);

  // model_status_note：muted 小字，仅当字段存在时（动态插入 #signal-percentile 之后）
  const statusNote = SIGNALS ? vpD(SIGNALS, "model_status_note") : null;
  if (!renderSignalMeterTail._statusEl) {
    const el = document.createElement("div");
    el.id = "signal-model-status";
    const percEl = document.getElementById("signal-percentile");
    if (percEl && percEl.parentNode) percEl.parentNode.insertBefore(el, percEl.nextSibling);
    renderSignalMeterTail._statusEl = el;
  }
  const statusEl = renderSignalMeterTail._statusEl;
  if (statusEl) {
    statusEl.innerHTML = statusNote
      ? `<span style="font-size:0.7rem;color:var(--muted);">${statusNote}</span>`
      : "";
  }

  renderProbSpark();   // D2 微图表:概率60日走势(与所选日期无关,幂等重画;lang toggle 的 updateSignal 重跑会带上)
}

// D2 微图表:模型概率近60日走势(SIGNALS.daily_signals 末60个交易日的 prob 原始输出)。
// 语义纪律:中性 --mut 单色——概率高低绝不染红绿(样本外无区分度,装饰不造信号感);0.5 参考线=抛硬币。
function renderProbSpark() {
  const el = document.getElementById("signal-spark");
  if (!el) return;
  el.innerHTML = "";
  if (typeof vpSpark !== "function" || !SIGNALS?.daily_signals) return;
  const dates = Object.keys(SIGNALS.daily_signals).sort().slice(-60);
  const vals = dates.map(d => SIGNALS.daily_signals[d]?.prob);
  if (vals.filter(v => v != null && isFinite(v)).length <= 1) return;   // ≤1 有效点 → 留空不装样子
  const lbl = document.createElement("div");
  lbl.style.cssText = "font-size:0.68rem;color:var(--muted);margin-bottom:2px";
  lbl.textContent = vpL("模型概率·近60日·仅历史非预测", "Model prob · last 60d · history, not a forecast");
  const box = document.createElement("div");
  box.style.display = "inline-block";   // .signal-meter 整体居中(text-align:center),spark 跟标签一起居中
  el.appendChild(lbl);
  el.appendChild(box);
  vpSpark(box, vals, { color: "var(--mut)", fill: true, w: 150, h: 26, refLine: 0.5 });
}

function renderFactors(rec, finalProb) {
  const MONTH = ["", vpL("1月","Jan"), vpL("2月","Feb"), vpL("3月","Mar"), vpL("4月","Apr"), vpL("5月","May"),
                 vpL("6月","Jun"), vpL("7月","Jul"), vpL("8月","Aug"), vpL("9月","Sep"), vpL("10月","Oct"),
                 vpL("11月","Nov"), vpL("12月","Dec")];
  const DOW_NAMES = [vpL("周一","Mon"), vpL("周二","Tue"), vpL("周三","Wed"), vpL("周四","Thu"), vpL("周五","Fri"), vpL("周六","Sat"), vpL("周日","Sun")];
  const DOW_LR = [0.940,0.981,1.038,1.004,1.038,1.0,1.0];

  // 日历效应文字
  const calLR = rec.cal_lr || 1.0;
  const hlLR  = rec.holiday_lr || 1.0;
  const womLR = rec.wom ? ({1:1.112,2:0.996,3:1.015,4:0.950,5:0.992}[rec.wom]||1.0) : 1.0;
  function lrToText(lr) {
    if (lr >= 1.20) return vpL("强利好 ↑↑","Strongly bullish ↑↑");
    if (lr >= 1.10) return vpL("利好 ↑","Bullish ↑");
    if (lr >= 1.02) return vpL("微正 →↑","Slightly positive →↑");
    if (lr >= 0.98) return vpL("中性 →","Neutral →");
    if (lr >= 0.90) return vpL("微负 →↓","Slightly negative →↓");
    return vpL("利空 ↓","Bearish ↓");
  }
  function lrToScore(lr) { return Math.min(0.9, Math.max(0.1, (lr - 0.85) / 0.45)); }

  const calNote = (rec.month===4 && rec.dom===15) ? vpL("报税截止日(66%)","Tax-filing deadline (66%)") :
                  (rec.month===4 && rec.dom<=14)  ? vpL("报税季前(57%)","Pre-tax season (57%)") :
                  (rec.month===12 && rec.dom>=11 && rec.dom<=15) ? vpL("税损收割(47%)","Tax-loss harvesting (47%)") :
                  (rec.month===12 && rec.dom>=21 && rec.dom<=25) ? vpL("圣诞前(61%)","Pre-Christmas (61%)") :
                  ([1,4,7,10].includes(rec.month) && rec.dom<=5) ? vpL("季初历史偏强窗口(59%)","Historically strong quarter-start window (59%)") : vpL("普通","Normal");

  const factors = [
    { name: vpL("月度季节性","Monthly seasonality"),
      tip: vpL("基于1928年以来S&P500月度历史胜率的贝叶斯先验概率，6月历史均值约62%",
                "Bayesian prior based on S&P 500 monthly historical win rates since 1928; June's historical average is about 62%"),
      val: MONTH[rec.month]+" "+Math.round(rec.prior*100)+"%",
      score: rec.prior,
      dir: rec.prior>0.6?"↑":rec.prior<0.5?"↓":"→" },
    { name: vpL(`星期效应(${DOW_NAMES[rec.dow||0]})`, `Day-of-week effect (${DOW_NAMES[rec.dow||0]})`),
      tip: vpL("周内效应：周三/周五历史胜率最高(55%+)，周一最弱；这是市场微结构造成的系统性规律",
                "Day-of-week effect: Wednesday/Friday have historically had the highest win rate (55%+), Monday the weakest; a systematic pattern driven by market microstructure"),
      val: lrToText(DOW_LR[rec.dow||0])+" LR×"+DOW_LR[rec.dow||0],
      score: lrToScore(DOW_LR[rec.dow||0]),
      dir: DOW_LR[rec.dow||0]>=1?"↑":"↓" },
    { name: vpL(`月内第${rec.wom||"?"}周`, `Week ${rec.wom||"?"} of month`),
      tip: vpL("月内周次效应：第1周(季初历史偏强窗口)和第3周往往强于第4周(月末税收/平仓压力)",
                "Intra-month week effect: week 1 (historically strong quarter-start window) and week 3 tend to outperform week 4 (month-end tax/position-closing pressure)"),
      val: lrToText(womLR)+" LR×"+womLR.toFixed(3),
      score: lrToScore(womLR),
      dir: womLR>=1?"↑":"↓" },
    { name: vpL("日历异常","Calendar anomaly"),
      tip: vpL("税季异常、报税截止日、圣诞行情等特殊日历效应，来自贝叶斯似然比(LR)调整",
                "Special calendar effects such as tax-season anomalies, the tax-filing deadline, and the Christmas rally — applied via a Bayesian likelihood-ratio (LR) adjustment"),
      val: calNote+" LR×"+calLR.toFixed(3),
      score: lrToScore(calLR),
      dir: calLR>=1.05?"↑":calLR<=0.95?"↓":"→" },
    { name: vpL("假日效应","Holiday effect"),
      tip: vpL("感恩节前夕胜率76%、节前节后历史胜率均高于基准（历史统计描述·非操作建议）",
                "Thanksgiving-eve win rate 76%; pre/post-holiday win rates have historically been above baseline (historical statistical description · not trading advice)"),
      val: hlLR>1.2?vpL("节日窗口 ↑↑","Holiday window ↑↑"):hlLR>1.0?vpL("节前/后 ↑","Pre/post-holiday ↑"):vpL("普通","Normal"),
      score: lrToScore(hlLR),
      dir: hlLR>1?"↑":"→" },
    { name: vpL("NASDAQ均线","NASDAQ moving average"),
      tip: vpL("价格在200日均线上方=多头结构(牛市)；下方=空头结构(熊市)。这是最基础的趋势判断工具",
                "Price above the 200-day MA = bullish structure (bull market); below = bearish structure (bear market). This is the most basic trend-reading tool"),
      val: rec.nasdaq_ma200?vpL("多头结构","Bullish structure"):vpL("空头结构","Bearish structure"),
      score: rec.nasdaq_ma200?0.75:0.35,
      dir: rec.nasdaq_ma200?"↑":"↓" },
    { name: vpL("BTC 20日动量","BTC 20-day momentum"),
      tip: vpL("BTC的20日价格动量(涨跌幅)。BTC往往领先纳指科技股1-2周：BTC涨→科技股跟涨概率高",
                "BTC's 20-day price momentum (% change). BTC tends to lead Nasdaq tech stocks by 1-2 weeks: when BTC rises, tech stocks are more likely to follow"),
      val: (rec.btc_mom20>0?"+":"")+Math.round((rec.btc_mom20||0)*100)+"%",
      score: (rec.btc_mom20||0)>0.03?0.72:(rec.btc_mom20||0)<-0.03?0.38:0.55,
      dir: (rec.btc_mom20||0)>0?"↑":"↓" },
    { name: vpL("DXY 美元趋势","DXY dollar trend"),
      tip: vpL("美元指数(DXY)与股市通常负相关：美元强→外资回流美债，股市承压；美元弱→股市往往受益",
                "The Dollar Index (DXY) is typically negatively correlated with stocks: a strong dollar pulls foreign capital into US Treasuries and pressures stocks; a weak dollar tends to benefit stocks"),
      val: (rec.dxy_trend>0?"+":"")+Math.round((rec.dxy_trend||0)*100)+"%",
      score: (rec.dxy_trend||0)<-0.01?0.72:(rec.dxy_trend||0)>0.01?0.38:0.55,
      dir: (rec.dxy_trend||0)<0?"↑":"↓" },
    { name: "NASDAQ RSI",
      tip: vpL("RSI(相对强弱指数)：>70超买(短期可能回调)；<30超卖(可能反弹)；50以上偏多，50以下偏空",
                "RSI (Relative Strength Index): >70 overbought (short-term pullback possible); <30 oversold (bounce possible); above 50 leans bullish, below 50 leans bearish"),
      val: Math.round(rec.nasdaq_rsi||50),
      score: (rec.nasdaq_rsi||50)<35?0.72:(rec.nasdaq_rsi||50)>75?0.35:0.55,
      dir: (rec.nasdaq_rsi||50)<35?vpL("↑(超卖)","↑(oversold)"):(rec.nasdaq_rsi||50)>75?vpL("↓(超买)","↓(overbought)"):"→" },
  ];

  const COLORS = {0.72:"#27ae60", 0.75:"#27ae60", 0.71:"#2ecc71",
                  0.55:"#f1c40f", 0.38:"#e67e22", 0.35:"#e74c3c"};
  function colForScore(s) {
    if(s>=0.70) return "#27ae60"; if(s>=0.60) return "#2ecc71";
    if(s>=0.50) return "#f1c40f"; if(s>=0.40) return "#e67e22"; return "#e74c3c";
  }

  const html = factors.map(f => `
    <div class="factor-row">
      <span class="factor-name"><span class="tip" data-tip="${f.tip}">${f.name}</span></span>
      <div class="factor-bar-wrap"><div class="factor-bar" style="width:${Math.round(f.score*100)}%;background:${colForScore(f.score)}"></div></div>
      <span class="factor-val" style="color:${colForScore(f.score)}">${f.val} ${f.dir}</span>
    </div>
  `).join("");
  document.getElementById("factor-list").innerHTML = html;
}


// ⑦ 事件影响参考：今日页用真 event_study 数据(历史同类事件30日反应)替代主观 what-if 勾选玩具
function renderEventRefToday() {
  const el = document.getElementById("event-ref-today");
  if (!el || !SIGNALS) return;
  const es = SIGNALS.event_study || {};
  // 事件类型名的英文由后端(build_signals 的 labels_en)给,这里 vpD 取用即可。
  // 2026-09-01 前这里写着"超出本文件翻译范围、已知缺口"——其实后端早就有 label_en,
  // 只是这条渲染路径没读。改掉时顺手把这条过时注释也删了,免得下次又照着它当"已知缺口"。
  const rows = Object.entries(es).map(([k, v]) => {
    const smallN = (v.n || 0) < 15;
    return `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.25rem .4rem">${vpD(v, "label") || k}</td>
      <td style="padding:.25rem .4rem;text-align:center;color:${smallN ? "#e67e22" : "var(--muted)"}">n=${v.n}${smallN ? " ⚠" : ""}</td>
      <td style="padding:.25rem .4rem;text-align:right">${v.avg_return > 0 ? "+" : ""}${v.avg_return}%</td>
      <td style="padding:.25rem .4rem;text-align:right;color:var(--muted)">${v.win_rate}% <span style="font-size:0.66rem">${vpL(`(基准${v.base_win_rate}%)`, `(baseline ${v.base_win_rate}%)`)}</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="4" style="padding:.4rem;color:var(--muted)">${vpL("暂无事件研究数据","No event-study data yet")}</td></tr>`;
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.76rem;line-height:1.55;margin-bottom:.5rem">${vpL(
      `历史同类事件后 <b>30 日</b>的平均反应（样本内统计）。<b>事件影响的是波动/不确定性，不是可交易方向</b>——小样本(n⚠)更别当预测；调度型事件(FOMC/CPI/非农)当天放大波动、方向无稳定偏向。`,
      `Average reaction in the <b>30 days</b> after similar past events (in-sample statistics). <b>The event's impact is on volatility/uncertainty, not a tradable direction</b> — small samples (n⚠) are even less reliable as predictions; scheduled events (FOMC/CPI/nonfarm payrolls) amplify volatility on the day, with no stable directional bias.`
    )}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.78rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">${vpL("事件类型","Event type")}</td><td style="padding:.2rem .4rem;text-align:center">${vpL("样本","Sample")}</td><td style="padding:.2rem .4rem;text-align:right">${vpL("30日均涨跌","30d avg move")}</td><td style="padding:.2rem .4rem;text-align:right">${vpL("胜率 vs 基准","Win rate vs baseline")}</td></tr>
      ${rows}
    </table>
    <div style="font-size:0.7rem;color:var(--muted);margin-top:.4rem">${vpL(
      `→ 统计含义：这些情形下市场不确定性/波动历史上通常放大，而非可交易方向信号。反事实因果(SVB→KRE)见"📋 登记簿"。`,
      `→ Statistical meaning: in these situations, market uncertainty/volatility has historically tended to amplify — it is not a tradable direction signal. For counterfactual causal analysis (SVB→KRE), see the 📋 Registry.`
    )}</div>`;
}

// ═══════════════════════════════════════════════════════
//  图表
// ═══════════════════════════════════════════════════════
// DARK 必须每次返回全新对象：Plotly.newPlot 会把推断结果（type:"date"/range 等）
// 回写进传入的 layout——共享同一个对象会被首张日期轴图污染，后续数字轴图全坏
// （症状：x 轴显示 Jan 1970 时间戳、translate(NaN,...) 报错）。getter 让全部
// `...DARK` / `...DARK.xaxis` 调用零改动地各拿一份副本。
function _darkLayout() {
  return { paper_bgcolor:"transparent", plot_bgcolor:"transparent",
    font:{color:"#e6edf3",size:11}, xaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"},
    yaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"}, margin:{t:30,b:40,l:50,r:20},
    hoverlabel:{bgcolor:"#161b22", bordercolor:"#30363d", font:{color:"#e6edf3", size:12}} };
}
Object.defineProperty(globalThis, "DARK", { get: _darkLayout });

async function loadCSV(path) {
  try {
    const r = await fetch(path);
    const text = await r.text();
    const lines = text.trim().split("\n");
    const headers = lines[0].split(",");
    return lines.slice(1).map(l => {
      const vals = l.split(",");
      const row = {};
      headers.forEach((h,i) => row[h.trim()] = vals[i]?.trim());
      return row;
    });
  } catch(e) { return []; }
}

let PRICES_JSON = null;
let CHARTS_EXTRA = null;

async function loadPricesJSON() {
  if (PRICES_JSON) return PRICES_JSON;
  try {
    const r = await fetch("prices.json");
    PRICES_JSON = await r.json();
  } catch(e) { PRICES_JSON = null; }
  return PRICES_JSON;
}

async function loadChartsExtra() {
  if (CHARTS_EXTRA) return CHARTS_EXTRA;
  try {
    const r = await fetch("charts_extra.json");
    CHARTS_EXTRA = await r.json();
  } catch(e) { CHARTS_EXTRA = {}; }
  return CHARTS_EXTRA;
}

async function renderPriceChart() {
  const pj = await loadPricesJSON();
  if (!pj) { Plotly.newPlot("chart-price", [], {...DARK, title:{text: vpL("价格数据加载失败","Failed to load price data")}}); return; }

  const SHOW = ["NASDAQ","NDX100","SP500","BTC","DXY","GOLD","VIX","ETH"];
  const dates = pj.dates;
  const assets = pj.assets;
  const traces = SHOW.filter(a => assets[a]).map(a => ({
    x: dates,
    y: assets[a].values,
    name: assets[a].label,
    type: "scatter", mode: "lines",
    line: {color: assets[a].color, width: 1.8},
    hovertemplate: `<b>${assets[a].label}</b> %{x}<br>${vpL("指数","Index")} %{y:.1f}<extra></extra>`,
    visible: ["NASDAQ","NDX100","SP500","BTC","DXY"].includes(a) ? true : "legendonly",
  }));

  Plotly.newPlot("chart-price", traces, {...DARK, hovermode:"x unified",
    yaxis:{...DARK.yaxis, title: vpL("归一化指数（起点=100）","Normalized index (start=100)")},
    legend:{orientation:"h", y:1.08}, height:400}, {responsive:true});
  // D3：外部零依赖切换条替代旧的 Plotly 原生 rangeselector（同图叠两套按钮会重复/不统一，
  // 已下线原生版——见本批交付说明"判断点①"）；纯前端 relayout，不重拉数据。
  if (typeof vpRangeBar === "function") vpRangeBar("chart-price", { dates });
}

async function renderCorrChart() {
  const extra = await loadChartsExtra();
  const rc = extra?.rolling_corr;
  if (!rc) return;
  const cols = Object.keys(rc.series);
  const colors = ["#f39c12","#9b59b6","#3498db","#2ecc71","#e74c3c","#1abc9c"];
  const traces = cols.map((c,i)=>({
    x:rc.dates, y:rc.series[c],
    name:c.replace("NASDAQ_vs_","NASDAQ↔"), type:"scatter", mode:"lines",
    line:{color:colors[i%colors.length],width:1.5}
  }));
  if(rc.dates.length>0) traces.push({
    x:[rc.dates[0],rc.dates[rc.dates.length-1]],y:[0,0],
    mode:"lines",line:{color:"#555",dash:"dash"},showlegend:false});
  Plotly.newPlot("chart-corr",traces,{...DARK,yaxis:{...DARK.yaxis,range:[-1,1],
    title: vpL("相关系数","Correlation")},hovermode:"x unified",legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderMonthlyChart() {
  const extra = await loadChartsExtra();
  const data = extra?.monthly_stats;
  if(!data || !data.length) return;
  const MONTH = ["", vpL("1月","Jan"), vpL("2月","Feb"), vpL("3月","Mar"), vpL("4月","Apr"), vpL("5月","May"),
                 vpL("6月","Jun"), vpL("7月","Jul"), vpL("8月","Aug"), vpL("9月","Sep"), vpL("10月","Oct"),
                 vpL("11月","Nov"), vpL("12月","Dec")];
  const assets=["NASDAQ","DXY","BTC","ETH"], colors={NASDAQ:"#2ecc71",DXY:"#3498db",BTC:"#f39c12",ETH:"#9b59b6"};
  const traces = assets.map(a=>({
    x:data.filter(r=>r.asset===a).map(r=>MONTH[+r.month]),
    y:data.filter(r=>r.asset===a).map(r=>Math.round(parseFloat(r.win_rate)*100)),
    name:a, type:"bar", marker:{color:colors[a]},
    hovertemplate:`<b>${a}</b> %{x}<br>${vpL("胜率","Win rate")} %{y}%<extra></extra>`
  }));
  Plotly.newPlot("chart-monthly",traces,{...DARK,barmode:"group",
    yaxis:{...DARK.yaxis,title: vpL("胜率 (%)","Win rate (%)")},legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderGarchChart() {
  const extra = await loadChartsExtra();
  const traces = [];
  const nd = extra?.garch_nasdaq;
  const bt = extra?.garch_btc;
  if(nd && nd.dates && nd.volatility)
    traces.push({x:nd.dates, y:nd.volatility,
      name: vpL("NASDAQ年化波动率","NASDAQ annualized volatility"),type:"scatter",mode:"lines",line:{color:"#2ecc71",width:1.5}});
  if(bt && bt.dates && bt.volatility)
    traces.push({x:bt.dates, y:bt.volatility,
      name: vpL("BTC年化波动率","BTC annualized volatility"),type:"scatter",mode:"lines",line:{color:"#f39c12",width:1.5},
      yaxis:"y2"});
  if(!traces.length) return;
  Plotly.newPlot("chart-garch",traces,{...DARK,hovermode:"x unified",
    yaxis:{...DARK.yaxis,title: vpL("NASDAQ波动率%","NASDAQ volatility %")},
    yaxis2:{overlaying:"y",side:"right",title: vpL("BTC波动率%","BTC volatility %"),gridcolor:"transparent"},
    legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderGrangerChart() {
  const extra = await loadChartsExtra();
  const data = extra?.granger;
  if(!data || !data.length) {
    const demoData = [
      {label: vpL("美元→纳指","USD→Nasdaq"),pval:0.0005,lag:8,sig:1},
      {label: vpL("BTC→纳指","BTC→Nasdaq"), pval:0.0067,lag:8,sig:1},
      {label: vpL("纳指→BTC","Nasdaq→BTC"), pval:0.0625,lag:1,sig:0},
      {label:"ETH→BTC",  pval:0.0001,lag:10,sig:1},
      {label:"BTC→ETH",  pval:0.0039,lag:6,sig:1},
    ];
    renderGrangerFromRows(demoData); return;
  }
  renderGrangerFromRows(data.map(r=>({label:r.label,pval:parseFloat(r.p_value),lag:+r.best_lag_days,sig:r.significant===true||r.significant==="True"?1:0})));
}

function renderGrangerFromRows(rows) {
  const colors = rows.map(r=>r.sig?"#2ecc71":"#e74c3c");
  Plotly.newPlot("chart-granger",[{
    type:"bar", orientation:"h",
    x:rows.map(r=>Math.max(-Math.log10(r.pval),0)),
    y:rows.map(r=>r.label),
    marker:{color:colors},
    text:rows.map(r=>`p=${r.pval.toFixed(4)} ${vpL(`滞后${r.lag}天`,`lag ${r.lag}d`)} ${r.sig?"✓":"✗"}`),
    textposition:"outside", hovertemplate:"%{y}<br>%{text}<extra></extra>",
  }],{...DARK,xaxis:{...DARK.xaxis,title: vpL("-log10(p值)，越大越显著","-log10(p-value); higher = more significant")},
    shapes:[{type:"line",x0:1.3,x1:1.3,y0:-0.5,y1:rows.length-0.5,
      line:{color:"#e74c3c",dash:"dash",width:1}}],
    annotations:[{x:1.3,y:rows.length-0.5,text:"p=0.05",showarrow:false,
      font:{color:"#e74c3c",size:10}}]},{responsive:true});
}

async function renderAnnualChart() {
  const extra = await loadChartsExtra();
  const data = extra?.annual_returns;
  if(!data || !data.length) return;
  const assets=["NASDAQ","DXY","BTC","ETH"];
  const years=data.map(r=>r.year);
  const z=assets.map(a=>data.map(r=>r[a]!=null?Math.round(parseFloat(r[a])*100):null));
  Plotly.newPlot("chart-annual",[{type:"heatmap",z,x:years,y:assets,
    colorscale:"RdYlGn",zmid:0,
    text:z.map(row=>row.map(v=>v!=null?v+"%":"—")),
    texttemplate:"%{text}",colorbar:{title: vpL("涨幅%","Return %")},
    hovertemplate:`<b>%{y}</b> %{x}${vpL("年","")}<br>%{text}<extra></extra>`}],
    {...DARK,margin:{...DARK.margin,b:60}},{responsive:true});
}

async function renderSignalHistory() {
  if(!SIGNALS) return;
  const entries = Object.entries(SIGNALS.daily_signals).slice(-500);
  const dates = entries.map(([k])=>k);
  const probs = entries.map(([,v])=>v.prob*100);
  const tiers = entries.map(([,v])=>v.tier);
  const colors = tiers.map(t=>[,"#e74c3c","#e67e22","#f1c40f","#2ecc71","#27ae60"][t]);

  Plotly.newPlot("chart-signal-history",[
    {x:dates,y:probs,type:"scatter",mode:"lines",name: vpL("贝叶斯概率","Bayesian probability"),
     line:{color:"#3498db",width:1.5},fill:"tozeroy",fillcolor:"rgba(52,152,219,.15)"},
    {x:dates,y:Array(dates.length).fill(60),mode:"lines",
     line:{color:"#2ecc71",dash:"dot",width:1},name: vpL("参考线(60%)","Reference line (60%)"),showlegend:true},
    {x:dates,y:Array(dates.length).fill(80),mode:"lines",
     line:{color:"#27ae60",dash:"dot",width:1},name: vpL("强势线(80%)","Strong-signal line (80%)"),showlegend:true},
  ],{...DARK,yaxis:{...DARK.yaxis,range:[0,100],title: vpL("信号概率%","Signal probability %")},
    hovermode:"x unified",legend:{orientation:"h",y:1.05}},{responsive:true});
  // D3：时间范围切换条（纯前端 relayout，y轴固定[0,100]不受影响）
  if (typeof vpRangeBar === "function") vpRangeBar("chart-signal-history", { dates });
}

// ── 标签切换（主图区，仅影响 id="tab-*" 的内容）──
const MAIN_TABS = ["forecast","corr","monthly","garch","granger","annual"];
const _mainTabRendered = new Set();
function switchTab(name, el) {
  el.closest(".tabs").querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  MAIN_TABS.forEach(t => {
    const el2 = document.getElementById("tab-"+t);
    if (el2) el2.classList.remove("active");
  });
  const pane = document.getElementById("tab-"+name);
  pane?.classList.add("active");
  setTimeout(() => {
    if (_mainTabRendered.has(name)) { resizeChartsIn(pane); return; }
    _mainTabRendered.add(name);
    const ph = document.getElementById("ph-"+name);
    if (ph) ph.style.display = "none";
    if (name === "forecast")  safeRender(renderForecastChart, "Forecast");
    if (name === "corr")      safeRender(renderCorrChart,     "Corr");
    if (name === "monthly")   safeRender(renderMonthlyChart,  "Monthly");
    if (name === "garch")     safeRender(renderGarchChart,    "Garch");
    if (name === "granger")   safeRender(renderGrangerChart,  "Granger");
    if (name === "annual")    safeRender(renderAnnualChart,   "Annual");
  }, 0);
}

// ═══════════════════════════════════════════════════════
//  DOW 周内效应面板
// ═══════════════════════════════════════════════════════
function renderDOWPanel() {
  if (!SIGNALS || !SIGNALS.dow) return;
  const dow = SIGNALS.dow;  // [{dow,day_name,win_rate,avg_return}]
  // "今天"按美东交易日算：阿德莱德等东半球访客的本地日期常比美东快一天，直接用 getDay() 会标错
  const etWd = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" }).format(new Date());
  const todayDow = ["Mon","Tue","Wed","Thu","Fri"].indexOf(etWd);  // 0=Mon；周末=-1（不标）
  const maxWR = Math.max(...dow.map(d => d.win_rate));
  const minWR = Math.min(...dow.map(d => d.win_rate));

  const NAMES = [vpL("周一","Mon"), vpL("周二","Tue"), vpL("周三","Wed"), vpL("周四","Thu"), vpL("周五","Fri")];
  const cards = NAMES.map((name, i) => {
    const d = dow.find(x => x.dow === i) || {win_rate: 54, avg_return: 0};
    const isToday = i === todayDow;
    const isBest  = d.win_rate === maxWR;
    const isWorst = d.win_rate === minWR;
    const cls = isToday ? "today" : isBest ? "best" : isWorst ? "worst" : "";
    const color = d.win_rate >= 56 ? "#27ae60" : d.win_rate >= 54 ? "#2ecc71" :
                  d.win_rate >= 52 ? "#f1c40f" : "#e74c3c";
    const rank = isBest ? vpL("🥇最佳","🥇 Best") : isWorst ? vpL("⚠最弱","⚠ Weakest") : isToday ? vpL("📍今天","📍 Today") : "";
    return `<div class="dow-card ${cls}">
      <div class="dow-name">${name}</div>
      <div class="dow-wr" style="color:${color}">${d.win_rate}%</div>
      <div class="dow-avg">${d.avg_return > 0 ? '+' : ''}${d.avg_return}%</div>
      <div class="dow-rank">${rank}</div>
    </div>`;
  });
  document.getElementById("dow-grid").innerHTML = cards.join("");

  const best = dow.reduce((a,b) => a.win_rate > b.win_rate ? a : b);
  const worst = dow.reduce((a,b) => a.win_rate < b.win_rate ? a : b);
  document.getElementById("dow-insight").innerHTML = vpL(
    `<strong>周内规律：</strong>历史上<strong style="color:#27ae60">${NAMES[best.dow]}（${best.win_rate}%）</strong>历史胜率最高，
     <strong style="color:#e74c3c">${NAMES[worst.dow]}（${worst.win_rate}%）</strong>最弱。
     <br><span style="color:var(--muted);font-size:0.79rem">⚠ 周内效应在现代段（2000后）已被套利趋弱（见🪦坟场），此为历史描述、非操作建议。</span>`,
    `<strong>Day-of-week pattern:</strong> historically <strong style="color:#27ae60">${NAMES[best.dow]} (${best.win_rate}%)</strong> has had the highest win rate,
     <strong style="color:#e74c3c">${NAMES[worst.dow]} (${worst.win_rate}%)</strong> the weakest.
     <br><span style="color:var(--muted);font-size:0.79rem">⚠ The day-of-week effect has been arbitraged away in the modern era (post-2000) — see the 🪦 graveyard; this is a historical description, not trading advice.</span>`
  );
}

// ═══════════════════════════════════════════════════════
//  卖出信号面板
// ═══════════════════════════════════════════════════════
function renderSellPanel() {
  if (!SIGNALS || !SIGNALS.sell) {
    // 演示数据；tier 用 getter（非静态字符串）：SIGNALS.sell 只在首次调用时构造一次并缓存，
    // 静态值会把当时的语言状态冻住，切语言后重渲染也读不到新值。
    SIGNALS.sell = { score: 33.7, get tier(){ return vpL("持有观察","Hold & watch"); }, rsi: 56, mom20: 2.6, ma_cross: 1, vol_pct: 25 };
  }
  const s = SIGNALS.sell;
  const score = s.score || 0;

  const barColor = score >= 70 ? "#e74c3c" : score >= 55 ? "#e67e22" :
                   score >= 40 ? "#f1c40f" : score >= 25 ? "#2ecc71" : "#27ae60";
  document.getElementById("sell-score-txt").textContent = score.toFixed(1) + "/100";
  document.getElementById("sell-bar").style.width = score + "%";
  document.getElementById("sell-bar").style.background = barColor;

  const tierColor = score >= 55 ? "#e74c3c" : score >= 40 ? "#f1c40f" : "#2ecc71";
  document.getElementById("sell-tier-txt").style.color = tierColor;
  document.getElementById("sell-tier-txt").textContent = vpD(s, "tier") || "—";

  const rsi = s.rsi > 100 ? "—" : (s.rsi || 0).toFixed(1);
  const rsiColor = s.rsi > 75 ? "#e74c3c" : s.rsi > 60 ? "#f1c40f" : "#2ecc71";
  const maText = s.ma_cross ? vpL("金叉 ✓","Golden cross ✓") : vpL("死叉 ✗","Death cross ✗");
  const maColor = s.ma_cross ? "#2ecc71" : "#e74c3c";
  const volColor = (s.vol_pct || 0) > 70 ? "#e74c3c" : (s.vol_pct || 0) > 40 ? "#f1c40f" : "#2ecc71";

  document.getElementById("sell-metrics").innerHTML = `
    <div class="sell-metric">
      <div class="sell-metric-label">${vpL("RSI（>75 超买区）","RSI (>75 overbought)")}</div>
      <div class="sell-metric-val" style="color:${rsiColor}">${rsi}</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">${vpL("20日动量","20-day momentum")}</div>
      <div class="sell-metric-val" style="color:${(s.mom20||0)>0?'#2ecc71':'#e74c3c'}">${(s.mom20||0)>0?'+':''}${(s.mom20||0).toFixed(1)}%</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">${vpL("均线状态","MA status")}</div>
      <div class="sell-metric-val" style="color:${maColor}">${maText}</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">${vpL("波动率分位","Volatility percentile")}</div>
      <div class="sell-metric-val" style="color:${volColor}">${(s.vol_pct||0).toFixed(0)}${vpL("%历史位","% percentile")}</div>
    </div>
  `;

  const advice = score >= 70 ? vpL("⚠️ 卖出评分处于历史高位区（多重风险信号叠加）","⚠️ Sell score is in the historical high zone (multiple risk signals stacking)") :
                 score >= 55 ? vpL("风险评分偏高","Risk score leans high") :
                 score >= 40 ? vpL("信号混合","Mixed signals") :
                 vpL("评分平静","Score is calm");
  document.getElementById("sell-insight").innerHTML = vpL(
    `<strong>当前风险状态：</strong>${advice}`,
    `<strong>Current risk state:</strong> ${advice}`
  );
}

// ══════════════════════════════════════════════════════
//  长历史 + 假日效应
// ══════════════════════════════════════════════════════
let LONG_HISTORY = null;
let currentPeriod = "1928+";

async function loadLongHistory() {
  try {
    const r = await fetch("long_history.json");
    LONG_HISTORY = await r.json();
    renderLongMonthly(currentPeriod);
    renderHolidayChart();
    renderBearMarkets();
  } catch(e) { console.warn("long_history.json 未找到", e); }
}

function setPeriod(period, el) {
  currentPeriod = period;
  document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  renderLongMonthly(period);
}

function renderLongMonthly(period) {
  if (!LONG_HISTORY) return;
  const rows = (LONG_HISTORY.monthly_by_period || {})[period] || [];
  if (!rows.length) return;

  const MONTH = ["", vpL("1月","Jan"), vpL("2月","Feb"), vpL("3月","Mar"), vpL("4月","Apr"), vpL("5月","May"),
                 vpL("6月","Jun"), vpL("7月","Jul"), vpL("8月","Aug"), vpL("9月","Sep"), vpL("10月","Oct"),
                 vpL("11月","Nov"), vpL("12月","Dec")];
  const colors = rows.map(r => {
    if (r.win_rate >= 65) return "#27ae60";
    if (r.win_rate >= 58) return "#2ecc71";
    if (r.win_rate >= 52) return "#f1c40f";
    if (r.win_rate >= 47) return "#e67e22";
    return "#e74c3c";
  });

  Plotly.newPlot("chart-longmonthly", [
    {type:"bar", x: rows.map(r=>MONTH[r.month]), y: rows.map(r=>r.win_rate),
     name: vpL("月度胜率%","Monthly win rate %"), marker:{color:colors},
     text: rows.map(r=>`${r.win_rate}%<br>${vpL("均值","avg")}${r.avg_return>0?"+":""}${r.avg_return}%<br>n=${r.n}`),
     hovertemplate:"<b>%{x}</b><br>%{text}<extra></extra>"},
    {type:"scatter", x: rows.map(r=>MONTH[r.month]), y: rows.map(r=>r.avg_return),
     name: vpL("月均收益%","Monthly avg return %"), yaxis:"y2", mode:"lines+markers",
     line:{color:"#3498db",width:2}, marker:{size:6},
     hovertemplate:`%{x} ${vpL("均值","avg")}%{y:.2f}%<extra></extra>`},
  ], {
    ...DARK,
    barmode:"overlay",
    yaxis: {...DARK.yaxis, title: vpL("胜率 %","Win rate %"), range:[30,85]},
    yaxis2: {overlaying:"y", side:"right", title: vpL("月均收益 %","Monthly avg return %"), gridcolor:"transparent",
              zeroline:true, zerolinecolor:"#555"},
    shapes:[{type:"line",x0:-0.5,x1:11.5,y0:50,y1:50,
             line:{color:"#555",dash:"dash",width:1}}],
    legend:{orientation:"h",y:1.05},
  }, {responsive:true});

  // 更新样本数徽章
  const totalN = rows.reduce((s,r)=>s+r.n,0);
  document.getElementById("period-sample-badge").textContent =
    vpL(`${period}  共${totalN}个月样本`, `${period}  ${totalN} monthly samples total`);

  // 找最强/最弱月
  const best  = rows.reduce((a,b) => a.win_rate > b.win_rate ? a : b);
  const worst = rows.reduce((a,b) => a.win_rate < b.win_rate ? a : b);
  document.getElementById("longmonthly-insight").innerHTML = vpL(
    `<strong>${period} 统计（${rows[0]?.n} 年/月）：</strong>
     最强月 <span style="color:#27ae60">${MONTH[best.month]}（${best.win_rate}%，均值${best.avg_return>0?"+":""}${best.avg_return}%）</span> ·
     最弱月 <span style="color:#e74c3c">${MONTH[worst.month]}（${worst.win_rate}%，均值${worst.avg_return}%）</span>
     · 9月效应在所有时段均成立（历史最稳定的熊市规律）`,
    `<strong>${period} stats (${rows[0]?.n} year-months):</strong>
     strongest month <span style="color:#27ae60">${MONTH[best.month]} (${best.win_rate}%, avg ${best.avg_return>0?"+":""}${best.avg_return}%)</span> ·
     weakest month <span style="color:#e74c3c">${MONTH[worst.month]} (${worst.win_rate}%, avg ${worst.avg_return}%)</span>
     · the September effect holds across every period tested (the most robust bearish-seasonality pattern on the site)`
  );
}

function renderHolidayChart() {
  if (!LONG_HISTORY || !LONG_HISTORY.holiday_effects) return;
  const he = LONG_HISTORY.holiday_effects;

  // name 用 vpL 双写；因 d.name 参与下方"基准"配色判断(includes("基准"))，翻译后同时判断
  // 中英两种子串，避免翻译把这条颜色高亮逻辑判没（两个子串检测是本次翻译的直接必然结果，
  // 非新引入的旁支逻辑改动）。
  const items = [
    {name: vpL("感恩节前夕(周三)","Thanksgiving eve (Wed)"), wr: he.thanksgiving_eve?.win_rate,    avg: he.thanksgiving_eve?.avg_return,    n: he.thanksgiving_eve?.n},
    {name: vpL("感恩节后(黑五)","Day after Thanksgiving (Black Friday)"),   wr: he.thanksgiving_friday?.win_rate, avg: he.thanksgiving_friday?.avg_return, n: he.thanksgiving_friday?.n},
    {name: vpL("圣诞行情(Dec26-Jan3)","Santa Claus rally (Dec26-Jan3)"), wr: he.santa_claus_rally?.win_rate, avg: he.santa_claus_rally?.avg_return, n: he.santa_claus_rally?.n},
    {name: vpL("节前交易日","Pre-holiday trading days"),       wr: he.pre_holiday?.win_rate,         avg: he.pre_holiday?.avg_return,         n: he.pre_holiday?.n},
    {name: vpL("节后交易日","Post-holiday trading days"),       wr: he.post_holiday?.win_rate,        avg: he.post_holiday?.avg_return,        n: he.post_holiday?.n},
    {name: vpL("1月效应(前5日)","January effect (first 5 days)"),   wr: he.january_effect?.win_rate,      avg: he.january_effect?.avg_return,      n: he.january_effect?.n},
    {name: vpL("普通交易日(基准)","Normal trading days (baseline)"), wr: he.normal?.win_rate,              avg: he.normal?.avg_return,              n: he.normal?.n},
  ].filter(d => d.wr != null).reverse();

  const colors = items.map(d => (d.name.includes("基准") || d.name.includes("baseline")) ? "#555" :
    d.wr >= 70 ? "#27ae60" : d.wr >= 60 ? "#2ecc71" : d.wr >= 55 ? "#f1c40f" : "#e74c3c");

  Plotly.newPlot("chart-holiday", [{
    type:"bar", orientation:"h",
    x: items.map(d=>d.wr), y: items.map(d=>d.name),
    marker:{color:colors},
    text: items.map(d=>`${d.wr}%${vpL("胜率","win rate")}  ${vpL("均值","avg")}${d.avg>0?"+":""}${(d.avg*100).toFixed ? d.avg.toFixed(2) : d.avg}%  n=${d.n}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>",
  }], {
    ...DARK,
    xaxis:{...DARK.xaxis, range:[40,85], title: vpL("日频胜率 %","Daily win rate %")},
    margin:{t:20,b:50,l:160,r:80},
    shapes:[{type:"line",x0:52.4,x1:52.4,y0:-0.5,y1:items.length-0.5,
             line:{color:"#555",dash:"dot",width:1}}],
    annotations:[{x:52.4,y:items.length-0.5,text: vpL("基准52.4%","baseline 52.4%"),
      showarrow:false,font:{color:"#8b949e",size:10}}],
  }, {responsive:true});

  document.getElementById("holiday-insight").innerHTML = vpL(
    `<strong>贝叶斯应用：</strong>感恩节前夕（周三）胜率 <span style="color:#27ae60">76.3%</span>，
     已自动纳入每日信号计算（似然比×1.46）。
     节前/节后统一+6%胜率优势，圣诞行情窗口+5.5%。
     <span style="color:var(--muted);font-size:0.78rem">数据来源：S&P 500 日频 1950-2026，约24,000个交易日。</span>`,
    `<strong>Bayesian application:</strong> Thanksgiving-eve (Wednesday) win rate <span style="color:#27ae60">76.3%</span>,
     already folded into the daily signal calculation (likelihood ratio ×1.46).
     Pre/post-holiday days carry a uniform +6% win-rate edge; the Santa Claus rally window +5.5%.
     <span style="color:var(--muted);font-size:0.78rem">Data source: S&P 500 daily frequency 1950-2026, ~24,000 trading days.</span>`
  );
}

function renderBearMarkets() {
  if (!LONG_HISTORY || !LONG_HISTORY.bear_markets) return;
  const bm = LONG_HISTORY.bear_markets;

  Plotly.newPlot("chart-bearmarkets", [{
    type:"bar", orientation:"h",
    x: bm.map(b=>b.drawdown),
    y: bm.map(b=>`${b.name} (${b.start})`),
    marker:{color: bm.map(b => b.drawdown < -50 ? "#c0392b" : b.drawdown < -30 ? "#e74c3c" : "#e67e22")},
    // b.cause / b.name（y 轴用的 ${b.name} (${b.start})，见下方 y:）是 long_history.py 里
    // BEAR_MARKETS 的中文常量数据，超出本文件(JS)翻译范围——EN 模式下熊市名称/成因仍是中文
    // (已知缺口，见交付说明)；此处只译静态包装词"跌幅/恢复/月"。
    text: bm.map(b=>`${vpL("跌幅","Drawdown")}${b.drawdown}%  ${vpL("恢复","recovery")}${b.recovery_months}${vpL("月","mo")}  ${b.cause}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>",
    cliponaxis: false,
  }], {
    ...DARK,
    xaxis:{...DARK.xaxis, title: vpL("最大跌幅 %","Max drawdown %"), range:[-105,5]},
    margin:{t:20,b:50,l:165,r:10},
  }, {responsive:true});
}

// ── 多元分析标签切换 ──
// 各标签页对应的渲染函数（首次打开时才渲染，保证容器可见、宽度正确）
const MV_RENDERERS = {
  modelcmp:   () => renderModelComparison(),
  shap:       () => renderSHAPChart(),
  prophet:    () => renderProphetChart(),
  kalman:     () => renderKalmanChart(),
  rolling:    () => renderRollingBetaChart(),
  path:       () => renderPathChart(),
  cca:        () => renderCCAChart(),
  backtest:   () => renderBacktestCharts(),
};
const _mvTabRendered = new Set(["modelcmp"]);   // modelcmp 启动时已渲染

// 让刚变为可见的容器里所有 Plotly 图重算尺寸（修复曾在隐藏状态下渲染的图）
function resizeChartsIn(container) {
  if (!container) return;
  container.querySelectorAll(".js-plotly-plot").forEach(c => {
    try { Plotly.Plots.resize(c); } catch(e) {}
  });
}

// 窗口缩放时全局重算（防手机横竖屏/调窗口后图表挤压）
let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    document.querySelectorAll(".js-plotly-plot").forEach(c => {
      try { Plotly.Plots.resize(c); } catch(e) {}
    });
  }, 250);
});

function switchMVTab(name, el) {
  document.querySelectorAll("#mv-tabs .tab").forEach(t=>t.classList.remove("active"));
  document.querySelectorAll("[id^='mvtab-']").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  const pane = document.getElementById("mvtab-"+name);
  pane.classList.add("active");
  setTimeout(() => {
    if (!_mvTabRendered.has(name)) {
      _mvTabRendered.add(name);
      safeRender(MV_RENDERERS[name] || (()=>{}), "MV:"+name);
    } else {
      resizeChartsIn(pane);   // 已渲染过：重算尺寸，防挤压/叠加
    }
  }, 0);
}

