#!/usr/bin/env python3

import argparse
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from ai_opportunity import analyze_ai_opportunity, build_bundle_plan
from amazon_reviews import fetch_asin_reviews
from amazon_scraper import AmazonScraperError, fetch_amazon_rows
from database import count_operation_logs, check_database_connection, ensure_operation_logs_table, log_operation
from market_gap import discover_market_gaps
from pdf_made_in_china import add_made_in_china_to_pdf
from product_hunter import analyze_product_hunter
from serpapi_amazon import SerpApiAmazonError, enrich_rows_with_seller_info, request_serpapi_json, search_display_page, to_text


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "sample_products.csv"
GENERATED_DIR = WEB_DIR / "generated"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
VIDEO_REMIX_DIR = ROOT / "video-remix-api"
VIDEO_REMIX_PORT = int(os.environ.get("VIDEO_REMIX_PORT", "8010"))
VIDEO_REMIX_PROCESS = None
VIDEO_REMIX_LOG = VIDEO_REMIX_DIR / "outputs" / "service.log"


def parse_args():
    parser = argparse.ArgumentParser(description="Run the local Amazon product web app.")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Host interface to bind. Use 0.0.0.0 on Render.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Local port for the web server. Defaults to PORT env or 8000.",
    )
    return parser.parse_args()


def normalize_text(value):
    return (value or "").strip().lower()


def to_float(value):
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value):
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def is_prime(value):
    return normalize_text(value) in {"yes", "y", "true", "1", "prime"}



