#!/usr/bin/env python3

from statistics import mean
from typing import Dict, List

from ai_opportunity import (
    CONSUMABLE_TERMS,
    FBM_FRIENDLY_TERMS,
    FBM_RISK_TERMS,
    REPEAT_TERMS,
    detect_pack_count,
    infer_brand,
    text_terms,
    to_number,
)
from serpapi_amazon import SerpApiAmazonError, request_serpapi_json, search_amazon_page, to_text

SPECIAL_SPEC_TERMS = {
    "grit", "arbor", "adapter", "adaptor", "diameter", "thick", "thin", "inch",
    "mm", "5/8", "7/8", "3/8", "1/2", "1/4", "thread", "pitch", "compatible",
    "fit", "fits", "bench", "chainsaw", "tile", "glass", "cbn", "diamond",
}
BUNDLE_SIDE_TERMS = {
    "adapter", "adaptor", "dressing", "stone", "flange", "nut", "washer", "case",
    "holder", "mandrel", "backing", "pad", "spanner", "wrench", "bushing", "glove",
}
OEM_TERMS = {
    "replacement", "compatible", "fits", "fit", "for", "oem", "part", "parts", "accessory",
    "adapter", "blade", "wheel", "filter", "pad", "belt", "chain", "grinder",
}
REVIEW_PAIN_PATTERNS = [
    ("数量/包装不足", {"one", "single", "pack", "package", "missing", "few", "quantity", "small"}),
    ("容易坏或寿命短", {"broke", "broken", "break", "crack", "cracked", "wear", "worn", "dull", "lasted"}),
    ("适配/尺寸问题", {"fit", "fits", "size", "arbor", "adapter", "wrong", "hole", "diameter"}),
    ("价格过高", {"expensive", "price", "cost", "overpriced", "money"}),
    ("质量不稳定", {"quality", "cheap", "poor", "defect", "defective", "wobble", "uneven"}),
]


def _price(value) -> float:
    return round(to_number(value), 2)


def _collect_products(keyword: str, limit: int = 20) -> Dict:
    rows: List[Dict] = []
    seen = set()
    total_results = 0
    for page in range(1, 4):
        payload = search_amazon_page(
            keyword=keyword,
            page=page,
            amazon_domain="amazon.com",
            language="en_US",
            sort="relevanceblender",
            device="desktop",
            dc="true",
        )
        total_results = payload.get("total_results", total_results)
        for row in payload.get("rows", []):
            asin = row.get("asin")
            if not asin or asin in seen:
                continue
            seen.add(asin)
            rows.append(row)
            if len(rows) >= limit:
                return {"rows": rows, "total_results": total_results or len(rows)}
        if not payload.get("has_next"):
            break
    return {"rows": rows[:limit], "total_results": total_results or len(rows)}


def _normalize(row: Dict) -> Dict:
    title = to_text(row.get("title"))
    return {
        "asin": to_text(row.get("asin")),
        "title": title,
        "price": _price(row.get("price")),
        "rating": _price(row.get("rating")),
        "reviews": int(to_number(row.get("reviews"))),
        "thumbnail": to_text(row.get("image_url")),
        "link": to_text(row.get("product_url")),
        "brand": to_text(row.get("brand")) or infer_brand(title),
        "category": to_text(row.get("category")),
        "sales": to_text(row.get("sales")),
        "pack_count": detect_pack_count(title),
        "is_prime": to_text(row.get("is_prime")).lower() in {"yes", "true", "prime"},
    }


def _fetch_review_snippets(asin: str, limit: int = 6) -> List[Dict]:
    if not asin:
        return []
    review_payloads = []
    for params in (
        {"engine": "amazon_reviews", "asin": asin, "amazon_domain": "amazon.com", "filter_by_star": "critical"},
        {"engine": "amazon_reviews", "asin": asin, "amazon_domain": "amazon.com"},
    ):
        try:
            review_payloads.append(request_serpapi_json(params))
            break
        except SerpApiAmazonError:
            continue

    if not review_payloads:
        return []
    payload = review_payloads[0]
    raw_reviews = payload.get("reviews") or payload.get("organic_results") or []
    snippets = []
    for review in raw_reviews[:limit]:
        if not isinstance(review, dict):
            continue
        text = to_text(review.get("body") or review.get("text") or review.get("snippet") or review.get("review"))
        title = to_text(review.get("title"))
        rating = _price(review.get("rating"))
        if not text and not title:
            continue
        snippets.append({"title": title, "body": text[:420], "rating": rating})
    return snippets


