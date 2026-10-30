#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("isolated", "attach")]
    [string]$Mode = "isolated",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $candidate = Join-Path $HOME ".local\bin\uv.exe"
    if (Test-Path $candidate) {
        $uv = $candidate
    }
}
if (-not $uv) {
    throw "uv not found. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
}

$commit = "1e9741af96c45bcac9e619c3ba32264bac6950e7"
$source = "git+https://github.com/youngminsw/Origin-Pro-MCP.git@$commit"
$installArgs = @("tool", "install", $source, "--with", "mcp<2", "--force")

if ($DryRun) {
    Write-Host ("uv " + ($installArgs -join " "))
}
else {
    & $uv @installArgs
    if ($LASTEXITCODE -ne 0) {
        throw "uv tool install failed with exit code $LASTEXITCODE"
    }
}

$exe = Join-Path $HOME ".local\bin\origin-pro-mcp.exe"
if (-not (Test-Path $exe)) {
    $command = Get-Command origin-pro-mcp -ErrorAction SilentlyContinue
    if ($command) {
        $exe = $command.Source
    }
    else {
        Write-Warning "origin-pro-mcp.exe not found. Locate it with: uv tool dir"
    }
}

$attach = if ($Mode -eq "attach") { "1" } else { "0" }
$entry = [ordered]@{
    "origin-pro" = [ordered]@{
        command = $exe
        args    = @()
        env     = [ordered]@{
            ORIGIN_PRO_MCP_USE_DAEMON = "1"
            ORIGIN_PRO_MCP_ATTACH     = $attach
        }
    }
}

Write-Host ""
Write-Host 'Add this under "mcpServers" in %USERPROFILE%\.qoder-cn\settings.json:'
$entry | ConvertTo-Json -Depth 6
