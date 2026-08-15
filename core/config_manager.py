"""
配置管理模块 — 企业级安全持久化

特性:
  - API Key 使用 Windows DPAPI 加密存储（非明文）
  - 配置持久化到 data/config.json
  - 启动时自动加载
  - 支持两种模式: 第三方 API / 本地模型 (LM Studio)

安全设计:
  - API Key 通过 win32crypt.CryptProtectData 加密（Windows DPAPI）
  - 加密后的密文存储在 JSON 中，离开本机无法解密
  - 非 Windows 平台回退到 base64（仅用于开发，生产环境应在 Windows 上运行）
  - 配置文件权限设置为仅当前用户可读写
"""

from __future__ import annotations

import json
import os
import platform
import base64
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("config_manager")

# 配置文件路径
_CONFIG_DIR = Path(__file__).parent.parent / "data"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# 默认值
DEFAULTS = {
    "mode": "api",              # "api" = 第三方 API, "local" = 本地模型
    "api_key": "",              # 加密存储
    "base_url": "",             # 明文
    "model": "",                # 明文
    "local_url": "http://localhost:1234/v1",  # 本地模型地址
}


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _encrypt(plaintext: str) -> str:
    """加密字符串，返回 base64 编码的密文"""
    if not plaintext:
        return ""

    if _is_windows():
        try:
            import win32crypt
            # CryptProtectData 返回 (description, encrypted_bytes)
            # pywin32 versions differ: some return ciphertext bytes directly,
            # while others return (description, ciphertext).
            protected = win32crypt.CryptProtectData(
                plaintext.encode("utf-8"),
                "E-Health Agent API Key",
                None,
                None,
                None,
                0,
            )
            encrypted = protected[-1] if isinstance(protected, tuple) else protected
            return base64.b64encode(encrypted).decode("ascii")
        except ImportError:
            # pywin32 未安装，回退
            logger.warning("pywin32 未安装，API Key 将以 base64 存储（非安全加密）")
            return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
        except Exception as e:
            logger.error(f"DPAPI 加密失败: {e}")
            return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    else:
        # 非 Windows：base64（仅开发用）
        return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def _decrypt(ciphertext: str) -> str:
    """解密字符串"""
    if not ciphertext:
        return ""

    if ciphertext.startswith("b64:"):
        # base64 回退模式
        return base64.b64decode(ciphertext[4:]).decode("utf-8")

    if _is_windows():
        try:
            import win32crypt
            encrypted = base64.b64decode(ciphertext)
            unprotected = win32crypt.CryptUnprotectData(
                encrypted,
                None,
                None,
                None,
                0,
            )
            plaintext = unprotected[-1] if isinstance(unprotected, tuple) else unprotected
            return plaintext.decode("utf-8")
        except ImportError:
            logger.warning("pywin32 未安装，无法解密 API Key")
            return ""
        except Exception as e:
            logger.error(f"DPAPI 解密失败: {e}")
            return ""
    else:
        return ""


def _ensure_config_dir() -> None:
    """确保配置目录存在"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _set_file_permissions(filepath: Path) -> None:
    """设置文件权限为仅当前用户可读写（Windows）"""
    if _is_windows():
        try:
            import subprocess
            # 用 icacls 移除继承，仅保留当前用户完全控制
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(
                    ["icacls", str(filepath), "/inheritance:r",
                     f"/grant:r", f"{user}:F"],
                    capture_output=True, timeout=5,
                )
        except Exception:
            pass  # 权限设置失败不影响主流程


def load_config() -> dict:
    """
    加载配置，返回包含以下键的字典:
        mode: "api" | "local"
        api_key: 解密后的明文 API Key
        base_url: API 地址
        model: 模型名称
        local_url: 本地模型地址
    """
    config = dict(DEFAULTS)

    if not _CONFIG_FILE.exists():
        return config

    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)

        config["mode"] = saved.get("mode", DEFAULTS["mode"])
        config["base_url"] = saved.get("base_url", "")
        config["model"] = saved.get("model", "")
        config["local_url"] = saved.get("local_url", DEFAULTS["local_url"])

        # 解密 API Key
        encrypted_key = saved.get("api_key", "")
        if encrypted_key:
            config["api_key"] = _decrypt(encrypted_key)
        else:
            config["api_key"] = ""

    except Exception as e:
        logger.error(f"加载配置失败: {e}")

    return config


def save_config(config: dict) -> bool:
    """
    保存配置到文件
    config 字典:
        mode: "api" | "local"
        api_key: 明文 API Key（会被加密后存储）
        base_url: API 地址
        model: 模型名称
        local_url: 本地模型地址
    """
    _ensure_config_dir()

    try:
        data = {
            "mode": config.get("mode", "api"),
            "api_key": _encrypt(config.get("api_key", "")),
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "local_url": config.get("local_url", DEFAULTS["local_url"]),
        }

        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        _set_file_permissions(_CONFIG_FILE)
        logger.info(f"配置已保存到 {_CONFIG_FILE}")
        return True

    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return False


def get_llm_config() -> dict:
    """
    根据当前模式返回 LLM 配置，可直接传给 LLMAgent
    返回:
        api_key: API Key（local 模式为空）
        base_url: API 地址（local 模式为 local_url）
        model: 模型名称
        mode: "api" | "local"
    """
    config = load_config()

    if config["mode"] == "local":
        return {
            "api_key": "",
            "base_url": config["local_url"],
            "model": config["model"] or "qwen2.5-7b-instruct",
            "mode": "local",
        }
    else:
        return {
            "api_key": config["api_key"],
            "base_url": config["base_url"],
            "model": config["model"],
            "mode": "api",
        }


def is_configured() -> bool:
    """检查是否已配置 LLM"""
    config = load_config()
    if config["mode"] == "local":
        return bool(config["local_url"])
    else:
        return bool(config["api_key"] and config["base_url"])


def get_status_text() -> str:
    """返回 LLM 状态文本（用于界面显示）"""
    config = load_config()

    if config["mode"] == "local":
        url = config["local_url"]
        model = config["model"] or "未指定"
        return f"本地模型 | {url} | {model}"

    if not config["api_key"]:
        return "未配置 (Mock)"

    key_preview = config["api_key"][:8] + "..." if len(config["api_key"]) > 8 else "***"
    url = config["base_url"] or "默认"
    model = config["model"] or "默认"
    return f"API | {url} | {model} | {key_preview}"