def _pain_points_from_reviews(reviews: List[Dict], product_title: str = "") -> List[str]:
    haystack = " ".join([product_title] + [f"{item.get('title', '')} {item.get('body', '')}" for item in reviews]).lower()
    terms = set(__import__("re").findall(r"[a-z0-9/]+", haystack))
    points = []
    for label, words in REVIEW_PAIN_PATTERNS:
        if terms & words:
            points.append(label)
    return points[:4]


def _market_context(products: List[Dict], total_results: int) -> Dict:
    top10 = products[:10]
    prices = [p["price"] for p in top10 if p.get("price")]
    reviews = [p["reviews"] for p in top10]
    single_count = sum(1 for p in products if p.get("pack_count", 1) == 1)
    multipack_count = len(products) - single_count
    brands = [p.get("brand", "").lower() for p in top10 if p.get("brand")]
    brand_concentration = 0
    if brands:
        brand_concentration = round(max(brands.count(item) for item in set(brands)) / len(brands) * 100, 1)
    return {
        "total_results": total_results,
        "sample_size": len(products),
        "avg_price": round(mean(prices), 2) if prices else 0,
        "avg_reviews": round(mean(reviews), 1) if reviews else 0,
        "single_ratio": round(single_count / max(len(products), 1) * 100, 1),
        "multipack_count": multipack_count,
        "brand_concentration": brand_concentration,
    }


def _score_gap(product: Dict, keyword: str, context: Dict, review_snippets: List[Dict]) -> Dict:
    terms = text_terms(keyword, product.get("title"), product.get("category"), product.get("sales"))
    price = product.get("price") or 0
    reviews = product.get("reviews") or 0
    pack_count = product.get("pack_count") or 1
    pain_points = _pain_points_from_reviews(review_snippets, product.get("title", ""))
    market_gap = []
    risks = []
    recommendations = []

    is_consumable = bool(terms & (CONSUMABLE_TERMS | REPEAT_TERMS))
    is_fbm_friendly = bool(terms & FBM_FRIENDLY_TERMS) and not bool(terms & FBM_RISK_TERMS)
    special_specs = sorted(terms & SPECIAL_SPEC_TERMS)[:6]
    oem_signal = bool(terms & OEM_TERMS) and price >= 12
    accessory_signal = bool(terms & BUNDLE_SIDE_TERMS)

    multipack_score = 0
    if pack_count == 1 and is_consumable and context.get("single_ratio", 0) >= 55:
        multipack_score = 20
        market_gap.append(f"样本约 {context.get('single_ratio')}% 是单件，缺少 3/5/10pcs 选择")
        recommendations.extend(["3 Pack", "5 Pack", "10 Pack"])
    elif pack_count > 1:
        multipack_score = 11
        market_gap.append(f"已有 {pack_count}pcs 竞品，可反推多件装需求")
        recommendations.append("参考竞品数量做差异化 Pack")
    elif is_consumable:
        multipack_score = 13
        market_gap.append("耗材属性明显，但多件装信号还需要进一步验证")

    bundle_score = 0
    if accessory_signal or is_consumable:
        bundle_score = 14
        market_gap.append("可围绕使用场景做 Starter Kit / Professional Kit")
        recommendations.append("Starter Kit")
    if special_specs and is_consumable:
        bundle_score = min(20, bundle_score + 6)
        recommendations.append("Professional Kit")

    replacement_score = 0
    if oem_signal:
        replacement_score = 20 if price >= 25 else 15
        market_gap.append("存在替代件/OEM 兼容信号，适合评估中国供应链替代")
        recommendations.append("OEM Compatible Alternative")
    elif terms & OEM_TERMS:
        replacement_score = 10

    review_score = 0
    if pain_points:
        review_score = 15
        market_gap.extend([f"Review 痛点：{point}" for point in pain_points[:3]])
    elif 0 < reviews < 500:
        review_score = 7
        market_gap.append("评论不高但已有需求，可重点观察 2-3 星评价")

    fbm_score = 10 if is_fbm_friendly or (7 <= price <= 45 and not (terms & FBM_RISK_TERMS)) else 4
    if fbm_score >= 8:
        market_gap.append("轻小配件/耗材属性较强，适合 FBM 快速测款")
    if terms & FBM_RISK_TERMS:
        risks.append("可能有大件、机器、易碎或售后复杂风险")

    profit_score = 0
    if 12 <= price <= 55:
        profit_score = 10
    elif 7 <= price < 12 or 55 < price <= 120:
        profit_score = 6
    else:
        profit_score = 2
    if price < 7:
        risks.append("单价过低，广告和履约费用容易吃掉利润")
    if price > 120:
        risks.append("高客单价多件装转化门槛高")

    niche_score = 5 if special_specs or context.get("total_results", 0) < 1200 else 2
    if special_specs:
        market_gap.append(f"特殊规格/专业词明显：{', '.join(special_specs)}")
        recommendations.append("特殊规格长尾款")

    score = multipack_score + bundle_score + replacement_score + review_score + fbm_score + profit_score + niche_score
    if reviews > 10000:
        score -= 18
        risks.append("Review 超过 10000，头部垄断压力大")
    elif reviews > 5000:
        score -= 10
        risks.append("Review 很高，直接硬刚难度大")
    if context.get("brand_concentration", 0) >= 50:
        score -= 6
        risks.append("Top10 品牌集中度较高，需避开品牌垄断")
    if not risks:
        risks.append("仍需人工确认专利、品牌词、兼容性和真实物流重量")
    if not recommendations:
        recommendations.append("先作为观察款，不建议马上上架")
    if not market_gap:
        market_gap.append("暂未识别出强供给缺陷，建议换更细分关键词")

    return {
        "score": max(0, min(100, round(score))),
        "score_breakdown": {
            "multipack": multipack_score,
            "bundle": bundle_score,
            "replacement": replacement_score,
            "review_pain": review_score,
            "fbm": fbm_score,
            "profit": profit_score,
            "niche": niche_score,
        },
        "market_gap": market_gap[:6],
        "multipack_opportunity": multipack_score >= 13,
        "bundle_opportunity": bundle_score >= 14,
        "replacement_opportunity": replacement_score >= 15,
        "review_pain_points": pain_points,
        "risk": risks[:4],
        "recommendation": recommendations[:5],
        "ai_analysis": "；".join(market_gap[:4]),
        "review_samples": review_snippets[:3],
    }


