// ═══════════════════════════════════════════════════════
//  Benchmark 记分卡（SIGNALS.benchmark）
//  每个模型 vs 它的诚实基线：硬基线 · 样本外/前向 · 前向不足不判输赢
// ═══════════════════════════════════════════════════════
// i18n 安全兜底(#5 深度面板双语化 W2a)：vpL(zh,en) 单一来源是 vp_i18n.js（W1a 接线）。
// 挂到 window 而非用 const/let 声明本地别名——5 个 app-*.js 共享同一全局脚本作用域，
// 若多文件各自 const/let 同名会因重复声明抛 SyntaxError、整文件失效（见 app-1.js 同款注释）。
// vp_i18n.js 尚未加载/接线时退化为恒返回 zh，页面纯中文不崩。
if (typeof window.vpL !== "function") window.vpL = function (zh, en) { return zh; };

function renderBenchmark() {
  const el = document.getElementById("benchmark");
  if (!el) return;
  const bm = SIGNALS && SIGNALS.benchmark;
  if (!bm || !Array.isArray(bm.rows) || !bm.rows.length) {
    el.innerHTML = `<span style="color:var(--muted)">${vpL("运行一次完整流水线后显示","Available after a full pipeline run")}</span>`;
    return;
  }
  // verdict → 颜色（✅绿 / ➖黄 / ❌红 / ⏳灰；数据缺失也用灰）
  const VC = {
    "✅打败": "#2ecc71", "➖持平": "#f1c40f",
    "❌未达": "#e74c3c", "⏳数据不足": "#8b949e", "数据缺失": "#8b949e",
  };
  const fmt = v => (v === null || v === undefined) ? "—" : esc(String(Number(v)));
  const fmtDelta = v => {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    return esc((n > 0 ? "+" : "") + n);
  };
  // 数据层双语(2026-08-25):benchmark.py 已为每行出 *_en。EN 优先取,缺失回落中文。
  // 注意 color 仍用**中文 verdict** 当 VC 的键——后端枚举值没变(改值会打断这张颜色表)。
  const EN = (typeof vpLang === "function") && vpLang() === "en";
  const F = (r, k) => (EN && r[k + "_en"]) ? r[k + "_en"] : r[k];
  const rows = bm.rows.map(r => {
    const color = VC[r.verdict] || "#8b949e";
    return `<tr style="border-top:1px solid var(--border-faint);" title="${esc(F(r,"note"))}">
      <td style="padding:.3rem .5rem;">${esc(F(r,"name"))}</td>
      <td style="padding:.3rem .5rem;color:var(--muted);">${esc(F(r,"metric"))}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${fmt(r.model_value)}</td>
      <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${esc(F(r,"baseline_label"))} ${fmt(r.baseline_value)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${fmtDelta(r.delta)}</td>
      <td style="padding:.3rem .5rem;text-align:center;"><span style="color:${color};font-weight:600;">${esc(F(r,"verdict"))}</span></td>
      <td style="padding:.3rem .5rem;color:var(--muted);font-size:0.72rem;">${esc(F(r,"basis"))}</td>
    </tr>`;
  }).join("");
  const s = bm.summary || {};
  el.innerHTML = `
    <div style="overflow-x:auto;max-width:100%;">
    <table style="width:100%;min-width:720px;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.72rem;">
        <th style="padding:.3rem .5rem;text-align:left;">${vpL("项目","Item")}</th>
        <th style="padding:.3rem .5rem;text-align:left;">${vpL("指标","Metric")}</th>
        <th style="padding:.3rem .5rem;text-align:right;">${vpL("模型值","Model value")}</th>
        <th style="padding:.3rem .5rem;text-align:right;">${vpL("基线","Baseline")}</th>
        <th style="padding:.3rem .5rem;text-align:right;">${vpL("差值","Delta")}</th>
        <th style="padding:.3rem .5rem;text-align:center;">${vpL("判定","Verdict")}</th>
        <th style="padding:.3rem .5rem;text-align:left;">${vpL("依据","Basis")}</th>
      </tr></thead><tbody>${rows}</tbody>
    </table>
    </div>
    <div style="display:flex;gap:.65rem;flex-wrap:wrap;margin-top:.7rem;font-size:0.72rem;color:var(--muted);">
      <span>✅ ${vpL("打败","Beats")} ${Number(s.beats ?? 0)}</span>
      <span>➖ ${vpL("持平","Ties")} ${Number(s.ties ?? 0)}</span>
      <span>❌ ${vpL("未达","Loses")} ${Number(s.loses ?? 0)}</span>
      <span>⏳ ${vpL("数据不足","Insufficient data")} ${Number(s.insufficient ?? 0)}</span>
    </div>
    ${bm.drift ? `<div style="margin-top:.5rem;font-size:0.75rem;color:${(bm.drift.degraded_count||0)>0?"#e74c3c":"var(--muted)"};">
      📡 ${vpL("漂移监控：","Drift monitor: ")}${(EN && bm.drift.status_en)
            ? esc(bm.drift.status_en)   /* 后端 status_en 已内含逐条变化明细,不再另拼 */
            : esc(bm.drift.status)+((bm.drift.changes||[]).length?"（"+bm.drift.changes.map(c=>esc(c.name)+":"+esc(c.from)+"→"+esc(c.to)).join("；")+"）":"")}</div>` : ""}
    <div class="insight" style="margin-top:.85rem;">
      <strong>${esc(EN && bm.headline_en ? bm.headline_en : bm.headline)}</strong><br>
      <span style="color:var(--muted);font-size:0.75rem;">${vpL("原则：","Principle: ")}${esc(EN && bm.principle_en ? bm.principle_en : bm.principle)}</span>
    </div>`;
}

function safeRender(fn, name) {
  try { fn(); } catch(e) { console.warn("renderError ["+name+"]:", e); }
}

// ── IntersectionObserver 懒渲染 ──
// Plotly 在 display:none 容器里画图会按默认 700px 宽计算（甚至给文字标签算出 NaN 坐标），
// 之前靠切视图后 Plots.resize 补救。懒渲染让隐藏视图的图表在首次可见时才画，一次画对，
// 顺带省掉首屏 10+ 张看不见的图的渲染时间。
const _lazyJobs = new Map();   // containerId -> {fn, name}

// D3 术语注解补扫：懒面板常在 vp_gloss.js 固定双扫(载入 + 2000ms)窗口之后才首次渲染，
// 里面的术语(EVT/保形/β/分位…)注解不到。渲染函数多为 async fetch→填 innerHTML，无统一
// 完成信号 → 触发后延时对该容器补扫一次（vpGlossScan 幂等：全页每词只注首次、已注解
// 子树自动跳过，重复调用零副作用；单容器子树扫描开销可忽略）。1.5s 是本地/CI 实测够
// fetch+渲染完成的缓冲；慢网下偶尔漏注不是错误（注解是增强，非功能依赖）。
function _glossRescan(el) {
  if (typeof vpGlossScan !== "function" || !el) return;
  setTimeout(() => { try { vpGlossScan(el); } catch (e) { /* 注解失败不影响面板 */ } }, 1500);
}

const _lazyObserver = new IntersectionObserver(entries => {
  const fired = new Set();     // 同一批回调里多个容器共用一个渲染函数时只跑一次
  for (const en of entries) {
    if (!en.isIntersecting) continue;
    const job = _lazyJobs.get(en.target.id);
    if (!job) continue;
    _lazyJobs.delete(en.target.id);
    _lazyObserver.unobserve(en.target);
    _glossRescan(en.target);
    if (fired.has(job.fn)) continue;
    fired.add(job.fn);
    safeRender(job.fn, job.name);
  }
}, { rootMargin: "250px" });

function lazyRender(containerId, fn, name) {
  const el = document.getElementById(containerId);
  if (!el) return;
  // offsetParent 为 null = 自己或祖先 display:none（隐藏视图）→ 挂观察器等可见
  if (el.offsetParent !== null) { safeRender(fn, name); _glossRescan(el); return; }
  _lazyJobs.set(containerId, { fn, name });
  _lazyObserver.observe(el);
}

