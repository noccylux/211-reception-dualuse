import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("retell_setup", Path(__file__).resolve().parent.parent / "scripts/retell_setup.py")
retell_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retell_setup)


def test_endpoints_put_the_secret_in_the_websocket_path_only():
    websocket, webhook = retell_setup.endpoints("https://abc.trycloudflare.com/", "s3cret")
    assert websocket == "wss://abc.trycloudflare.com/llm-websocket/s3cret"
    assert webhook == "https://abc.trycloudflare.com/retell-webhook"


@pytest.mark.parametrize("url", ["http://abc.trycloudflare.com", "abc.trycloudflare.com", "https://abc.trycloudflare.com/x"])
def test_endpoints_require_a_bare_https_origin(url):
    with pytest.raises(SystemExit):
        retell_setup.endpoints(url, "s3cret")
