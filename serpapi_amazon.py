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
    "ship_from",
    "seller_region",
    "seller_city",
    "seller_match_basis",
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
        "ship_from": "",
        "seller_region": "unknown",
        "seller_city": "",
        "seller_match_basis": "",
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



CHINA_LOCATION_KEYWORDS = {
    "china", "prc", "mainland china", "hong kong", "shenzhen", "guangzhou",
    "dongguan", "foshan", "yiwu", "hangzhou", "shanghai", "beijing",
    "ningbo", "xiamen", "fuzhou", "suzhou", "nanjing", "wuhan", "chengdu",
    "zhengzhou", "xuchang", "luoyang", "anyang", "nanyang", "changsha", "qingdao",
    "guangdong", "zhejiang", "fujian", "jiangsu", "shandong", "henan",
    "中国", "香港", "深圳", "广州", "东莞", "佛山", "义乌", "杭州", "上海", "北京",
    "宁波", "厦门", "福州", "苏州", "南京", "武汉", "成都", "郑州", "许昌", "洛阳",
    "安阳", "南阳", "长沙", "青岛", "广东", "浙江", "福建", "江苏", "山东", "河南",
}

US_LOCATION_KEYWORDS = {
    "united states", "usa", "u.s.", "us ", "amazon.com", "california", "new york",
    "florida", "texas", "washington", "illinois", "new jersey", "georgia",
    "los angeles", "chicago", "houston", "seattle", "miami", "dallas", "美国",
}

CITY_KEYWORDS = {
    "shenzhen", "guangzhou", "dongguan", "foshan", "yiwu", "hangzhou", "shanghai",
    "beijing", "ningbo", "xiamen", "fuzhou", "suzhou", "nanjing", "wuhan", "chengdu",
    "zhengzhou", "xuchang", "luoyang", "anyang", "nanyang", "changsha", "qingdao",
    "los angeles", "chicago", "houston", "seattle", "miami", "dallas", "new york",
    "深圳", "广州", "东莞", "佛山", "义乌", "杭州", "上海", "北京", "宁波", "厦门",
    "福州", "苏州", "南京", "武汉", "成都", "郑州", "许昌", "洛阳", "安阳", "南阳",
    "长沙", "青岛",
}


LOCATION_ALIASES = {
    "中国": ["china", "prc", "mainland china"],
    "香港": ["hong kong"],
    "广东": ["guangdong"],
    "浙江": ["zhejiang"],
    "福建": ["fujian"],
    "江苏": ["jiangsu"],
    "山东": ["shandong"],
    "河南": ["henan"],
    "深圳": ["shenzhen", "guangdong"],
    "广州": ["guangzhou", "guangdong"],
    "东莞": ["dongguan", "guangdong"],
    "佛山": ["foshan", "guangdong"],
    "义乌": ["yiwu", "zhejiang"],
    "杭州": ["hangzhou", "zhejiang"],
    "上海": ["shanghai"],
    "北京": ["beijing"],
    "宁波": ["ningbo", "zhejiang"],
    "厦门": ["xiamen", "fujian"],
    "福州": ["fuzhou", "fujian"],
    "苏州": ["suzhou", "jiangsu"],
    "南京": ["nanjing", "jiangsu"],
    "武汉": ["wuhan"],
    "成都": ["chengdu"],
    "郑州": ["zhengzhou", "henan"],
    "许昌": ["xuchang", "henan"],
    "洛阳": ["luoyang", "henan"],
    "安阳": ["anyang", "henan"],
    "南阳": ["nanyang", "henan"],
    "长沙": ["changsha"],
    "青岛": ["qingdao", "shandong"],
    "美国": ["united states", "usa", "u.s.", "amazon.com"],
    "纽约": ["new york"],
    "洛杉矶": ["los angeles", "california"],
    "芝加哥": ["chicago", "illinois"],
    "休斯顿": ["houston", "texas"],
    "西雅图": ["seattle", "washington"],
}


def expand_location_terms(value: str) -> List[str]:
    text = to_text(value).lower().strip()
    if not text:
        return []

    terms = {text}
    compact = text.replace(" ", "")
    if compact != text:
        terms.add(compact)

    separators = [",", ";", "/", "|", "，", "；", "、"]
    normalized = text
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    for part in normalized.split():
        if part:
            terms.add(part)

    for chinese, aliases in LOCATION_ALIASES.items():
        chinese_lower = chinese.lower()
        if chinese in value or chinese_lower in terms:
            terms.add(chinese_lower)
            terms.update(alias.lower() for alias in aliases)
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in text:
                terms.add(chinese_lower)
                terms.add(alias_lower)
                terms.update(item.lower() for item in aliases)

    return sorted(term for term in terms if term)


def classify_seller_location(*values: str) -> Dict[str, str]:
    combined = " ".join(to_text(value) for value in values if value).lower()
    if not combined:
        return {"seller_region": "unknown", "seller_city": "", "seller_match_basis": ""}

    city = next((item for item in CITY_KEYWORDS if item in combined), "")
    if any(item in combined for item in CHINA_LOCATION_KEYWORDS):
        return {
            "seller_region": "china",
            "seller_city": city,
            "seller_match_basis": combined[:220],
        }
    if any(item in combined for item in US_LOCATION_KEYWORDS):
        return {
            "seller_region": "us",
            "seller_city": city,
            "seller_match_basis": combined[:220],
        }
    return {"seller_region": "unknown", "seller_city": city, "seller_match_basis": combined[:220]}