function bindStaticControls() {
  if (bindStaticControls._bound) return;
  bindStaticControls._bound = true;
  const on = (id, event, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener(event, fn);
  };

  on("refresh-data-btn", "click", e => refreshData(e.currentTarget));
  document.querySelector(".view-nav")?.addEventListener("click", e => {
    const btn = e.target.closest(".view-btn[data-view]");
    if (btn) switchView(btn.dataset.view, btn);
  });
  document.querySelector(".ob-dismiss")?.addEventListener("click", dismissOnboarding);
  document.getElementById("period-btns")?.addEventListener("click", e => {
    const btn = e.target.closest(".period-btn[data-period]");
    if (btn) setPeriod(btn.dataset.period, btn);
  });
  document.querySelectorAll("[data-main-tab]").forEach(btn =>
    btn.addEventListener("click", () => switchTab(btn.dataset.mainTab, btn)));
  document.querySelectorAll("[data-mv-tab]").forEach(btn =>
    btn.addEventListener("click", () => switchMVTab(btn.dataset.mvTab, btn)));
  document.querySelectorAll("[data-cal-tab]").forEach(btn =>
    btn.addEventListener("click", () => switchCalTab(btn.dataset.calTab, btn)));

  on("cgt-calc-btn", "click", calculateCGT);
  on("spcx-price-btn", "click", fetchSPCXPrice);
  on("portfolio-refresh-btn", "click", fetchPortfolioPrices);
  on("auto-refresh-btn", "click", e => toggleAutoRefresh(e.currentTarget));
  ["spcx-shares-input", "spcx-price-input"].forEach(id => on(id, "input", updateSPCXCalc));

  document.addEventListener("click", e => {
    // data-forecast-date(40日热力横带)的 click/hover/键盘交互自成一套(见 app-3.js
    // _fcCellActivate 等)，不在这里委托 —— 避免"tap先peek再确认"逻辑被这里的无条件单击抢先触发。
    const cost = e.target.closest("[data-cost-index]");
    if (cost) { setPortfolioCost(Number(cost.dataset.costIndex)); return; }
    const scrollTarget = e.target.closest("[data-scroll-target]");
    if (scrollTarget) {
      e.preventDefault();
      document.getElementById(scrollTarget.dataset.scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (e.target.closest("[data-fear-greed-retry]")) { fetchFearAndGreed(); return; }
    const stock = e.target.closest("[data-stock-symbol]");
    if (stock) {
      renderStockChart(stock.dataset.stockSymbol);
      if (typeof toggleStockRowExpand === "function") toggleStockRowExpand(stock.dataset.stockSymbol);
      return;
    }
    const sell = e.target.closest("[data-game-sell]");
    if (sell) { gameSell(sell.dataset.gameSell); return; }
    if (e.target.closest("[data-game-buy]")) { gameBuy(); return; }
    if (e.target.closest("[data-game-reset]")) { gameReset(); return; }
    if (e.target.closest("[data-tz-toggle]")) { toggleTZMode(); return; }
    const ov = e.target.closest("[data-overnight]");
    if (ov) { renderOvernight(ov.dataset.overnight, ov); return; }
  });
  document.addEventListener("input", e => {
    const spcx = e.target.closest("[data-spcx-save]");
    if (spcx) saveSPCXData(spcx.dataset.spcxSave, spcx.value);
  });
  document.addEventListener("keydown", e => {
    if (e.key !== "Enter" && e.key !== " ") return;
    // data-forecast-date 键盘交互见 app-3.js（同一套 Enter/Esc 逻辑，不在此重复委托）
    const cost = e.target.closest("[data-cost-index]");
    if (cost) {
      e.preventDefault();
      setPortfolioCost(Number(cost.dataset.costIndex));
      return;
    }
    const stock = e.target.closest("[data-stock-symbol]");
    if (stock) {
      e.preventDefault();
      renderStockChart(stock.dataset.stockSymbol);
      if (typeof toggleStockRowExpand === "function") toggleStockRowExpand(stock.dataset.stockSymbol);
    }
  });
}

// 启动渲染序列。抽成具名函数以支持"🔄 手动刷新"：所有渲染器都是幂等覆盖，
// 重新 init()（拉最新 JSON）后再跑一遍即完成无整页刷新的数据更新。
function renderAll() {
  bindStaticControls();
  safeRender(renderDOWPanel,        "DOW");
  safeRender(renderSellPanel,       "Sell");
  safeRender(renderOppPanel,        "Opp");
  safeRender(renderForecastChart,   "Forecast");
  safeRender(renderTodayRec,        "TodayRec");
  safeRender(renderForecastCalendar,"ForecastCal");
  safeRender(renderForecastStrip,   "ForecastStrip");
  safeRender(renderSentimentPanel,  "Sentiment");
  safeRender(renderEconCalendar,    "EconCal");
  lazyRender("chart-dip-recovery",  renderDipGuide, "DipGuide");
  safeRender(renderSPCXTracker,     "SPCX");
  lazyRender("chart-accuracy",      renderPredictionAccuracy, "PredAccuracy");
  safeRender(renderIndicesCompare,  "IndicesCompare");
  safeRender(renderLiveTracking,    "LiveTracking");
  safeRender(renderMarketClock,     "MarketClock");
  safeRender(renderTodayLine,       "TodayLine");
  loadStocksPanel();
  lazyRender("chart-overnight",     loadOvernightPanel, "Overnight");
  loadNewsPanel();
  loadBriefPanel();
  loadPaperPanel();
  loadReportPanel();
  safeRender(renderBenchmark,       "Benchmark");
  fetchFearAndGreed();
  loadQuotes();   // 盘中轻量报价（10分钟级），SPCX 监视卡优先消费
  loadDataFreshness();   // 📡 数据新鲜度徽章：让"自动刷新到几点 + 盘中/休市"一眼可见
  loadDigest();          // 📋 今日摘要（三层诚实摘要，描述非预测）
  loadTipjar();          // 🎲 试胆区（玩具预测+公开计分，娱乐非建议）
  loadOutlook();         // 📈 观点/预测（授权出格区：方向 + 看好看淡）
  initOnboarding();      // 👋 新手引导横幅（首次访问显示）
  lazyRender("chart-spcx-ipo",      renderSPCXDetail, "SPCXDetail");
  // Sync SPCX inputs with localStorage
  const savedShares = localStorage.getItem("spcx_shares");
  const savedPrice  = localStorage.getItem("spcx_price");
  if (savedShares) { const el = document.getElementById("spcx-shares-input"); if (el) el.value = savedShares; }
  if (savedPrice)  { const el = document.getElementById("spcx-price-input");  if (el) el.value = savedPrice; }
  renderPortfolioTable(0.71);  // render with fallback rate; user can refresh for live prices
  _mainTabRendered.add("forecast");
  _calTabRendered.add("digit");  // digit 是日历组默认标签，由懒渲染负责首画
  lazyRender("placebo-overview", loadPlacebo, "Placebo");   // 🔬 规律防伪诚实总览
  lazyRender("event-causal", loadEventCausal, "EventCausal"); // 🎯 反事实事件影响(方法B)
  lazyRender("risk-dashboard", loadRiskDashboard, "RiskDash"); // 📉 风险仪表盘(方法D)
  lazyRender("conformal", loadConformal, "Conformal");        // 📐 收益区间(方法E 保形预测)
  lazyRender("cycles-spectral", loadCycles, "Cycles");        // 🌀 周期检验(方法F 谱+红噪声)
  lazyRender("fdr-crossfamily", loadFdrCrossfamily, "FdrCF"); // 🧮 诚实总账(#5 跨检验族 FDR)
  lazyRender("cpcv", loadCpcv, "CPCV");                       // 🎲 过拟合概率 PBO(方法G CSCV)
  lazyRender("calibration-drift", loadCalibrationDrift, "CalDrift"); // 📉 校准漂移(#3 逐折校准随时间)
  lazyRender("stock-checkup", loadStockCheckup, "StockCheckup");     // 🩺 个股诚实体检(块0 基础风险画像)
  lazyRender("honest-graveyard", loadGraveyard, "Graveyard");        // 🪦 诚实坟场(死掉的模型+消失的规律)
  lazyRender("market-regime", loadMarketRegime, "MarketRegime");     // 🌡️ 当前市场风险体制(R1,描述非预测)
  lazyRender("exploratory", loadExploratory, "Exploratory");         // 🔬 探索区(未验证猜测,怀疑训练场)
  lazyRender("overreaction", loadOverreaction, "Overreaction");       // 🔁 短期反转(R3,描述非抄底)
  lazyRender("chart-digit", renderDigitChart, "Digit");
  lazyRender("chart-ipo-cycle", renderIPOCycle, "IPOCycle");
  lazyRender("factor-audit", renderFactorAudit, "FactorAudit");
  lazyRender("vol-model", renderVolModel, "VolModel");
  lazyRender("market-structure", renderMarketStructure, "MarketStructure");
  lazyRender("event-impact", renderEventImpact, "EventImpact");
  lazyRender("quant-methodology", renderQuantMethodology, "QuantMethodology");
  lazyRender("chart-horizon", renderHorizonView, "Horizon");
  // ⑥ 登记簿页：把诚实统计面板从"研究"运行时搬到"登记簿"。这些 id 上面已 lazyRender 观察过；
  // appendChild 搬的是同一活节点(IntersectionObserver 跟随节点、id 不变 → 懒渲染键照常)，勿改成 clone。
  const _regHost = document.getElementById("registry-panels");
  // 分组标题:结构(搬 DOM)只在首次构建(幂等门 reg-group-0);标题**文本**每次 renderAll 都按当前语言
  // 重设——W2a 报告的"已建后切语言标题不重译"缺口的最小修(Fable:只刷文本·不重搬 DOM·不动顺序)。
  const _groups = [
    [vpL("🔬 规律真伪 · 防伪（真规律 vs 幻觉）","🔬 Real vs. fake patterns · placebo checks (real edge vs. illusion)"), ["placebo-overview", "cpcv", "fdr-crossfamily", "calibration-drift", "cycles-spectral"]],
    [vpL("🌡️ 风险与不确定性（描述当前环境，非预测）","🌡️ Risk & uncertainty (describes the current environment, not a prediction)"), ["market-regime", "risk-dashboard", "conformal"]],
    [vpL("🩺 个股 · 因子","🩺 Stocks · factors"), ["stock-checkup", "factor-audit"]],
    [vpL("🎯 事件因果","🎯 Event causality"), ["event-causal"]],
    [vpL("🔭 探索中 vs 已死（未验证/被套利，别拿来交易）","🔭 Exploratory vs. dead (unverified/arbitraged — don't trade on these)"), ["exploratory", "overreaction", "honest-graveyard"]],
  ];
  if (_regHost && !document.getElementById("reg-group-0")) {   // 首次:建标题节点 + 按组搬面板
    _groups.forEach(([title, ids], gi) => {
      const h = document.createElement("div");
      h.id = "reg-group-" + gi;
      h.style.cssText = "font-size:1.02rem;font-weight:700;margin:1.4rem .2rem .4rem;padding-bottom:.3rem;border-bottom:1px solid var(--border)";
      h.textContent = title;
      _regHost.appendChild(h);
      ids.forEach(id => {
        const w = document.getElementById(id)?.closest(".chart-wrap");
        if (w) _regHost.appendChild(w);   // 按组顺序搬入(首次构建,顺序即定)
      });
    });
  } else if (_regHost) {                                       // 已建:只刷标题文本(切语言重译)
    _groups.forEach(([title], gi) => {
      const h = document.getElementById("reg-group-" + gi);
      if (h) h.textContent = title;
    });
  }
  lazyRender("honest-registry", loadHonestRegistry, "Registry");   // 🧾 诚实总览自动汇总
  // 恢复上次浏览的视图（默认"今日"）；手动刷新时 savedView==当前视图，顺带触发图表重算尺寸
  const savedView = localStorage.getItem("alpha_view");
  if (savedView && savedView !== "today") {
    const btn = document.querySelector(`.view-btn[data-view="${savedView}"]`);
    if (btn) switchView(savedView, btn);
  }

  // 移动端/触屏：.tip 的 ⓘ 解释是 hover-only，触屏无 hover → 点击切换显示、点别处收起；
  // 同时给静态 .tip 补 tabindex 使键盘可聚焦（配 style.css 的 .tip:focus-visible::after）。
  document.querySelectorAll(".tip").forEach(t => {
    if (!t.hasAttribute("tabindex")) t.setAttribute("tabindex", "0");
  });
  if (!renderAll._tipBound) {        // 只绑一次(renderAll 会被 refreshData 重调，否则 document 监听器累积泄漏)
    renderAll._tipBound = true;
    document.addEventListener("click", (e) => {
      const tip = e.target.closest(".tip");
      document.querySelectorAll(".tip.tip-show").forEach(t => { if (t !== tip) t.classList.remove("tip-show"); });
      if (tip) tip.classList.toggle("tip-show");
    });
  }

  // 标题层级 a11y：面板标题/图表头原为无语义 <div>，全页仅 1 个 <h1> → 读屏无法按标题导航。
  // 补 role=heading + aria-level=2（覆盖 7 视图所有静态标题，含隐藏视图）。纯 ARIA，零视觉变化。
  document.querySelectorAll(".panel-title, .chart-header").forEach(h => {
    if (!h.hasAttribute("role")) { h.setAttribute("role", "heading"); h.setAttribute("aria-level", "2"); }
  });
}
init().then(renderAll);

// ═══════════════════════════════════════════════════════
//  ⏳ 长期视角：持有期基率统计（SIGNALS.horizon_stats）
// ═══════════════════════════════════════════════════════
const _HZ_ORDER = ["6mo", "1y", "3y", "5y", "10y"];
// 值用 getter：_HZ_CN 是模块级 const，只在脚本加载时构造一次；若烘成静态字符串，
// 语言切换后 renderHorizonView() 重跑也读不到新语言（同 app-1.js TIER_META 的教训）。
const _HZ_CN = {
  get "6mo"() { return vpL("6个月","6mo"); },
  get "1y"()  { return vpL("1年","1y"); },
  get "3y"()  { return vpL("3年","3y"); },
  get "5y"()  { return vpL("5年","5y"); },
  get "10y"() { return vpL("10年","10y"); },
};
const _HZ_COLORS = { SP500: "#3498db", NASDAQ: "#2ecc71", SOX: "#e67e22" };

function renderHorizonView() {
  const hs = SIGNALS?.horizon_stats;
  if (!hs?.indices) return;

  // ① 分组柱状图：P(涨) by 持有期 × 指数
  const traces = Object.entries(hs.indices).map(([key, idx]) => ({
    type: "bar", name: vpL(`${idx.label}（${idx.start.slice(0,4)}起）`, `${idx.label} (since ${idx.start.slice(0,4)})`),
    x: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => _HZ_CN[h]),
    y: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => +(idx.horizons[h].p_positive * 100).toFixed(1)),
    marker: { color: _HZ_COLORS[key] || "#888" },
    text: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => (idx.horizons[h].p_positive * 100).toFixed(0) + "%"),
    textposition: "outside", cliponaxis: false,
    hovertemplate: vpL("<b>%{x}</b> " + idx.label + "<br>历史上涨概率 %{y}%<extra></extra>",
                        "<b>%{x}</b> " + idx.label + "<br>Historical up-probability %{y}%<extra></extra>"),
  }));
  Plotly.newPlot("chart-horizon", traces, {
    ...DARK, barmode: "group",
    yaxis: { ...DARK.yaxis, title: vpL("历史上涨概率 (%)","Historical up-probability (%)"), range: [0, 108] },
    xaxis: { ...DARK.xaxis, type: "category" },
    legend: { orientation: "h", y: 1.08 },
    margin: { t: 30, b: 40, l: 55, r: 15 },
    shapes: [{ type: "line", x0: -0.5, x1: 4.5, y0: 50, y1: 50,
               line: { color: "#888", dash: "dot", width: 1 } }],
    annotations: [{ x: 4.4, y: 52, text: vpL("抛硬币线","Coin-flip line"), showarrow: false,
                    font: { color: "#888", size: 10 } }],
  }, { responsive: true });

  // ② 每指数明细表
  const fm = v => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
  const tables = Object.values(hs.indices).map(idx => {
    const rows = _HZ_ORDER.filter(h => idx.horizons[h]).map(h => {
      const r = idx.horizons[h];
      const pc = r.p_positive >= 0.9 ? "#27ae60" : r.p_positive >= 0.75 ? "#2ecc71"
               : r.p_positive >= 0.65 ? "#f1c40f" : "#e67e22";
      return `<tr style="border-top:1px solid var(--border-faint);">
        <td style="padding:.3rem .5rem;font-weight:600;">${_HZ_CN[h]}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:${pc};font-weight:700;">${(r.p_positive*100).toFixed(0)}%</td>
        <td style="padding:.3rem .5rem;text-align:right;">${fm(r.ann_median)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${fm(r.ann_p25)} ~ ${fm(r.ann_p75)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:#e74c3c;">${fm(r.worst_total)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${(r.p_loss_gt_20*100).toFixed(0)}%</td>
      </tr>`;
    }).join("");
    return `<div style="margin-bottom:1rem;">
      <div style="font-size:0.85rem;font-weight:700;margin-bottom:.3rem;">
        ${vpD(idx,"label")} <span style="color:var(--muted);font-weight:400;font-size:0.72rem;">${idx.start.slice(0,4)}–${idx.end.slice(0,4)} · ${vpL(`${idx.years}年`, `${idx.years}y`)}</span></div>
      <table style="width:100%;border-collapse:collapse;font-size:0.78rem;">
        <thead><tr style="color:var(--muted);">
          <th style="text-align:left;padding:.25rem .5rem;">${vpL("持有期","Holding period")}</th>
          <th style="text-align:right;padding:.25rem .5rem;">${vpL("P(涨)","P(up)")}</th>
          <th style="text-align:right;padding:.25rem .5rem;">${vpL("年化中位","Ann. median")}</th>
          <th style="text-align:right;padding:.25rem .5rem;">${vpL("年化 25~75 分位","Ann. 25th–75th pct")}</th>
          <th style="text-align:right;padding:.25rem .5rem;">${vpL("最差总回报","Worst total return")}</th>
          <th style="text-align:right;padding:.25rem .5rem;">${vpL("P(亏&gt;20%)","P(loss&gt;20%)")}</th>
        </tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("");
  document.getElementById("horizon-tables").innerHTML = tables;

  document.getElementById("horizon-honesty").innerHTML =
    `<strong>${vpL("读这张表的正确姿势：","How to read this table correctly:")}</strong>${((vpLang() === "en" && hs.honesty_en) || hs.honesty || []).map(h => `<br>· ${h}`).join("")}`;

  renderHorizonStocks();
}

// 观察池长期质量表（依赖 STOCKS，可能晚于本视图渲染 → 两边都调一次，幂等）
function renderHorizonStocks() {
  const el = document.getElementById("horizon-stocks");
  if (!el || !STOCKS?.stocks) return;
  const rows = Object.entries(STOCKS.stocks).map(([sym, s]) => {
    const st = s.stats;
    const c = v => v == null ? "—"
      : `<span style="color:${v >= 0 ? "#2ecc71" : "#e74c3c"}">${v > 0 ? "+" : ""}${v}%</span>`;
    return `<tr style="border-top:1px solid var(--border-faint);">
      <td style="padding:.3rem .5rem;font-weight:600;">${sym}<span style="color:var(--muted);font-weight:400;font-size:0.68rem;"> ${s.label}</span></td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.ytd)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.chg_1y)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.from_high_52w)}</td>
      <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${st.vol20_ann}%</td>
      <td style="padding:.3rem .5rem;text-align:center;">${st.above_ma200 ? '<span style="color:#2ecc71">✓</span>' : '<span style="color:#e74c3c">✗</span>'}</td>
    </tr>`;
  }).join("");
  el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:0.78rem;">
    <thead><tr style="color:var(--muted);">
      <th style="text-align:left;padding:.25rem .5rem;">${vpL("股票","Stock")}</th>
      <th style="text-align:right;padding:.25rem .5rem;">YTD</th>
      <th style="text-align:right;padding:.25rem .5rem;">${vpL("近1年","Past 1y")}</th>
      <th style="text-align:right;padding:.25rem .5rem;">${vpL("距52周高点","From 52w high")}</th>
      <th style="text-align:right;padding:.25rem .5rem;">${vpL("年化波动","Ann. volatility")}</th>
      <th style="text-align:center;padding:.25rem .5rem;">${vpL("MA200上方","Above MA200")}</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// ── 🔄 手动刷新：重新拉取全部 JSON 并重渲染（不整页刷新，滚动位置和视图保留）──
