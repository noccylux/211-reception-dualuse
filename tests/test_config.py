import pytest

from dualuse.config import load_env, require


def test_load_env_fills_empty_and_missing_settings_but_keeps_real_ones(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EMPTY=from-file\nSET=from-file\nMISSING=from-file\nBLANK_IN_FILE=\n")
    # WSLENV forwards a Windows variable that is absent in the parent as an empty one.
    environ = {"EMPTY": "", "SET": "real"}
    load_env(env_file, environ)
    assert environ == {"EMPTY": "from-file", "SET": "real", "MISSING": "from-file"}


def test_load_env_without_a_file_changes_nothing(tmp_path):
    environ = {"EMPTY": ""}
    load_env(tmp_path / ".env", environ)
    assert environ == {"EMPTY": ""}


def test_require_returns_set_value(monkeypatch):
    monkeypatch.setenv("DUALUSE_TEST_SETTING", "value")
    assert require("DUALUSE_TEST_SETTING") == "value"


@pytest.mark.parametrize("value", [None, ""])
def test_require_names_missing_variable(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DUALUSE_TEST_SETTING", raising=False)
    else:
        monkeypatch.setenv("DUALUSE_TEST_SETTING", value)
    with pytest.raises(RuntimeError, match="DUALUSE_TEST_SETTING"):
        require("DUALUSE_TEST_SETTING")
