/* vp_i18n.js — Valpha Lab 共享 i18n 脚手架 v1.0
   依赖：无（dependency-free）。同源自托管，不引境外 CDN。

   暴露的全局 API：
     vpEsc(s)                   — HTML 转义（防 XSS）
     vpLang()                   — 读当前语言（"zh" | "en"），默认 "zh"
     vpSetLang(l)               — 持久化语言到 localStorage
     vpT(I18N, key, lang)       — 查 I18N[key][lang]，回退到 key 本身
     vpL(zh, en)                — 按当前语言在 zh/en 间选一个（内联双语，见下方定义处用法）
     vpApplyStatic(I18N, opts)  — 批量渲染 [data-i18n] 元素 + #lang 按钮 + html.lang
     vpBindLang(I18N, onToggle) — 绑定 #lang 点击切换，可传可选的页面重渲染回调

   设计原则：
     · 每个函数接受显式参数，不依赖模块级 LANG 状态——页面保留自己的 let LANG = vpLang()
       并在切换时同步，控制流与原内联代码完全一致
     · 行为与各页面原有内联实现完全相同，可逐页安全替换
     · 每个页面保留自己的 I18N 对象（页面专属内容不变）
*/
(function (win) {
  "use strict";

  /* ── vpEsc ────────────────────────────────────────────────────────
     对任意值做 HTML 转义，防 XSS。
     与各页面 inline `esc` 函数行为完全相同。
  ────────────────────────────────────────────────────────────────── */
  function vpEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ── vpLang / vpSetLang ───────────────────────────────────────────
     读写 localStorage 'valpha_lang'，兼容隐私模式（try/catch）。
  ────────────────────────────────────────────────────────────────── */
  function vpLang() {
    try { return localStorage.getItem("valpha_lang") || "zh"; } catch (e) { return "zh"; }
  }

  function vpSetLang(l) {
    try { localStorage.setItem("valpha_lang", l); } catch (e) {}
  }

  /* ── vpT ──────────────────────────────────────────────────────────
     在 I18N 对象中查找 key 对应 lang 的字符串。
     找不到时回退到 key 本身（与各页面 `t` 函数行为相同）。
  ────────────────────────────────────────────────────────────────── */
  function vpT(I18N, key, lang) {
    return (I18N[key] && I18N[key][lang]) || key;
  }

  /* ── vpL ──────────────────────────────────────────────────────────
     通用双语内联 helper：按当前语言在 zh/en 两个值之间选一个。
     不限于字符串——数组/对象同样可用（如按语言切换整份标签表）。
     用法：
       短标签    vpL("卖出窗口","Sell window")
       插值句    vpLang()==="en" ? `tier ${n}` : `第${n}档`（整句双写，见规格 §1）
     供深度面板脚本（app-1..5.js）内联调用，单一实现、不逐文件复制。
  ────────────────────────────────────────────────────────────────── */
  function vpL(zh, en) {
    return vpLang() === "en" ? en : zh;
  }

  /* ── vpApplyStatic ────────────────────────────────────────────────
     批量渲染页面内所有 [data-i18n] 元素，更新 #lang 按钮文字，
     并同步 document.documentElement.lang 属性。

     opts（可选）：
       { langBtnId: "lang" }  — #lang 按钮的 ID，默认 "lang"

     与各页面 `applyStatic()` 函数行为完全相同。
  ────────────────────────────────────────────────────────────────── */
  function vpApplyStatic(I18N, opts) {
    var lang = vpLang();
    var btnId = (opts && opts.langBtnId) || "lang";

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.innerHTML = vpT(I18N, el.dataset.i18n, lang);
    });

    var btn = document.getElementById(btnId);
    if (btn) btn.textContent = lang === "zh" ? "EN" : "中";

    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }

  /* ── vpBindLang ───────────────────────────────────────────────────
     绑定 #lang 按钮的 onclick：
       · 切换语言（zh ↔ en）
       · 持久化到 localStorage
       · 调用 vpApplyStatic 更新静态文本
       · 调用可选的 onToggle(newLang) 回调（页面专属重渲染，如重建卡片）

     opts（可选）：同 vpApplyStatic。

     与各页面 `$("lang").onclick = () => { ... }` 行为完全相同。
  ────────────────────────────────────────────────────────────────── */
  function vpBindLang(I18N, onToggle, opts) {
    var btnId = (opts && opts.langBtnId) || "lang";
    var btn = document.getElementById(btnId);
    if (!btn) return;

    btn.onclick = function () {
      var next = vpLang() === "zh" ? "en" : "zh";
      vpSetLang(next);
      vpApplyStatic(I18N, opts);
      if (typeof onToggle === "function") onToggle(next);
    };
  }

  /* ── 暴露到全局 ──────────────────────────────────────────────────── */
  // 数据层双语取值器(2026-08-26):Python 产的 JSON 里同一字段带 *_en 变体时,EN 模式优先取,
  // 缺失回落中文(诚实:宁可显示中文,也不显示空白或机翻)。给 app-*.js / 各页统一用,免得每处重写。
  function vpD(obj, key) {
    if (!obj) return "";
    return (vpLang() === "en" && obj[key + "_en"]) ? obj[key + "_en"] : obj[key];
  }

  win.vpD           = vpD;
  win.vpEsc         = vpEsc;
  win.vpLang        = vpLang;
  win.vpSetLang     = vpSetLang;
  win.vpT           = vpT;
  win.vpL           = vpL;
  win.vpApplyStatic = vpApplyStatic;
  win.vpBindLang    = vpBindLang;

}(window));
