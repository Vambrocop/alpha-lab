"""test_reassert_covers_ledgers — 缓存回灌防护的结构性守门。

## 历史(别删,这段是这个测试存在的理由)

2026-07-28:refresh-data 的 re-assert 步骤只护了 2/19 个账本 → actions/cache 命中旧缓存时把
陈旧账本整个回灌 → `git add -A` 把缩水版提交上去。当时的修法是**手工列出全部账本文件名**,
再写这个测试盯着"新账本有没有被加进清单"。

2026-08-29:用户的 `my_portfolio.txt` 还是被抹了——因为它是**输入清单**不是账本,不在 SPECS 里,
于是也不在手工清单里。补进去,测试又加一条。**打第二个补丁的时候就该看出:问题不是清单漏了谁,
是"由人维护一份必须完整的清单"这件事本身不可靠。**

2026-09-03 根治(§2 #1),两处结构性改动让清单彻底消失:
  ① 缓存路径从整个 `market-analysis/data` 收窄到 `raw/` + `processed/` → 31 个顶层账本
     根本不再进缓存,没有回灌可言;
  ② re-assert 改成 `git checkout -- market-analysis/data/`(整目录复位)→ 它只作用于**被跟踪**
     的文件,天然覆盖全部现有账本 + 将来新增的任何账本。

所以本测试也随之改写:**不再核对清单是否完整**(清单没了),改为钉死上面两条结构性质,
防止有人把它改回"逐个列文件名"或把缓存路径改回整个目录。
"""
import re
from pathlib import Path

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "refresh-data.yml"


def _step(name_fragment):
    """抓某一步(从 name 行到下一个 `- name:`)的原文。"""
    text = WF.read_text(encoding="utf-8")
    m = re.search(re.escape(name_fragment) + r".*?(?=\n      - name:)", text, re.S)
    assert m, f"refresh-data.yml 找不到步骤: {name_fragment}"
    return m.group(0)


def test_cache_does_not_cover_tracked_ledgers():
    """缓存路径**绝不能**是整个 market-analysis/data —— 那样 31 个被跟踪账本又会进缓存。"""
    block = _step("Restore data cache from last run")
    paths = re.findall(r"^\s+(market-analysis/data\S*)\s*$", block, re.M)
    assert paths, "缓存步骤没解析到 path,写法变了先修这里"
    assert "market-analysis/data" not in paths, (
        "缓存路径又变回整个 market-analysis/data 了 —— 被跟踪的 append-only 账本会重新进缓存,"
        "旧缓存命中即回灌陈旧账本(07-28 连红四天 / 08-29 抹掉自选组合 都是这个根因)。"
        "只该缓存可再生的派生数据。")
    for p in paths:
        assert p.startswith("market-analysis/data/"), f"缓存路径过宽: {p}"


def test_reassert_resets_whole_tracked_dir_not_a_handmade_list():
    """复位必须是**整目录**,不能退回逐个列文件名(清单会漂移,已被咬过两次)。"""
    block = _step("Re-assert tracked data files from git")
    assert "git checkout -- market-analysis/data/" in block, (
        "整目录复位不见了。逐个列文件名的写法会漏掉新账本 —— "
        "my_portfolio.txt 就是这么被抹掉的。")
    # 逐个列文件名的特征:同一 run 块里出现 3 个以上 .csv 字面量
    csvs = re.findall(r"[\w./-]+\.csv", block)
    assert len(csvs) < 3, (
        f"这一步又开始逐个列账本文件名了({csvs[:5]}...) —— 那正是被根治掉的漂移源。")


def test_reassert_also_covers_root_benchmark_ledger():
    """`.benchmark-history.json` 是写在仓库根的 append-only 战绩账本,不在 data/ 目录下,
    必须单独复位 —— 否则它不受整目录复位保护。"""
    block = _step("Re-assert tracked data files from git")
    assert ".benchmark-history.json" in block, (
        "根部的 .benchmark-history.json 没被复位保护 —— 它是公开计分账本。")


def test_no_git_add_dash_A_in_any_workflow():
    """`git add -A` 是把陈旧回灌提交上去的最后一环,全仓不许再出现(注释除外)。"""
    wf_dir = WF.parent
    offenders = []
    for f in sorted(wf_dir.glob("*.yml")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue                      # 注释里提它是在讲历史,放行
            if "git add -A" in stripped:
                offenders.append(f"{f.name}:{i}")
    assert not offenders, (
        f"这些地方还在用 git add -A: {offenders} —— 改成显式暂存(见 tools/ci_publish.py)")


def test_publish_goes_through_the_locally_testable_script():
    """发布逻辑必须走 ci_publish.py —— inline YAML 版本本地跑不了,那正是 07-24 连红的根因。"""
    for wf in ("refresh-data.yml", "weekly-review.yml"):
        text = (WF.parent / wf).read_text(encoding="utf-8")
        assert "tools/ci_publish.py" in text, f"{wf} 的发布没走 ci_publish.py"


def test_ledger_guard_is_warn_only():
    """防缩水门只许警告。07-28 它以阻断 push 的方式失败,全站停更四天。"""
    text = WF.read_text(encoding="utf-8")
    assert "--guard tools/ci_ledger_guard.py" in text, "防缩水门没挂上"
    # WF = <root>/.github/workflows/refresh-data.yml → parents[2] 才是仓库根
    src = (WF.parents[2] / "tools" / "ci_publish.py").read_text(encoding="utf-8")
    assert "warn-only" in src and "::warning::" in src, "门必须以 warning 形式报告,不得阻断"
