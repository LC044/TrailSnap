[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallDirectory,
    [Parameter(Mandatory)][string]$InstanceTag,
    [string]$ProductName = 'TrailSnap'
)
$ErrorActionPreference = 'Stop'
if ($ProductName -match '[\\/]') { throw 'Invalid product name' }
$root = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
function Matches-Installation($Value) {
    if (-not $Value) { return $false }
    return [IO.Path]::GetFullPath(([string]$Value).Trim('"')).TrimEnd('\') -eq $root
}
$registryRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$replacement = Get-ItemProperty -LiteralPath (Join-Path $registryRoot "$ProductName-$InstanceTag")
if (-not (Matches-Installation $replacement.InstallLocation)) { throw 'Replacement uninstall entry does not match installation' }
$legacy = Join-Path $registryRoot $ProductName
if (Test-Path -LiteralPath $legacy) {
    $entry = Get-ItemProperty -LiteralPath $legacy
    if (Matches-Installation $entry.InstallLocation) {
        # Remove only the obsolete entry pointing to this exact installation.
        # A historical installation in another directory belongs to the user.
        Remove-Item -LiteralPath $legacy
    }
}
