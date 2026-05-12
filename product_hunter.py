#!/usr/bin/env python3

import json
import os
import re
from statistics import mean
from typing import Dict, List
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_opportunity import (
    CONSUMABLE_TERMS,
    FBM_FRIENDLY_TERMS,
    FBM_RISK_TERMS,
    REPEAT_TERMS,
    OPENAI_MODEL,
    build_pack_recommendations,
    detect_pack_count,
    extract_openai_text,
    infer_brand,
    readable_openai_error,
    text_terms,
    to_number,
)
from serpapi_amazon import SerpApiAmazonError, load_dotenv, search_amazon_page, to_text


def _money(value: float) -> str:
    if value <= 0:
        return ""
    rounded = max(value, 0.99)
    dollars = int(rounded)
    cents_price = dollars + 0.99
    if cents_price < rounded * 0.94:
        cents_price = round(rounded, 2)
    return f"${cents_price:.2f}"


def _price_number(value) -> float:
    return round(to_number(value), 2)


def _collect_first_products(keyword: str, limit: int = 20) -> Dict:
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


def _normalize_row(row: Dict) -> Dict:
    title = to_text(row.get("title"))
    price = _price_number(row.get("price"))
    return {
        "asin": to_text(row.get("asin")),
        "title": title,
        "price": price,
        "rating": _price_number(row.get("rating")),
        "reviews": int(to_number(row.get("reviews"))),
        "thumbnail": to_text(row.get("image_url")),
        "link": to_text(row.get("product_url")),
        "brand": to_text(row.get("brand")) or infer_brand(title),
        "category": to_text(row.get("category")),
        "is_prime": to_text(row.get("is_prime")).lower() in {"yes", "true", "prime"},
        "sales": to_text(row.get("sales")),
        "pack_count": detect_pack_count(title),
    }


def _score_product(product: Dict, keyword: str, context: Dict) -> Dict:
    terms = text_terms(keyword, product.get("title"), product.get("category"), product.get("sales"))
    price = product.get("price") or 0
    reviews = product.get("reviews") or 0
    pack_count = product.get("pack_count") or 1
    reasons = []
    risks = []

    has_consumable = bool(terms & (CONSUMABLE_TERMS | REPEAT_TERMS))
    has_fbm_signal = bool(terms & FBM_FRIENDLY_TERMS)
    has_fbm_risk = bool(terms & FBM_RISK_TERMS)

    fbm_score = 0
    if has_fbm_signal:
        fbm_score = 20
        reasons.append("标题包含轻小耗材/配件信号，适合先用 FBM 小批量测款")
    elif 7 <= price <= 45:
        fbm_score = 13
        reasons.append("价格带适合低成本测试，物流风险需要再确认")
    else:
        fbm_score = 7
    if has_fbm_risk:
        fbm_score = max(0, fbm_score - 9)
        risks.append("可能存在大件、易碎、液体、机器类等 FBM 风险词")

    consumable_score = 20 if has_consumable else 8
    if has_consumable:
        reasons.append("有耗材、替代件或复购属性，买家可能重复购买")
    else:
        risks.append("耗材/替代件属性不够明显")

    bundle_score = 0
    if pack_count == 1 and has_consumable and price >= 7:
        bundle_score = 20
        reasons.append("当前多为单件形态，可尝试 3/5/10 件装拉高客单价")
    elif pack_count > 1:
        bundle_score = 12
        reasons.append(f"市场已有 {pack_count}pcs 形态，可作为套装数量和定价参考")
    elif price >= 10:
        bundle_score = 10
        reasons.append("单价足够做组合装，但需要验证多件购买动机")

    if reviews < 500:
        competition_score = 15
        review_score = 10
        reasons.append("评论数低于 500，新卖家更容易切入")
    elif reviews < 1500:
        competition_score = 10
        review_score = 6
        reasons.append("评论量中等，可以用差异化组合测试")
    elif reviews < 5000:
        competition_score = 5
        review_score = 2
        risks.append("评论量偏高，需要避开直接硬刚")
    else:
        competition_score = 1
        review_score = 0
        risks.append("评论超过 5000，竞争压力很大")

    if 10 <= price <= 50:
        price_score = 15
        reasons.append("价格高于 $10，有组合装和利润空间")
    elif 7 <= price < 10:
        price_score = 7
        risks.append("单价偏低，广告和运费容易吃掉利润")
    elif price > 50:
        price_score = 9
        risks.append("单价偏高，多件装转化门槛可能较高")
    else:
        price_score = 2
        risks.append("价格低于 $7，不适合优先做组合装")

    score = round(fbm_score + consumable_score + bundle_score + competition_score + price_score + review_score)
    if context.get("single_ratio", 0) >= 60 and pack_count == 1 and has_consumable:
        score = min(100, score + 4)
        reasons.append(f"该关键词样本约 {context['single_ratio']}% 为单件，存在 Bundle 空白")
    if context.get("top10_avg_reviews", 0) > 3000:
        score = max(0, score - 5)
        risks.append("Top10 平均评论较高，整体竞争偏强")

    is_good = score >= 65 and bundle_score >= 12 and price >= 7 and reviews < 5000
    packs = build_pack_recommendations(price or context.get("top10_avg_price") or 19.99, source="product")
    suggested_price = {
        "3_pack": _money((price or 19.99) * 3 * 0.90),
        "5_pack": _money((price or 19.99) * 5 * 0.85),
        "10_pack": _money((price or 19.99) * 10 * 0.80),
    }
    pack_prices = [
        {"pack": row["pack"], "price": _money(row["target_price"]), "unit_price": _money(row["unit_price"])}
        for row in packs
    ]
    purchase_cost_rate = 0.30 if has_consumable else 0.38
    fulfillment_rate = 0.16
    ad_rate = 0.12
    estimated_margin = max(0, round((1 - purchase_cost_rate - fulfillment_rate - ad_rate) * 100))

    if not reasons:
        reasons.append("当前数据不足，只能作为候选观察")
    if not risks:
        risks.append("仍需确认品牌词、外观专利、兼容性和真实物流重量")

    return {
        "opportunity_score": max(0, min(100, score)),
        "is_good_for_bundle": is_good,
        "bundle_suggestion": "建议做 3件装、5件装、10件装" if is_good else "暂不建议优先做多件装",
        "suggested_price": suggested_price,
        "pack_prices": pack_prices,
        "estimated_profit_margin": f"{estimated_margin}%",
        "profit_logic": "按采购约30%、履约约16%、广告约12%粗估，适合先用 FBM 测点击和转化。",
        "risk": "；".join(risks[:3]),
        "ai_reason": "；".join(reasons[:4]),
        "score_breakdown": {
            "fbm": fbm_score,
            "consumable": consumable_score,
            "bundle": bundle_score,
            "competition": competition_score,
            "price": price_score,
            "review": review_score,
        },
    }


