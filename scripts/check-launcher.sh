#!/usr/bin/env bash
set -euo pipefail
launcher="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/uv-run.sh"
cd /tmp
bash "$launcher" python -c '
import os
import sys
from pathlib import Path

expected = ["a b", "", "a\"b", "a\x27b", "$(touch unwanted)", "/tmp/path", "中文", "a\nb", "trailing\\"]
assert sys.argv[1:] == expected, repr(sys.argv[1:])
assert sys.platform == "linux"
assert os.environ["WSL_DISTRO_NAME"] == "WSL"
assert Path(sys.prefix) == Path.cwd() / ".venv_wsl"
print("WSL environment, working directory, and argument preservation passed")
' 'a b' '' 'a"b' "a'b" '$(touch unwanted)' '/tmp/path' '中文' $'a\nb' 'trailing\'
status=0
bash "$launcher" python -c 'raise SystemExit(37)' || status=$?
[[ "$status" == 37 ]]
echo "Exit status preservation passed"