let _refreshing = false;
async function refreshData(btn) {
  if (_refreshing) return;
  _refreshing = true;
  if (btn) btn.textContent = "⏳";
  try {
    // 清空懒渲染缓存，已打开过的子标签下次点击时用新数据重画
    try { _calTabRendered.clear(); } catch(e) {}
    try { _mainTabRendered.clear(); } catch(e) {}
    try { if (typeof _mvTabRendered !== "undefined") _mvTabRendered.clear(); } catch(e) {}
    await init();
    renderAll();
    if (btn) { btn.textContent = vpL("✓ 已更新","✓ Updated"); setTimeout(() => btn.textContent = vpL("🔄 刷新","🔄 Refresh"), 2000); }
  } catch(e) {
    console.warn("refreshData 失败", e);
    if (btn) { btn.textContent = vpL("✗ 失败","✗ Failed"); setTimeout(() => btn.textContent = vpL("🔄 刷新","🔄 Refresh"), 2500); }
  } finally {
    _refreshing = false;
  }
}

// 📡 数据新鲜度徽章：读各源时间戳 → "几分钟前 + 美东盘中/休市(均自动刷新)"，让实时性一眼可见
async function loadDataFreshness() {
  const el = document.getElementById("data-freshness");
  if (!el) return;
  const g = async f => { try { const r = await fetch(f + "?_=" + Date.now()); return r.ok ? await r.json() : null; } catch (e) { return null; } };
  const [q, n, h] = await Promise.all([g("quotes.json"), g("news.json"), g("data_health.json")]);
  const now = Date.now();
  const ago = t => { if (!t) return null; const m = Math.round((now - t) / 60000); if (m < 1) return vpL("刚刚","just now"); if (m < 60) return vpL(m + " 分钟前", m + "m ago"); const h = m / 60; return h < 24 ? vpL(Math.round(h) + " 小时前", Math.round(h) + "h ago") : vpL(Math.round(h / 24) + " 天前", Math.round(h / 24) + "d ago"); };
  const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
  let hh = +p.find(x => x.type === "hour").value; if (hh === 24) hh = 0;
  const mins = hh * 60 + +p.find(x => x.type === "minute").value;
  const weekday = !["Sat", "Sun"].includes(p.find(x => x.type === "weekday").value);
  const open = weekday && mins >= 570 && mins < 960;   // 美东 9:30–16:00
  const qT = q && q.generated ? Date.parse(q.generated) : 0;
  const nT = n && n.updated ? Date.parse(n.updated.replace(" UTC", "Z").replace(" ", "T")) : 0;
  const status = open ? vpL("🟢 美股盘中 · 报价每 10 分钟自动刷新","🟢 US market open · quotes auto-refresh every 10 min")
    : (weekday ? vpL("⚪ 盘前/盘后休市 · 开盘(美东9:30)后自动刷新","⚪ Pre/post-market closed · auto-refreshes after open (9:30am ET)")
              : vpL("⚪ 周末休市 · 下个交易日自动刷新","⚪ Weekend closed · auto-refreshes next trading day"));
  const stale = open && qT && (now - qT > 30 * 60000);
  const hs = h && h.summary;
  const health = hs ? ` · ${vpL("数据源","sources")} ${Number(hs.ok || 0)}/${Number(hs.total || 0)} live`
    + (hs.cache ? ` · ${vpL("缓存","cached")} ${Number(hs.cache)}` : "")
    + (hs.stale ? ` · ${vpL("过期","stale")} ${Number(hs.stale)}` : "")
    + (hs.missing ? ` · ${vpL("缺失","missing")} ${Number(hs.missing)}` : "") : "";
  _dataHealth = h;   // 存给"数据源详情"抽屉用
  const _dhDrawer = document.getElementById("data-health-drawer");
  const _dhOpen = _dhDrawer && !_dhDrawer.hidden;
  el.innerHTML = `📡 ${vpL("报价","Quotes")} ${ago(qT) || "—"}${ago(nT) ? " · " + vpL("要闻 ","news ") + ago(nT) : ""} · ${status}`
    + health
    + (stale ? ` <span style="color:#e67e22">${vpL("⚠ 盘中超 30 分未刷新，CI 可能异常","⚠ No refresh for 30+ min during market hours — CI may be malfunctioning")}</span>` : "")
    + (h && h.sources ? ` <span class="dh-toggle" role="button" tabindex="0" aria-expanded="${_dhOpen ? "true" : "false"}" style="cursor:pointer;color:var(--accent,#58a6ff);text-decoration:underline dotted;">${_dhOpen ? vpL("▴ 收起","▴ Collapse") : vpL("▾ 数据源详情","▾ Data-source details")}</span>` : "");
  const _tog = el.querySelector(".dh-toggle");
  if (_tog) {
    _tog.addEventListener("click", toggleDataHealthDrawer);
    _tog.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleDataHealthDrawer(); } });
  }
  if (_dhOpen) _dhDrawer.innerHTML = renderDataHealthDrawer();   // 刷新时同步抽屉内容
}

// 📡 数据源详情抽屉：点徽章 → 逐源 live/缓存/过期 + 最新日期/滞后（problems 排前）
let _dataHealth = null;

function toggleDataHealthDrawer() {
  const d = document.getElementById("data-health-drawer");
  if (!d) return;
  d.hidden = !d.hidden;
  if (!d.hidden) d.innerHTML = renderDataHealthDrawer();
  const tog = document.querySelector("#data-freshness .dh-toggle");
  if (tog) { tog.textContent = d.hidden ? vpL("▾ 数据源详情","▾ Data-source details") : vpL("▴ 收起","▴ Collapse"); tog.setAttribute("aria-expanded", String(!d.hidden)); }
}

