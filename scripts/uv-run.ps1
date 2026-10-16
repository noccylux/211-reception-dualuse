#requires -Version 7.3
# Standard native argument passing preserves empty strings and embedded quotes.
$PSNativeCommandArgumentPassing = 'Standard'
$repoDirectory = Split-Path -Parent $PSScriptRoot
& wsl.exe -d WSL --cd $repoDirectory --exec bash scripts/uv-run.sh @args
exit $LASTEXITCODE
