"""配置管理 UI 辅助。"""

from __future__ import annotations

from core.config_manager import get_status_text, load_config, save_config, get_llm_config

__all__ = ["get_status_text", "load_config", "save_config", "get_llm_config"]
