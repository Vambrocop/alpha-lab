# 交互审计：真浏览器加载每一页(含 9 个工具页) + 点每个按钮抓死按钮/报错 + 查横向溢出(导航切掉) +
# 失败请求 + 本地数据新鲜度。补 site_audit.py 的盲区(它只测 dashboard 视图、不点普通按钮、不测工具页)。
# 用法: py tools/interaction_audit.py [--mobile]
import http.server, threading, functools, os, sys, json, glob, datetime

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = 8951
WEB = "market-analysis/web"
MOBILE = "--mobile" in sys.argv
CI = "--ci" in sys.argv or os.environ.get("CI") == "true"
VP = {"width": 390, "height": 844} if MOBILE else {"width": 1440, "height": 1000}
# 硬问题=真代码 bug(退非零拦 CI)；软=瞬时 live 部署 404 / 网络抖动(只警告)
HARD_KW = ("溢出", "按钮", "加载失败", "pageerror", "循环动画未清", "reduced-motion违规")

PAGES = ["dashboard.html", "index.html", "valpha150.html", "sectors.html", "radar.html",
         "advisor.html", "wild.html", "ipo.html", "methodology.html", "self_growing.html",
         "discoveries.html", "fxreturn.html", "prediction.html", "heatmap.html", "au.html",
         "picks.html", "fear.html", "dip.html", "vixvol.html", "feargreed.html", "treasury.html"]  # picks:SPEC_PICKS_V2·③;fear:SPEC_FEAR_EXTREMES·③;dip:SPEC_DIP_HOLD·③;vixvol:VIX波动预报复现图;feargreed:SPEC_FEAR_GREED·③
DASH_VIEWS = ["today", "outlook", "plan", "longterm", "research", "lab", "registry", "quant", "mine"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def overflow_check(page):
    """横向溢出(导航/页面被切) + 导航是否换行全显。"""
    return page.evaluate("""() => {
        const out = [];
        const de = document.documentElement;
        if (de.scrollWidth > window.innerWidth + 4)
            out.push(`页面横向溢出 scrollWidth=${de.scrollWidth} > vw=${window.innerWidth}`);
        const nav = document.querySelector('.view-nav');
        if (nav && nav.scrollWidth > nav.clientWidth + 4)
            out.push(`导航被切 scrollWidth=${nav.scrollWidth} > clientWidth=${nav.clientWidth}（项看不全）`);
        return out;
    }""")


def click_visible_buttons(page, scope_js="document"):
    """点 scope 内所有可见 button，抓点击导致的报错。返回 [(label, ok)]。不点 <a>(会导航)。"""
    n = page.evaluate(f"""() => {{
        const root = {scope_js};
        if (!root) return [];
        return [...root.querySelectorAll('button')].filter(b => b.offsetWidth || b.offsetHeight)
            .map(b => (b.id || b.textContent || b.getAttribute('aria-label') || '?').trim().slice(0,28));
    }}""")
    results = []
    for i, label in enumerate(n):
        before = len(page._iaud_console)
        try:
            page.evaluate(f"""() => {{
                const root = {scope_js};
                const bs = [...root.querySelectorAll('button')].filter(b => b.offsetWidth || b.offsetHeight);
                if (bs[{i}]) bs[{i}].click();
            }}""")
            page.wait_for_timeout(160)
        except Exception as e:
            results.append((label, f"点击抛错 {str(e)[:60]}"))
            continue
        new_errs = page._iaud_console[before:]
        if new_errs:
            results.append((label, "触发报错: " + new_errs[-1][:80]))
    return results


def infinite_animation_check(page):
    """D4-3 检查②: 数据渲染完成后，容器内不应还有 iterations===Infinity 的动画在跑
    (典型漏洞: 骨架 shimmer 的 innerHTML 没被真正替换掉，还在后台循环)。"""
    try:
        return page.evaluate("""() => {
            const anims = document.documentElement.getAnimations({subtree: true});
            return anims
                .filter(a => { try { return a.effect.getTiming().iterations === Infinity; }
                               catch (e) { return false; } })
                .map(a => a.animationName || (a.effect && a.effect.target && a.effect.target.id) || '?');
        }""")
    except Exception as e:
        return [f"getAnimations 检查抛错: {str(e)[:60]}"]


def reduced_motion_check(browser, url):
    """D4-3 检查①: prefers-reduced-motion:reduce 下重载页面，采样全部元素的
    transition-duration / animation-duration，断言全部为 0s(全局 reduced-motion 规则须生效)。"""
    page = browser.new_page(viewport=VP)
    page.emulate_media(reduced_motion="reduce")
    out = []
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1200)
        out = page.evaluate("""() => {
            const nz = d => d.split(',').some(s => parseFloat(s) > 0);
            const bad = [];
            for (const el of document.querySelectorAll('*')) {
                const cs = getComputedStyle(el);
                if (nz(cs.transitionDuration) || nz(cs.animationDuration)) {
                    bad.push(`${el.id || el.className || el.tagName} t=${cs.transitionDuration} a=${cs.animationDuration}`);
                    if (bad.length >= 5) break;
                }
            }
            return bad;
        }""")
    except Exception as e:
        out = [f"reduced-motion 检查加载失败: {str(e)[:80]}"]
    page.close()
    return out


