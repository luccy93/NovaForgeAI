"""Plugin SDK — base plugin interface, lifecycle hooks, and sandbox isolation."""

import importlib
import inspect
import json
import os
import sys
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PluginMeta:
    name: str
    version: str
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


class PluginSandbox:
    """Minimal sandbox: restricts plugin file access to its own directory."""

    def __init__(self, plugin_dir: str):
        self._plugin_dir = os.path.abspath(plugin_dir)

    def validate_path(self, path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self._plugin_dir, path))
        if not abs_path.startswith(self._plugin_dir):
            raise PermissionError(f"Access denied: {path}")
        return abs_path

    def read_file(self, path: str) -> str:
        full = self.validate_path(path)
        with open(full) as f:
            return f.read()

    def write_file(self, path: str, content: str):
        full = self.validate_path(path)
        with open(full, "w") as f:
            f.write(content)


class BasePlugin(ABC):
    """Abstract base class for all NovaForge plugins."""

    def __init__(self):
        self.meta: Optional[PluginMeta] = None
        self.sandbox: Optional[PluginSandbox] = None
        self._initialized = False

    @abstractmethod
    def initialize(self) -> None:
        ...

    def on_event(self, event_type: str, payload: dict) -> Optional[dict]:
        return None

    def on_agent_run(self, agent: str, task: str, context: dict) -> Optional[dict]:
        return None

    def on_api_request(self, method: str, path: str, body: dict) -> Optional[dict]:
        return None

    def on_startup(self) -> None:
        pass

    def on_shutdown(self) -> None:
        pass

    def health_check(self) -> dict:
        return {"status": "healthy", "plugin": self.meta.name if self.meta else "unknown"}


class PluginLoader:
    """Discovers, loads, and manages plugins from a directory."""

    def __init__(self, plugin_dir: Optional[str] = None):
        self.plugin_dir = plugin_dir or os.path.join(
            os.path.dirname(__file__), "..", "plugins"
        )
        self.plugins: dict[str, BasePlugin] = {}

    def discover(self) -> list[str]:
        if not os.path.isdir(self.plugin_dir):
            return []
        return [
            d for d in os.listdir(self.plugin_dir)
            if os.path.isdir(os.path.join(self.plugin_dir, d))
            and not d.startswith("_")
        ]

    def load_plugin(self, name: str) -> Optional[BasePlugin]:
        plugin_path = os.path.join(self.plugin_dir, name)
        if not os.path.isdir(plugin_path):
            return None

        manifest_path = os.path.join(plugin_path, "plugin.json")
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
        else:
            manifest = {"name": name, "version": "1.0.0"}

        sys.path.insert(0, os.path.dirname(plugin_path))
        try:
            module = importlib.import_module(f"{name}.main")
            for _, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BasePlugin)
                    and obj is not BasePlugin
                ):
                    instance = obj()
                    instance.meta = PluginMeta(
                        name=manifest.get("name", name),
                        version=manifest.get("version", "1.0.0"),
                        description=manifest.get("description", ""),
                        author=manifest.get("author", ""),
                        hooks=manifest.get("hooks", []),
                    )
                    instance.sandbox = PluginSandbox(plugin_path)
                    return instance
        except Exception as e:
            print(f"Failed to load plugin '{name}': {e}")
            traceback.print_exc()
        finally:
            sys.path.pop(0)
        return None

    def load_all(self) -> dict[str, BasePlugin]:
        for name in self.discover():
            plugin = self.load_plugin(name)
            if plugin:
                self.plugins[name] = plugin
        return self.plugins

    def initialize_all(self) -> list[str]:
        initialized = []
        for name, plugin in self.plugins.items():
            try:
                plugin.initialize()
                plugin._initialized = True
                plugin.on_startup()
                initialized.append(name)
            except Exception as e:
                print(f"Failed to initialize plugin '{name}': {e}")
        return initialized

    def shutdown_all(self):
        for name, plugin in self.plugins.items():
            try:
                plugin.on_shutdown()
            except Exception:
                pass


plugin_loader = PluginLoader()
