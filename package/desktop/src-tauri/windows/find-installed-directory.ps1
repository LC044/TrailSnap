[CmdletBinding()]
param([string]$ProductName = 'TrailSnap', [string]$OutputFile)
$ErrorActionPreference = 'Stop'
$locations = @(
    foreach ($registryRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (-not (Test-Path -LiteralPath $registryRoot)) { continue }
        foreach ($key in Get-ChildItem -LiteralPath $registryRoot) {
            if ($key.PSChildName -ne $ProductName -and -not $key.PSChildName.StartsWith($ProductName + '-')) { continue }
            $entry = Get-ItemProperty -LiteralPath $key.PSPath
            if (-not $entry.InstallLocation) { continue }
            $path = [IO.Path]::GetFullPath(([string]$entry.InstallLocation).Trim('"')).TrimEnd('\')
            if ((Test-Path -LiteralPath (Join-Path $path 'uninstall.exe')) -and
                ((Test-Path -LiteralPath (Join-Path $path 'trailsnap-desktop.exe')) -or
                 (Test-Path -LiteralPath (Join-Path $path 'TrailSnap.exe')))) { $path }
        }
    }
) | Sort-Object -Unique
$result = @($locations) -join "`r`n"
if ($OutputFile) {
    # NSIS reads UTF-16 directly; console code pages cannot corrupt Chinese paths.
    [IO.File]::WriteAllText($OutputFile, $result, (New-Object Text.UnicodeEncoding($false, $false)))
} elseif ($result) { $result }
if (@($locations).Count -gt 1) { exit 2 }
exit 0