function renderDataHealthDrawer() {
  const h = _dataHealth;
  if (!h || !h.sources) return `<span style="color:var(--muted);font-size:.78rem;">${vpL("数据源详情暂不可用","Data-source details unavailable")}</span>`;
  const isLive = s => s.status === "ok" && /^live/.test(String(s.source || ""));
  const items = Object.values(h.sources);
  items.sort((a, b) => (isLive(a) - isLive(b))
    || String(a.kind).localeCompare(String(b.kind)) || String(a.name).localeCompare(String(b.name)));
  const tag = s => {
    if (s.status !== "ok") return [String(s.status || vpL("异常","error")), "#e74c3c"];
    if (String(s.source) === "cache") return [vpL("缓存","cached"), "#f39c12"];
    if (/^live/.test(String(s.source || ""))) return ["live", "#2ecc71"];
    return [String(s.source || "?"), "#8b949e"];
  };
  const rows = items.map(s => {
    const [lbl, col] = tag(s);
    const stale = s.age_days != null && s.stale_after_days != null && s.age_days > s.stale_after_days;
    const age = s.age_days == null ? "" : ` · ${Number(s.age_days)}d`;
    return `<tr style="border-top:1px solid var(--border-faint);">`
      + `<td style="padding:.2rem .5rem;color:var(--text);">${esc(s.name)}</td>`
      + `<td style="padding:.2rem .5rem;color:var(--muted);font-size:.72rem;">${esc(s.provider || "")}</td>`
      + `<td style="padding:.2rem .5rem;text-align:center;color:${col};">${esc(lbl)}</td>`
      + `<td style="padding:.2rem .5rem;text-align:right;color:${stale ? "#e67e22" : "var(--muted)"};white-space:nowrap;">${esc(s.last_date || "—")}${age}</td>`
      + `</tr>`;
  }).join("");
  const sm = h.summary || {};
  const gen = String(h.generated || "").slice(0, 16).replace("T", " ");
  return `<div style="font-size:.72rem;color:var(--muted);margin:0 0 .35rem;">${vpL(`共 ${Number(sm.total || 0)} 源`, `${Number(sm.total || 0)} sources total`)} · live ${Number(sm.ok || 0)}`
    + (sm.cache ? ` · ${vpL("缓存","cached")} ${Number(sm.cache)}` : "")
    + (sm.stale ? ` · ${vpL("过期","stale")} ${Number(sm.stale)}` : "")
    + (sm.missing ? ` · ${vpL("缺失","missing")} ${Number(sm.missing)}` : "")
    + (gen ? ` · ${vpL("生成","generated")} ${esc(gen)} UTC` : "")
    + vpL("（cache/过期排在前）</div>","(cache/stale sorted first)</div>")
    + `<table style="width:100%;border-collapse:collapse;font-size:.78rem;"><thead><tr style="color:var(--muted);font-size:.7rem;">`
    + `<th style="padding:.2rem .5rem;text-align:left;">${vpL("数据源","Source")}</th><th style="padding:.2rem .5rem;text-align:left;">${vpL("提供方","Provider")}</th>`
    + `<th style="padding:.2rem .5rem;text-align:center;">${vpL("来源","Origin")}</th><th style="padding:.2rem .5rem;text-align:right;">${vpL("最新 · 滞后","Latest · lag")}</th>`
    + `</tr></thead><tbody>${rows}</tbody></table>`;
}

// 📈 观点/预测：读 outlook.json，纳指方向 + 个股看好/看淡 + 免责（用户授权的出格区）。
function loadOutlook() {
  const el = document.getElementById("outlook");
  if (!el) return;
  fetch("outlook.json?_=" + Date.now()).then(r => r.ok ? r.json() : null).then(d => {
    if (!d) return;
    const ic = d.index_call;
    const up = "var(--green,#2ecc71)", dn = "#e74c3c";
    // p.view/ic.call 是后端 outlook.json 的枚举值("看好"/"看淡"/"看涨"/"看跌")，比较逻辑保持匹配原文不变；
    // 仅展示文本按语言可读地映射，不影响判断。
    const viewLabel = v => v === '看好' ? vpL('看好','Bullish') : v === '看淡' ? vpL('看淡','Bearish') : v;
    const callLabel = c => c === '看涨' ? vpL('看涨','Bullish') : c === '看跌' ? vpL('看跌','Bearish') : c;
    const picks = (arr) => (arr || []).map(p =>
      `<li style="margin:.25rem 0;"><b>${esc(p.symbol)}</b> <span style="color:${p.view === '看好' ? up : dn};font-weight:600;">${esc(viewLabel(p.view))}</span> <span style="color:var(--muted);font-size:.78rem;">${esc(p.reason)}</span></li>`).join("");
    // P1-7 coin-flip band：|prob−50%|≤4 → 不加粗绿红、显"≈掷硬币"（复用 index.html nasdaqPlain 的阈值/措辞）
    let icHtml = "";
    if (ic) {
      const pct = ic.prob != null ? Math.round(ic.prob * 100) : null;
      const coin = pct != null && Math.abs(pct - 50) <= 4;
      const callStyle = coin ? "color:var(--muted);font-weight:400;" : `color:${ic.call === '看涨' ? up : dn};`;
      const note = pct == null ? "" : (coin ? vpL("≈掷硬币，无验证优势，别当真","≈ coin-flip, no proven edge — don't take it seriously") : vpL("短期方向谁都难测，仅参考","Short-term direction is hard for anyone to call — reference only"));
      icHtml = `<div style="margin:.2rem 0 .5rem;font-size:1rem;">🎯 <b>${esc(ic.target)}${esc(ic.horizon)}${vpL("方向：","direction: ")}<span style="${callStyle}">${esc(callLabel(ic.call))}</span></b> <span style="color:var(--muted);font-size:.76rem;">${esc(ic.basis)}</span>`
        + (note ? ` <span style="color:var(--muted);font-size:.76rem;">（${note}）</span>` : "")
        + `</div>`;
    }
    el.innerHTML =
      icHtml
      + `<div style="display:flex;gap:2rem;flex-wrap:wrap;">`
      + `<div><div style="font-weight:600;margin-bottom:.2rem;">👍 ${vpL("看好","Bullish")}</div><ul style="margin:0;padding-left:1.1rem;list-style:none;">${picks(d.bullish)}</ul></div>`
      + `<div><div style="font-weight:600;margin-bottom:.2rem;">👎 ${vpL("看淡","Bearish")}</div><ul style="margin:0;padding-left:1.1rem;list-style:none;">${picks(d.bearish)}</ul></div>`
      + `</div>`
      + (d.disclaimer ? `<div style="font-size:.7rem;color:var(--muted);margin-top:.5rem;border-top:1px solid var(--border-faint);padding-top:.3rem;">${esc(d.disclaimer)}</div>` : "");
  }).catch(() => {});
}

// 🎲 试胆区：读 tipjar.json，玩具预测器的最新一注 + 公开战绩(≈掷硬币) + 满屏免责。
function loadTipjar() {
  const el = document.getElementById("tipjar");
  if (!el) return;
  fetch("tipjar.json?_=" + Date.now()).then(r => r.ok ? r.json() : null).then(d => {
    if (!d || d.hit_rate == null) return;
    const panel = document.getElementById("tipjar-panel");
    if (panel) panel.style.display = "";
    const lt = d.latest;
    const rec = (d.recent || []).slice().reverse().map(r => {
      const mk = r.hit == null ? "·" : (r.hit ? "✓" : "✗");
      const c = r.hit == null ? "var(--muted)" : (r.hit ? "var(--green,#2ecc71)" : "#e74c3c");
      return `<span style="color:${c};" title="${vpL(`${esc(r.as_of)} 赌${esc(r.call)}→实${esc(r.actual || '?')}`, `${esc(r.as_of)} bet ${esc(r.call)} → actual ${esc(r.actual || '?')}`)}">${mk}</span>`;
    }).join(" ");
    const cav = esc(vpD(d,"caveat") || "").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    el.innerHTML =
      `<div style="font-size:.76rem;color:var(--muted);margin:.1rem 0;">${vpL("规则：","Rule: ")}${esc(vpD(d,"rule"))}</div>`
      + (lt ? `<div style="margin:.35rem 0;">${vpL(`最新一注（${esc(lt.as_of)} 收盘后）：纳指次日`, `Latest bet (after ${esc(lt.as_of)} close): Nasdaq next day`)} <b style="font-size:1.05rem;">${lt.call === 'UP' ? vpL('📈 赌涨','📈 Bet up') : vpL('📉 赌跌','📉 Bet down')}</b></div>` : "")
      + `<div style="margin:.4rem 0;font-size:.95rem;">${vpL("滚动战绩","Rolling record")} <b>${Number(d.hits)}/${Number(d.n_scored)} = ${Number(d.hit_rate)}%</b> <span style="color:var(--muted);font-size:.72rem;">${vpL(`≈50% 掷硬币才是常态 · 近20注 ${Number(d.hit_rate_last20)}% 只是噪声`, `≈50% coin-flip is the normal baseline · last 20 bets ${Number(d.hit_rate_last20)}% is just noise`)}</span></div>`
      + (rec ? `<div style="margin:.3rem 0;font-size:.8rem;">${vpL("近 12 注：","Last 12 bets: ")}${rec}</div>` : "")
      + `<div style="font-size:.68rem;color:var(--muted);margin-top:.4rem;border-top:1px solid var(--border-faint);padding-top:.3rem;">${cav}</div>`;
  }).catch(() => {});
}

// 📋 今日摘要：读 digest.json，渲染三层(事实/留意/探索)。esc 转义 + 仅把 **x** 渲成粗体。
function loadDigest() {
  const el = document.getElementById("daily-digest");
  if (!el) return;
  fetch("digest.json?_=" + Date.now()).then(r => r.ok ? r.json() : null).then(d => {
    if (!d || !d.tier1_facts) return;
    const panel = document.getElementById("daily-digest-panel");
    if (panel) panel.style.display = "";
    const li = arr => (arr || []).map(x => `<li style="margin:.2rem 0;line-height:1.5;">${esc(x).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</li>`).join("");
    // 三层列表各自取 *_en(英文模式且有英文时);缺英文回落中文,不会因漏译而空列表
    const pick = k => ((vpLang() === "en" && d[k + "_en"]?.length) ? d[k + "_en"] : (d[k] || []));
    el.innerHTML =
      `<div style="font-size:.72rem;color:var(--muted);margin-bottom:.2rem;">${esc(d.date || "")}</div>`
      + `<div style="font-weight:600;font-size:.82rem;margin:.3rem 0 .1rem;">${vpL("① 今天什么变了","① What changed today")}</div><ul style="margin:0;padding-left:1.1rem;">${li(pick("tier1_facts"))}</ul>`
      + (pick("tier2_watch").length ? `<div style="font-weight:600;font-size:.82rem;margin:.45rem 0 .1rem;">${vpL("② 值得看一眼","② Worth a glance")} <span style="font-weight:400;color:var(--muted);font-size:.66rem;">${vpL("描述·非预测","descriptive · not a prediction")}</span></div><ul style="margin:0;padding-left:1.1rem;">${li(pick("tier2_watch"))}</ul>` : "")
      + (pick("tier3_explore").length ? `<div style="font-weight:600;font-size:.82rem;margin:.45rem 0 .1rem;color:var(--muted);">${vpL("③ 探索","③ Exploratory")} <span style="font-weight:400;font-size:.66rem;">${vpL("很可能是噪声·不可交易","likely noise · not tradable")}</span></div><ul style="margin:0;padding-left:1.1rem;color:var(--muted);">${li(pick("tier3_explore"))}</ul>` : "")
      + (d.caveat ? `<div style="font-size:.66rem;color:var(--muted);margin-top:.4rem;border-top:1px solid var(--border-faint);padding-top:.3rem;">${esc(vpD(d,"caveat"))}</div>` : "");
  }).catch(() => {});
}

// 新手引导横幅:首次访问显示,关闭后 localStorage 记住不再弹
function dismissOnboarding() {
  const el = document.getElementById("onboarding");
  if (el) el.style.display = "none";
  try { localStorage.setItem("alphalab_ob_seen", "1"); } catch (e) { /* 隐私模式忽略 */ }
}
function initOnboarding() {
  const el = document.getElementById("onboarding");
  if (!el) return;
  let seen = false;
  try { seen = localStorage.getItem("alphalab_ob_seen") === "1"; } catch (e) { /* 隐私模式当未看过 */ }
  if (!seen) el.style.display = "";   // 首次访问才显示
}