def _find_first_dict(payload, keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _extract_bullets(product):
    candidates = [
        product.get("feature_bullets"),
        product.get("feature_bullets_flat"),
        product.get("about_this_item"),
        product.get("features"),
        product.get("bullet_points"),
    ]
    bullets = []
    for candidate in candidates:
        if isinstance(candidate, list):
            bullets.extend(to_text(item) for item in candidate if to_text(item))
        elif isinstance(candidate, dict):
            for value in candidate.values():
                if isinstance(value, list):
                    bullets.extend(to_text(item) for item in value if to_text(item))
                elif to_text(value):
                    bullets.append(to_text(value))
        elif to_text(candidate):
            bullets.extend(part.strip() for part in re.split(r"[\n•]+", to_text(candidate)) if part.strip())
    seen = set()
    unique = []
    for bullet in bullets:
        key = bullet.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(bullet)
    return unique[:8]


def fetch_asin_product_detail(params):
    asin = (params.get("asin") or "").strip().upper()
    if not asin:
        raise ValueError("asin is required")
    payload = request_serpapi_json({
        "engine": "amazon_product",
        "asin": asin,
        "amazon_domain": params.get("amazon_domain") or "amazon.com",
        "language": params.get("language") or "en_US",
        "device": params.get("device") or "desktop",
    })
    product = _find_first_dict(payload, ["product_results", "product", "product_information"])
    title = to_text(product.get("title") or payload.get("title"))
    price = product.get("extracted_price") or product.get("price") or payload.get("price")
    rating = product.get("rating") or payload.get("rating")
    reviews = product.get("reviews") or product.get("reviews_count") or payload.get("reviews")
    description = to_text(product.get("description") or product.get("product_description") or payload.get("description"))
    return {
        "asin": asin,
        "title": title,
        "brand": to_text(product.get("brand") or product.get("manufacturer") or payload.get("brand")),
        "price": str(price or ""),
        "rating": str(rating or ""),
        "reviews": str(reviews or ""),
        "feature_bullets": _extract_bullets(product),
        "description": description,
        "category": to_text(product.get("category") or product.get("categories") or payload.get("category")),
        "product_url": to_text(product.get("link") or product.get("product_link") or payload.get("search_metadata", {}).get("amazon_url")),
        "image_url": to_text(product.get("main_image") or product.get("thumbnail") or product.get("image")),
        "data_source": "SerpApi amazon_product",
    }

def read_rows():
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def filter_rows(params):
    keyword = normalize_text(params.get("keyword"))
    data_source = params.get("data_source") or "serpapi"
    error_message = ""
    page_size = to_int(params.get("page_size")) or 30
    if page_size not in {30, 50}:
        page_size = 30
    pagination = {
        "page": to_int(params.get("page")) or 1,
        "page_size": page_size,
        "total_results": 0,
        "total_pages": 0,
        "has_next": False,
    }

    if data_source == "serpapi":
        selected_node = params.get("node") or params.get("category_node") or ""
        selected_rh = params.get("rh") or ""
        if not keyword and not selected_node and not selected_rh:
            rows = []
            error_message = "SerpApi 搜索模式需要输入关键词，或选择 Amazon 大类 / 自定义 node / rh。"
        else:
            try:
                amazon_domain = params.get("amazon_domain") or "amazon.com"
                language = params.get("language") or "en_US"
                device = params.get("device") or "desktop"
                page_payload = search_display_page(
                    keyword=keyword,
                    display_page=pagination["page"],
                    page_size=page_size,
                    sort=params.get("sort") or "relevanceblender",
                    amazon_domain=amazon_domain,
                    language=language,
                    node=selected_node,
                    rh=selected_rh,
                    delivery_zip=params.get("delivery_zip") or "",
                    shipping_location=params.get("shipping_location") or "",
                    device=device,
                    dc=params.get("dc") or "true",
                )
                rows = page_payload["rows"]
                pagination.update({
                    "page": page_payload["page"],
                    "page_size": page_payload["page_size"],
                    "total_results": page_payload["total_results"],
                    "total_pages": page_payload["total_pages"],
                    "has_next": page_payload["has_next"],
                })
                rows = enrich_rows_with_seller_info(
                    rows,
                    seller_region=params.get("seller_region") or "",
                    seller_city=params.get("seller_city") or "",
                    amazon_domain=amazon_domain,
                    language=language,
                    device=device,
                    return_all_when_no_match=True,
                )
            except SerpApiAmazonError as error:
                rows = []
                error_message = str(error)
    elif data_source == "amazon_live":
        if not keyword:
            rows = []
            error_message = "在线搜索模式需要先输入关键词。"
        else:
            try:
                rows = fetch_amazon_rows(keyword=keyword, pages=1, limit=page_size)
            except AmazonScraperError as error:
                rows = []
                error_message = str(error)
    else:
        rows = read_rows()
        filtered_demo = []
        for row in rows:
            if keyword and keyword not in normalize_text(row.get("title")):
                continue
            filtered_demo.append(row)
        rows = filtered_demo[:page_size]

    seller_filter_applied = bool(params.get("seller_region") or params.get("seller_city"))
    seller_filter_no_match = seller_filter_applied and any(
        row.get("seller_filter_status") == "no_match" for row in rows
    )

    summary = {
        "dataset_count": len(rows),
        "count": 0 if seller_filter_no_match else len(rows),
        "page": pagination["page"],
        "page_size": pagination["page_size"],
        "total_results": pagination["total_results"],
        "total_pages": pagination["total_pages"],
        "has_next": pagination["has_next"],
        "average_price": round(
            sum(to_float(row.get("price")) or 0 for row in rows) / len(rows), 2
        )
        if rows
        else 0,
        "average_rating": round(
            sum(to_float(row.get("rating")) or 0 for row in rows) / len(rows), 2
        )
        if rows
        else 0,
        "prime_ratio": round(
            sum(1 for row in rows if is_prime(row.get("is_prime"))) / len(rows) * 100,
            1,
        )
        if rows
        else 0,
        "data_source": {
            "serpapi": "SerpApi Amazon Search API",
            "amazon_live": "Amazon.com direct live search",
            "demo": DATA_FILE.name,
        }.get(data_source, DATA_FILE.name),
        "mode": data_source,
        "error": error_message,
        "seller_filter_applied": seller_filter_applied,
        "seller_filter_no_match": seller_filter_no_match,
        "sample_keywords": [
            "earbuds",
            "laptop",
            "keyboard",
            "matcha",
            "projector",
            "bottle",
        ],
    }
    return {"summary": summary, "items": rows}


def fetch_exchange_rate(params):
    amount = to_float(params.get("amount")) or 1
    base = (params.get("from") or "USD").strip().upper()
    target = (params.get("to") or "CNY").strip().upper()
    if len(base) != 3 or len(target) != 3:
        raise ValueError("Currency codes must be 3-letter ISO codes.")

    url = f"https://fxapi.app/api/{base.lower()}/{target.lower()}.json"
    request = Request(url, headers={"User-Agent": "TradeHarbor/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except HTTPError as error:
        raise RuntimeError(f"FX API returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("FX API returned invalid JSON.") from error

    rate = to_float(payload.get("rate"))
    if rate is None:
        raise RuntimeError("FX API did not return a valid rate.")

    return {
        "amount": amount,
        "from": base,
        "to": target,
        "rate": rate,
        "converted": round(amount * rate, 4),
        "timestamp": payload.get("timestamp", ""),
        "provider": "fxapi.app",
    }


def is_port_open(host="127.0.0.1", port=VIDEO_REMIX_PORT):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def tail_text(path, max_chars=3000):
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="ignore")
        return data[-max_chars:]
    except Exception:
        return ""


def video_remix_status_payload():
    global VIDEO_REMIX_PROCESS
    managed_running = bool(VIDEO_REMIX_PROCESS and VIDEO_REMIX_PROCESS.poll() is None)
    port_running = is_port_open(port=VIDEO_REMIX_PORT)
    if VIDEO_REMIX_PROCESS and VIDEO_REMIX_PROCESS.poll() is not None:
        VIDEO_REMIX_PROCESS = None
    return {
        "running": managed_running or port_running,
        "managed": managed_running,
        "port": VIDEO_REMIX_PORT,
        "url": f"http://127.0.0.1:{VIDEO_REMIX_PORT}",
        "log_tail": tail_text(VIDEO_REMIX_LOG),
    }


def start_video_remix_service():
    global VIDEO_REMIX_PROCESS
    status = video_remix_status_payload()
    if status["running"]:
        return {"ok": True, "result": status, "message": "8010 服务已经在运行。"}
    if not VIDEO_REMIX_DIR.exists():
        raise RuntimeError("video-remix-api 目录不存在。")

    VIDEO_REMIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    python_bin = VIDEO_REMIX_DIR / ".venv" / "bin" / "python"
    python_cmd = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_cmd,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(VIDEO_REMIX_PORT),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    with VIDEO_REMIX_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write("\n--- starting video-remix-api ---\n")
        log_file.write(" ".join(command) + "\n")
        log_file.flush()
        VIDEO_REMIX_PROCESS = subprocess.Popen(
            command,
            cwd=str(VIDEO_REMIX_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

    time.sleep(1.0)
    if VIDEO_REMIX_PROCESS.poll() is not None and not is_port_open(port=VIDEO_REMIX_PORT):
        exit_code = VIDEO_REMIX_PROCESS.returncode
        VIDEO_REMIX_PROCESS = None
        raise RuntimeError(
            "8010 服务启动失败。请先安装依赖：cd video-remix-api && pip install -r requirements.txt。"
            f" 退出码：{exit_code}。日志：{tail_text(VIDEO_REMIX_LOG, 1200)}"
        )
    return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务已启动。"}


def stop_video_remix_service():
    global VIDEO_REMIX_PROCESS
    if not VIDEO_REMIX_PROCESS or VIDEO_REMIX_PROCESS.poll() is not None:
        VIDEO_REMIX_PROCESS = None
        if is_port_open(port=VIDEO_REMIX_PORT):
            return {
                "ok": False,
                "result": video_remix_status_payload(),
                "error": "检测到 8010 端口有服务在运行，但不是当前页面启动的进程，无法安全关闭。",
            }
        return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务当前未运行。"}

    VIDEO_REMIX_PROCESS.terminate()
    try:
        VIDEO_REMIX_PROCESS.wait(timeout=5)
    except subprocess.TimeoutExpired:
        VIDEO_REMIX_PROCESS.kill()
        VIDEO_REMIX_PROCESS.wait(timeout=3)
    VIDEO_REMIX_PROCESS = None
    return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务已关闭。"}


class AmazonProductHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_operation_log(self, action, params, payload, status, started_at):
        try:
            log_operation(
                action=action,
                method=self.command,
                path=urlparse(self.path).path,
                query_params=params,
                success=bool(payload.get("ok", status < HTTPStatus.BAD_REQUEST)) if isinstance(payload, dict) else status < HTTPStatus.BAD_REQUEST,
                status_code=int(status),
                duration_ms=round((time.monotonic() - started_at) * 1000),
                error=(payload.get("error", "") if isinstance(payload, dict) else ""),
                client_ip=self.client_address[0] if self.client_address else "",
                user_agent=self.headers.get("User-Agent", ""),
            )
        except Exception as error:
            print(f"Operation log skipped for {action}: {error}")

    def send_json_and_log(self, action, params, payload, status, started_at):
        self.send_json(payload, status)
        self.write_operation_log(action, params, payload, status, started_at)

    def parse_multipart_form(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("请使用表单上传 PDF 文件。")

        boundary_match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type)
        if not boundary_match:
            raise ValueError("上传请求缺少 multipart boundary。")
        boundary = (boundary_match.group(1) or boundary_match.group(2)).strip()

        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            raise ValueError("上传文件为空。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("PDF 文件过大，请控制在 25MB 以内。")

        body = self.rfile.read(content_length)
        fields = {}
        files = {}
        for raw_part in body.split(("--" + boundary).encode("utf-8")):
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if not part or part == b"--":
                continue
            if part.endswith(b"--"):
                part = part[:-2]
                if part.endswith(b"\r\n"):
                    part = part[:-2]

            header_blob, separator, value = part.partition(b"\r\n\r\n")
            if not separator:
                continue

            headers = header_blob.decode("utf-8", errors="ignore").split("\r\n")
            disposition = next(
                (line for line in headers if line.lower().startswith("content-disposition:")),
                "",
            )
            name_match = re.search(r'name="([^"]+)"', disposition)
            if not name_match:
                continue
            name = name_match.group(1)
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            if filename_match:
                files[name] = {
                    "filename": filename_match.group(1),
                    "content": value,
                }
            else:
                fields[name] = value.decode("utf-8", errors="ignore").strip()

        return fields, files

    def do_POST(self):
        started_at = time.monotonic()
        parsed = urlparse(self.path)
        if parsed.path == "/api/video-remix-service":
            params = {}
            try:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    payload_in = json.loads(body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    payload_in = {}
                action = (payload_in.get("action") or "status").strip().lower()
                params = {"action": action}
                if action == "start":
                    payload = start_video_remix_service()
                    status = HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST
                elif action == "stop":
                    payload = stop_video_remix_service()
                    status = HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST
                else:
                    payload = {"ok": True, "result": video_remix_status_payload()}
                    status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error), "result": video_remix_status_payload()}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("video_remix_service", params, payload, status, started_at)
            return

        if parsed.path == "/api/pdf-made-in-china":
            params = {}
            try:
                fields, files = self.parse_multipart_form()
                uploaded_pdf = files.get("pdf") or files.get("file")
                filename = (uploaded_pdf or {}).get("filename") or "labels.pdf"
                params = {
                    "filename": filename,
                    "file_size": len((uploaded_pdf or {}).get("content", b"")),
                    "text": fields.get("text") or "Made In China",
                    "font_size": fields.get("font_size") or "8",
                }
                if not uploaded_pdf:
                    raise ValueError("请先选择一个 PDF 文件。")
                if not filename.lower().endswith(".pdf"):
                    raise ValueError("当前只支持上传 PDF 文件。")

                result = add_made_in_china_to_pdf(
                    uploaded_pdf.get("content", b""),
                    GENERATED_DIR,
                    text=fields.get("text") or "Made In China",
                    font_size=to_float(fields.get("font_size")) or 8,
                )
                result["file_url"] = f"/generated/{result['output_name']}"
                result["message"] = f"已识别 {result['labels_detected']} 个标签，并写入 Made In China。"
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            self.send_json_and_log("pdf_made_in_china", params, payload, status, started_at)
            return

        self.send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/video-remix-service":
            started_at = time.monotonic()
            params = {}
            payload = {"ok": True, "result": video_remix_status_payload()}
            status = HTTPStatus.OK
            self.send_json_and_log("video_remix_service_status", params, payload, status, started_at)
            return

        if parsed.path == "/api/db-health":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {
                    "ok": True,
                    "result": check_database_connection(
                        use_direct=(params.get("direct") or "false").lower() == "true"
                    ),
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("db_health", params, payload, status, started_at)
            return

        if parsed.path == "/api/operation-logs/count":
            started_at = time.monotonic()
            params = {}
            try:
                payload = {"ok": True, "result": {"count": count_operation_logs()}}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json(payload, status)
            return

        if parsed.path == "/api/products":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, **filter_rows(params)}
            except Exception as error:
                payload = {
                    "ok": True,
                    "summary": {
                        "count": 0,
                        "dataset_count": 0,
                        "page": to_int(params.get("page")) or 1,
                        "page_size": to_int(params.get("page_size")) or 30,
                        "total_results": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "average_price": 0,
                        "average_rating": 0,
                        "prime_ratio": 0,
                        "data_source": "SerpApi Amazon Search API",
                        "mode": params.get("data_source") or "serpapi",
                        "error": f"查询接口临时失败：{error}",
                        "seller_filter_applied": False,
                        "seller_filter_no_match": False,
                        "sample_keywords": ["earbuds", "laptop", "keyboard", "matcha", "projector", "bottle"],
                    },
                    "items": [],
                }
            status = HTTPStatus.OK
            self.send_json_and_log("products_search", params, payload, status, started_at)
            return

        if parsed.path == "/api/exchange":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": fetch_exchange_rate(params)}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("exchange_rate", params, payload, status, started_at)
            return

        if parsed.path == "/api/ai-opportunity":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": analyze_ai_opportunity(params.get("keyword", ""))}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("ai_opportunity", params, payload, status, started_at)
            return

        if parsed.path == "/api/bundle-plan":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": build_bundle_plan(params.get("keyword", ""), params)}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("bundle_plan", params, payload, status, started_at)
            return

        if parsed.path == "/api/product-hunter":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {
                    "ok": True,
                    "result": analyze_product_hunter(
                        params.get("keyword", ""),
                        limit=to_int(params.get("limit")) or 20,
                    ),
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("product_hunter", params, payload, status, started_at)
            return

        if parsed.path == "/api/market-gaps":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {
                    "ok": True,
                    "result": discover_market_gaps(
                        params.get("keyword", ""),
                        limit=to_int(params.get("limit")) or 20,
                        review_limit=to_int(params.get("review_limit")) or 5,
                    ),
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("market_gaps", params, payload, status, started_at)
            return


        if parsed.path == "/api/asin-product":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": fetch_asin_product_detail(params)}
            except Exception as error:
                fallback_asin = (params.get("asin") or "").strip().upper()
                payload = {
                    "ok": True,
                    "warning": f"ASIN 商品详情临时获取失败：{error}",
                    "result": {
                        "asin": fallback_asin,
                        "title": "",
                        "brand": "",
                        "price": "",
                        "rating": "",
                        "reviews": "",
                        "feature_bullets": [],
                        "description": "",
                        "category": "",
                        "product_url": "",
                        "image_url": "",
                        "data_source": "fallback",
                    },
                }
            status = HTTPStatus.OK
            self.send_json_and_log("asin_product", params, payload, status, started_at)
            return

        if parsed.path == "/api/asin-reviews":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {
                    "ok": True,
                    "result": fetch_asin_reviews(
                        params.get("asin", ""),
                        max_pages=to_int(params.get("max_pages")) or 5,
                        filter_by_star=params.get("filter_by_star") or "all",
                        amazon_domain=params.get("amazon_domain") or "amazon.com",
                        sort_by=params.get("sort_by") or "recent",
                        translate_zh=(params.get("translate_zh") or "true").lower() != "false",
                    ),
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("asin_reviews", params, payload, status, started_at)
            return

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()


def main():
    args = parse_args()
    try:
        ensure_operation_logs_table()
        print("Operation logs table is ready.")
    except Exception as error:
        print(f"Operation logs table setup skipped: {error}")
    server = ThreadingHTTPServer((args.host, args.port), AmazonProductHandler)
    print(f"Amazon product web app running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
