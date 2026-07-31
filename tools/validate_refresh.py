"""validate_refresh.py — 校验每周本地刷新(insider + ndx)产物的新鲜度/完整性。

只读+报告,不改任何文件。退出码:0=全过,非0=有问题(供 weekly_local_refresh.ps1 记进日志、
让用户复核前一眼看到红旗)。CI 抓不到、只本地补的数据源,用这个当"补齐是否真成功"的守门。
"""
import datetime
import json
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "market-analysis" / "web"


def _age_days(s):
    """generated 可能是 '2026-07-31'(日) 或 '2026-07-31T05:15:08Z'(ISO)——都折算成距今天数。"""
    s = str(s).strip()
    try:
        if "T" in s:
            t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            t = datetime.datetime.fromisoformat(s).replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 86400
    except Exception:
        return None


problems = []


def check(name, fn):
    try:
        fn()
        print(f"  [OK] {name}")
    except AssertionError as e:
        problems.append(f"{name}: {e}")
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        problems.append(f"{name}: 异常 {e}")
        print(f"  [FAIL] {name}: 异常 {e}")


def chk_insider():
    d = json.load(open(WEB / "insider.json", encoding="utf-8"))
    age = _age_days(d.get("generated", ""))
    assert age is not None, f"generated 缺失/无法解析:{d.get('generated')!r}"
    assert age <= 8, f"generated 太旧(距今 {age:.1f} 天>8)——本次抓取可能没成功刷新"
    buys = d.get("buys", [])
    assert isinstance(buys, list) and len(buys) >= 1, f"buys 为空({len(buys)})——SEC 抓取可能 403/空返回"


def chk_ndx():
    d = json.load(open(WEB / "ndx.json", encoding="utf-8"))
    age = _age_days(d.get("generated", ""))
    assert age is not None, f"generated 缺失/无法解析:{d.get('generated')!r}"
    assert age <= 10, f"generated 太旧(距今 {age:.1f} 天>10)——本次 ndx 抓取可能没成功"
    n = d.get("n")
    assert isinstance(n, int) and n >= 50, f"成分数异常(n={n})——Wikipedia 抓取可能失败"


print("=== 校验刷新产物(只读)===")
check("insider.json 新鲜(≤8天)+ 非空 buys", chk_insider)
check("ndx.json 新鲜(≤10天)+ 成分完整(≥50)", chk_ndx)

if problems:
    print(f"[FAIL] {len(problems)} 项未过——请查上面 fetch 日志(SEC 403 / wiki 改版 / 网络)")
    sys.exit(1)
print("[OK] 全部校验通过")