// ═══════════════════════════════════════════════════════
//  顶层视图切换（今日/买卖时机/实验/研究/我的）
// ═══════════════════════════════════════════════════════
const VIEWS = ["today", "outlook", "plan", "longterm", "lab", "research", "registry", "quant", "mine"];
function switchView(name, btn) {
  document.querySelectorAll(".view-nav .view-btn").forEach(b => {
    const on = b === btn;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  VIEWS.forEach(v => {
    const sec = document.getElementById("view-" + v);
    if (sec) sec.style.display = (v === name) ? "" : "none";
  });
  localStorage.setItem("alpha_view", name);
  // Plotly 在 display:none 里算不出宽度，切换后重算本视图全部图表
  requestAnimationFrame(() => resizeChartsIn(document.getElementById("view-" + name)));
}

// ═══════════════════════════════════════════════════════
//  IPO 周期视角（SPCX 面板子块）：超级IPO上市后12个月大盘最大回撤
//  数值为历史约值（指数日线口径），用作情绪温度计而非精确统计
// ═══════════════════════════════════════════════════════
// mkt(市场简称)/中石油A 的 name 用 getter：MEGA_IPOS 是模块级 const，只在脚本加载时构造一次；
// 若烘成静态字符串，语言切换后 renderIPOCycle() 重跑也读不到新语言（同 _HZ_CN/app-1.js TIER_META 的教训）。
const MEGA_IPOS = [
  { name:"NTT 1987-02",        get mkt(){ return vpL("日经","Nikkei"); },   dd:-21, top:true  },
  { name:"Blackstone 2007-06", get mkt(){ return vpL("标普","S&P"); },      dd:-18, top:true  },
  { get name(){ return vpL("中石油A 2007-11","PetroChina-A 2007-11"); }, get mkt(){ return vpL("上证","Shanghai Comp"); }, dd:-70, top:true  },
  { name:"Visa 2008-03",       get mkt(){ return vpL("标普","S&P"); },      dd:-48, top:false },
  { name:"Glencore 2011-05",   get mkt(){ return vpL("富时","FTSE"); },     dd:-17, top:true  },
  { name:"Facebook 2012-05",   get mkt(){ return vpL("标普","S&P"); },      dd:-10, top:false },
  { name:"Alibaba 2014-09",    get mkt(){ return vpL("标普","S&P"); },      dd:-10, top:false },
  { name:"Coinbase 2021-04",   get mkt(){ return vpL("BTC","BTC"); },       dd:-55, top:true  },
  { name:"Rivian 2021-11",     get mkt(){ return vpL("纳指","Nasdaq"); },   dd:-33, top:true  },
  { name:"Google 2004-08",     get mkt(){ return vpL("标普","S&P"); },      dd:-7,  top:false },
];
// ── 因子样本外尸检（P2-5，研究面板）──
function renderFactorAudit() {
  const el = document.getElementById("factor-audit");
  if (!el) return;
  const fa = SIGNALS?.factor_audit;
  if (!fa) { el.innerHTML = `<span style="color:var(--muted)">${vpL("运行一次完整流水线后显示","Available after a full pipeline run")}</span>`; return; }
  // VC/SEGC 的 key 是后端枚举值(INFORMATIVE/FRAGILE/... 及 sg.status 的中文枚举)，用于匹配 f.verdict/sg.status，
  // 保持原文不改；只有数组第二个元素(展示用短标签)走 vpL。
  const VC = { INFORMATIVE: ["#2ecc71", vpL("稳健","Robust")], FRAGILE: ["#f39c12", vpL("regime依赖","Regime-dependent")],
               MISLEADING: ["#e74c3c", vpL("反向误导","Reverse/misleading")], NOISE: ["#8b949e", vpL("噪声","Noise")] };
  const esc2 = s => esc(s);
  const SEGC = { "现代仍有效": ["#2ecc71", vpL("仍有效","Still holds")], "现代已淡": ["#f39c12", vpL("已淡·疑套利","Faded · likely arbitraged")],
                 "现代检验力不足": ["#8b949e", vpL("样本不足","Underpowered")], "两段均无显著边际": ["#6e7681", vpL("本无边际","No edge either way")] };
  const rows = (fa.factors || []).map(f => {
    const [c, txt] = VC[f.verdict] || ["#8b949e", f.verdict];
    const hd = f.holdout_diff_pp == null ? "—" : (f.holdout_diff_pp > 0 ? "+" : "") + f.holdout_diff_pp;
    const sgn = f.n_folds_signed ? `${Math.round((f.sign_agree_frac||0)*f.n_folds_signed)}/${f.n_folds_signed}` : "—";
    const sg = f.segment;
    let segHtml = `<span style="color:var(--muted);">—</span>`;
    if (sg) {
      const [sc, sl] = SEGC[sg.status] || ["#8b949e", sg.status];
      const rd = sg.recent_diff_pp == null ? "" :
        ` <span style="color:var(--muted);font-size:.72rem">${sg.recent_diff_pp>0?"+":""}${Number(sg.recent_diff_pp)}pp</span>`;
      const tip = vpL(`全段 ${sg.full_diff_pp>0?"+":""}${Number(sg.full_diff_pp)}pp(p=${Number(sg.full_p)}) → 最近${sg.window_years}年触发${sg.recent_n_fires}次`,
                       `Full period ${sg.full_diff_pp>0?"+":""}${Number(sg.full_diff_pp)}pp (p=${Number(sg.full_p)}) → fired ${sg.recent_n_fires} times in the last ${sg.window_years}y`);
      segHtml = `<span style="color:${sc};font-weight:600;" title="${esc2(tip)}">${sl}</span>${rd}`;
    }
    return `<tr style="border-top:1px solid var(--border-faint);">
      <td style="padding:.25rem .5rem;">${esc2(f.name)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:var(--muted);">${f.assumed_dir>0?vpL("看涨","Bullish"):vpL("看跌","Bearish")}</td>
      <td style="padding:.25rem .5rem;text-align:right;">${f.dev_diff_pp>0?"+":""}${Number(f.dev_diff_pp)}pp</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--muted);">${Number(f.dev_p_boot)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:var(--muted);" title="${vpL('逐折符号一致折数','Number of folds with sign agreement')}">${sgn}</td>
      <td style="padding:.25rem .5rem;text-align:right;">${hd}pp</td>
      <td style="padding:.25rem .5rem;text-align:center;"><span style="color:${c};font-weight:600;">${txt}</span></td>
      <td style="padding:.25rem .5rem;text-align:center;">${segHtml}</td>
    </tr>`;
  }).join("");
  const s = fa.summary || {};
  const probe = fa.target_probe || {};
  const dirAuc = probe.direction_auc_pooled_2012_2024, volAuc = probe.vol_auc_holdout;
  const baseHold = fa.base_rate_holdout != null ? Math.round(fa.base_rate_holdout*100) : null;
  const df = fa.deflation;   // 多重检验校正（反过拟合）；缺失则优雅不显示
  // df.note/df.caveat 是后端 JSON 数据值(自由文本)，不译(同 event_study/bear_markets 先例)；周边前端撰写的说明句译。
  const deflHtml = df ? vpL(`<div class="insight" style="margin-top:.7rem;border-left:3px solid #8b949e;">
      <strong>🎲 多重检验校正（反过拟合 / 数据挖掘校正）：</strong>测了 ${df.n_factors} 个因子，方向一致且原始 p&lt;${df.q_level} 有 ${df.n_raw_dir_sig_p10} 个；
      依赖稳健校正后 <b style="color:#2ecc71">BY(保守)留 ${df.n_by_sig_q10}</b> / BH(乐观)留 ${df.n_bh_sig_q10}，最佳因子 Bonferroni(FWER) p=${df.best_factor_bonferroni_p}。
      ${df.note ? `<br><span style="color:var(--muted);font-size:0.76rem">${esc2(df.note)}</span>` : ""}
      ${df.caveat ? `<br><span style="color:var(--muted);font-size:0.72rem">⚠ ${esc2(df.caveat)}</span>` : ""}
    </div>`, `<div class="insight" style="margin-top:.7rem;border-left:3px solid #8b949e;">
      <strong>🎲 Multiple-testing correction (anti-overfitting / data-mining correction):</strong>Tested ${df.n_factors} factors; ${df.n_raw_dir_sig_p10} had a consistent sign and a raw p&lt;${df.q_level};
      after a dependency-robust correction, <b style="color:#2ecc71">BY (conservative) keeps ${df.n_by_sig_q10}</b> / BH (optimistic) keeps ${df.n_bh_sig_q10}; the best factor's Bonferroni (FWER) p=${df.best_factor_bonferroni_p}.
      ${df.note ? `<br><span style="color:var(--muted);font-size:0.76rem">${esc2(df.note)}</span>` : ""}
      ${df.caveat ? `<br><span style="color:var(--muted);font-size:0.72rem">⚠ ${esc2(df.caveat)}</span>` : ""}
    </div>`) : "";
  const sl = fa.segment_lens;   // 时间衰减透镜（口径异于 OOS：in-sample 描述原始边际是否随时间消失）
  const segNote = sl ? vpL(`<div class="insight" style="margin-top:.7rem;border-left:3px solid #f39c12;">
      <strong>🕰️ 现代段透镜（最近 ${sl.window_years} 年 vs 全段 · 描述性）：</strong>原始边际近年仍在 ${sl.n_alive} 个、
      <b style="color:#f39c12">已淡(疑被套利) ${sl.n_faded} 个</b>、现代样本不足 ${sl.n_underpowered} 个。
      <br><span style="color:var(--muted);font-size:0.76rem">${esc2(sl.method||"")}</span>
      <br><span style="color:var(--muted);font-size:0.74rem">⚠ 「现代仍有效」=<b>原始边际</b>近年还在，<b>不等于可交易</b>——须对照同行「裁决」列：如 BTC 动量段位仍有效、但 OOS 裁决=FRAGILE(2017-21 加密牛 regime，不可外推)。${esc2(sl.note||"")}</span>
    </div>`, `<div class="insight" style="margin-top:.7rem;border-left:3px solid #f39c12;">
      <strong>🕰️ Modern-window lens (last ${sl.window_years}y vs. the full period · descriptive):</strong>Of the original edges, ${sl.n_alive} are still present in recent years,
      <b style="color:#f39c12">${sl.n_faded} have faded (possibly arbitraged away)</b>, and ${sl.n_underpowered} are underpowered in the modern window.
      <br><span style="color:var(--muted);font-size:0.76rem">${esc2(sl.method||"")}</span>
      <br><span style="color:var(--muted);font-size:0.74rem">⚠ "Still holds in the modern window" = the <b>original edge</b> is still present in recent years, <b>not the same as tradable</b> — cross-check the "verdict" column: e.g. BTC momentum's segment still holds, but the OOS verdict = FRAGILE (concentrated in the 2017-21 crypto bull regime, not extrapolatable). ${esc2(sl.note||"")}</span>
    </div>`) : "";
  const methodIntro = vpL(
    `方法：测试折拼接为样本外序列算「触发胜率−基率」（块自助 CI）；purged+embargo 扩窗用于跨折<b>符号稳定性</b>检验；
      再用<b>从未参与训练的 2024-2026</b>做终审。「符号」列=逐折方向一致的折数（全一致才算稳健）。
      看跌因子压低胜率是<b>对</b>，不是有害。`,
    `Method: test folds are concatenated into an out-of-sample series to compute "trigger win rate − base rate" (block-bootstrap CI); purged+embargo expanding windows test <b>cross-fold sign stability</b>;
      then a final check uses <b>2024-2026 data that never participated in training</b>. The "sign" column = number of folds where the direction agrees (only counts as robust if all folds agree).
      A bearish factor that lowers the win rate is <b>correct</b>, not harmful.`
  );
  const insightMain = vpL(
    `<strong>结论：${s.informative ?? 0} 个因子样本外稳健，${s.fragile ?? 0} 个 regime 依赖，${s.noise ?? "?"} 个噪声，${s.misleading ?? 0} 个反向。</strong><br>
      <b>没有一个因子在所有 regime 上符号稳定</b>。最强的 <b style="color:#f39c12">BTC 20日动量</b>（涨/跌两向）拼接后高度显著
      （p≤0.08）、且在 2024-2026 确认，但逐折符号会翻——信号高度集中在 2017-2021 加密牛市，属 <b>regime 依赖，不可外推</b>。
      均线、RSI、波动率、隔夜动量等技术因子<b>全是噪声</b>。模型 AUC&lt;0.5 不是市场纯随机，
      而是没有跨 regime 稳定的因子 + 重复计数的日历效应。<br>
      <span style="color:var(--muted)">主观事件因子（${(fa.subjective_event_lrs||[]).join("、")}）无任何历史样本支撑，应标注或移出。
      ${baseHold!=null?`注：holdout(2024-2026)是 ${baseHold}% 上涨的强牛市单一 regime，对看涨因子的"方向不翻"确认力有限。`:""}</span><br><br>
      <strong>换靶子探针：</strong>方向 AUC 跨 regime 摆动（2012-2024 拼接 <b>${dirAuc ?? "?"}</b>，单一 2024-2026 ${probe.direction_auc_holdout ?? "?"}）——
      这种不稳定本身就是非平稳性；波动率 AUC <b style="color:#2ecc71">${volAuc ?? "?"}</b> 更高（单点 holdout，仍需多 regime 复核）。
      <b>数据倾向：把 ML/深度学习力气投向"预测波动率/市场状态"，而非"预测涨跌方向"。</b>`,
    `<strong>Conclusion: ${s.informative ?? 0} factors are OOS-robust, ${s.fragile ?? 0} are regime-dependent, ${s.noise ?? "?"} are noise, ${s.misleading ?? 0} are reversed.</strong><br>
      <b>Not a single factor has a sign that's stable across all regimes</b>. The strongest, <b style="color:#f39c12">BTC 20-day momentum</b> (both up/down directions), is highly significant once concatenated
      (p≤0.08) and confirmed in 2024-2026, but its sign flips fold to fold — the signal is heavily concentrated in the 2017-2021 crypto bull market, so it's <b>regime-dependent and not extrapolatable</b>.
      Technical factors like moving averages, RSI, volatility, and overnight momentum are <b>all noise</b>. Model AUC&lt;0.5 doesn't mean the market is pure randomness —
      it means there's no factor that's stable across regimes, plus double-counted calendar effects.<br>
      <span style="color:var(--muted)">Subjective event factors (${(fa.subjective_event_lrs||[]).join(", ")}) have no historical sample support at all and should be flagged or removed.
      ${baseHold!=null?`Note: the holdout (2024-2026) is a single strong-bull regime with ${baseHold}% up-days, so it has limited power to confirm bullish factors' "direction doesn't flip."`:""}</span><br><br>
      <strong>Switching targets — probe:</strong>Direction AUC swings across regimes (2012-2024 pooled <b>${dirAuc ?? "?"}</b>, single 2024-2026 holdout ${probe.direction_auc_holdout ?? "?"})——
      this instability is itself non-stationarity; volatility AUC <b style="color:#2ecc71">${volAuc ?? "?"}</b> is higher (single-point holdout, still needs multi-regime confirmation).
      <b>What the data suggests: point ML/deep-learning effort at "predicting volatility/market state," not "predicting up/down direction."</b>`
  );
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.7rem;">
      ${methodIntro}
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.72rem;">
        <th style="padding:.25rem .5rem;text-align:left;">${vpL("因子","Factor")}</th><th style="padding:.25rem .5rem;">${vpL("假设","Assumed dir.")}</th>
        <th style="padding:.25rem .5rem;text-align:right;">${vpL("开发集差","Dev-set diff")}</th><th style="padding:.25rem .5rem;text-align:right;">${vpL("块自助p","Block-boot p")}</th>
        <th style="padding:.25rem .5rem;">${vpL("符号","Sign")}</th>
        <th style="padding:.25rem .5rem;text-align:right;">holdout</th><th style="padding:.25rem .5rem;">${vpL("裁决","Verdict")}</th>
        <th style="padding:.25rem .5rem;" title="${vpL(`描述性：原始边际在最近${fa.segment_lens?.window_years||8}年还在不在(口径异于OOS裁决)`, `Descriptive: whether the original edge is still present in the last ${fa.segment_lens?.window_years||8}y (different basis from the OOS verdict)`)}">${vpL(`现代段(${fa.segment_lens?.window_years||8}年)`, `Modern window (${fa.segment_lens?.window_years||8}y)`)}</th>
      </tr></thead><tbody>${rows}</tbody>
    </table>
    <div class="insight" style="margin-top:.85rem;">
      ${insightMain}
    </div>${deflHtml}${segNote}`;
}

// ── 波动率状态预测原型（P2-6，研究面板）──
function renderVolModel() {
  const el = document.getElementById("vol-model");
  if (!el) return;
  const v = SIGNALS?.vol_model;
  if (!v) { el.innerHTML = `<span style="color:var(--muted)">${vpL("运行一次完整流水线后显示","Available after a full pipeline run")}</span>`; return; }
  const ho = v.holdout_auc, vix = v.holdout_vix_only_auc, dir = v.direction_auc_reference, gain = v.holdout_model_gain_over_vix;
  const vd = v.vol_direction;
  const bar = (auc, label, color) => {
    const pct = auc == null ? 0 : Math.max(0, Math.min(100, ((auc - 0.5) / 0.5) * 100));
    return `<div style="margin:.35rem 0;">
      <div style="display:flex;justify-content:space-between;font-size:0.78rem;">
        <span>${label}</span><span style="font-weight:700;color:${color}">${auc != null ? Number(auc).toFixed(3) : "—"}</span></div>
      <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;"></div></div>
    </div>`;
  };
  const imps = (v.importances || []).slice(0, 6).map(i =>
    `<tr style="border-top:1px solid var(--border-faint);"><td style="padding:.2rem .5rem;">${esc(i.feature)}</td>
     <td style="padding:.2rem .5rem;text-align:right;color:${i.importance>0?"#2ecc71":"var(--muted)"}">${i.importance>0?"+":""}${Number(i.importance)}</td></tr>`).join("");
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">
      ${vpL("靶子：","Target: ")}${esc(vpD(v,"target")||"")}。${vpL("模型：","Model: ")}${esc(vpD(v,"model")||"")}。<br>${esc(vpD(v,"method")||"")}
    </div>
    ${vd ? `
    <div style="font-size:0.82rem;font-weight:700;margin:.2rem 0 .3rem;">${vpL('① 波动率会"升还是降"？（一个被审查纠正的诚实教训）','① Will volatility "rise or fall"? (an honest lesson caught and corrected by review)')}</div>
    ${bar(vd.mechanical_null_auc, vpL("机械假象地板（打乱未来后基线仍有的 AUC）","Mechanical-illusion floor (AUC still present after shuffling the future)"), "#e67e22")}
    ${bar(vd.pooled_auc_naive_meanrev, vpL("自指基线(-当前波动)：大半是上面的假象","Self-referential baseline (−current vol): mostly the same illusion above"), "#9b59b6")}
    ${bar(vd.pooled_auc_model, vpL("模型(波动动态特征)：坐在同一假象台座上","Model (vol-dynamics features): sitting on the same illusory pedestal"), "#8b949e")}
    <div class="insight" style="margin:.5rem 0 1rem;">
      ${vpL(
        `<strong>⚠ 这里差点上当：rv20 同时在标签两侧（fwd&gt;rv20）又当特征，制造<b style="color:#e67e22">机械自指假象</b>——把未来打乱、毁掉一切真信号后，基线 AUC 仍≈${Number(vd.mechanical_null_auc).toFixed(2)}。</strong>
      所以 ${Number(vd.pooled_auc_model).toFixed(2)}/${Number(vd.pooled_auc_naive_meanrev).toFixed(2)} 这种"高 AUC"<b>大半是假象、不可交易</b>。
      唯一可解释的是模型 vs 同样自指基线之差 ${vd.model_vs_naive ? `= <b>${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}</b>（CI ${JSON.stringify(vd.model_vs_naive.ci95)}，p=${vd.model_vs_naive.p_boot}，<b>不显著</b>）` : ""}。
      <b>诚实结论：连波动率升降，用机械公平的对比也没找到稳健可利用信号。</b>`,
        `<strong>⚠ We almost got fooled here: rv20 sits on both sides of the label (fwd&gt;rv20) and is used as a feature, creating a <b style="color:#e67e22">mechanical self-referential illusion</b> — after shuffling the future and destroying every real signal, the baseline AUC is still ≈${Number(vd.mechanical_null_auc).toFixed(2)}.</strong>
      So a "high AUC" of ${Number(vd.pooled_auc_model).toFixed(2)}/${Number(vd.pooled_auc_naive_meanrev).toFixed(2)} is <b>mostly illusion, not tradable</b>.
      The only interpretable thing is the model vs. the same self-referential baseline's difference ${vd.model_vs_naive ? `= <b>${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}</b> (CI ${JSON.stringify(vd.model_vs_naive.ci95)}, p=${vd.model_vs_naive.p_boot}, <b>not significant</b>)` : ""}.
      <b>Honest conclusion: even for volatility rising/falling, a mechanically fair comparison found no robust exploitable signal.</b>`
      )}
      <span style="color:var(--muted)">${esc(vpD(vd,"note")||"")}</span>
    </div>` : ""}

    <div style="font-size:0.82rem;font-weight:700;margin:.2rem 0 .3rem;">${vpL('② 对照：预测波动率"绝对水平"（VIX 必然赢=同义反复）','② Comparison: predicting volatility\'s "absolute level" (VIX necessarily wins = tautology)')}</div>
    ${bar(ho, vpL("波动率水平·模型(12特征) · 终审","Vol level · model (12 features) · final holdout"), "#8b949e")}
    ${bar(vix, vpL("波动率水平·只看VIX · 终审","Vol level · VIX-only · final holdout"), "#9b59b6")}
    ${bar(dir, vpL("对照：涨跌方向（不可测）","Comparison: up/down direction (not predictable)"), "#e74c3c")}
    <div style="font-size:0.74rem;color:var(--muted);margin:.3rem 0 .6rem;">${vpL("条形=AUC相对0.5(随机)的优势。","Bars = AUC's edge over 0.5 (random).")}
      ${vpL(`水平靶子上模型只比裸看 VIX 高 ${gain ?? "?"}——VIX 就是波动率水平的市场报价，赢是同义反复，信息量低。`, `On the level target, the model only beats looking at raw VIX by ${gain ?? "?"} — VIX literally is the market's quote on the volatility level, so "winning" is a tautology with low information content.`)}</div>
    <div style="font-size:0.75rem;color:var(--muted);margin-bottom:.2rem;">${vpL("holdout 排列重要性（水平靶子）","Holdout permutation importance (level target)")}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.78rem;"><tbody>${imps}</tbody></table>
    <div class="insight" style="margin-top:.7rem;">
      ${vpL(
        `<strong>总结：波动率比涨跌方向可测得多；但要问对问题。</strong><br>
      预测<b>波动"水平"</b>→ VIX 必然赢（同义反复）；预测<b>波动"升降"</b>→ VIX 失效，真信号在<b>均值回归</b>里，
      模型只能再多挤出一丝且不 robust。启示：<b>选对靶子 + 市场已把容易的部分定价</b>，复杂模型很难再加价值。`,
        `<strong>Summary: volatility is far more predictable than up/down direction — but you have to ask the right question.</strong><br>
      Predicting the <b>"level"</b> of volatility → VIX necessarily wins (tautology); predicting <b>"rises/falls"</b> in volatility → VIX loses its edge and the real signal lives in <b>mean-reversion</b>,
      where the model can only squeeze out a little more, and not robustly. Takeaway: <b>pick the right target + the market has already priced in the easy part</b> — a fancier model struggles to add much value.`
      )}
      <span style="color:var(--muted)">${esc(vpD(v,"note")||"")}</span>
    </div>`;
}

// ── 事件影响一览（整合宏观日历 + 历史事件研究 + 诚实框架）──
function renderEventImpact() {
  const el = document.getElementById("event-impact");
  if (!el || !SIGNALS) return;
  const cal = SIGNALS.macro_calendar || [];
  const es = SIGNALS.event_study || {};
  const today = localDateStr();

  // ① 即将到来的调度型事件（宏观日历）——放大波动、方向无稳定偏向
  const upcoming = cal.filter(e => e.date >= today).slice(0, 8).map(e => {
    const d = new Date(e.date + "T00:00:00");
    const days = Math.round((d - new Date(today + "T00:00:00")) / 86400000);
    return `<div style="display:flex;justify-content:space-between;gap:.5rem;padding:.25rem .5rem;border-top:1px solid var(--border-faint);">
      <span>${esc(e.date)} <span style="color:var(--muted);font-size:0.72rem;">${days<=0?vpL("今天","today"):vpL(`约${days}天后`, `in ~${days}d`)}</span></span>
      <span style="color:var(--text);font-size:0.78rem;">${esc(vpD(e,"label"))}</span></div>`;
  }).join("") || `<div style="color:var(--muted);font-size:0.78rem;padding:.3rem .5rem;">${vpL("近期无已排程宏观事件","No scheduled macro events in the near term")}</div>`;

  // ② 历史事件类型反应——诚实呈现：小样本、样本内，去掉绿红方向色与裸 p 值
  // （绿红色=暗示可预测方向，裸 p 值=被读成"显著信号"，都违反铁律；胜率带基准对照）
  const rows = Object.entries(es).map(([k, v]) => {
    const ar = v.avg_return, smallN = (v.n || 0) < 15;
    return `<tr style="border-top:1px solid var(--border-faint);">
      <td style="padding:.25rem .5rem;">${esc(vpD(v,"label") || k)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:${smallN?"#e67e22":"var(--muted)"};" title="${vpL('样本量','Sample size')}">n=${esc(v.n)}${smallN?" ⚠":""}</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--text);">${ar>0?"+":""}${esc(ar)}%</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--muted);">${esc(v.win_rate)}% <span style="font-size:0.66rem;">(${vpL("基准","baseline")}${esc(v.base_win_rate)}%)</span></td>
    </tr>`;
  }).join("");

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">
      ${vpL(
        `"如何把指数级事件纳入考虑"的诚实答案：<b>调度型事件（FOMC/CPI/非农）当天放大波动、方向无稳定偏向；
      历史冲击事件后市场反应样本太小、且是样本内统计，不能当预测。</b>事件影响的是<b>波动/不确定性</b>，不是可交易的方向。`,
        `The honest answer to "how should index-moving events be factored in": <b>scheduled events (FOMC/CPI/non-farm payrolls) amplify volatility that day, with no stable directional bias;
      the market's historical reaction after shock events has too small a sample, and it's an in-sample statistic — it can't be used as a forecast.</b>What events affect is <b>volatility/uncertainty</b>, not a tradable direction.`
      )}
    </div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.2rem;">${vpL("① 即将到来的调度型事件（波动放大日）","① Upcoming scheduled events (volatility-amplifying days)")}</div>
    <div style="margin-bottom:.8rem;">${upcoming}
      <div style="font-size:0.7rem;color:var(--muted);margin-top:.3rem;">${vpL('→ 纳入方式：这些天<b>避免重仓新开/加杠杆</b>，等尘埃落定，而不是猜方向。', '→ How to factor this in: on these days, <b>avoid opening large new positions or adding leverage</b> and wait for the dust to settle, rather than guessing direction.')}</div>
    </div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.2rem;">${vpL("② 历史冲击事件后 30 日反应（样本内统计）","② 30-day reaction after historical shock events (in-sample statistics)")}</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.76rem;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.25rem .5rem;">${vpL("事件类型","Event type")}</th><th style="padding:.25rem .5rem;">${vpL("样本","Sample")}</th>
        <th style="text-align:right;padding:.25rem .5rem;">${vpL("30日均涨跌","Avg. 30d move")}</th><th style="text-align:right;padding:.25rem .5rem;">${vpL("胜率 vs 基准","Win rate vs. baseline")}</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="insight" style="margin-top:.85rem;">
      ${vpL(
        `<strong>诚实警告：</strong>上表多数事件 <b>n 极小</b>（如首次加息 n=5、疫情 n=2），且是<b>样本内</b>统计、重叠窗口 p 值偏乐观——
      <b>这是"历史上发生过什么"，不是"下次会怎样"。</b>地缘冲击/疫情这类一次性事件尤其不可外推；胜率几乎都贴着基准（无边际）。
      事件提高的是波动/不确定性。<b>注：本站"叠加事件"开关会按这些历史 LR 微调概率，但幅度小、未经样本外验证——当 what-if 玩具看，别当强信号。</b>
      <span style="color:var(--muted)">纳入事件的正确方式 = 在高波动事件日控制仓位/风险，而非预测涨跌。</span>`,
        `<strong>Honest warning:</strong>most events in the table above have a <b>very small n</b> (e.g. first rate hike n=5, pandemic n=2), and it's <b>in-sample</b> statistics with overlapping windows that bias p-values optimistic —
      <b>this is "what happened historically," not "what will happen next time."</b>One-off events like geopolitical shocks/pandemics are especially non-extrapolatable; win rates sit almost exactly at the baseline (no edge).
      What events raise is volatility/uncertainty. <b>Note: this site's "layer in events" toggle nudges the probability using these historical likelihood ratios, but the size is small and it hasn't been out-of-sample validated — treat it as a what-if toy, not a strong signal.</b>
      <span style="color:var(--muted)">The correct way to factor in events = manage position size/risk on high-volatility event days, not predict direction.</span>`
      )}
    </div>`;
}

// ── 量化方法论页面（把项目映射到专业量化文献 + 诚实负结果）──
function renderQuantMethodology() {
  const el = document.getElementById("quant-methodology");
  if (!el) return;
  // 织入几个真实数字，让"方法论"不是空话
  const bm = SIGNALS?.benchmark?.summary || {};
  const vd = SIGNALS?.vol_model?.vol_direction;
  const fa = SIGNALS?.factor_audit?.summary || {};
  const dirAuc = SIGNALS?.factor_audit?.target_probe?.direction_auc_pooled_2012_2024;

  const method = (name, lit, how) => `
    <tr style="border-top:1px solid var(--border-faint);">
      <td style="padding:.3rem .5rem;font-weight:600;">${name}</td>
      <td style="padding:.3rem .5rem;color:var(--muted);font-size:0.74rem;">${lit}</td>
      <td style="padding:.3rem .5rem;font-size:0.78rem;">${how}</td>
    </tr>`;

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.8rem;line-height:1.65;margin-bottom:.8rem;">
      ${vpL(
        `这个项目最初从生态学/农学的"什么都试试"出发，诚实做下去，<b style="color:var(--text)">独立收敛到了 López de Prado 的现代量化反过拟合框架</b>——
      机构与对冲基金用的就是这套。卖点不是"信号准"，而是<b style="color:var(--text)">诚实分清真规律 vs 幻觉</b>。`,
        `This project started from an ecology/agronomy "try everything" mindset, and by being honest about the results it <b style="color:var(--text)">independently converged on López de Prado's modern quant anti-overfitting framework</b> —
      the same one institutions and hedge funds use. The selling point isn't "the signal is accurate," it's <b style="color:var(--text)">honestly telling real patterns apart from illusions</b>.`
      )}
    </div>

    <div style="font-size:0.85rem;font-weight:700;margin:.3rem 0 .3rem;">${vpL("① 我们用的方法 ↔ 专业量化文献","① Methods we use ↔ professional quant literature")}</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.3rem .5rem;">${vpL("方法","Method")}</th><th style="text-align:left;padding:.3rem .5rem;">${vpL("文献出处","Literature source")}</th><th style="text-align:left;padding:.3rem .5rem;">${vpL("我们怎么用","How we use it")}</th></tr></thead>
      <tbody>
        ${method(vpL("Walk-forward 验证","Walk-forward validation"), vpL("Pardo（交易策略验证黄金标准）","Pardo (gold standard for trading-strategy validation)"), vpL("六折滚动，训练→测试，跨多个 regime","Six rolling folds, train→test, spanning multiple regimes"))}
        ${method("Purged + Embargo CV", vpL("López de Prado 2017（防时序泄漏）","López de Prado 2017 (prevents temporal leakage)"), vpL("因子尸检/波动率：切掉跨界泄漏的训练尾部","Factor autopsy/volatility: trims the training tail that leaks across the boundary"))}
        ${method(vpL("块自助（Block Bootstrap）","Block bootstrap"), vpL("重叠窗口的正确显著性","Correct significance for overlapping windows"), vpL("20日重叠→t检验p值偏乐观一个数量级，改用整块重采样","20-day overlap → t-test p-values are optimistic by an order of magnitude, so we resample whole blocks instead"))}
        ${method(vpL("干净保留集（Holdout）","Clean holdout"), vpL("嵌套验证","Nested validation"), vpL("2024-2026 从未进训练；且只用来证伪不证实","2024-2026 never enters training, and is used only to falsify, never to confirm"))}
        ${method(vpL("硬基线对比","Hard-baseline comparison"), vpL("不比稻草人","Never compare against a strawman"), vpL("方向比基率(非0.5)、波动比VIX、策略比买入持有","Direction vs. base rate (not 0.5), volatility vs. VIX, strategy vs. buy-and-hold"))}
        ${method(vpL("回测过拟合警惕","Backtest-overfitting vigilance"), "Bailey & López de Prado 2014", vpL("试几个配置就能凑高回测→我们把试过的都登记、做多重比较校正","Trying a few configs can inflate backtests → we log every configuration tried and apply a multiple-comparison correction"))}
        ${method(vpL("机械假象检测","Mechanical-illusion detection"), vpL("置换检验(permutation null)","Permutation test (permutation null)"), vpL("波动率升降：打乱未来证明高AUC是自指假象，不是信号","Volatility rising/falling: shuffling the future proves a high AUC is a self-referential illusion, not a signal"))}
      </tbody>
    </table>

    <div style="font-size:0.85rem;font-weight:700;margin:1rem 0 .3rem;">${vpL("② 我们用这套方法证伪了什么（诚实负结果）","② What we've falsified with this method (honest negative results)")}</div>
    <div class="insight" style="margin-top:0;">
      <div style="line-height:1.8;">
        ${vpL(
          `❌ <b>短期方向不可样本外预测</b>：综合信号拼接 AUC ≈ <b>${dirAuc!=null?Number(dirAuc).toFixed(2):"0.45"}</b>（&lt;0.5）；逻辑回归更差。<br>
        ❌ <b>因子大多是噪声</b>：尸检 ${fa.noise ?? 13} 个噪声 / ${fa.fragile ?? 2} 个 regime 依赖 / <b>${fa.informative ?? 0} 个稳健</b>。<br>
        ❌ <b>波动率"水平"可测但已被 VIX 定价</b>；连"升/降"用机械公平对比也<b>无稳健信号</b>${vd?.model_vs_naive?`（模型−基线 ${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}，p=${vd.model_vs_naive.p_boot}，不显著）`:""}。<br>
        ✅ <b>真实可用的</b>：股权溢价(买入持有)、波动率聚集、隔夜异象、相关性体制——用于<b>管理风险</b>，不是预测涨跌。`,
          `❌ <b>Short-term direction can't be predicted out-of-sample</b>: pooled composite-signal AUC ≈ <b>${dirAuc!=null?Number(dirAuc).toFixed(2):"0.45"}</b> (&lt;0.5); logistic regression is worse.<br>
        ❌ <b>Most factors are noise</b>: the autopsy found ${fa.noise ?? 13} noise / ${fa.fragile ?? 2} regime-dependent / <b>${fa.informative ?? 0} robust</b>.<br>
        ❌ <b>Volatility's "level" is predictable but already priced in by VIX</b>; even "rising/falling" shows <b>no robust signal</b> under a mechanically fair comparison${vd?.model_vs_naive?` (model − baseline ${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}, p=${vd.model_vs_naive.p_boot}, not significant)`:""}.<br>
        ✅ <b>What's genuinely usable</b>: the equity risk premium (buy-and-hold), volatility clustering, the overnight anomaly, correlation regimes — useful for <b>managing risk</b>, not predicting direction.`
        )}
      </div>
      <div style="margin-top:.6rem;color:var(--muted);">
        ${vpL(`Benchmark 记分卡当前：打败 ${bm.beats ?? 0} · 持平 ${bm.ties ?? 0} · 未达 ${bm.loses ?? 0} · 数据不足 ${bm.insufficient ?? 0}。
        "迄今 0 个模型稳健打败诚实基线"——这是诚实现状，不是失败。`,
        `Benchmark scorecard currently: beats ${bm.beats ?? 0} · ties ${bm.ties ?? 0} · loses ${bm.loses ?? 0} · insufficient data ${bm.insufficient ?? 0}.
        "So far, 0 models robustly beat the honest baseline" — that's the honest current state, not a failure.`)}
      </div>
    </div>

    <div style="font-size:0.85rem;font-weight:700;margin:1rem 0 .3rem;">${vpL('③ 和"散户量化"的区别 + 升级路线','③ How this differs from "retail quant" + the upgrade path')}</div>
    <div style="font-size:0.8rem;line-height:1.7;color:var(--muted);">
      ${vpL(
        `<b style="color:var(--text)">区别</b>：99% 的散户量化用样本内回测自吹"我的信号很准"；我们用块自助 + 干净保留集 + benchmark，
      敢公开说"打不赢基率"。<b style="color:var(--text)">这才是机构量化的标准。</b><br>
      <b style="color:var(--text)">升级路线</b>：要更严谨，升<b>验证方法</b>不升模型——Combinatorial Purged CV (CPCV) + Deflated Sharpe
      （文献证明比单一 walk-forward 更能防过拟合）。加 XGBoost 之类只会让回测更好看、样本外更差。`,
        `<b style="color:var(--text)">The difference</b>: 99% of retail quant uses in-sample backtests to brag "my signal is accurate"; we use block bootstrap + a clean holdout + a benchmark scorecard,
      and are willing to publicly say "doesn't beat the base rate." <b style="color:var(--text)">That's the institutional-quant standard.</b><br>
      <b style="color:var(--text)">The upgrade path</b>: to get more rigorous, upgrade the <b>validation method</b>, not the model — Combinatorial Purged CV (CPCV) + Deflated Sharpe
      (the literature shows these guard against overfitting better than a single walk-forward). Adding something like XGBoost would only make backtests look better while making out-of-sample results worse.`
      )}
    </div>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.7rem;">
      ${vpL('文献：López de Prado《Advances in Financial Machine Learning》；Bailey & López de Prado 2014（回测过拟合）；Pardo（walk-forward）。仅供学习研究，不构成投资建议。',
            'Literature: López de Prado, <i>Advances in Financial Machine Learning</i>; Bailey & López de Prado 2014 (backtest overfitting); Pardo (walk-forward). For research/education only — not investment advice.')}
    </div>`;
}

// ── 市场结构解释（PCA + 相关性体制 + 因果回路）──
function renderMarketStructure() {
  const el = document.getElementById("market-structure");
  if (!el) return;
  const ms = SIGNALS?.market_structure;
  if (!ms) { el.innerHTML = `<span style="color:var(--muted)">${vpL("运行一次完整流水线后显示","Available after a full pipeline run")}</span>`; return; }

  // 近零载荷归零，避免 "-0" 显示
  const ld = x => Math.abs(x) < 0.005 ? 0 : Number(x);
  // PCA：主成分解释力 + 载荷（前5）
  const pcs = (ms.pca?.components || []).map(c => {
    const load = c.loadings.slice(0, 5).map(l => {
      const val = ld(l.loading);
      const col = val > 0 ? "#2ecc71" : val < 0 ? "#e74c3c" : "var(--muted)";
      return `<span style="color:${col};margin-right:.5rem;">${esc(vpD(l,"label"))} ${val>0?"+":""}${val}</span>`;
    }).join("");
    return `<div style="margin:.3rem 0;">
      <div style="font-size:0.78rem;"><b>PC${c.pc}</b> ${vpL(`解释 <b>${Number(c.explained_pct)}%</b> 共同变动`, `explains <b>${Number(c.explained_pct)}%</b> of co-movement`)}</div>
      <div style="font-size:0.74rem;line-height:1.6;">${load}</div></div>`;
  }).join("");

  // 相关性体制：按 |shift| 排序。高亮门槛 0.4（>3×SE，超出噪声带才标记）
  const se = ms.corr_se ?? 0.13;
  const cr = [...(ms.correlation_regime || [])].sort((a,b)=>Math.abs(b.shift)-Math.abs(a.shift));
  const crRows = cr.map(r => {
    const big = Math.abs(r.shift) >= 0.4;
    const sc = r.shift > 0 ? "#2ecc71" : "#e74c3c";
    return `<tr style="border-top:1px solid var(--border-faint);${big?"background:rgba(241,196,15,.06);":""}">
      <td style="padding:.22rem .5rem;">${esc(vpD(r,"pair"))}</td>
      <td style="padding:.22rem .5rem;text-align:right;">${r.recent_60d>0?"+":""}${Number(r.recent_60d)}</td>
      <td style="padding:.22rem .5rem;text-align:right;color:var(--muted);">${r.full_history>0?"+":""}${Number(r.full_history)}<span style="font-size:0.62rem;">·${r.full_years}y</span></td>
      <td style="padding:.22rem .5rem;text-align:right;color:${sc};font-weight:${big?700:400};">${r.shift>0?"+":""}${Number(r.shift)}${big?" ⚠":""}</td>
    </tr>`;
  }).join("");

  // 因果回路（定性系统动力学）：两个核心反馈环
  const loop = (title, color, nodes, kind) => `
    <div style="border:1px solid ${color}44;border-radius:8px;padding:.6rem .8rem;background:${color}0d;">
      <div style="font-size:0.78rem;font-weight:700;color:${color};margin-bottom:.3rem;">${title}</div>
      <div style="font-size:0.76rem;line-height:1.7;">${nodes.join(' <span style="color:'+color+'">→</span> ')}
        <span style="color:${color}">↻</span></div>
      <div style="font-size:0.68rem;color:var(--muted);margin-top:.25rem;">${kind}</div>
    </div>`;

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">${esc(vpD(ms,"window")||"")}</div>
    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.3rem;">${vpL("① 主成分分析（PCA）：市场的共同因子","① Principal component analysis (PCA): the market's common factors")}</div>
    ${pcs}
    <div style="font-size:0.72rem;color:var(--muted);margin:.3rem 0 .8rem;">${esc(vpD(ms.pca||{},"pc1_note")||"")}</div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.3rem;">${vpL("② 相关性体制：近60日 vs 各对完整历史","② Correlation regime: last 60 days vs. each pair's full history")}
      <span style="font-size:0.66rem;color:var(--muted);font-weight:400;">${vpL(`⚠ 60日为小样本，标准误≈±${se}，单格变化≥0.4(高亮)才超出噪声带`, `⚠ 60 days is a small sample, standard error ≈ ±${se} — only a cell change ≥0.4 (highlighted) exceeds the noise band`)}</span></div>
    <table style="width:100%;border-collapse:collapse;font-size:0.76rem;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.22rem .5rem;">${vpL("资产对","Asset pair")}</th><th style="text-align:right;padding:.22rem .5rem;">${vpL("近60日","Last 60d")}</th>
        <th style="text-align:right;padding:.22rem .5rem;">${vpL("完整历史","Full history")}</th><th style="text-align:right;padding:.22rem .5rem;">${vpL("变化","Change")}</th></tr></thead>
      <tbody>${crRows}</tbody>
    </table>

    <div style="font-size:0.8rem;font-weight:600;margin:.85rem 0 .4rem;">${vpL("③ 因果回路：波动生态的反馈结构（定性·系统动力学）","③ Causal loops: the feedback structure of the volatility ecosystem (qualitative · system dynamics)")}</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.5rem;">
      ${loop(vpL("波动聚集 · 平衡环","Volatility clustering · balancing loop"), "#3498db",
             vpL(["波动↑","风险厌恶↑","抛售/对冲","波动更高","随后均值回归","波动↓"],
                 ["Vol ↑","Risk aversion ↑","Selling/hedging","Vol even higher","Then mean-reverts","Vol ↓"]),
             vpL("balancing：波动有记忆但会回落，是可预测性来源","balancing: volatility has memory but reverts — a source of predictability"))}
      ${loop(vpL("强平螺旋 · 增强环","Liquidation spiral · reinforcing loop"), "#e74c3c",
             vpL(["价格↓","保证金不足","被迫卖出","价格更↓"],
                 ["Price ↓","Margin shortfall","Forced selling","Price even lower ↓"]),
             vpL("reinforcing：危机时正反馈，相关性趋同、分散失效","reinforcing: positive feedback during crises — correlations converge and diversification fails"))}
    </div>

    <div class="insight" style="margin-top:.8rem;">
      ${vpL(
        `<strong>当前结构读数：</strong>PC1（risk-on/off）解释约 ${ms.pca?.components?.[0]?.explained_pct ?? "?"}% 的跨资产共动——
      一个"风险偏好"开关解释了最大一块共同变动。高亮行（|变化|≥0.4，超出 60 日噪声带）<b>值得留意但仍需更长窗口确认</b>：
      例如纳指–黄金转正、纳指–利率/美元转负，<i>可能</i>暗示市场转向"利率/流动性主导"（降息预期来时股和黄金齐涨）——
      但 60 日样本噪声大，这是假设不是定论。`,
        `<strong>Current structural read:</strong>PC1 (risk-on/off) explains about ${ms.pca?.components?.[0]?.explained_pct ?? "?"}% of cross-asset co-movement —
      a single "risk appetite" switch explains the biggest chunk of shared movement. Highlighted rows (|change|≥0.4, beyond the 60-day noise band) are <b>worth watching but still need a longer window to confirm</b>:
      for example Nasdaq–gold turning positive, Nasdaq–rates/USD turning negative, <i>may</i> hint the market is shifting toward "rates/liquidity-driven" (stocks and gold rallying together when rate-cut expectations arrive) —
      but the 60-day sample is noisy; this is a hypothesis, not a conclusion.`
      )}
      <span style="color:var(--muted)">${esc(vpD(ms,"note")||"")}</span>
    </div>`;
}

