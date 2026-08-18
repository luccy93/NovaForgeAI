"""Backend-specific conftest — sets up import paths without triggering the
full FastAPI application import chain (which has broken dependencies)."""

import importlib
import importlib.util
import os
import sys
import types

_BACKEND_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)

def _ensure_package(name: str, path: str) -> types.ModuleType:
    """Register or create a package module in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    pkg = types.ModuleType(name)
    pkg.__path__ = [path]
    pkg.__package__ = name
    sys.modules[name] = pkg
    return pkg


def _import_module_from_file(name: str, filepath: str) -> types.ModuleType:
    """Import a single module from a file, bypassing package __init__ chains."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    """Pre-load the SQLAlchemy Base and ALL model classes so that mapper
    configuration succeeds when code_intelligence models are instantiated.

    SQLAlchemy configures all mappers lazily on first instance creation.
    The ``Repository`` model has string-based relationships to
    ``Organization``, ``Project``, etc., so every model registered with
    the same ``Base`` must be importable before any instance is created.
    """
    app_dir = os.path.join(_BACKEND_ROOT, "app")

    # 1. Ensure package stubs exist so sub-imports don't trigger __init__.py
    _ensure_package("app", app_dir)
    _ensure_package("app.core", os.path.join(app_dir, "core"))
    _ensure_package("app.models", os.path.join(app_dir, "models"))
    _ensure_package("app.code_intelligence", os.path.join(app_dir, "code_intelligence"))

    # 2. Core modules (config → database)
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    for mod_name, filename in [
        ("app.core.config", "config.py"),
        ("app.core.database", "database.py"),
    ]:
        if mod_name not in sys.modules:
            _import_module_from_file(mod_name, os.path.join(app_dir, "core", filename))

    # 3. ALL app.models.* files — order matters (no circular refs, but
    #    cross-references via strings need every class registered).
    #    user.py and organization.py must come before support.py /
    #    conversation.py so that ``User`` and ``Organization`` are defined.
    for mod_name, filename in [
        ("app.models.user", "user.py"),
        ("app.models.organization", "organization.py"),
        ("app.models.repository", "repository.py"),
        ("app.models.support", "support.py"),
        ("app.models.conversation", "conversation.py"),
    ]:
        if mod_name not in sys.modules:
            _import_module_from_file(mod_name, os.path.join(app_dir, "models", filename))

    # 4. Code intelligence models
    _ensure_package("app.code_intelligence", os.path.join(app_dir, "code_intelligence"))
    _import_module_from_file(
        "app.code_intelligence.models",
        os.path.join(app_dir, "code_intelligence", "models.py"),
    )

    # 5. Force mapper configuration NOW while all classes are available.
    from sqlalchemy.orm import configure_mappers
    configure_mappers()


_bootstrap()
