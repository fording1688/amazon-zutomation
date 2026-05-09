#!/usr/bin/env python3

import argparse
import csv
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from amazon_scraper import AmazonScraperError, fetch_amazon_rows
from serpapi_amazon import SerpApiAmazonError, search_multiple_pages


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "sample_products.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Run the local Amazon product web app.")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local port for the web server. Defaults to 8000.",
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

    if data_source == "serpapi":
        if not keyword:
            rows = []
            error_message = "SerpApi 搜索模式需要先输入关键词。"
        else:
            try:
                sort_map = {
                    "rating": "review-rank",
                    "reviews": "review-rank",
                    "price": "price-asc-rank",
                    "title": "relevanceblender",
                    "sales": "exact-aware-popularity-rank",
                }
                rows = search_multiple_pages(
                    keyword=keyword,
                    pages=1,
                    limit=to_int(params.get("limit")) or 20,
                    sort=sort_map.get(params.get("sort_by") or "rating", "relevanceblender"),
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
                rows = fetch_amazon_rows(keyword=keyword, pages=1)
            except AmazonScraperError as error:
                rows = []
                error_message = str(error)
    else:
        rows = read_rows()

    brand = normalize_text(params.get("brand"))
    category = normalize_text(params.get("category"))
    seller = normalize_text(params.get("seller"))
    min_price = to_float(params.get("min_price"))
    max_price = to_float(params.get("max_price"))
    min_rating = to_float(params.get("min_rating"))
    min_reviews = to_int(params.get("min_reviews"))
    min_sales = to_int(params.get("min_sales"))
    prime_only = params.get("prime_only") == "true"
    sort_by = params.get("sort_by") or "rating"
    descending = params.get("descending") == "true"
    limit = to_int(params.get("limit"))

    filtered = []
    for row in rows:
        if data_source != "serpapi" and keyword and keyword not in normalize_text(row.get("title")):
            continue
        if brand and brand != normalize_text(row.get("brand")):
            continue
        if category and category != normalize_text(row.get("category")):
            continue
        if seller and seller != normalize_text(row.get("seller")):
            continue

        price = to_float(row.get("price"))
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue

        rating = to_float(row.get("rating"))
        if min_rating is not None and (rating is None or rating < min_rating):
            continue

        reviews = to_int(row.get("reviews"))
        if min_reviews is not None and (reviews is None or reviews < min_reviews):
            continue

        sales = to_int(row.get("sales"))
        if min_sales is not None and (sales is None or sales < min_sales):
            continue

        if prime_only and not is_prime(row.get("is_prime")):
            continue

        filtered.append(row)

    def sort_key(row):
        if sort_by in {"price", "rating", "reviews", "sales"}:
            return to_float(row.get(sort_by)) or float("-inf")
        return normalize_text(row.get(sort_by))

    filtered.sort(key=sort_key, reverse=descending)
    if limit is not None:
        filtered = filtered[:limit]

    summary = {
        "dataset_count": len(rows),
        "count": len(filtered),
        "average_price": round(
            sum(to_float(row.get("price")) or 0 for row in filtered) / len(filtered), 2
        )
        if filtered
        else 0,
        "average_rating": round(
            sum(to_float(row.get("rating")) or 0 for row in filtered) / len(filtered), 2
        )
        if filtered
        else 0,
        "prime_ratio": round(
            sum(1 for row in filtered if is_prime(row.get("is_prime"))) / len(filtered) * 100,
            1,
        )
        if filtered
        else 0,
        "data_source": {
            "serpapi": "SerpApi Amazon Search API",
            "amazon_live": "Amazon.com direct live search",
            "demo": DATA_FILE.name,
        }.get(data_source, DATA_FILE.name),
        "mode": data_source,
        "error": error_message,
        "sample_keywords": [
            "earbuds",
            "laptop",
            "keyboard",
            "matcha",
            "projector",
            "bottle",
        ],
    }
    return {"summary": summary, "items": filtered}


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

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()


def main():
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AmazonProductHandler)
    print(f"Amazon product web app running at http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
