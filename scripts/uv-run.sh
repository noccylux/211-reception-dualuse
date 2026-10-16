#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        # Git's own cygpath: Anaconda ships one that can precede it on PATH and
        # maps /d/... to D:\anaconda3\Library\d\..., which wsl.exe rejects.
        windows_repo="$(/usr/bin/cygpath -w "$repo_dir")"
        # Keep MSYS from rewriting Linux command arguments passed to wsl.exe.
        # WSL_UTF8 makes wsl.exe errors readable instead of UTF-16 mojibake.
        export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' WSL_UTF8=1
        exec wsl.exe -d WSL --cd "$windows_repo" --exec bash scripts/uv-run.sh "$@"
        ;;
    Linux) ;;
    *)
        echo "This launcher requires WSL WSL or Git Bash on Windows." >&2
        exit 1
        ;;
esac

if [[ "${WSL_DISTRO_NAME:-}" != WSL ]]; then
    echo "Run in WSL: wsl.exe -d WSL -- bash scripts/uv-run.sh ..." >&2
    exit 1
fi

if [[ $# -eq 0 ]]; then
    echo "Usage: bash scripts/uv-run.sh <command> [arguments...]" >&2
    exit 2
fi

cd "$repo_dir"
export VIRTUAL_ENV="$repo_dir/.venv_wsl"
if [[ ! -f "$VIRTUAL_ENV/pyvenv.cfg" || ! -x "$VIRTUAL_ENV/bin/python" ]]; then
    echo "Missing or broken WSL environment: $VIRTUAL_ENV. Restore it explicitly with Linux uv; no automatic repair was attempted." >&2
    exit 1
fi

# Execute in the existing environment without invoking uv's environment manager.
# See docs/changes/2026-09-25-008-safe-wsl-command-launcher.md.
export PATH="$VIRTUAL_ENV/bin:$PATH"
unset PYTHONHOME
"$VIRTUAL_ENV/bin/python" -c 'import sys; from pathlib import Path; sys.exit(0 if sys.platform == "linux" and Path(sys.prefix) == Path(sys.argv[1]) else "Invalid WSL virtual environment")' "$VIRTUAL_ENV"
exec "$@"
