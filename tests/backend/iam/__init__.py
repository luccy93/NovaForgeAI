"""IAM package init for tests."""
import sys
import importlib

_bootstrap_done = False


def _bootstrap():
    global _bootstrap_done
    if _bootstrap_done:
        return
    _bootstrap_done = True
    if "app" not in sys.modules:
        import types
        stub = types.ModuleType("app")
        stub.__path__ = []
        sys.modules["app"] = stub
    for mod_name in [
        "app.core", "app.core.config", "app.core.logging",
        "app.core.database", "app.core.events",
    ]:
        if mod_name not in sys.modules:
            try:
                importlib.import_module(mod_name)
            except Exception:
                pass


_bootstrap()
