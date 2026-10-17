"""Public standalone scoring API. Importing this module opens no database/socket."""
import uuid

from .core import Engine, extract_call, RULE_VERSION
from .scoring import assess_call, get_policy, POLICY_VERSION

__version__ = "1.0.0"


class ScoringPlugin(Engine):
    """A self-contained SQLite scoring lifecycle; one instance per database/process."""

    def __init__(self, db_path=":memory:", settings=None, extractor=None):
        super().__init__(db_path=db_path, settings=settings, extractor=extractor)
        with self.lock:
            if not self.s.get("plugin_store_id"):
                self.s["plugin_store_id"] = str(uuid.uuid4())
                self._save()

    @property
    def store_id(self):
        """Persistent consumer identity; changes when this store is explicitly reset."""
        with self.lock:
            return self.s["plugin_store_id"]

    def reset(self):
        with self.lock:
            result = super().reset()
            self.s["plugin_store_id"] = str(uuid.uuid4())
            self._save()
            return result

    def close(self):
        with self.lock:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def create_app(db_path=":memory:", allowed_hosts=None):
    """Create an ASGI app explicitly; no global application instance exists."""
    from .web import create_app as factory
    return factory(db_path=db_path, allowed_hosts=allowed_hosts)


__all__ = ["ScoringPlugin", "Engine", "extract_call", "assess_call", "get_policy",
           "create_app", "RULE_VERSION", "POLICY_VERSION", "__version__"]
