"""Portable map plugin; importing performs no I/O or network requests."""
__version__ = "1.0.0"


def create_app(db_path=":memory:", allowed_hosts=None, transport=None):
    """Build a standalone or mounted ASGI app. See README for trust boundaries."""
    from .api import create_app as factory
    return factory(db_path=db_path, allowed_hosts=allowed_hosts, transport=transport)


def __getattr__(name):
    if name == "StateStore":
        from .store import StateStore
        return StateStore
    raise AttributeError(name)