def discover_market_gaps(keyword: str, limit: int = 20, review_limit: int = 5) -> Dict:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("请输入关键词，例如 diamond wheel。")
    limit = min(max(int(limit or 20), 1), 20)
    payload = _collect_products(keyword, limit=limit)
    products = [_normalize(row) for row in payload["rows"]]
    context = _market_context(products, payload["total_results"])

    analyzed = []
    review_errors = []
    for index, product in enumerate(products):
        review_snippets = []
        if index < max(0, min(review_limit, 8)):
            try:
                review_snippets = _fetch_review_snippets(product.get("asin"), limit=6)
            except Exception as error:
                review_errors.append(f"{product.get('asin')}: {error}")
        gap = _score_gap(product, keyword, context, review_snippets)
        analyzed.append({**product, "gap": gap})

    high_score_count = sum(1 for item in analyzed if item.get("gap", {}).get("score", 0) >= 70)
    multipack_count = sum(1 for item in analyzed if item.get("gap", {}).get("multipack_opportunity"))
    bundle_count = sum(1 for item in analyzed if item.get("gap", {}).get("bundle_opportunity"))
    replacement_count = sum(1 for item in analyzed if item.get("gap", {}).get("replacement_opportunity"))
    top_gaps = []
    for item in sorted(analyzed, key=lambda row: row.get("gap", {}).get("score", 0), reverse=True)[:6]:
        top_gaps.extend(item.get("gap", {}).get("market_gap", [])[:2])
    deduped_top_gaps = []
    for gap in top_gaps:
        if gap not in deduped_top_gaps:
            deduped_top_gaps.append(gap)

    return {
        "keyword": keyword,
        "summary": {
            **context,
            "high_score_count": high_score_count,
            "multipack_count": multipack_count,
            "bundle_count": bundle_count,
            "replacement_count": replacement_count,
            "review_analyzed_count": min(len(products), max(0, min(review_limit, 8))),
            "top_market_gaps": deduped_top_gaps[:6],
        },
        "products": analyzed,
        "review_errors": review_errors[:5],
        "notes": [
            "该模块重点识别供给缺陷，不只看销量/Review/BSR。",
            "Review 抓取作为增强项，若 SerpApi 不返回评论，系统会自动用本地市场缺陷规则继续分析。",
            "真正上架前仍需人工确认专利、品牌词、适配型号、采购成本和物流限制。",
        ],
    }
