#!/usr/bin/env python3

import json
import os
import re
from statistics import mean
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from serpapi_amazon import (
    SerpApiAmazonError,
    extract_seller_info,
    load_dotenv,
    request_serpapi_json,
    search_amazon_page,
    to_text,
)


PACK_PATTERN = re.compile(r"\b(\d+)\s*(?:pcs?|pieces?|pack|packs|count|ct)\b", re.I)
BRAND_PATTERN = re.compile(r"^([A-Z][A-Za-z0-9&+\-]{1,24})\b")
MAX_DETAIL_LOOKUPS = int(os.environ.get("AI_OPPORTUNITY_DETAIL_LOOKUPS", "6"))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def to_number(value) -> float:
    if value is None:
        return 0
    text = str(value).replace(",", "").replace("$", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0


def infer_brand(title: str) -> str:
    match = BRAND_PATTERN.search(title or "")
    if not match:
        return ""
    candidate = match.group(1).strip("- ")
    blocked = {"the", "for", "and", "with", "diamond", "amazon", "cbn"}
    return "" if candidate.lower() in blocked else candidate


def detect_pack_count(title: str) -> int:
    match = PACK_PATTERN.search(title or "")
    if not match:
        return 1
    try:
        return max(int(match.group(1)), 1)
    except ValueError:
        return 1



def first_text(*values) -> str:
    for value in values:
        text = to_text(value)
        if text:
            return text
    return ""


def find_nested_value(data, keys) -> str:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = str(key).lower().replace("_", "").replace("-", "")
            if normalized_key in keys:
                text = to_text(value)
                if text and not isinstance(value, (dict, list)):
                    return text
            found = find_nested_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_nested_value(item, keys)
            if found:
                return found
    return ""


def extract_seller_id(payload: Dict) -> str:
    explicit = find_nested_value(payload, {"sellerid", "merchantid", "merchant"})
    if explicit:
        return explicit
    text = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"(?:seller|me)=([A-Z0-9]{8,24})", text)
    return match.group(1) if match else ""


def extract_bsr(payload: Dict) -> str:
    product = payload.get("product_results") or {}
    information = product.get("product_information") or payload.get("product_information") or {}
    direct = first_text(
        product.get("best_sellers_rank"),
        product.get("best_seller_rank"),
        information.get("Best Sellers Rank") if isinstance(information, dict) else "",
        information.get("Best Seller Rank") if isinstance(information, dict) else "",
    )
    if direct:
        return direct
    return find_nested_value(payload, {"bestsellersrank", "bestsellerrank", "salesrank"})


