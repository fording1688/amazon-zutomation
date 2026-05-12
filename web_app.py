#!/usr/bin/env python3

import argparse
import csv
import json
import os
from urllib.error import HTTPError, URLError
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from ai_opportunity import analyze_ai_opportunity, build_bundle_plan
from amazon_reviews import fetch_asin_reviews
from amazon_scraper import AmazonScraperError, fetch_amazon_rows
from market_gap import discover_market_gaps
from product_hunter import analyze_product_hunter
from serpapi_amazon import SerpApiAmazonError, enrich_rows_with_seller_info, search_display_page


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "sample_products.csv"


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


class AmazonProductHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/products":
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            payload = filter_rows(params)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/exchange":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/ai-opportunity":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return


        if parsed.path == "/api/bundle-plan":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/product-hunter":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/market-gaps":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/asin-reviews":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()


def main():
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AmazonProductHandler)
    print(f"Amazon product web app running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