function renderIPOCycle() {
  const el = document.getElementById("chart-ipo-cycle");
  if (!el) return;
  const rows = [...MEGA_IPOS].sort((a, b) => a.dd - b.dd);
  Plotly.newPlot("chart-ipo-cycle", [{
    type: "bar", orientation: "h",
    y: rows.map(r => r.name), x: rows.map(r => r.dd),
    marker: { color: rows.map(r => r.dd <= -15 ? "#e74c3c" : "#2ecc71") },
    text: rows.map(r => vpL(`${r.dd}%（${r.mkt}）`, `${r.dd}% (${r.mkt})`)), textposition: "auto",
    hovertemplate: vpL("%{y}<br>上市后12个月所在市场最大回撤 ≈ %{x}%<extra></extra>",
                        "%{y}<br>Max drawdown of that market in the 12mo after listing ≈ %{x}%<extra></extra>"),
  }], {...DARK, margin:{...DARK.margin, l:150},
    xaxis:{...DARK.xaxis, title: vpL("上市后12个月大盘最大回撤 %","Max market drawdown in 12mo post-listing (%)")}}, {responsive:true});
  const ins = document.getElementById("ipo-cycle-insight");
  if (ins) {
    const bad = MEGA_IPOS.filter(r => r.dd <= -15).length;
    ins.innerHTML = vpLang() === "en" ? `<strong>IPO cycle lens:</strong>Of ${MEGA_IPOS.length} historic "mega/national" IPOs,
      ${bad} were followed by a ≥15% drawdown in that market within 12 months (NTT 1987, PetroChina 2007, and Rivian 2021 came close to the very top).
      The mechanism is real — issuers pick the moment when valuations are richest and retail enthusiasm is hottest to sell shares (IPO heat is a component of the Baker-Wurgler sentiment index);
      but the lead time varies from 0–18 months, and there are calm counter-examples too, like Google/Alibaba/Facebook.
      <span style="color:var(--muted)">Values are historical approximations. Use it as a sentiment thermometer, not a timing button — this site's answer is always the calibrated probability above.</span>` : `<strong>IPO 周期视角：</strong>史上${MEGA_IPOS.length}个"超级/全民"IPO中，
      ${bad} 个之后12个月内所在市场出现 ≥15% 回撤（NTT 1987、中石油 2007、Rivian 2021 几乎贴顶）。
      机制真实——发行人挑估值最贵、散户最热情的时候卖股票（IPO 热度是 Baker-Wurgler 情绪指数成分）；
      但领先期 0–18 个月不等，也有谷歌/阿里/脸书这样的平静反例。
      <span style="color:var(--muted)">数值为历史约值。当温度计用，别当择时按钮——本站的答案永远是上面的校准概率。</span>`;
  }
}