def count_variants(payload: Dict) -> int:
    product = payload.get("product_results") or {}
    candidates = [
        product.get("variants"),
        product.get("variations"),
        payload.get("variants"),
        payload.get("variations"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return len(candidate)
        if isinstance(candidate, dict):
            return sum(len(value) if isinstance(value, list) else 1 for value in candidate.values())
    return 0


def normalize_category(value) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text = to_text(item.get("name") or item.get("title"))
            else:
                text = to_text(item)
            if text:
                parts.append(text)
        return " > ".join(parts)
    return to_text(value)


def fetch_product_detail_info(
    asin: str,
    amazon_domain: str = "amazon.com",
    language: str = "en_US",
    device: str = "desktop",
) -> Dict:
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
    product = payload.get("product_results") or {}
    details = extract_seller_info(payload)
    category = normalize_category(product.get("categories") or product.get("category"))
    return {
        **details,
        "brand": first_text(product.get("brand"), product.get("manufacturer")),
        "seller_id": extract_seller_id(payload),
        "bsr": extract_bsr(payload),
        "variant_count": count_variants(payload),
        "category": category,
    }



def fetch_first_search_rows(keyword: str, limit: int = 50) -> Dict:
    rows: List[Dict] = []
    seen_asins = set()
    total_results = 0
    has_next = False
    for page in range(1, 6):
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
        has_next = payload.get("has_next", False)
        before_count = len(rows)
        for row in payload.get("rows", []):
            asin = row.get("asin")
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)
            rows.append(row)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
        if not has_next and len(rows) == before_count:
            break
    return {
        "rows": rows[:limit],
        "total_results": total_results or len(rows),
    }


def normalize_products(rows: List[Dict]) -> List[Dict]:
    products = []
    for row in rows:
        title = to_text(row.get("title"))
        pack_count = detect_pack_count(title)
        products.append(
            {
                "asin": to_text(row.get("asin")),
                "title": title,
                "price": to_number(row.get("price")),
                "rating": to_number(row.get("rating")),
                "reviews": int(to_number(row.get("reviews"))),
                "brand": to_text(row.get("brand")) or infer_brand(title),
                "seller_name": to_text(row.get("seller")),
                "seller_id": to_text(row.get("seller_id")),
                "is_prime": to_text(row.get("is_prime")) == "Yes",
                "bsr": to_text(row.get("bsr")),
                "variant_count": int(to_number(row.get("variant_count"))),
                "pack_count": pack_count,
                "has_multipack": pack_count > 1,
                "image_url": to_text(row.get("image_url")),
                "category": to_text(row.get("category")),
                "product_url": to_text(row.get("product_url")),
                "sales": to_text(row.get("sales")),
            }
        )
    return products


def compute_competition(products: List[Dict]) -> Dict:
    top10 = products[:10]
    prices = [item["price"] for item in top10 if item["price"] > 0]
    reviews = [item["reviews"] for item in top10]
    brands = [item["brand"].lower() for item in top10 if item["brand"]]
    titles = [item["title"].lower() for item in top10]

    avg_reviews = round(mean(reviews), 1) if reviews else 0
    avg_price = round(mean(prices), 2) if prices else 0
    review_pressure = min(avg_reviews / 1500, 1) * 32
    brand_share = 0
    if brands:
        brand_share = max(brands.count(brand) for brand in set(brands)) / len(brands)
    brand_pressure = brand_share * 18
    price_spread = 0
    if len(prices) >= 2 and avg_price:
        price_spread = (max(prices) - min(prices)) / avg_price
    price_war_pressure = max(0, min((0.45 - price_spread) / 0.45, 1)) * 18
    similar_terms = ["diamond", "grinding", "wheel", "bit", "cbn", "glass", "disc"]
    similarity = 0
    if titles:
        similarity = mean(sum(1 for term in similar_terms if term in title) for title in titles) / len(similar_terms)
    similarity_pressure = similarity * 18
    ad_pressure = min(sum(1 for item in products if item.get("category") == "Sponsored") / max(len(products), 1), 1) * 14

    score = round(min(review_pressure + brand_pressure + price_war_pressure + similarity_pressure + ad_pressure, 100))
    if score >= 70:
        level = "高竞争"
        suitable_new_seller = "不建议新卖家直接硬刚"
    elif score >= 45:
        level = "中等竞争"
        suitable_new_seller = "适合用差异化小批量测试"
    else:
        level = "低到中竞争"
        suitable_new_seller = "适合新卖家观察进入"

    return {
        "score": score,
        "level": level,
        "suitable_new_seller": suitable_new_seller,
        "suitable_fbm_test": "适合 FBM 小批量测款" if score < 75 else "FBM 可测，但需要强差异化",
        "top10_avg_reviews": avg_reviews,
        "top10_avg_price": avg_price,
        "signals": {
            "review_pressure": round(review_pressure, 1),
            "brand_pressure": round(brand_pressure, 1),
            "price_war_pressure": round(price_war_pressure, 1),
            "similar_listing_pressure": round(similarity_pressure, 1),
            "ad_pressure": round(ad_pressure, 1),
        },
    }


def compute_bundle_opportunity(products: List[Dict]) -> Dict:
    total = len(products) or 1
    single_count = sum(1 for item in products if item["pack_count"] == 1)
    pack_counts = {}
    for item in products:
        pack_counts[str(item["pack_count"])] = pack_counts.get(str(item["pack_count"]), 0) + 1
    single_ratio = round(single_count / total * 100, 1)
    has_gap = single_ratio >= 65 and sum(1 for item in products if item["pack_count"] in {3, 5, 10}) <= max(3, total * 0.18)
    recommended = [3, 5, 10] if has_gap else [3, 5]
    reasons = [
        "工业/耗材属性明显，用户存在复购或备货需求",
        "多件装能降低用户单件采购成本",
        "组合装可与同质化单件 Listing 做差异化",
    ]
    if has_gap:
        reasons.insert(0, f"当前样本约 {single_ratio}% 为单件或未标注组合，Bundle 空白较明显")
    return {
        "single_ratio": single_ratio,
        "pack_distribution": pack_counts,
        "has_bundle_gap": has_gap,
        "recommended_bundles": recommended,
        "reasons": reasons,
    }


def compute_profit(products: List[Dict]) -> Dict:
    prices = [item["price"] for item in products[:10] if item["price"] > 0]
    base_price = mean(prices) if prices else 19.99
    purchase_cost = round(base_price * 0.28, 2)
    fba_fee = round(max(3.8, base_price * 0.18), 2)
    ad_rate = 0.12
    bundles = [1, 3, 5, 10]
    rows = []
    for count in bundles:
        price = round(base_price * count * (0.92 if count > 1 else 1), 2)
        cost = purchase_cost * count
        fee = fba_fee + max(0, count - 1) * 0.65
        ad = price * ad_rate
        profit = price - cost - fee - ad
        margin = profit / price * 100 if price else 0
        rows.append(
            {
                "bundle": f"{count}pcs" if count > 1 else "1pc",
                "price": round(price, 2),
                "estimated_cost": round(cost, 2),
                "estimated_fee": round(fee, 2),
                "estimated_ads": round(ad, 2),
                "profit": round(profit, 2),
                "margin": round(margin, 1),
            }
        )
    best = max(rows, key=lambda item: item["profit"])
    return {
        "assumptions": {
            "base_price": round(base_price, 2),
            "purchase_cost_estimate": purchase_cost,
            "fba_or_fbm_fee_estimate": fba_fee,
            "ad_rate_estimate": "12%",
        },
        "rows": rows,
        "best_bundle": best,
    }


def local_ai_report(keyword: str, products: List[Dict], competition: Dict, bundle: Dict, profit: Dict) -> Dict:
    opportunity_score = max(0, min(100, round((100 - competition["score"]) * 0.52 + (18 if bundle["has_bundle_gap"] else 6) + (profit["best_bundle"]["margin"] * 0.35))))
    should_enter = opportunity_score >= 58 and competition["score"] < 78
    return {
        "opportunity_score": opportunity_score,
        "competition_level": competition["level"],
        "recommend_enter": "建议进入，但以组合装/小批量测试切入" if should_enter else "谨慎进入，先做小样本验证",
        "recommended_playbook": [
            "优先做 3pcs/5pcs 组合装测试，避免直接复制单件低价 Listing",
            "标题和主图突出规格、适配场景、工业耗材属性",
            "先 FBM 或小批量 FBA 测款，确认转化后再放量",
            "记录差评关键词，后续可扩展 Review AI 分析优化 Listing",
        ],
        "price_strategy": f"以 Top10 均价 ${competition['top10_avg_price']} 为锚点，组合装按单件价 8%~12% 折扣呈现更划算。",
        "bulk_sales_fit": "适合做批量销售/组合装" if bundle["has_bundle_gap"] else "可测试组合装，但需先验证市场接受度",
        "summary": f"{keyword} 当前竞争为 {competition['level']}，Top10 平均评论 {competition['top10_avg_reviews']}，Top10 平均价格 ${competition['top10_avg_price']}。{'存在 Bundle 空白市场。' if bundle['has_bundle_gap'] else '组合机会不算明显，但仍可通过规格/数量差异化测试。'}",
    }



def extract_openai_text(payload: Dict) -> str:
    direct = to_text(payload.get("output_text"))
    if direct:
        return direct

    chunks = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text") if isinstance(content, dict) else ""
            if isinstance(text, dict):
                text = text.get("value") or text.get("text")
            if text:
                chunks.append(to_text(text))
    return "\n".join(chunk for chunk in chunks if chunk)


def readable_openai_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        detail = error.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(detail)
            message = (payload.get("error") or {}).get("message") or detail
            code = (payload.get("error") or {}).get("code") or ""
        except json.JSONDecodeError:
            message = detail or str(error)
            code = ""
        if error.code == 429 or code == "insufficient_quota":
            return "OpenAI 额度不足或账单未启用，已自动降级为本地规则分析。"
        return f"OpenAI HTTP {error.code}: {message[:220]}"
    if isinstance(error, URLError):
        return f"OpenAI 网络连接失败：{error.reason}"
    if isinstance(error, TimeoutError):
        return "OpenAI 请求超时，已自动降级为本地规则分析。"
    if isinstance(error, json.JSONDecodeError):
        return "OpenAI 返回内容不是有效 JSON。"
    return str(error)


def openai_enhance_report(keyword: str, products: List[Dict], base_report: Dict) -> Dict[str, str]:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"text": "", "error": "未配置 OPENAI_API_KEY，当前使用本地规则分析。"}
    prompt = {
        "keyword": keyword,
        "products_sample": products[:20],
        "base_report": base_report,
    }
    instruction = (
        "你是一个务实的 Amazon 跨境选品分析师。请基于 SERP 数据生成中文报告，"
        "重点判断竞争、Bundle 机会、利润策略、新卖家打法和风险。"
        "不要夸大结论；如果字段缺失，请明确说明是假设。"
    )
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            "input": [
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": "请输出结构化中文报告，包含：结论、竞争判断、Bundle机会、利润建议、进入打法、风险提醒。\n"
                    + json.dumps(prompt, ensure_ascii=False),
                },
            ],
            "max_output_tokens": 1200,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"text": "", "error": readable_openai_error(error)}
    return {"text": extract_openai_text(payload), "error": ""}


