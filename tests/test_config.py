import pytest

from dualuse.config import require


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
