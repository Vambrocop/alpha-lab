/* vp_honestread.js — 大白话 AI 读数盒(共享·dip/vixvol/feargreed 三研究页用)。
   读 honest_reads.json[key] 的一段大白话(LLM 据真数字生成、已过后置守门);
   guard!=="ok" / 无 text / 拉不到 → 整盒不显示(优雅降级)。文案为中文(LLM 出 zh),标签双语固定。
   依赖:可选 window.vpEsc(有则转义)。无 CDN、同源。 */
(function (win) {
  "use strict";
  async function vpHonestRead(key, elId) {
    var el = document.getElementById(elId);
    if (!el) return;
    try {
      var r = await fetch("honest_reads.json", { cache: "no-store" });
      if (!r.ok) return;
      var j = await r.json();
      var read = j && j.reads && j.reads[key];
      if (!read || read.guard !== "ok" || !read.text) return;   // 优雅降级:不显示
      var esc = win.vpEsc || function (s) { return String(s == null ? "" : s); };
      el.innerHTML =
        '<div class="airead-label">🗣️ 大白话读 · plain-language (AI · 喂真数字 / fed real numbers)</div>' +
        '<div class="airead-text">' + esc(read.text) + '</div>';
      el.style.display = "block";
    } catch (e) { /* 静默降级 */ }
  }
  win.vpHonestRead = vpHonestRead;
}(window));
