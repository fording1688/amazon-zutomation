#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import ssl
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
SENSITIVE_KEYS = ("password", "pwd", "token", "secret", "api_key", "apikey")


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


def _ssl_context_from_url(database_url: str):
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or ["require"])[0]
    if sslmode in {"verify-ca", "verify-full"}:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def connect_database(use_direct: bool = False):
    database_url = get_database_url(use_direct=use_direct)
    if not database_url:
        raise RuntimeError("DATABASE_URL 未配置。")

    try:
        import pg8000.dbapi
    except ImportError as error:
        raise RuntimeError("数据库依赖 pg8000 未安装，请运行 pip install -r requirements.txt。") from error

    parsed = urlparse(database_url)
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "",
        port=parsed.port or 5432,
        database=(parsed.path or "/postgres").lstrip("/"),
        timeout=12,
        ssl_context=_ssl_context_from_url(database_url),
    )


def check_database_connection(use_direct: bool = False):
    database_url = get_database_url(use_direct=use_direct)
    conn = connect_database(use_direct=use_direct)
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


def ensure_operation_logs_table():
    conn = connect_database(use_direct=True)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            create table if not exists public.operation_logs (
              id bigserial primary key,
              action text not null,
              method text not null,
              path text not null,
              query_params jsonb not null default '{}'::jsonb,
              success boolean not null default false,
              status_code integer,
              duration_ms integer,
              error text,
              client_ip text,
              user_agent text,
              created_at timestamptz not null default now()
            )
            """
        )
        cursor.execute(
            "create index if not exists idx_operation_logs_created_at on public.operation_logs (created_at desc)"
        )
        cursor.execute(
            "create index if not exists idx_operation_logs_action_created_at on public.operation_logs (action, created_at desc)"
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def _redact_value(value):
    if value is None:
        return None
    text = str(value)
    if len(text) > 500:
        return text[:500] + "..."
    return text


def sanitize_params(params):
    safe = {}
    for key, value in (params or {}).items():
        key_text = str(key)
        if any(flag in key_text.lower() for flag in SENSITIVE_KEYS):
            safe[key_text] = "***REDACTED***"
            continue
        if isinstance(value, (list, tuple)):
            safe[key_text] = [_redact_value(item) for item in value]
        else:
            safe[key_text] = _redact_value(value)
    return safe


def log_operation(
    *,
    action: str,
    method: str,
    path: str,
    query_params=None,
    success: bool,
    status_code: int,
    duration_ms: int,
    error: str = "",
    client_ip: str = "",
    user_agent: str = "",
):
    conn = connect_database(use_direct=False)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            insert into public.operation_logs (
              action,
              method,
              path,
              query_params,
              success,
              status_code,
              duration_ms,
              error,
              client_ip,
              user_agent
            ) values (%s, %s, %s, cast(%s as jsonb), %s, %s, %s, %s, %s, %s)
            """,
            (
                action,
                method,
                path,
                json.dumps(sanitize_params(query_params), ensure_ascii=False),
                success,
                int(status_code or 0),
                int(duration_ms or 0),
                (error or "")[:1000],
                client_ip,
                (user_agent or "")[:500],
            ),
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def count_operation_logs():
    conn = connect_database(use_direct=False)
    try:
        cursor = conn.cursor()
        cursor.execute("select count(*) from public.operation_logs")
        count = cursor.fetchone()[0]
        cursor.close()
        return int(count or 0)
    finally:
        conn.close()