def request_serpapi_json(params: Dict) -> Dict:
    params = {**params, "api_key": get_api_key(), "output": "json"}
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
    return payload


def extract_seller_info(payload: Dict) -> Dict[str, str]:
    purchase_options = payload.get("purchase_options") or {}
    selected_option = next(iter(purchase_options.values()), {}) if purchase_options else {}
    features = selected_option.get("features") or {}
    sold_by = to_text((features.get("sold_by") or {}).get("text"))
    ship_from = to_text(
        (features.get("ships_from") or features.get("shipper_seller") or {}).get("text")
    )

    seller_chunks = [sold_by, ship_from]
    for seller in payload.get("other_sellers", []) or []:
        seller_chunks.extend([
            to_text(seller.get("sold_by")),
            to_text(seller.get("ship_from")),
            to_text(seller.get("seller_feedback")),
        ])
        if not sold_by:
            sold_by = to_text(seller.get("sold_by"))
        if not ship_from:
            ship_from = to_text(seller.get("ship_from"))

    location = classify_seller_location(*seller_chunks)
    return {
        "seller": sold_by,
        "ship_from": ship_from,
        **location,
    }


def fetch_product_seller_info(
    asin: str,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    device: str = "desktop",
) -> Dict[str, str]:
    if not asin:
        return {}
    payload = request_serpapi_json(
        {
            "engine": "amazon_product",
            "asin": asin,
            "amazon_domain": amazon_domain,
            "language": language,
            "device": device,
            "other_sellers": "true",
        }
    )
    return extract_seller_info(payload)


def matches_seller_filter(row: Dict[str, str], seller_region: str = "", seller_city: str = "") -> bool:
    region = seller_region.lower().strip()
    city_terms = expand_location_terms(seller_city)
    haystack = " ".join(
        [
            row.get("seller_city", ""),
            row.get("seller", ""),
            row.get("ship_from", ""),
            row.get("seller_match_basis", ""),
        ]
    ).lower()

    if region and region != "any":
        region_terms = {
            "china": CHINA_LOCATION_KEYWORDS,
            "us": US_LOCATION_KEYWORDS,
        }.get(region, set())
        region_matches_text = any(term in haystack for term in region_terms)
        if row.get("seller_region") != region and not region_matches_text:
            return False

    if city_terms and not any(term in haystack for term in city_terms):
        return False
    return True


def enrich_rows_with_seller_info(
    rows: List[Dict[str, str]],
    seller_region: str = "",
    seller_city: str = "",
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    device: str = "desktop",
    return_all_when_no_match: bool = False,
) -> List[Dict[str, str]]:
    if not seller_region and not seller_city:
        return rows

    enriched: List[Dict[str, str]] = []
    analyzed_rows: List[Dict[str, str]] = []
    for row in rows:
        try:
            seller_info = fetch_product_seller_info(
                row.get("asin", ""),
                amazon_domain=amazon_domain,
                language=language,
                device=device,
            )
        except SerpApiAmazonError as error:
            seller_info = {
                "seller_region": "unknown",
                "seller_city": "",
                "seller_match_basis": f"seller lookup failed: {error}",
            }
        next_row = {**row, **seller_info}
        analyzed_rows.append(next_row)
        if matches_seller_filter(next_row, seller_region=seller_region, seller_city=seller_city):
            enriched.append(next_row)
    if not enriched and return_all_when_no_match:
        for row in analyzed_rows:
            row["seller_filter_status"] = "no_match"
        return analyzed_rows
    return enriched


ESTIMATED_AMAZON_RESULTS_PER_PAGE = 48


def search_amazon_page(
    keyword: str,
    page: int = 1,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    sort: str = "relevanceblender",
    node: str = "",
    rh: str = "",
    delivery_zip: str = "",
    shipping_location: str = "",
    device: str = "desktop",
    dc: str = "true",
) -> Dict:
    if not keyword.strip() and not node and not rh:
        raise SerpApiAmazonError("Keyword, node, or rh is required.")

    params = {
        "engine": "amazon",
        "amazon_domain": amazon_domain,
        "language": language,
        "page": max(page, 1),
        "s": sort,
        "device": device,
        "dc": dc,
    }
    optional_params = {
        "k": keyword.strip(),
        "node": node,
        "rh": rh,
        "delivery_zip": delivery_zip,
        "shipping_location": shipping_location,
    }
    params.update({key: value for key, value in optional_params.items() if value})
    payload = request_serpapi_json(params)
    rows = collect_products(payload, keyword)
    total_results = payload.get("search_information", {}).get("total_results") or len(rows)
    return {
        "rows": rows,
        "total_results": int(total_results) if str(total_results).isdigit() else len(rows),
        "serpapi_page": payload.get("search_information", {}).get("page") or page,
        "has_next": bool((payload.get("serpapi_pagination") or {}).get("next")),
    }


