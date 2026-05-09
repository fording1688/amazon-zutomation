#!/usr/bin/env python3

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
SERPAPI_ENDPOINT = "https://serpapi.com/search"
CSV_FIELDS = [
    "asin",
    "title",
    "price",
    "rating",
    "reviews",
    "product_url",
    "image_url",
    "is_prime",
    "brand",
    "category",
    "seller",
    "sales",
    "source_keyword",
]


class SerpApiAmazonError(RuntimeError):
    """Raised when SerpApi cannot return usable Amazon search data."""


def load_dotenv(path: Path = ENV_FILE) -> None:
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


def get_api_key(api_key: Optional[str] = None) -> str:
    load_dotenv()
    resolved = api_key or os.environ.get("SERPAPI_API_KEY", "")
    if not resolved:
        raise SerpApiAmazonError(
            "Missing SerpApi key. Set SERPAPI_API_KEY in .env or your shell environment."
        )
    return resolved


def to_price(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value).replace("$", "").strip()


def to_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_product(product: Dict, keyword: str, category: str = "") -> Dict[str, str]:
    return {
        "asin": to_text(product.get("asin")),
        "title": to_text(product.get("title")),
        "price": to_price(product.get("extracted_price") or product.get("price")),
        "rating": to_text(product.get("rating")),
        "reviews": to_text(product.get("reviews")),
        "product_url": to_text(product.get("link_clean") or product.get("link")),
        "image_url": to_text(product.get("thumbnail")),
        "is_prime": "Yes" if product.get("prime") else "No",
        "brand": to_text(product.get("brand")),
        "category": category,
        "seller": "",
        "sales": to_text(product.get("bought_last_month")),
        "source_keyword": keyword,
    }


def collect_products(payload: Dict, keyword: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen_asins = set()

    for product in payload.get("organic_results", []) or []:
        row = normalize_product(product, keyword)
        if not row["asin"] or not row["title"] or row["asin"] in seen_asins:
            continue
        seen_asins.add(row["asin"])
        rows.append(row)

    for section in payload.get("featured_products", []) or []:
        category = to_text(section.get("title"))
        for product in section.get("products", []) or []:
            row = normalize_product(product, keyword, category=category)
            if not row["asin"] or not row["title"] or row["asin"] in seen_asins:
                continue
            seen_asins.add(row["asin"])
            rows.append(row)

    product_ads = payload.get("product_ads")
    ad_products = []
    if isinstance(product_ads, dict):
        ad_products = product_ads.get("products", []) or []
    elif isinstance(product_ads, list):
        ad_products = product_ads

    for product in ad_products:
        row = normalize_product(product, keyword, category="Sponsored")
        if not row["asin"] or not row["title"] or row["asin"] in seen_asins:
            continue
        seen_asins.add(row["asin"])
        rows.append(row)

    return rows


def search_amazon_products(
    keyword: str,
    page: int = 1,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    sort: str = "relevanceblender",
    api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    if not keyword.strip():
        raise SerpApiAmazonError("Keyword is required.")

    params = {
        "engine": "amazon",
        "k": keyword,
        "amazon_domain": amazon_domain,
        "language": language,
        "page": max(page, 1),
        "s": sort,
        "api_key": get_api_key(api_key),
        "output": "json",
    }
    url = f"{SERPAPI_ENDPOINT}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "Amazon Product Finder/1.0"})

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise SerpApiAmazonError(f"SerpApi returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise SerpApiAmazonError(f"Network error: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise SerpApiAmazonError("SerpApi returned invalid JSON.") from error

    if payload.get("error"):
        raise SerpApiAmazonError(str(payload["error"]))

    rows = collect_products(payload, keyword)
    if not rows:
        status = payload.get("search_metadata", {}).get("status", "unknown")
        raise SerpApiAmazonError(f"SerpApi returned no Amazon products. Search status: {status}.")
    return rows


def search_multiple_pages(
    keyword: str,
    pages: int = 1,
    limit: Optional[int] = None,
    sort: str = "relevanceblender",
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen_asins = set()

    for page in range(1, max(pages, 1) + 1):
        for row in search_amazon_products(keyword=keyword, page=page, sort=sort):
            if row["asin"] in seen_asins:
                continue
            seen_asins.add(row["asin"])
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                return rows

    return rows


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def save_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    if path.suffix.lower() == ".json":
        write_json(path, rows)
        return
    write_csv(path, rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Amazon products through SerpApi.")
    parser.add_argument("keyword", help="Search keyword, for example: iphone case")
    parser.add_argument("--output", "-o", help="Save results to .csv or .json")
    parser.add_argument("--pages", type=int, default=1, help="How many Amazon pages to fetch.")
    parser.add_argument("--limit", type=int, help="Maximum number of products to keep.")
    parser.add_argument(
        "--sort",
        default="relevanceblender",
        choices=[
            "relevanceblender",
            "price-asc-rank",
            "price-desc-rank",
            "review-rank",
            "date-desc-rank",
            "exact-aware-popularity-rank",
        ],
        help="Amazon sort option passed to SerpApi.",
    )
    return parser.parse_args()


def print_preview(rows: List[Dict[str, str]]) -> None:
    print(f"Fetched products: {len(rows)}")
    for index, row in enumerate(rows[:10], start=1):
        print(
            f"{index}. {row['asin']} | {row['title']} | "
            f"price={row['price'] or '-'} | rating={row['rating'] or '-'} | "
            f"reviews={row['reviews'] or '-'}"
        )


def main() -> None:
    args = parse_args()
    try:
        rows = search_multiple_pages(
            keyword=args.keyword,
            pages=args.pages,
            limit=args.limit,
            sort=args.sort,
        )
    except SerpApiAmazonError as error:
        raise SystemExit(f"Search failed: {error}") from error

    print_preview(rows)
    if args.output:
        save_rows(Path(args.output), rows)
        print(f"Saved results to: {args.output}")


if __name__ == "__main__":
    main()
