#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
import ssl
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def load_env_file(path: Path = ENV_FILE):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _database_password():
    return (
        os.environ.get("supabase_pwd")
        or os.environ.get("SUPABASE_PWD")
        or os.environ.get("SUPABASE_DB_PASSWORD")
        or ""
    )


def _inject_password(database_url: str):
    password = _database_password()
    if not password:
        return database_url
    return database_url.replace("[YOUR-PASSWORD]", quote(password, safe=""))


def get_database_url(use_direct: bool = False):
    load_env_file()
    if use_direct and os.environ.get("DIRECT_URL"):
        return _inject_password(os.environ["DIRECT_URL"])
    return _inject_password(os.environ.get("DATABASE_URL", ""))


def _safe_url_info(url: str):
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "",
        "port": parsed.port,
        "database": parsed.path.lstrip("/") or "",
        "username": parsed.username or "",
        "scheme": parsed.scheme,
    }


def check_database_connection(use_direct: bool = False):
    database_url = get_database_url(use_direct=use_direct)
    if not database_url:
        raise RuntimeError("DATABASE_URL 未配置。")

    try:
        import pg8000.dbapi
    except ImportError as error:
        raise RuntimeError("数据库依赖 pg8000 未安装，请运行 pip install -r requirements.txt。") from error

    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or ["require"])[0]
    if sslmode in {"verify-ca", "verify-full"}:
        ssl_context = ssl.create_default_context()
    else:
        ssl_context = ssl._create_unverified_context()

    conn = pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "",
        port=parsed.port or 5432,
        database=(parsed.path or "/postgres").lstrip("/"),
        timeout=12,
        ssl_context=ssl_context,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            select
              current_database(),
              current_user,
              inet_server_addr()::text,
              inet_server_port(),
              version()
            """
        )
        database, user, server_addr, server_port, version = cursor.fetchone()
        cursor.close()
    finally:
        conn.close()

    return {
        "connected": True,
        "mode": "direct" if use_direct else "pooled",
        "url": _safe_url_info(database_url),
        "database": database,
        "user": user,
        "server_addr": server_addr,
        "server_port": server_port,
        "version": (version or "").split(",")[0],
    }
