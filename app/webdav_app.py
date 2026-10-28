"""Embedded WsgiDAV app for /dav (downloads/ tree)."""

from __future__ import annotations

from typing import Any, Optional

from a2wsgi import WSGIMiddleware

from app.config import WebdavSettings, load_settings
from app.services.file_manager import get_storage_root


def webdav_is_ready(cfg: Optional[WebdavSettings] = None) -> bool:
    s = cfg or load_settings().webdav
    return bool(s.enabled and s.username.strip() and s.password)


def build_wsgidav_config(cfg: Optional[WebdavSettings] = None) -> dict[str, Any]:
    s = cfg or load_settings().webdav
    if not webdav_is_ready(s):
        raise ValueError("WebDAV 未启用或未配置用户名/密码")

    root = str(get_storage_root())
    username = s.username.strip()
    password = s.password
    return {
        "host": "0.0.0.0",
        "port": 0,
        "mount_path": "/dav",
        "provider_mapping": {
            "/": {
                "root": root,
                "readonly": bool(s.read_only),
            },
        },
        "verbose": 1,
        "http_authenticator": {
            "domain_controller": None,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
            "trusted_auth_header": None,
        },
        "simple_dc": {
            "user_mapping": {
                "*": {
                    username: {
                        "password": password,
                        "roles": ["admin"],
                    }
                }
            }
        },
        "dir_browser": {"enable": True},
    }


def create_webdav_asgi_app(cfg: Optional[WebdavSettings] = None):
    from wsgidav.wsgidav_app import WsgiDAVApp

    wsgi_app = WsgiDAVApp(build_wsgidav_config(cfg))
    return WSGIMiddleware(wsgi_app)
