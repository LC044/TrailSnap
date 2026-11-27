# GitHub-only validation for TrailSnap nightly automation. No local test execution.
[CmdletBinding(DefaultParameterSetName = 'Baseline')]
param(
    [Parameter(ParameterSetName = 'Baseline')][switch]$Baseline,
    [Parameter(ParameterSetName = 'PR', Mandatory)][ValidateRange(1, 2147483647)][int]$PullRequest,
    [Parameter(ParameterSetName = 'PR', Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedHead,
    [Parameter(ParameterSetName = 'PR')][switch]$Merge,
    [Parameter(ParameterSetName = 'PR')][switch]$CheckOnce,
    [ValidateRange(5, 120)][int]$TimeoutMinutes = 65
)

$ErrorActionPreference = 'Stop'
$repo = 'LC044/TrailSnap'
$env:GH_PROMPT_DISABLED = '1'
$isPR = $PSCmdlet.ParameterSetName -eq 'PR'
$result = [ordered]@{ state = 'LOOKUP_ERROR' }
if ($isPR) { $result.pr = $PullRequest; $result.head = $ExpectedHead; $result.url = "https://github.com/$repo/pull/$PullRequest" }
$checkedBase = $null
$deadline = [DateTimeOffset]::UtcNow.AddMinutes($TimeoutMinutes)

function Read-GhJson([string[]]$Arguments, [int[]]$ValidExitCodes = @(0)) {
    $text = & gh @Arguments 2>$null
    if ($LASTEXITCODE -notin $ValidExitCodes) { throw 'GitHub query failed' }
    return ($text -join "`n" | ConvertFrom-Json -NoEnumerate -ErrorAction Stop)
}

function Limit-Text([string]$Text, [int]$Size) {
    $Text = $Text -replace '[\x00-\x1f\x7f]', ' '
    return $Text.Substring(0, [Math]::Min($Size, $Text.Length))
}

function Test-EveningMergeWindow {
    $hour = (Get-Date -AsUTC).AddHours(8).Hour
    return ($hour -ge 20 -and $hour -lt 23)
}

function Read-NightlyPR {
    Read-GhJson -Arguments @('pr', 'view', "$PullRequest", '-R', $repo, '--json', 'headRefName,headRefOid,baseRefName,baseRefOid,state,isDraft,isCrossRepository,labels,mergeStateStatus,statusCheckRollup')
}

function Test-NightlyPR($Pr) {
    return ($Pr.state -eq 'OPEN' -and !$Pr.isCrossRepository -and $Pr.baseRefName -eq 'master' -and
        $Pr.headRefName -match '^(codex/)?nightly/test-watch-\d{8}$' -and 'codex-automation' -in $Pr.labels.name)
}

function Get-Failures($Checks) {
    @($Checks | Select-Object -First 3 | ForEach-Object {
        $link = [string]$_.link
        $id = if ($link -match '/job/(\d+)(?:[/?#]|$)') { $Matches[1] } else { $_.databaseId }
        @{ name = (Limit-Text $_.name 110); workflow = (Limit-Text $_.workflow 60); job = $id }
    })
}

function Add-FailureExcerpt {
    # Keep specific assertions/errors instead of echoing the entire failure log.
    $job = @($result.failures | Where-Object { $_.job -match '^\d+$' } | Select-Object -First 1)
    if (!$job.Count) { return }
    $lines = & gh run view -R $repo --job $job[0].job --log-failed 2>$null
    if ($LASTEXITCODE -ne 0) { return }
    $result.excerptJob = $job[0].job
    $result.excerpt = @($lines | Where-Object { $_ -match '(?i)\bFAILED\b|\b(?:AssertionError|Error|TimeoutError)\s*:|##\[error\]|\btest_\w+.*::' } |
        Select-Object -Last 8 | ForEach-Object { Limit-Text ($_ -replace '^[^\t]*\t[^\t]*\t', '') 220 })
}

try {
    if ($Merge -and ($CheckOnce -or !(Test-EveningMergeWindow))) {
        $result.state = 'MERGE_BLOCKED'
        $result.reason = 'Merge only in the 20:00–23:00 Asia/Shanghai window'
    } else {
        do {
            $result.state = 'PENDING'
            if ($isPR) {
                $pr = Read-NightlyPR
                if (!(Test-NightlyPR $pr)) { $result.state = 'PR_NOT_ELIGIBLE'; break }
                if ($pr.headRefOid -ne $ExpectedHead) { $result.state = 'HEAD_CHANGED'; break }
                if ($null -eq $checkedBase) { $checkedBase = $pr.baseRefOid }
                if ($pr.baseRefOid -ne $checkedBase) { $result.state = 'BASE_CHANGED'; break }
                # Right after a push GitHub may have registered no checks yet.
                if (@($pr.statusCheckRollup | Where-Object { $null -ne $_ }).Count -gt 0) {
                    $checks = Read-GhJson -Arguments @('pr', 'checks', "$PullRequest", '-R', $repo, '--json', 'bucket,event,link,name,workflow') -ValidExitCodes @(0, 1, 8)
                    $afterChecks = Read-NightlyPR
                    if (!(Test-NightlyPR $afterChecks)) { $result.state = 'PR_NOT_ELIGIBLE'; break }
                    if ($afterChecks.headRefOid -ne $ExpectedHead) { $result.state = 'HEAD_CHANGED'; break }
                    if ($afterChecks.baseRefOid -ne $checkedBase) { $result.state = 'BASE_CHANGED'; break }
                    $bad = @($checks | Where-Object { $_.bucket -in @('fail', 'cancel') })
                    $e2e = @($checks | Where-Object { $_.event -eq 'pull_request' -and $_.workflow -eq 'Tests' -and $_.name -eq 'E2E (Playwright + docker compose)' })
                    if ($bad.Count) {
                        $result.state = if ($bad.bucket -contains 'fail') { 'CI_FAIL' } else { 'CI_INCOMPLETE' }
                        $result.failures = @(Get-Failures $bad)
                        if ($result.state -eq 'CI_FAIL') { Add-FailureExcerpt }
                    } elseif ($e2e.Count -eq 1 -and $e2e[0].bucket -eq 'pass' -and
                        !@($checks | Where-Object { $_.bucket -notin @('pass', 'skipping') }).Count) {
                        $result.state = 'PASS'
                        $result.passed = @($checks | Where-Object bucket -eq 'pass').Count
                        $result.skipped = @($checks | Where-Object bucket -eq 'skipping').Count
                        if ($Merge) {
                            $result.state = 'MERGE_BLOCKED'
                            $result.reason = 'Draft or not clean'
                            if (!$afterChecks.isDraft -and $afterChecks.mergeStateStatus -eq 'CLEAN') {
                                $commonBase = & gh api "repos/$repo/compare/$checkedBase...$ExpectedHead" --jq '.merge_base_commit.sha' 2>$null
                                if ($LASTEXITCODE -ne 0 -or $commonBase -ne $checkedBase) {
                                    $result.reason = 'PR head does not contain the checked master SHA'
                                } else {
                                    $beforeMerge = Read-NightlyPR
                                    if (!(Test-NightlyPR $beforeMerge) -or $beforeMerge.isDraft -or $beforeMerge.mergeStateStatus -ne 'CLEAN') {
                                        $result.reason = 'PR no longer eligible'
                                    } elseif (!(Test-EveningMergeWindow) -or $beforeMerge.headRefOid -ne $ExpectedHead -or $beforeMerge.baseRefOid -ne $checkedBase) {
                                        $result.reason = 'Head/base changed or merge window ended'
                                    } else {
                                        # REST merge rejects a changed head, obeys branch rules, and does not enqueue auto-merge.
                                        $result.state = 'MERGE_UNCONFIRMED'
                                        $result.reason = 'Verify PR state before retrying'
                                        $receipt = Read-GhJson -Arguments @('api', '--method', 'PUT', "repos/$repo/pulls/$PullRequest/merge", '-f', "sha=$ExpectedHead", '-f', 'merge_method=squash')
                                        if ($receipt.merged -eq $true) {
                                            $result.state = 'MERGED'; $result.mergeSha = $receipt.sha; $result.Remove('reason')
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            } else {
                $runs = Read-GhJson -Arguments @('run', 'list', '-R', $repo, '--workflow', 'tests.yml', '--branch', 'master', '--limit', '12', '--json', 'databaseId,event,createdAt,status,conclusion,headSha,url')
                $run = $runs | Where-Object { $_.event -in @('push', 'schedule') } | Select-Object -First 1
                if ($null -eq $run) { $result.state = 'NO_RUN'; break }
                $result.runId = $run.databaseId; $result.head = $run.headSha; $result.url = $run.url
                $result.createdAt = $run.createdAt
                if ($run.status -eq 'completed') {
                    $result.state = switch ($run.conclusion) { 'success' { 'PASS' } { $_ -in @('failure', 'timed_out') } { 'CI_FAIL' } default { 'CI_INCOMPLETE' } }
                    if ($result.state -eq 'CI_FAIL') {
                        $detail = Read-GhJson -Arguments @('run', 'view', "$($run.databaseId)", '-R', $repo, '--json', 'jobs')
                        $result.failures = @(Get-Failures ($detail.jobs | Where-Object { $_.conclusion -in @('failure', 'timed_out') }))
                        Add-FailureExcerpt
                    }
                }
                break  # A baseline is a snapshot, not another workflow to start or wait for.
            }
            if ($result.state -ne 'PENDING' -or $CheckOnce) { break }
            if ([DateTimeOffset]::UtcNow.AddMinutes(5) -gt $deadline) { $result.state = 'CI_PENDING_TIMEOUT'; break }
            Start-Sleep -Seconds 300
        } while ($true)
    }
} catch {
    if ($result.state -eq 'CI_FAIL') { $result.detailUnavailable = $true }
    elseif ($result.state -ne 'MERGE_UNCONFIRMED') { $result.state = 'LOOKUP_ERROR' }
}
$result | ConvertTo-Json -Depth 5 -Compress
