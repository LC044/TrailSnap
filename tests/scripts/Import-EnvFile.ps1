<#
.SYNOPSIS
    把一个 .env 文件加载进当前 PowerShell 会话的 $env:（子进程会继承）。

.DESCRIPTION
    解析 KEY=VALUE 行，忽略空行与 # 注释，去掉值两端的引号。
    设置到 Env: provider，使后续启动的 docker / pnpm / uv 子进程都能读到。
    这一份逻辑是 docker / 前端 e2e / 后端 / AI 四方共享同一环境变量的关键。

.PARAMETER Path
    .env 文件绝对路径。

.EXAMPLE
    . .\Import-EnvFile.ps1
    Import-EnvFile -Path .\tests\.env.test
#>
function Import-EnvFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "环境变量文件不存在: $Path"
    }

    $count = 0
    foreach ($raw in Get-Content -Path $Path) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }

        $idx = $line.IndexOf('=')
        if ($idx -le 0) { continue }

        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()

        # 去掉两端成对引号
        if ($val.Length -ge 2 -and
            (($val.StartsWith('"') -and $val.EndsWith('"')) -or
             ($val.StartsWith("'") -and $val.EndsWith("'")))) {
            $val = $val.Substring(1, $val.Length - 2)
        }

        Set-Item -Path "Env:$key" -Value $val
        $count++
    }

    Write-Verbose "已从 $Path 加载 $count 个环境变量"
}
