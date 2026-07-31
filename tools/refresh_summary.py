"""refresh_summary.py — 大白话总结(给不看技术日志的人)。

读 insider.json / ndx.json 的新鲜度 + git 变更,产出一段人话:成不成功、insider/ndx 更没更新、
校验过没过、要不要你动手。写 tools/refresh_logs/LATEST_SUMMARY.txt(永远是最新一次)+ 打印 + 追加进本次日志。

argv:
  --insider-attempted true|false   SEC_UA 有没有设(没设=没抓 insider)
  --validate-exit N                validate_refresh.py 退出码(0=过)
  --log <path>                     本次技术日志路径(写进总结让用户找得到)
  --skipped-reason "<text>"        可选:Tuesday 兜底跳过时的原因(周一已成功)
"""
import argparse
import datetime
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "market-analysis" / "web"
LOGDIR = ROOT / "tools" / "refresh_logs"


def _age_days(s):
    s = str(s).strip()
    try:
        if "T" in s:
            t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            t = datetime.datetime.fromisoformat(s).replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 86400
    except Exception:
        return None


def _load(name):
    try:
        return json.load(open(WEB / name, encoding="utf-8"))
    except Exception:
        return None


def _git_changed():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "status", "--short"],
                           capture_output=True, text=True)
        return [ln[3:].strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def _src(label, attempted, data, count_key, max_age, unit):
    """→ (显示行, ok?)"""
    if not attempted:
        return f"  - {label}: SKIPPED (SEC contact email not set)", False
    if not data:
        return f"  - {label}: NOT updated (could not read the output file)", False
    ag = _age_days(data.get("generated", ""))
    n = data.get(count_key)
    if ag is not None and ag <= max_age:
        return f"  - {label}: updated OK  ({n} {unit}, dated {str(data.get('generated'))[:10]})", True
    stale = f"{ag:.0f} days old" if ag is not None else "no date"
    return f"  - {label}: NOT updated (data looks stale: {stale})", False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insider-attempted", default="true")
    ap.add_argument("--validate-exit", type=int, default=1)
    ap.add_argument("--log", default="")
    ap.add_argument("--skipped-reason", default="")
    a = ap.parse_args()

    L = []
    W = L.append
    now = datetime.datetime.now()
    W("=" * 60)
    W(f"  Valpha weekly data refresh  -  {now:%a %Y-%m-%d %H:%M}")
    W("=" * 60)
    W("")

    if a.skipped_reason:
        W("  RESULT:  SKIPPED (this is fine, no action needed)")
        W("")
        W(f"  {a.skipped_reason}")
        W("")
        W("  WHAT YOU NEED TO DO:  Nothing.")
        W("=" * 60)
        _emit(L, a.log)
        return

    insider_attempted = a.insider_attempted.lower() == "true"
    ins_line, ins_ok = _src("Insider (SEC Form 4)", insider_attempted, _load("insider.json"), "n_buys", 8, "buys")
    ndx_line, ndx_ok = _src("NDX (Nasdaq-100)", True, _load("ndx.json"), "n", 10, "members")
    val_ok = a.validate_exit == 0
    overall = ins_ok and ndx_ok and val_ok

    W(f"  RESULT:  {'ALL GOOD' if overall else 'NEEDS YOUR ATTENTION'}")
    W("")
    W(ins_line)
    W(ndx_line)
    W(f"  - Validation checks: {'passed' if val_ok else 'FAILED'}")
    W("")

    changed = _git_changed()
    data_changed = [f for f in changed if ("insider" in f or "ndx" in f)]
    if data_changed:
        W(f"  Did anything change?  Yes - {len(data_changed)} data file(s) refreshed (NOT committed).")
    else:
        W("  Did anything change?  No new data this run (already up to date).")
    W("")

    W("  WHAT YOU NEED TO DO:")
    if overall and data_changed:
        W("    Review, then commit when you have a moment:")
        W("        cd E:\\finance")
        W('        git add -A && git commit -m "data: weekly local refresh (insider + ndx)" && git push')
        W("    Or to throw this run away:  git checkout -- .")
    elif overall and not data_changed:
        W("    Nothing - the data was already current, nothing to commit.")
    else:
        W("    Something did not refresh (see the lines above).")
        if insider_attempted and not ins_ok:
            W("    Insider is usually a temporary SEC block - the Tuesday fallback will retry automatically.")
        if not ndx_ok:
            W("    NDX did not update - if this repeats, tell Claude.")
        W("    Nothing was committed. If problems persist across runs, tell Claude.")
    W("")
    W("  (By design, this never commits or pushes on its own.)")
    if a.log:
        W(f"  Full technical log: {a.log}")
    W("=" * 60)
    _emit(L, a.log)


def _emit(lines, logpath):
    text = "\n".join(lines) + "\n"
    print(text)
    try:
        LOGDIR.mkdir(parents=True, exist_ok=True)
        (LOGDIR / "LATEST_SUMMARY.txt").write_text(text, encoding="utf-8")
        if logpath:
            with open(logpath, "a", encoding="utf-8") as f:
                f.write("\n" + text)
    except Exception as e:
        print("summary write error:", e)


if __name__ == "__main__":
    main()
