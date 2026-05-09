#!/usr/bin/env python3

import argparse
import csv
import html
import json
import random
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


AMAZON_SEARCH_URL = "https://www.amazon.com/s?k={keyword}&page={page}"
BASE_URL = "https://www.amazon.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
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


class AmazonScraperError(RuntimeError):
    """Raised when Amazon blocks, changes markup, or returns no parseable data."""


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


def clean_text(value: Optional[str]) -> str:
    text = html.unescape(strip_tags(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def absolutize_url(url: str) -> str:
    if not url:
        return ""
    url = html.unescape(url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url}"


def extract_first(patterns: Iterable[str], text: str, flags: int = re.DOTALL) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_price(card_html: str) -> str:
    offscreen = extract_first(
        [
            r'<span[^>]+class="[^"]*a-offscreen[^"]*"[^>]*>(\$[\d,.]+)</span>',
            r'<span[^>]+class="[^"]*a-color-base[^"]*"[^>]*>(\$[\d,.]+)</span>',
        ],
        card_html,
    )
    if offscreen:
        return offscreen.replace("$", "")

    whole = extract_first([r'<span[^>]+class="[^"]*a-price-whole[^"]*"[^>]*>(.*?)</span>'], card_html)
    fraction = extract_first(
        [r'<span[^>]+class="[^"]*a-price-fraction[^"]*"[^>]*>(\d{2})</span>'],
        card_html,
    )
    if not whole:
        return ""
    whole = whole.replace(",", "").replace(".", "")
    return f"{whole}.{fraction or '00'}"


def extract_reviews(card_html: str) -> str:
    review_patterns = [
        r'href="[^"]*product-reviews[^"]*"[^>]*>.*?<span[^>]*>([\d,]+)</span>',
        r'href="[^"]*customerReviews[^"]*"[^>]*>.*?<span[^>]*>([\d,]+)</span>',
        r'aria-label="([\d,]+) ratings?"',
        r'aria-label="([\d,]+) reviews?"',
        r'<span[^>]+class="[^"]*s-underline-text[^"]*"[^>]*>([\d,]+)</span>',
    ]
    return extract_first(review_patterns, card_html)


def extract_title(card_html: str) -> str:
    h2_match = re.search(r"<h2\b(?P<attrs>[^>]*)>(?P<body>.*?)</h2>", card_html, re.DOTALL)
    if h2_match:
        aria_title = extract_first([r'aria-label="([^"]+)"'], h2_match.group("attrs"), flags=0)
        if aria_title:
            return aria_title
        span_title = extract_first([r"<span[^>]*>(.*?)</span>"], h2_match.group("body"))
        if span_title:
            return span_title

    return extract_first(
        [
            r'<span[^>]+class="[^"]*a-size-medium[^"]*"[^>]*>(.*?)</span>',
            r'<span[^>]+class="[^"]*a-size-base-plus[^"]*"[^>]*>(.*?)</span>',
        ],
        card_html,
    )


def extract_product_url(card_html: str) -> str:
    h2_match = re.search(r"<h2\b[^>]*>(?P<body>.*?)</h2>", card_html, re.DOTALL)
    if h2_match:
        href = extract_first([r'<a[^>]+href="([^"]+)"'], h2_match.group("body"))
        if href:
            return absolutize_url(href)

    href = extract_first(
        [
            r'<a[^>]+class="[^"]*a-link-normal[^"]*s-no-outline[^"]*"[^>]+href="([^"]+)"',
            r'<a[^>]+href="([^"]*/dp/[^"]+)"',
        ],
        card_html,
    )
    return absolutize_url(href)


def iter_search_cards(document: str) -> Iterable[Dict[str, str]]:
    pattern = re.compile(
        r'<div\b(?P<attrs>[^>]*data-asin="(?P<asin>[^"]*)"[^>]*data-component-type="s-search-result"[^>]*)>'
        r'(?P<body>.*?)(?=<div\b[^>]*data-asin="[^"]*"[^>]*data-component-type="s-search-result"|</body>|</html>)',
        re.DOTALL,
    )

    for match in pattern.finditer(document):
        asin = clean_text(match.group("asin"))
        if not asin:
            continue
        yield {
            "asin": asin,
            "attrs": match.group("attrs"),
            "body": match.group("body"),
        }


def parse_amazon_html(document: str, keyword: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen_asins = set()

    for card in iter_search_cards(document):
        asin = card["asin"]
        if asin in seen_asins:
            continue

        body = card["body"]
        title = extract_title(body)
        if not title:
            continue

        rating = extract_first(
            [
                r'<span[^>]+class="[^"]*a-icon-alt[^"]*"[^>]*>([\d.]+) out of 5 stars</span>',
                r'aria-label="([\d.]+) out of 5 stars"',
            ],
            body,
        )
        image_url = extract_first(
            [r'<img[^>]+class="[^"]*s-image[^"]*"[^>]+src="([^"]+)"'],
            body,
        )
        is_prime = "Yes" if re.search(r'aria-label="Amazon Prime"|>\s*Prime\s*</span>', body) else "No"

        seen_asins.add(asin)
        items.append(
            {
                "asin": asin,
                "title": title,
                "price": extract_price(body),
                "rating": rating,
                "reviews": extract_reviews(body),
                "product_url": extract_product_url(body),
                "image_url": html.unescape(image_url),
                "is_prime": is_prime,
                "brand": "",
                "category": "",
                "seller": "",
                "sales": "",
                "source_keyword": keyword,
            }
        )

    return items


def build_request(keyword: str, page: int, user_agent: str = DEFAULT_USER_AGENT) -> Request:
    url = AMAZON_SEARCH_URL.format(keyword=quote_plus(keyword), page=page)
    return Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        },
    )


def fetch_page(keyword: str, page: int, timeout: int = 20) -> str:
    request = build_request(keyword, page)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except HTTPError as error:
        if error.code in {403, 429, 503}:
            raise AmazonScraperError(
                f"Amazon returned HTTP {error.code}, usually because the request was blocked "
                "by anti-bot protection. Try again later, reduce pages, or use an approved "
                "Amazon data API/proxy service for stable production crawling."
            ) from error
        raise AmazonScraperError(f"Amazon returned HTTP {error.code}.") from error
    except URLError as error:
        raise AmazonScraperError(f"Network error: {error.reason}") from error


def detect_block_page(document: str) -> Optional[str]:
    lowered = document.lower()
    if "captcha" in lowered or "automated access" in lowered:
        return "Amazon returned a CAPTCHA or automated-access verification page."
    if "sorry, we just need to make sure you're not a robot" in lowered:
        return "Amazon returned a robot-check page."
    return None


def fetch_amazon_rows(
    keyword: str,
    pages: int = 1,
    limit: Optional[int] = None,
    delay: float = 1.5,
    timeout: int = 20,
) -> List[Dict[str, str]]:
    if not keyword.strip():
        raise AmazonScraperError("Keyword is required.")

    rows: List[Dict[str, str]] = []
    seen_asins = set()

    for page in range(1, pages + 1):
        document = fetch_page(keyword, page=page, timeout=timeout)
        block_message = detect_block_page(document)
        if block_message:
            raise AmazonScraperError(block_message)

        parsed = parse_amazon_html(document, keyword=keyword)
        for row in parsed:
            if row["asin"] in seen_asins:
                continue
            seen_asins.add(row["asin"])
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                return rows

        if page < pages:
            time.sleep(delay + random.uniform(0, 0.7))

    if not rows:
        raise AmazonScraperError("Amazon page loaded, but no product cards were parsed.")
    return rows


def read_html_file(path: Path, keyword: str = "") -> List[Dict[str, str]]:
    document = path.read_text(encoding="utf-8", errors="ignore")
    block_message = detect_block_page(document)
    if block_message:
        raise AmazonScraperError(block_message)
    rows = parse_amazon_html(document, keyword=keyword)
    if not rows:
        raise AmazonScraperError("No product cards were parsed from the HTML file.")
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
    parser = argparse.ArgumentParser(
        description="Scrape Amazon.com search result data by keyword."
    )
    parser.add_argument("keyword", nargs="?", help="Search keyword, for example: laptop")
    parser.add_argument("--output", "-o", help="Save results to .csv or .json")
    parser.add_argument("--pages", type=int, default=1, help="How many search pages to fetch.")
    parser.add_argument("--limit", type=int, help="Maximum number of products to keep.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between pages in seconds.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--html-file",
        help="Parse a saved Amazon HTML file instead of requesting Amazon.com.",
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
    keyword = args.keyword or ""

    try:
        if args.html_file:
            rows = read_html_file(Path(args.html_file), keyword=keyword)
            if args.limit is not None:
                rows = rows[: args.limit]
        else:
            rows = fetch_amazon_rows(
                keyword=keyword,
                pages=max(args.pages, 1),
                limit=args.limit,
                delay=max(args.delay, 0),
                timeout=args.timeout,
            )
    except AmazonScraperError as error:
        raise SystemExit(f"Scrape failed: {error}") from error

    print_preview(rows)
    if args.output:
        output_path = Path(args.output)
        save_rows(output_path, rows)
        print(f"Saved results to: {output_path}")


if __name__ == "__main__":
    main()
