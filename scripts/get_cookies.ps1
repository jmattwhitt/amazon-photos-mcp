# Amazon Photos MCP — Cookie Extractor (PowerShell wrapper)
#
# Convenience wrapper — sets working directory and forwards args to the
# Python script. No elevation logic (Chrome/Edge app-bound encryption is a
# rookie-rs limitation, not a privilege issue — use Firefox or --manual).
#
# Usage (from repo root):
#   .\scripts\get_cookies.ps1
#   .\scripts\get_cookies.ps1 --browser firefox
#   .\scripts\get_cookies.ps1 --manual
#   .\scripts\get_cookies.ps1 --show

param(
    [string]$Browser = "",
    [switch]$Show,
    [switch]$Manual
)

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot     = Split-Path -Parent $ScriptDir
$PythonScript = Join-Path $ScriptDir "get_cookies.py"

$PythonArgs = @()
if ($Browser) { $PythonArgs += "--browser", $Browser }
if ($Show)    { $PythonArgs += "--show" }
if ($Manual)  { $PythonArgs += "--manual" }

Set-Location $RepoRoot
& uv run --extra scripts python $PythonScript @PythonArgs
exit $LASTEXITCODE