def search_display_page(
    keyword: str,
    display_page: int = 1,
    page_size: int = 30,
    sort: str = "relevanceblender",
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    node: str = "",
    rh: str = "",
    delivery_zip: str = "",
    shipping_location: str = "",
    device: str = "desktop",
    dc: str = "true",
) -> Dict:
    page_size = page_size if page_size in {30, 50} else 30
    display_page = max(display_page, 1)
    start_index = (display_page - 1) * page_size
    end_index = start_index + page_size
    needed_api_pages = max(1, (end_index + ESTIMATED_AMAZON_RESULTS_PER_PAGE - 1) // ESTIMATED_AMAZON_RESULTS_PER_PAGE)

    rows: List[Dict[str, str]] = []
    seen_asins = set()
    total_results = 0
    has_next = False

    for serpapi_page in range(1, needed_api_pages + 1):
        payload = search_amazon_page(
            keyword=keyword,
            page=serpapi_page,
            sort=sort,
            amazon_domain=amazon_domain,
            language=language,
            node=node,
            rh=rh,
            delivery_zip=delivery_zip,
            shipping_location=shipping_location,
            device=device,
            dc=dc,
        )
        total_results = payload.get("total_results", total_results)
        has_next = payload.get("has_next", False)
        for row in payload["rows"]:
            asin = row.get("asin")
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)
            rows.append(row)

    return {
        "rows": rows[start_index:end_index],
        "total_results": total_results,
        "page": display_page,
        "page_size": page_size,
        "total_pages": max(1, (total_results + page_size - 1) // page_size) if total_results else 0,
        "has_next": has_next or end_index < total_results,
    }

def search_amazon_products(
    keyword: str,
    page: int = 1,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    sort: str = "relevanceblender",
    node: str = "",
    rh: str = "",
    delivery_zip: str = "",
    shipping_location: str = "",
    device: str = "desktop",
    dc: str = "true",
    api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    del api_key
    rows = search_amazon_page(
        keyword=keyword,
        page=page,
        amazon_domain=amazon_domain,
        language=language,
        sort=sort,
        node=node,
        rh=rh,
        delivery_zip=delivery_zip,
        shipping_location=shipping_location,
        device=device,
        dc=dc,
    )["rows"]
    if not rows:
        raise SerpApiAmazonError("SerpApi returned no Amazon products.")
    return rows


def search_multiple_pages(
    keyword: str,
    pages: int = 1,
    limit: Optional[int] = None,
    sort: str = "relevanceblender",
    start_page: int = 1,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    node: str = "",
    rh: str = "",
    delivery_zip: str = "",
    shipping_location: str = "",
    device: str = "desktop",
    dc: str = "true",
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen_asins = set()

    first_page = max(start_page, 1)
    last_page = first_page + max(pages, 1) - 1

    for page in range(first_page, last_page + 1):
        for row in search_amazon_products(
            keyword=keyword,
            page=page,
            sort=sort,
            amazon_domain=amazon_domain,
            language=language,
            node=node,
            rh=rh,
            delivery_zip=delivery_zip,
            shipping_location=shipping_location,
            device=device,
            dc=dc,
        ):
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
    parser.add_argument("keyword", nargs="?", default="", help="Search keyword, for example: iphone case")
    parser.add_argument("--output", "-o", help="Save results to .csv or .json")
    parser.add_argument("--pages", type=int, default=1, help="How many Amazon pages to fetch.")
    parser.add_argument("--page", type=int, default=1, help="Starting Amazon page number.")
    parser.add_argument("--limit", type=int, help="Maximum number of products to keep.")
    parser.add_argument("--amazon-domain", default="amazon.com", help="Amazon domain, for example amazon.com.")
    parser.add_argument("--language", default="en_US", help="Amazon language locale, for example en_US.")
    parser.add_argument("--node", default="", help="Amazon category node ID.")
    parser.add_argument("--rh", default="", help="Amazon advanced filter parameter.")
    parser.add_argument("--delivery-zip", default="", help="ZIP/postal code used for delivery filtering.")
    parser.add_argument("--shipping-location", default="", help="Shipping country used for filtering.")
    parser.add_argument(
        "--device",
        default="desktop",
        choices=["desktop", "mobile", "tablet"],
        help="Device type passed to SerpApi.",
    )
    parser.add_argument(
        "--dc",
        default="true",
        choices=["true", "false"],
        help="Enable or disable Amazon spelling correction.",
    )
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
            start_page=args.page,
            limit=args.limit,
            sort=args.sort,
            amazon_domain=args.amazon_domain,
            language=args.language,
            node=args.node,
            rh=args.rh,
            delivery_zip=args.delivery_zip,
            shipping_location=args.shipping_location,
            device=args.device,
            dc=args.dc,
        )
    except SerpApiAmazonError as error:
        raise SystemExit(f"Search failed: {error}") from error

    print_preview(rows)
    if args.output:
        save_rows(Path(args.output), rows)
        print(f"Saved results to: {args.output}")


if __name__ == "__main__":
    main()
