#requires -Version 7.3
# Run a command in the project's WSL virtual environment through scripts/uv-run.sh.
# The WSL distribution comes from DUALUSE_WSL_DISTRO in the environment or in .env.
# Standard native argument passing preserves empty strings and embedded quotes.
$PSNativeCommandArgumentPassing = 'Standard'
$repoDirectory = Split-Path -Parent $PSScriptRoot
$distro = $env:DUALUSE_WSL_DISTRO
if (-not $distro) {
    $envFile = Join-Path $repoDirectory '.env'
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^DUALUSE_WSL_DISTRO=' } | Select-Object -Last 1
        if ($line) { $distro = ($line -replace '^DUALUSE_WSL_DISTRO=', '').Trim().Trim('"').Trim("'") }
    }
}
if (-not $distro) {
    Write-Error "Set DUALUSE_WSL_DISTRO (in .env or the environment) to the WSL distribution that holds .venv_wsl, or use 'uv run' (README.md, Run)."
    exit 1
}
& wsl.exe -d $distro --cd $repoDirectory --exec bash scripts/uv-run.sh @args
exit $LASTEXITCODE
