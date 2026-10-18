[CmdletBinding()]
param([Parameter(Mandatory)][string]$InstallDirectory)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
if ($root.TrimEnd('\') -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) { throw 'Refusing to remove a drive root.' }
$prefix = $root + '\'
$app = [IO.Path]::GetFullPath((Join-Path $root 'app'))
if (-not $app.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Program directory escaped installation.' }
if (Test-Path -LiteralPath (Join-Path $root 'instance.json')) {
    $config = Get-Content -LiteralPath (Join-Path $root 'instance.json') -Raw | ConvertFrom-Json
    $data = if ($config.dataRoot.kind -eq 'relative') { Join-Path $root $config.dataRoot.path } else { $config.dataRoot.path }
    $data = [IO.Path]::GetFullPath($data).TrimEnd('\')
    if ($data -eq $app -or $data.StartsWith($app + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Configured library is inside app; preserving it. Move the library before removing program files.'
    }
}
if (Test-Path -LiteralPath $app) {
    $entry = Get-Item -LiteralPath $app
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to remove a linked program directory.' }
    if (Get-ChildItem -LiteralPath $app -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) {
        throw 'Refusing to remove linked program resources.'
    }
    Remove-Item -LiteralPath $app -Recurse -Force
}
foreach ($name in @('TrailSnap.exe', 'portable.json', 'portable-launcher.exe')) {
    $target = [IO.Path]::GetFullPath((Join-Path $root $name))
    if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid program file path.' }
    if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
}
# instance.json, userdata, maintenance and snapshots intentionally survive.
