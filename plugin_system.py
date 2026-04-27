#!/usr/bin/env python3
"""
Plugin System for Suite Orchestrator
Allows external systems to extend functionality through plugins
"""

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os

@dataclass
class PluginInfo:
    """Plugin metadata"""
    name: str
    version: str
    description: str
    author: str
    hooks: List[str]  # List of hook names this plugin implements

class PluginBase(ABC):
    """Base class for all plugins"""
    
    def __init__(self):
        self.info = self.get_info()
    
    @abstractmethod
    def get_info(self) -> PluginInfo:
        """Return plugin information"""
        pass
    
    def on_service_start(self, service_name: str, pid: int) -> None:
        """Called when a service starts"""
        pass
    
    def on_service_stop(self, service_name: str, pid: int) -> None:
        """Called when a service stops"""
        pass
    
    def on_service_error(self, service_name: str, error: Exception) -> None:
        """Called when a service encounters an error"""
        pass
    
    def on_health_check(self, health_data: Dict[str, Any]) -> None:
        """Called during health checks"""
        pass
    
    def on_metrics_collect(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Called when collecting metrics - can add custom metrics"""
        return {}
    
    def on_config_load(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Called when loading configuration - can modify config"""
        return config
    
    def on_shutdown(self) -> None:
        """Called when orchestrator shuts down"""
        pass

class PluginManager:
    """Manages plugin loading and execution"""
    
    def __init__(self, plugin_dir: Optional[Path] = None):
        self.plugin_dir = plugin_dir or Path(__file__).parent / "plugins"
        self.plugins: Dict[str, PluginBase] = {}
        self.hooks: Dict[str, List[Callable]] = {
            'service_start': [],
            'service_stop': [],
            'service_error': [],
            'health_check': [],
            'metrics_collect': [],
            'config_load': [],
            'shutdown': []
        }
    
    def load_plugins(self):
        """Load all plugins from plugin directory"""
        if not self.plugin_dir.exists():
            self.plugin_dir.mkdir(parents=True, exist_ok=True)
            return
        
        # Look for Python files in plugin directory
        for plugin_file in self.plugin_dir.glob("*.py"):
            if plugin_file.name == "__init__.py":
                continue
            
            try:
                self.load_plugin(plugin_file)
            except Exception as e:
                print(f"⚠️ Failed to load plugin {plugin_file.name}: {e}")
    
    def load_plugin(self, plugin_file: Path):
        """Load a single plugin"""
        module_name = f"plugins.{plugin_file.stem}"
        
        # Import the module
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin {plugin_file}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find PluginBase subclasses
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, PluginBase) and 
                obj != PluginBase):
                
                plugin_instance = obj()
                plugin_name = plugin_instance.info.name
                
                self.plugins[plugin_name] = plugin_instance
                self._register_hooks(plugin_instance)
                
                print(f"✓ Loaded plugin: {plugin_name} v{plugin_instance.info.version}")
                break
    
    def _register_hooks(self, plugin: PluginBase):
        """Register plugin hooks"""
        if hasattr(plugin, 'on_service_start'):
            self.hooks['service_start'].append(plugin.on_service_start)
        if hasattr(plugin, 'on_service_stop'):
            self.hooks['service_stop'].append(plugin.on_service_stop)
        if hasattr(plugin, 'on_service_error'):
            self.hooks['service_error'].append(plugin.on_service_error)
        if hasattr(plugin, 'on_health_check'):
            self.hooks['health_check'].append(plugin.on_health_check)
        if hasattr(plugin, 'on_metrics_collect'):
            self.hooks['metrics_collect'].append(plugin.on_metrics_collect)
        if hasattr(plugin, 'on_config_load'):
            self.hooks['config_load'].append(plugin.on_config_load)
        if hasattr(plugin, 'on_shutdown'):
            self.hooks['shutdown'].append(plugin.on_shutdown)
    
    def call_hook(self, hook_name: str, *args, **kwargs) -> Any:
        """Call all registered hooks for a given hook name"""
        results = []
        for hook in self.hooks.get(hook_name, []):
            try:
                result = hook(*args, **kwargs)
                if result is not None:
                    results.append(result)
            except Exception as e:
                print(f"⚠️ Plugin hook error in {hook_name}: {e}")
        
        # For metrics_collect, merge all results
        if hook_name == 'metrics_collect' and results:
            merged = {}
            for result in results:
                if isinstance(result, dict):
                    merged.update(result)
            return merged if merged else None
        
        # For config_load, apply modifications sequentially
        if hook_name == 'config_load' and results:
            config = args[0] if args else {}
            for result in results:
                if isinstance(result, dict):
                    config.update(result)
            return config
        
        return results if results else None
    
    def list_plugins(self) -> List[PluginInfo]:
        """List all loaded plugins"""
        return [plugin.info for plugin in self.plugins.values()]

