#!/usr/bin/env python3

import json
import os
from http.client import RemoteDisconnected
from statistics import mean
from typing import Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from serpapi_amazon import SerpApiAmazonError, request_serpapi_json, to_text


STAR_FILTERS = {
    "all": "",
    "critical": "critical",
    "positive": "positive",
    "one_star": "one_star",
    "two_star": "two_star",
    "three_star": "three_star",
    "four_star": "four_star",
    "five_star": "five_star",
}


TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
REVIEW_TRANSLATION_LIMIT = int(os.environ.get("REVIEW_TRANSLATION_LIMIT", "80"))


def _extract_google_translation(payload) -> str:
    parts = []
    if not isinstance(payload, list) or not payload:
        return ""
    for item in payload[0] or []:
        if isinstance(item, list) and item:
            parts.append(to_text(item[0]))
    return "".join(parts).strip()


def _translate_to_chinese(text: str) -> str:
    text = to_text(text)
    if not text:
        return ""
    data = urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text[:4500],
        }
    ).encode("utf-8")
    request = Request(
        TRANSLATE_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "User-Agent": "TradeHarbor/1.0",
        },
    )
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    return _extract_google_translation(payload)


def _translate_reviews_to_chinese(reviews: List[Dict]) -> List[str]:
    errors = []
    for index, review in enumerate(reviews):
        if index >= REVIEW_TRANSLATION_LIMIT:
            review["body_zh"] = "未翻译：超过本次翻译上限，可调高 REVIEW_TRANSLATION_LIMIT。"
            continue
        source_text = review.get("body") or review.get("title") or ""
        if not source_text:
            review["body_zh"] = ""
            continue
        try:
            review["body_zh"] = _translate_to_chinese(source_text)
        except Exception as error:
            review["body_zh"] = "翻译暂不可用"
            if len(errors) < 3:
                errors.append(str(error))
    return errors


def _number(value) -> float:
    if value is None:
        return 0
    text = str(value).replace(",", "").strip()
    for token in text.split():
        try:
            return float(token)
        except ValueError:
            continue
    try:
        return float(text)
    except ValueError:
        return 0


def _review_author(review: Dict) -> str:
    profile = review.get("profile") or review.get("author") or {}
    if isinstance(profile, dict):
        return to_text(profile.get("name") or profile.get("profile_name") or profile.get("link"))
    return to_text(profile or review.get("profile_name") or review.get("author_name"))


def _review_images(review: Dict) -> List[str]:
    images = review.get("images") or review.get("media") or []
    urls = []
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                url = to_text(item.get("link") or item.get("thumbnail") or item.get("image"))
            else:
                url = to_text(item)
            if url:
                urls.append(url)
    return urls


def _normalize_review(review: Dict, page: int) -> Dict:
    body = to_text(
        review.get("body")
        or review.get("text")
        or review.get("snippet")
        or review.get("content")
        or review.get("review")
    )
    title = to_text(review.get("title") or review.get("review_title"))
    rating = _number(review.get("rating"))
    verified = review.get("verified_purchase")
    if isinstance(verified, bool):
        verified_text = "Yes" if verified else "No"
    else:
        verified_text = to_text(verified or review.get("verified") or "")
    return {
        "id": to_text(review.get("id") or review.get("review_id")),
        "page": page,
        "rating": rating,
        "title": title,
        "body": body,
        "body_zh": "",
        "date": to_text(review.get("date") or review.get("review_date")),
        "author": _review_author(review),
        "verified_purchase": verified_text,
        "helpful_votes": to_text(review.get("helpful_votes") or review.get("helpful") or review.get("helpful_count")),
        "variant": to_text(review.get("product_variant") or review.get("variant") or review.get("style")),
        "country": to_text(review.get("country") or review.get("review_country")),
        "images": _review_images(review),
    }