def analyze_ai_opportunity(keyword: str) -> Dict:
    if not keyword.strip():
        raise ValueError("请输入 Amazon 关键词。")
    page_payload = fetch_first_search_rows(keyword=keyword, limit=50)
    rows = page_payload["rows"]
    # Seller/Product detail lookups are expensive; analyze top rows first, keep all 50 SERP rows.
    detail_rows = []
    for row in rows[:MAX_DETAIL_LOOKUPS]:
        try:
            detail_info = fetch_product_detail_info(
                row.get("asin", ""),
                amazon_domain="amazon.com",
                language="en_US",
                device="desktop",
            )
        except SerpApiAmazonError as error:
            detail_info = {"seller_match_basis": f"detail lookup failed: {error}"}
        detail_rows.append({**row, **detail_info})
    rows = detail_rows + rows[MAX_DETAIL_LOOKUPS:]
    products = normalize_products(rows)
    competition = compute_competition(products)
    bundle = compute_bundle_opportunity(products)
    profit = compute_profit(products)
    report = local_ai_report(keyword, products, competition, bundle, profit)
    openai_result = openai_enhance_report(keyword, products, {"competition": competition, "bundle": bundle, "profit": profit, "report": report})
    enhanced = openai_result.get("text", "")
    return {
        "keyword": keyword,
        "total_results": page_payload.get("total_results", 0),
        "products": products,
        "competition": competition,
        "bundle": bundle,
        "profit": profit,
        "report": report,
        "openai_report": enhanced,
        "openai_error": openai_result.get("error", ""),
        "ai_mode": "openai" if enhanced else "local_rules",
        "notes": [
            f"前 {len(products)} 个 SERP 商品参与分析。",
            f"卖家详情默认补充前 {min(MAX_DETAIL_LOOKUPS, len(products))} 个商品，避免 SerpApi 次数消耗过高。",
            "BSR、变体数量、Seller ID 取决于 SerpApi 当前返回字段；未返回时会显示为空。",
        ],
    }
