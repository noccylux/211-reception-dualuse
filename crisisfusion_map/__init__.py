"""Portable map plugin; importing performs no I/O or network requests."""
__version__ = "1.0.0"


def create_app(db_path=":memory:", allowed_hosts=None, transport=None, area=None):
    """Build a standalone or mounted ASGI app. See README for trust boundaries.

    ``area`` is the service-area spec (see ``geo.LA_COUNTY``); the default is LA County.
    """
    from .api import create_app as factory
    return factory(db_path=db_path, allowed_hosts=allowed_hosts, transport=transport, area=area)


def __getattr__(name):
    if name == "StateStore":
        from .store import StateStore
        return StateStore
    raise AttributeError(name)