def audit():
    handler = functools.partial(Quiet, directory=WEB)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    findings = {}

    with sync_playwright() as p:
        if CI:
            b = p.chromium.launch()
        else:
            try:
                b = p.chromium.launch(channel="msedge")
            except Exception:
                b = p.chromium.launch()
        for pg in PAGES:
            page = b.new_page(viewport=VP)
            page._iaud_console = []
            page.on("console", lambda m: page._iaud_console.append(f"[{m.type}] {m.text[:160]}")
                    if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: page._iaud_console.append(f"[pageerror] {str(e)[:160]}"))
            bad = []
            page.on("requestfailed", lambda r: bad.append(f"{r.url.split('/')[-1]} ({r.failure})"))
            page.on("response", lambda r: bad.append(f"{r.url.split('/')[-1]} HTTP {r.status}") if r.status >= 400 else None)
            issues = []
            try:
                page.goto(f"http://127.0.0.1:{PORT}/{pg}", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1800)
            except Exception as e:
                findings[pg] = ["加载失败: " + str(e)[:80]]
                page.close(); continue

            issues += [f"溢出: {x}" for x in overflow_check(page)]

            # D4-3 检查②: 数据已渲染，骨架 shimmer 等循环动画不该还挂着
            inf_anims = infinite_animation_check(page)
            if inf_anims:
                issues.append("循环动画未清(渲染后仍有 infinite iterations): " + ", ".join(inf_anims[:5]))

            # D4-3 检查①: prefers-reduced-motion:reduce 下重载，采样元素时长须全 0s
            rm_bad = reduced_motion_check(b, f"http://127.0.0.1:{PORT}/{pg}")
            if rm_bad:
                issues.append("reduced-motion违规(时长未清零): " + " | ".join(rm_bad[:5]))

            if pg == "dashboard.html":
                for v in DASH_VIEWS:
                    try:
                        page.evaluate(f"""() => switchView('{v}', document.querySelector('.view-btn[data-view=\"{v}\"]'))""")
                        page.wait_for_timeout(500)
                    except Exception:
                        issues.append(f"视图 {v}: switchView 抛错")
                        continue
                    issues += [f"[{v}] 溢出: {x}" for x in overflow_check(page)]
                    for label, err in click_visible_buttons(page, f"document.getElementById('view-{v}')"):
                        issues.append(f"[{v}] 按钮「{label}」{err}")
            else:
                for label, err in click_visible_buttons(page):
                    issues.append(f"按钮「{label}」{err}")

            # 控制台报错 + 失败请求(去重，排除已知良性)
            errs = [e for e in dict.fromkeys(page._iaud_console)]
            bads = [x for x in dict.fromkeys(bad) if "favicon" not in x]
            if errs: issues.append("控制台: " + " | ".join(errs[:4]))
            if bads: issues.append("失败请求: " + " | ".join(bads[:5]))
            findings[pg] = issues
            page.close()
        b.close()
    srv.shutdown()
    return findings


def freshness():
    now = datetime.datetime.now(datetime.timezone.utc)
    stale = []
    for f in sorted(glob.glob(f"{WEB}/*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        g = None
        for k in ("generated", "asof", "updated"):
            if isinstance(d, dict) and d.get(k):
                g = str(d[k]); break
        if not g:
            continue
        try:
            ts = g.replace("Z", "+00:00").replace(" UTC", "")
            dt = datetime.datetime.fromisoformat(ts if "T" in ts else ts + "T00:00:00")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            age_d = (now - dt).days
            if age_d >= 4:
                stale.append(f"{os.path.basename(f)}: {g} ({age_d}天前)")
        except Exception:
            pass
    return stale


if __name__ == "__main__":
    print(f"=== 交互审计 ({'移动端' if MOBILE else '桌面'} {VP['width']}px) ===")
    fnd = audit()
    total = sum(len(v) for v in fnd.values())
    for pg, issues in fnd.items():
        if issues:
            print(f"\n● {pg} ({len(issues)})")
            for x in issues:
                print(f"    {x}")
        else:
            print(f"\n● {pg}  ✓ 无交互问题")
    print(f"\n=== 本地数据新鲜度(≥4天才报) ===")
    st = freshness()
    for x in st:
        print(f"    ⚠ {x}")
    if not st:
        print("    ✓ 无明显陈旧产物")
    hard = [(pg, x) for pg, issues in fnd.items() for x in issues if any(k in x for k in HARD_KW)]
    print(f"\n总交互问题 {total}（硬 {len(hard)} = 真 bug，软 {total - len(hard)} = 瞬时404/网络抖动）")
    sys.exit(1 if hard else 0)