def _raw_reviews(payload: Dict) -> List[Dict]:
    candidates = [
        payload.get("reviews"),
        payload.get("organic_results"),
        (payload.get("reviews_results") or {}).get("reviews") if isinstance(payload.get("reviews_results"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _total_reviews(payload: Dict) -> int:
    candidates = [
        payload.get("total_reviews"),
        payload.get("reviews_count"),
        payload.get("ratings_total"),
        (payload.get("reviews_results") or {}).get("total_reviews") if isinstance(payload.get("reviews_results"), dict) else None,
        (payload.get("reviews_results") or {}).get("reviews_count") if isinstance(payload.get("reviews_results"), dict) else None,
    ]
    for candidate in candidates:
        number = int(_number(candidate))
        if number:
            return number
    return 0


def _find_review_lists(value) -> List[Dict]:
    found: List[Dict] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if "review" in key_text and isinstance(child, list):
                found.extend(item for item in child if isinstance(item, dict))
            found.extend(_find_review_lists(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_review_lists(item))
    return found


def _fetch_product_review_fallback(asin: str, amazon_domain: str) -> Dict:
    try:
        payload = request_serpapi_json(
            {
                "engine": "amazon_product",
                "asin": asin,
                "amazon_domain": amazon_domain,
            }
        )
    except Exception as error:
        return {"reviews": [], "error": f"amazon_product 兜底也失败：{error}"}

    raw = _raw_reviews(payload) or _find_review_lists(payload)
    reviews = [_normalize_review(item, 1) for item in raw]
    # Some product detail responses only expose rating counters, not review text.
    reviews = [item for item in reviews if item.get("title") or item.get("body")]
    return {"reviews": reviews, "error": ""}


def fetch_asin_reviews(
    asin: str,
    max_pages: int = 5,
    filter_by_star: str = "all",
    amazon_domain: str = "amazon.com",
    sort_by: str = "recent",
    translate_zh: bool = True,
) -> Dict:
    asin = asin.strip().upper()
    if not asin:
        raise ValueError("请输入 ASIN。")
    max_pages = min(max(int(max_pages or 5), 1), 20)
    filter_value = STAR_FILTERS.get(filter_by_star, "")
    reviews: List[Dict] = []
    errors: List[str] = []
    total_reviews = 0
    has_next = False
    pages_fetched = 0
    source = "amazon_reviews"

    for page in range(1, max_pages + 1):
        params = {
            "engine": "amazon_reviews",
            "asin": asin,
            "amazon_domain": amazon_domain,
            "page": page,
        }
        if filter_value:
            params["filter_by_star"] = filter_value
        if sort_by:
            params["sort_by"] = sort_by
        try:
            payload = request_serpapi_json(params)
        except (SerpApiAmazonError, RemoteDisconnected, OSError) as error:
            errors.append(f"第 {page} 页失败：{error}")
            break

        page_reviews = [_normalize_review(item, page) for item in _raw_reviews(payload)]
        total_reviews = _total_reviews(payload) or total_reviews
        reviews.extend(page_reviews)
        pages_fetched = page
        pagination = payload.get("serpapi_pagination") or {}
        has_next = bool(pagination.get("next") or pagination.get("next_page"))
        if not page_reviews or not has_next:
            break

    if not reviews:
        fallback = _fetch_product_review_fallback(asin, amazon_domain)
        if fallback.get("reviews"):
            reviews = fallback["reviews"]
            pages_fetched = 1
            has_next = False
            source = "amazon_product_fallback"
        if fallback.get("error"):
            errors.append(fallback["error"])

    translation_errors = _translate_reviews_to_chinese(reviews) if translate_zh else []
    if translation_errors:
        errors.append("中文翻译部分失败：" + "；".join(translation_errors))

    ratings = [item["rating"] for item in reviews if item.get("rating")]
    low_rating_count = sum(1 for item in reviews if item.get("rating") and item["rating"] <= 3)
    verified_count = sum(1 for item in reviews if "verified" in item.get("verified_purchase", "").lower() or item.get("verified_purchase") == "Yes")
    unsupported = any("Unsupported `amazon_reviews`" in error for error in errors)
    return {
        "asin": asin,
        "summary": {
            "fetched_count": len(reviews),
            "pages_fetched": pages_fetched,
            "max_pages": max_pages,
            "total_reviews": total_reviews or len(reviews),
            "has_more": has_next and pages_fetched >= max_pages,
            "average_rating": round(mean(ratings), 2) if ratings else 0,
            "low_rating_count": low_rating_count,
            "verified_count": verified_count,
            "filter_by_star": filter_by_star,
            "sort_by": sort_by,
            "source": source,
            "reviews_engine_supported": not unsupported,
            "translation_enabled": translate_zh,
        },
        "reviews": reviews,
        "errors": errors,
        "notes": [
            "SerpApi 的 Amazon Reviews 按页返回；这里会自动翻页到没有下一页或达到最大页数。",
            "如果当前 SerpApi 账号不支持 amazon_reviews，系统会尝试 amazon_product 详情兜底，但可能只能拿到少量评论片段或拿不到完整评论。",
            "如果要稳定抓取完整评论，建议后续接 Rainforest API、Keepa 或支持 Reviews 的 SerpApi 套餐。",
            "中文评论内容由在线翻译接口生成，适合快速理解，正式分析时建议结合英文原文核对。",
        ],
    }