def _extract_json_block(text: str):
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.S)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"(\[\s*\{.*\}\s*\]|\{.*\})", text, re.S)
    if match:
        return json.loads(match.group(1))
    return None


def _merge_openai_analysis(products: List[Dict], ai_payload) -> int:
    if isinstance(ai_payload, dict):
        ai_items = ai_payload.get("products") or ai_payload.get("items") or []
    else:
        ai_items = ai_payload if isinstance(ai_payload, list) else []
    by_asin = {to_text(item.get("asin")): item for item in ai_items if isinstance(item, dict) and item.get("asin")}
    merged = 0
    for product in products:
        item = by_asin.get(product.get("asin"))
        if not item:
            continue
        analysis = product.setdefault("analysis", {})
        if item.get("opportunity_score") is not None:
            analysis["opportunity_score"] = max(0, min(100, int(to_number(item.get("opportunity_score")))))
        if item.get("is_good_for_bundle") is not None:
            analysis["is_good_for_bundle"] = bool(item.get("is_good_for_bundle"))
        for source_key, target_key in [
            ("bundle_suggestion", "bundle_suggestion"),
            ("profit_logic", "profit_logic"),
            ("risk", "risk"),
            ("ai_reason", "ai_reason"),
            ("analysis_reason", "ai_reason"),
        ]:
            if item.get(source_key):
                analysis[target_key] = to_text(item.get(source_key))
        if isinstance(item.get("suggested_price"), dict):
            analysis["suggested_price"] = item["suggested_price"]
        merged += 1
    return merged


