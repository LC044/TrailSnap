# Select the shared nightly PR and start from its remote head, never from the live checkout.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateRange(1, 4)][int]$Slot,
    [switch]$InspectOnly
)

$ErrorActionPreference = 'Stop'
$env:GH_PROMPT_DISABLED = '1'
$repo = 'LC044/TrailSnap'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$now = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
$result = [ordered]@{ state = 'LOOKUP_ERROR'; slot = $Slot }
try {
    $raw = & gh pr list -R $repo --base master --state open --label codex-automation --limit 50 --json number,headRefName,headRefOid,isCrossRepository,isDraft,url 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot list nightly PRs' }
    $prs = @((($raw -join "`n") | ConvertFrom-Json -NoEnumerate) | Where-Object {
        !$_.isCrossRepository -and $_.headRefName -match '^(codex/)?nightly/test-watch-\d{8}$'
    })
    if ($prs.Count -gt 1) {
        $result.state = 'MULTIPLE_NIGHTLY_PRS'
        $result.prs = @($prs | Select-Object -First 4 -ExpandProperty number)
    } else {
        $candidate = $prs | Select-Object -First 1
        $branch = if ($candidate) { $candidate.headRefName } else { 'codex/nightly/test-watch-' + $now.ToString('yyyyMMdd') }
        $result.branch = $branch
        if ($candidate) {
            $result.pr = $candidate.number; $result.head = $candidate.headRefOid
            $result.url = $candidate.url; $result.draft = $candidate.isDraft
        }
        $result.state = 'READY'
        if (!$InspectOnly) {
            $refs = @('refs/heads/master:refs/remotes/origin/master')
            if ($candidate) { $refs += "refs/heads/${branch}:refs/remotes/origin/$branch" }
            $null = & git -C $root fetch --quiet --no-tags --no-write-fetch-head origin @refs 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'Could not fetch nightly refs' }
            $base = & git -C $root rev-parse --verify refs/remotes/origin/master 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'Could not resolve origin/master' }
            $head = $base
            if ($candidate) {
                $head = & git -C $root rev-parse --verify "refs/remotes/origin/$branch" 2>$null
                if ($LASTEXITCODE -ne 0) { throw 'Could not resolve nightly branch' }
                if ($head -ne $candidate.headRefOid) { $result.state = 'HEAD_CHANGED' }
            }
            if ($result.state -eq 'READY') {
                $parent = Join-Path $root 'tests/artifacts/nightly-ci/worktrees'
                $null = New-Item -ItemType Directory -Path $parent -Force
                $id = '{0}-{1}-{2}' -f $now.ToString('yyyyMMdd-HHmmss'), $Slot, [guid]::NewGuid().ToString('N').Substring(0, 8)
                $path = Join-Path $parent $id
                $null = & git -C $root worktree add --detach --quiet $path $head 2>$null
                if ($LASTEXITCODE -ne 0) { throw 'Failed to create isolated worktree' }
                $result.worktree = $path; $result.base = $base; $result.head = $head
                $null = & git -C $path merge-base --is-ancestor $base $head 2>$null
                if ($LASTEXITCODE -notin @(0, 1)) { throw 'Could not compare nightly head and master' }
                $result.baseNeedsSync = $LASTEXITCODE -eq 1
            }
        }
    }
} catch {
    $result.state = 'SETUP_ERROR'
    $result.reason = $_.Exception.Message
}
$result | ConvertTo-Json -Depth 4 -Compress
