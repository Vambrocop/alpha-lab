/* vp_related.js — 「情绪·择时·波动·利率」五研究页互链(共享·DRY)。
   给定当前页 key,渲染指向同簇其余四页的小导航。语言按加载时 vpLang() 取(与 AI 盒一致·渲一次)。
   依赖:可选 window.vpLang。无 CDN、同源。 */
(function (win) {
  "use strict";
  var CLUSTER = [
    { key: "feargreed", href: "feargreed.html", zh: "🌡️ 恐慌贪婪", en: "🌡️ Fear & Greed" },
    { key: "fear",      href: "fear.html",      zh: "😱 恐慌之后", en: "😱 After fear" },
    { key: "dip",       href: "dip.html",       zh: "📉 跌了买值不值", en: "📉 Buy the dip?" },
    { key: "vixvol",    href: "vixvol.html",    zh: "📈 VIX 预测什么", en: "📈 What VIX predicts" },
    { key: "treasury",  href: "treasury.html",  zh: "🏦 美债利率有关吗", en: "🏦 Do yields move stocks?" }
  ];
  function vpRelated(currentKey, elId) {
    var el = document.getElementById(elId);
    if (!el) return;
    var lang = win.vpLang ? win.vpLang() : "zh";
    var label = lang === "en" ? "Related · sentiment · timing · volatility · rates" : "相关研究 · 情绪 · 择时 · 波动 · 利率";
    var links = CLUSTER.filter(function (c) { return c.key !== currentKey; })
      .map(function (c) { return '<a href="' + c.href + '">' + (lang === "en" ? c.en : c.zh) + '</a>'; })
      .join("");
    el.innerHTML = '<div class="rel-label">' + label + '</div><div class="rel-links">' + links + '</div>';
  }
  win.vpRelated = vpRelated;
}(window));
