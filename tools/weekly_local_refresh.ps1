# tools/weekly_local_refresh.ps1
# ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 as system ANSI (GBK) without a BOM,
# so non-ASCII in the source breaks parsing. Keep this file ASCII; the Python scripts' Chinese
# output is captured into the log via the UTF-8 console encoding below.
#
# Valpha LOCAL data refresh: fills the sources CI cannot fetch (SEC insider + Wikipedia ndx,
# both blocked from GitHub Actions IPs).
#
# SCHEDULE (task "ValphaWeeklyRefresh", 3 triggers, all 10:00 Adelaide):
#   - Monday : main weekly run (always).
#   - Tuesday: FALLBACK -- runs only if Monday's run did NOT succeed this week.
#   - Friday : end-of-week refresh (always) -- captures Thu-evening US data before the weekend.
#
# RULE: fetch + validate + write logs ONLY. NEVER git commit / push. Changes are left for review.
# After each run a plain-English summary is written to tools\refresh_logs\LATEST_SUMMARY.txt.
#
# Run manually:  powershell -NoProfile -ExecutionPolicy Bypass -File E:\finance\tools\weekly_local_refresh.ps1
# Remove task:   schtasks /delete /tn "ValphaWeeklyRefresh" /f

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}   # capture py UTF-8 output

$repo = "E:\finance"
Set-Location $repo
$env:PYTHONUTF8 = "1"

$stamp  = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logdir = Join-Path $repo "tools\refresh_logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory -Force -Path $logdir | Out-Null }
$log    = Join-Path $logdir "weekly_refresh_$stamp.log"
$marker = Join-Path $logdir ".last_success"     # stores yyyy-MM-dd of the last successful run

function Log([string]$m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Output $line
  Add-Content -Path $log -Value $line -Encoding utf8
}
function RunPy([string]$script) {
  Log ("--- py {0} ---" -f $script)
  $out = & py $script 2>&1 | Out-String
  Add-Content -Path $log -Value $out -Encoding utf8
}
function Show-Toast([string]$title, [string]$msg) {
  # best-effort Windows toast; if unavailable the Desktop flag file is the real signal
  try {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $tn = $tmpl.GetElementsByTagName("text")
    $tn.Item(0).AppendChild($tmpl.CreateTextNode($title)) | Out-Null
    $tn.Item(1).AppendChild($tmpl.CreateTextNode($msg))   | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($tmpl)
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
  } catch { Log ("(toast unavailable: {0})" -f $_.Exception.Message) }
}

Log "=== Valpha local refresh START ($stamp) ==="
Log ("repo: {0}" -f $repo)

# --- decide whether to run today ------------------------------------------------
# Tuesday is a fallback: skip it if a run already succeeded this week (i.e. Monday was fine).
# Monday and Friday always run. Manual runs on any other day always run.
$today = (Get-Date).Date
$daysSinceMon = ([int]$today.DayOfWeek + 6) % 7          # Mon=0, Tue=1, ... Sun=6
$thisMonday = $today.AddDays(-$daysSinceMon)
if ($today.DayOfWeek -eq [System.DayOfWeek]::Tuesday) {
  $lastOk = $null
  if (Test-Path $marker) {
    try { $lastOk = [datetime]::ParseExact(((Get-Content $marker -Raw).Trim()), 'yyyy-MM-dd', $null) } catch {}
  }
  if ($lastOk -and $lastOk -ge $thisMonday) {
    Log ("Tuesday fallback not needed: a run already succeeded this week ({0})." -f $lastOk.ToString('yyyy-MM-dd'))
    & py tools\refresh_summary.py --skipped-reason "Monday's run already succeeded this week, so the Tuesday fallback was not needed." --log "$log"
    exit 0
  }
  Log "Tuesday fallback: no successful run yet this week -> running now."
}

# --- 1. insider (SEC Form 4) -- needs SEC_UA_CONTACT user env var (email stays out of the repo)
$insiderAttempted = "true"
if ([string]::IsNullOrWhiteSpace($env:SEC_UA_CONTACT)) {
  $insiderAttempted = "false"
  Log "[SKIP insider] SEC_UA_CONTACT not set -> SEC returns 403. Set it: setx SEC_UA_CONTACT '<app> <email>'"
} else {
  Log "SEC_UA_CONTACT is set (email not written to log)"
  RunPy "market-analysis\scripts\fetch_insider.py"
  RunPy "market-analysis\scripts\insider_signal.py"
}

# --- 2. ndx (Wikipedia NASDAQ-100 constituents)
RunPy "market-analysis\scripts\build_ndx.py"

# --- 3. seal append-only ledger (insider_signal_log may have grown) -- keep CSV / manifest consistent
RunPy "market-analysis\scripts\ledger_sidecar.py"

# --- 4. validate outputs (freshness + non-empty); update success marker if it passed
Log "=== validate ==="
$val = & py tools\validate_refresh.py 2>&1 | Out-String
$valExit = $LASTEXITCODE
Add-Content -Path $log -Value $val -Encoding utf8
if ($valExit -eq 0) {
  Set-Content -Path $marker -Value (Get-Date -Format 'yyyy-MM-dd') -Encoding ascii
  Log ("validation passed (success marker updated: {0})" -f (Get-Date -Format 'yyyy-MM-dd'))
} else {
  Log "!! validation FAILED (see above) -- success marker NOT updated (Tuesday fallback will retry)"
}

# --- 5. technical change list (NOT committed)
Log "=== changes to review (git, NOT committed) ==="
$st = & git -C $repo status --short 2>$null | Out-String
Add-Content -Path $log -Value $st -Encoding utf8
$ds = & git -C $repo diff --stat 2>$null | Out-String
Add-Content -Path $log -Value $ds -Encoding utf8

# --- 6. plain-English summary (console + LATEST_SUMMARY.txt + appended to this log)
Log "=== plain-English summary (also saved to tools\refresh_logs\LATEST_SUMMARY.txt) ==="
& py tools\refresh_summary.py --insider-attempted $insiderAttempted --validate-exit $valExit --log "$log"
$summaryExit = $LASTEXITCODE

# --- 7. self-check notify: quiet confirm toast on success; on a real problem, a can't-miss Desktop
#        file + an alert toast. If the "Valpha - ACTION NEEDED.txt" file is NOT on your Desktop, all is well.
$desktop = [Environment]::GetFolderPath('Desktop')
$flag    = Join-Path $desktop "Valpha - ACTION NEEDED.txt"
if ($summaryExit -eq 2) {
  try { Copy-Item -Path (Join-Path $logdir "LATEST_SUMMARY.txt") -Destination $flag -Force } catch {}
  Show-Toast "Valpha refresh - ACTION NEEDED" "Something did not refresh. Open 'Valpha - ACTION NEEDED.txt' on your Desktop."
  Log "NOTIFY: problem -> Desktop flag written + alert toast"
} else {
  if (Test-Path $flag) { Remove-Item $flag -Force -ErrorAction SilentlyContinue }
  Show-Toast "Valpha refresh OK" "insider + ndx updated, validation passed. Nothing to do."
  Log "NOTIFY: success -> confirm toast (nothing on your Desktop = all good)"
}

Log "=== DONE. Never committed / pushed. See LATEST_SUMMARY.txt, then commit manually if it looks right. ==="
