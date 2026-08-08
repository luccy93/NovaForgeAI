from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type
from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, PluginMetadata, PluginStatus, PluginType


class PluginLoadError(Exception):
    pass


class PluginInfo(BaseModel):
    metadata: PluginMetadata
    status: PluginStatus = PluginStatus.UNLOADED
    config: Dict[str, Any] = Field(default_factory=dict)
    instance: Optional[BasePlugin] = None
    error: Optional[str] = None
    load_time: Optional[float] = None
    model_config = {"arbitrary_types_allowed": True}


class PluginRegistry:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._plugins: Dict[str, PluginInfo] = {}
        self._load_order: List[str] = []
        self._local_plugin_dirs: List[Path] = []

    @property
    def plugins(self) -> Dict[str, PluginInfo]:
        return self._plugins

    @property
    def loaded_plugins(self) -> List[PluginInfo]:
        return [p for p in self._plugins.values() if p.status == PluginStatus.READY]

    @property
    def failed_plugins(self) -> List[PluginInfo]:
        return [p for p in self._plugins.values() if p.status == PluginStatus.ERROR]

    def add_local_plugin_dir(self, path: Path) -> None:
        path = path.resolve()
        if path not in self._local_plugin_dirs:
            self._local_plugin_dirs.append(path)

    async def load_plugin(self, metadata: PluginMetadata) -> PluginInfo:
        if metadata.name in self._plugins:
            return self._plugins[metadata.name]

        plugin_info = PluginInfo(
            metadata=metadata,
            status=PluginStatus.UNLOADED,
            config=self.config.get("plugins", {}).get(metadata.name, {}),
        )
        self._plugins[metadata.name] = plugin_info

        try:
            plugin_info.status = PluginStatus.LOADING
            plugin_instance = self._load_plugin_class(metadata)
            if plugin_instance:
                plugin_info.instance = plugin_instance
                plugin_info.status = PluginStatus.INITIALIZING
                plugin_info.status = PluginStatus.READY
                self._load_order.append(metadata.name)
            else:
                plugin_info.status = PluginStatus.ERROR
                plugin_info.error = f"Plugin class not found for {metadata.name}"
        except Exception as e:
            plugin_info.status = PluginStatus.ERROR
            plugin_info.error = str(e)

        return plugin_info

    def _load_plugin_class(self, metadata: PluginMetadata) -> Optional[BasePlugin]:
        for plugin_dir in self._local_plugin_dirs:
            plugin_path = plugin_dir / metadata.name
            if plugin_path.exists():
                try:
                    sys.path.insert(0, str(plugin_dir))
                    module = importlib.import_module(metadata.name)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            instance = obj()
                            if instance.metadata.name == metadata.name:
                                return instance
                except Exception:
                    pass
                finally:
                    if str(plugin_dir) in sys.path:
                        sys.path.remove(str(plugin_dir))
        return None

    async def unload_plugin(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        plugin_info = self._plugins[name]
        if plugin_info.instance:
            try:
                plugin_info.status = PluginStatus.SHUTTING_DOWN
                await plugin_info.instance.shutdown()
                plugin_info.status = PluginStatus.SHUTDOWN
            except Exception as e:
                plugin_info.status = PluginStatus.ERROR
                plugin_info.error = str(e)
                return False
        if name in self._load_order:
            self._load_order.remove(name)
        return True

    async def shutdown_all(self) -> None:
        for name in reversed(self._load_order):
            await self.unload_plugin(name)

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        return list(self._plugins.values())