def _openai_enhance_products(keyword: str, products: List[Dict], summary: Dict) -> Dict:
    if os.environ.get("PRODUCT_HUNTER_OPENAI", "1") == "0":
        return {"mode": "local_rules", "error": "PRODUCT_HUNTER_OPENAI=0，当前使用本地规则评分。", "merged": 0}
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"mode": "local_rules", "error": "未配置 OPENAI_API_KEY，当前使用本地规则评分。", "merged": 0}

    slim_products = []
    for product in products:
        analysis = product.get("analysis") or {}
        slim_products.append(
            {
                "asin": product.get("asin"),
                "title": product.get("title"),
                "price": product.get("price"),
                "rating": product.get("rating"),
                "reviews": product.get("reviews"),
                "brand": product.get("brand"),
                "category": product.get("category"),
                "pack_count": product.get("pack_count"),
                "local_score": analysis.get("opportunity_score"),
                "local_reason": analysis.get("ai_reason"),
            }
        )

    instruction = (
        "你是务实的 Amazon 跨境选品顾问。请按每个商品判断是否适合用中国供应链做低成本切入、"
        "3件装/5件装/10件装、替代件、组合套装和 FBM 测款。必须保守，不要夸大。"
    )
    user_payload = {
        "keyword": keyword,
        "summary": summary,
        "products": slim_products,
        "required_json_shape": {
            "products": [
                {
                    "asin": "B0XXXXXXX",
                    "opportunity_score": 88,
                    "is_good_for_bundle": True,
                    "bundle_suggestion": "建议做 3件装、5件装、10件装",
                    "suggested_price": {"3_pack": "$34.99", "5_pack": "$54.99", "10_pack": "$99.99"},
                    "profit_logic": "为什么有利润空间",
                    "ai_reason": "为什么适合或不适合",
                    "risk": "品牌/专利/物流/退货等风险",
                }
            ]
        },
    }
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            "input": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": "只返回 JSON，不要 Markdown。\n" + json.dumps(user_payload, ensure_ascii=False)},
            ],
            "max_output_tokens": 2600,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=50) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        text = extract_openai_text(payload)
        ai_payload = _extract_json_block(text)
        merged = _merge_openai_analysis(products, ai_payload)
        return {"mode": "openai" if merged else "local_rules", "error": "" if merged else "OpenAI 未返回可合并的 JSON，已保留本地评分。", "merged": merged}
    except (HTTPError, URLError, TimeoutError, RemoteDisconnected, OSError, json.JSONDecodeError, ValueError) as error:
        return {"mode": "local_rules", "error": readable_openai_error(error), "merged": 0}


def _summary(products: List[Dict], total_results: int) -> Dict:
    top10 = products[:10]
    prices = [item["price"] for item in top10 if item.get("price")]
    reviews = [item["reviews"] for item in top10]
    single_count = sum(1 for item in products if item.get("pack_count", 1) == 1)
    good_count = sum(1 for item in products if item.get("analysis", {}).get("is_good_for_bundle"))
    avg_reviews = round(mean(reviews), 1) if reviews else 0
    avg_price = round(mean(prices), 2) if prices else 0
    competition_level = "低到中竞争"
    if avg_reviews >= 3000:
        competition_level = "高竞争"
    elif avg_reviews >= 900:
        competition_level = "中等竞争"
    return {
        "total_results": total_results,
        "sample_size": len(products),
        "top10_avg_price": avg_price,
        "top10_avg_reviews": avg_reviews,
        "single_ratio": round(single_count / max(len(products), 1) * 100, 1),
        "bundle_candidate_count": good_count,
        "competition_level": competition_level,
        "estimated_cpc": "暂未接入 Amazon Ads 数据",
    }


def analyze_product_hunter(keyword: str, limit: int = 20) -> Dict:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("请输入关键词，例如 diamond wheel。")
    limit = min(max(int(limit or 20), 1), 20)
    payload = _collect_first_products(keyword, limit=limit)
    products = [_normalize_row(row) for row in payload["rows"]]

    provisional_summary = _summary(products, payload["total_results"])
    context = {
        "top10_avg_price": provisional_summary["top10_avg_price"],
        "top10_avg_reviews": provisional_summary["top10_avg_reviews"],
        "single_ratio": provisional_summary["single_ratio"],
    }
    analyzed = []
    for product in products:
        analysis = _score_product(product, keyword, context)
        analyzed.append({**product, "analysis": analysis})

    summary = _summary(analyzed, payload["total_results"])
    try:
        openai_result = _openai_enhance_products(keyword, analyzed, summary)
    except Exception as error:
        openai_result = {
            "mode": "local_rules",
            "error": f"OpenAI 增强分析失败，已使用本地规则评分：{error}",
            "merged": 0,
        }
    summary = _summary(analyzed, payload["total_results"])
    return {
        "keyword": keyword,
        "summary": summary,
        "products": analyzed,
        "ai_mode": openai_result.get("mode"),
        "openai_error": openai_result.get("error", ""),
        "openai_merged": openai_result.get("merged", 0),
        "notes": [
            "第一版 MVP 使用 SerpApi 搜索结果 + 规则评分，并会尝试用 OpenAI 一次性增强 20 个商品判断。",
            "机会评分用于筛选候选，不等于最终上架结论；上架前仍需人工确认专利、品牌、物流重量和供货成本。",
            "如 OpenAI 额度不足或网络失败，系统会自动回退本地规则，保证表格仍可输出。",
        ],
    }
