const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

test('installer releases an orphaned runtime file lock and leaves other installations running', {
  skip: process.platform !== 'win32', timeout: 45000,
}, () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'trailsnap-installer-test-'))
  const runner = path.join(temporaryRoot, 'test.ps1')
  const helper = path.resolve(__dirname, '../../../desktop/src-tauri/windows/stop-installed-processes.ps1')
  const powershell = path.join(process.env.SystemRoot, 'System32/WindowsPowerShell/v1.0/powershell.exe')
  fs.writeFileSync(runner, String.raw`
param([string]$Root, [string]$Helper)
$ErrorActionPreference = 'Stop'
$inside = Join-Path $Root 'installed'
$outside = Join-Path $Root 'installed-other'
New-Item -ItemType Directory -Path $inside,$outside -Force | Out-Null
$executable = Join-Path $inside 'trailsnap-server.exe'
Add-Type -OutputAssembly $executable -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.IO;
using System.Threading;
public class LockFixture {
    public static void Main(string[] args) {
        using (var file = new FileStream(args[0], FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) {
            Thread.Sleep(30000);
        }
    }
}
'@
Copy-Item -LiteralPath $executable -Destination (Join-Path $outside 'trailsnap-server.exe')
$lock = Join-Path $inside 'pillow.pyd'
$otherLock = Join-Path $outside 'pillow.pyd'
$first = $null
$second = $null
try {
    $first = Start-Process -FilePath $executable -ArgumentList ('"' + $lock + '"') -WindowStyle Hidden -PassThru
    $second = Start-Process -FilePath (Join-Path $outside 'trailsnap-server.exe') -ArgumentList ('"' + $otherLock + '"') -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while (!(Test-Path -LiteralPath $lock) -or !(Test-Path -LiteralPath $otherLock)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Fixtures did not acquire file locks' }
        Start-Sleep -Milliseconds 100
    }
    $locked = $false
    try { $handle = [IO.File]::Open($lock, 'Open', 'ReadWrite', 'None'); $handle.Dispose() }
    catch [IO.IOException] { $locked = $true }
    if (!$locked) { throw 'Fixture did not reproduce the file lock' }
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Helper -InstallDirectory $inside
    if ($LASTEXITCODE -ne 0) { throw 'Installer cleanup failed' }
    if (Get-Process -Id $first.Id -ErrorAction SilentlyContinue) { throw 'Orphaned server survived' }
    if (!(Get-Process -Id $second.Id -ErrorAction SilentlyContinue)) { throw 'Other installation was stopped' }
    $handle = [IO.File]::Open($lock, 'Open', 'ReadWrite', 'None')
    $handle.Dispose()
    Write-Output 'Runtime lock released; sibling installation preserved'
} finally {
    foreach ($fixture in @($first,$second)) {
        if ($fixture) { Stop-Process -Id $fixture.Id -Force -ErrorAction SilentlyContinue }
    }
}
`)
  try {
    const result = spawnSync(powershell, ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', runner,
      '-Root', temporaryRoot, '-Helper', helper], { encoding: 'utf8', timeout: 40000, windowsHide: true })
    assert.equal(result.status, 0, `${result.error || ''}\n${result.stdout}\n${result.stderr}`)
    assert.match(result.stdout, /Runtime lock released; sibling installation preserved/)
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true })
  }
})
