[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallDirectory
)

$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
public static class TrailSnapInstallerPaths {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetLongPathName(string path, StringBuilder buffer, uint length);
}
'@
function Get-LongPath([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path)
    $buffer = New-Object Text.StringBuilder 32768
    $length = [TrailSnapInstallerPaths]::GetLongPathName($fullPath, $buffer, $buffer.Capacity)
    if ($length -gt 0 -and $length -lt $buffer.Capacity) { return $buffer.ToString() }
    return $fullPath
}
$installRoot = (Get-LongPath $InstallDirectory).TrimEnd('\') + '\'
if ($installRoot -eq [IO.Path]::GetPathRoot($installRoot)) {
    throw 'Refusing to stop processes for a drive root.'
}

# PyInstaller's bootloader and Python runtime are separate processes. An
# installer can kill the desktop window before its exit handler stops either
# process, leaving DLLs/PYD files locked. Match paths, never global image names.
function Get-InstalledProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and
        (Get-LongPath $_.ExecutablePath).StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase) -and
        $_.Name -in @('trailsnap-desktop.exe', 'trailsnap-server.exe', 'trailsnap-ai.exe', 'llama-server.exe')
    })
}

# Give the app a chance to run its normal server/AI shutdown first.
foreach ($appProcess in (Get-InstalledProcesses | Where-Object Name -eq 'trailsnap-desktop.exe')) {
    $app = Get-Process -Id $appProcess.ProcessId -ErrorAction SilentlyContinue
    if ($app) { [void]$app.CloseMainWindow() }
}
Start-Sleep -Milliseconds 500

$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    $remaining = @(Get-InstalledProcesses)
    if ($remaining.Count -eq 0) { exit 0 }
    foreach ($installedProcess in $remaining) {
        # Recheck the PID's path before terminating it, in case a process exited
        # and Windows reused its PID since the snapshot above.
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($installedProcess.ProcessId)"
        if ($current -and $current.ExecutablePath -eq $installedProcess.ExecutablePath) {
            Stop-Process -Id $current.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Milliseconds 200
} while ([DateTime]::UtcNow -lt $deadline)

if (@(Get-InstalledProcesses).Count -gt 0) {
    throw 'Unable to stop the previous TrailSnap runtime.'
}
