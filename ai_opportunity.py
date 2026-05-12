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
CONSUMABLE_TERMS = {
    "abrasive", "sandpaper", "sanding", "disc", "disk", "wheel", "grinding",
    "cutting", "blade", "bit", "pad", "belt", "filter", "bag", "glove",
    "needle", "nozzle", "tip", "brush", "roll", "refill", "replacement",
    "cartridge", "paper", "tape", "screw", "bolt", "nut", "insert", "strip",
}
REPEAT_TERMS = {
    "abrasive", "sandpaper", "sanding", "grinding", "cutting", "disc", "disk",
    "wheel", "blade", "filter", "glove", "bag", "refill", "replacement",
    "disposable", "consumable", "industrial", "shop", "workshop", "contractor",
}
FBM_FRIENDLY_TERMS = {
    "disc", "disk", "wheel", "bit", "pad", "blade", "filter", "bag", "glove",
    "screw", "bolt", "nut", "small", "mini", "replacement", "refill",
}
FBM_RISK_TERMS = {
    "machine", "bench", "table", "stand", "cabinet", "liquid", "chemical",
    "spray", "battery", "oversize", "heavy", "fragile", "ceramic",
}


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



def text_terms(*values: str) -> set:
    text = " ".join(to_text(value).lower() for value in values if value)
    return set(re.findall(r"[a-z0-9]+", text))


def has_any_term(terms: set, keywords: set) -> bool:
    return bool(terms & keywords)


def compute_candidate_score(product: Dict, keyword_terms: set) -> Dict:
    terms = text_terms(product.get("title"), product.get("category"), product.get("sales"))
    score = 0
    reasons = []

    if keyword_terms and len(keyword_terms & terms) >= max(1, min(2, len(keyword_terms))):
        score += 18
        reasons.append("标题与关键词匹配度较高")
    if product.get("pack_count", 1) == 1:
        score += 18
        reasons.append("当前是单件装，适合改造成多件装测试")
    elif product.get("pack_count") in {2, 3, 4, 5, 10}:
        score += 10
        reasons.append("市场已出现多件装，可作为数量和定价参考")
    if product.get("price", 0) > 0:
        score += 10
        reasons.append("有明确售价，可做组合装价格锚点")
    if 0 < product.get("price", 0) <= 45:
        score += 12
        reasons.append("单价适合用 3/5/10pcs 拉高客单价")
    if product.get("rating", 0) >= 4:
        score += 8
        reasons.append("评分不低，说明基础需求可验证")
    if 10 <= product.get("reviews", 0) <= 1500:
        score += 12
        reasons.append("评论量有需求信号，但不是完全不可追")
    elif product.get("reviews", 0) > 1500:
        score += 4
        reasons.append("评论量较高，只适合作为竞品参考")
    if has_any_term(terms, CONSUMABLE_TERMS):
        score += 14
        reasons.append("标题包含耗材/替换件属性")
    if product.get("is_prime"):
        score += 4
        reasons.append("Prime 竞品存在，说明用户对配送速度敏感")

    return {
        "score": min(score, 100),
        "reasons": reasons[:4],
    }


def compute_bulk_strategy(keyword: str, products: List[Dict], competition: Dict, bundle: Dict, profit: Dict) -> Dict:
    keyword_terms = text_terms(keyword)
    all_terms = text_terms(keyword, *(item.get("title", "") for item in products[:30]))
    total = len(products) or 1
    avg_price = competition.get("top10_avg_price") or profit.get("assumptions", {}).get("base_price") or 0
    prices = [item["price"] for item in products[:20] if item.get("price", 0) > 0]
    multipack_products = [item for item in products if item.get("pack_count", 1) > 1]
    single_products = [item for item in products if item.get("pack_count", 1) == 1]

    consumable_hits = sorted(all_terms & CONSUMABLE_TERMS)
    repeat_hits = sorted(all_terms & REPEAT_TERMS)
    fbm_friendly_hits = sorted(all_terms & FBM_FRIENDLY_TERMS)
    fbm_risk_hits = sorted(all_terms & FBM_RISK_TERMS)

    consumable_score = min(100, 28 + len(consumable_hits) * 12 + (10 if bundle.get("has_bundle_gap") else 0)) if consumable_hits else 22
    repeat_score = min(100, 20 + len(repeat_hits) * 10 + min(len(multipack_products) * 4, 20)) if repeat_hits else 28
    fbm_score = 52
    if fbm_friendly_hits:
        fbm_score += min(len(fbm_friendly_hits) * 8, 28)
    if avg_price and avg_price <= 50:
        fbm_score += 10
    if fbm_risk_hits:
        fbm_score -= min(len(fbm_risk_hits) * 12, 36)
    fbm_score = max(0, min(100, fbm_score))
    market_gap_score = min(100, int(bundle.get("single_ratio", 0)) + (12 if bundle.get("has_bundle_gap") else 0) - min(len(multipack_products) * 2, 18))
    competition_fit = max(0, 100 - competition.get("score", 0))
    bulk_score = round(consumable_score * 0.26 + repeat_score * 0.22 + fbm_score * 0.2 + market_gap_score * 0.2 + competition_fit * 0.12)

    blockers = []
    if consumable_score < 45:
        blockers.append("耗材属性不明显，用户未必有多件购买动机")
    if repeat_score < 45:
        blockers.append("复购信号偏弱，多 PCS 可能只是库存压力而不是需求")
    if fbm_score < 45:
        blockers.append("FBM 友好度偏低，可能存在重量、易碎、液体/化学品或大件风险")
    if competition.get("score", 0) >= 78:
        blockers.append("竞争评分过高，新卖家直接测试容易被大评论竞品压制")
    if prices and min(prices) < avg_price * 0.48:
        blockers.append("价格带差异较大，存在低价竞品压价风险")

    candidate_rows = []
    for item in products:
        score_info = compute_candidate_score(item, keyword_terms)
        if score_info["score"] < 42:
            continue
        candidate_rows.append(
            {
                "asin": item.get("asin"),
                "title": item.get("title"),
                "price": item.get("price"),
                "rating": item.get("rating"),
                "reviews": item.get("reviews"),
                "brand": item.get("brand"),
                "seller_name": item.get("seller_name"),
                "product_url": item.get("product_url"),
                "image_url": item.get("image_url"),
                "pack_count": item.get("pack_count"),
                "score": score_info["score"],
                "reasons": score_info["reasons"],
            }
        )
    candidate_rows.sort(key=lambda item: item["score"], reverse=True)

    recommended_packs = build_pack_recommendations(avg_price or 19.99, source="keyword")

    is_suitable = bulk_score >= 58 and len(blockers) <= 2
    if bulk_score >= 72 and not blockers:
        decision = "适合优先测试多 PCS 组合装"
    elif is_suitable:
        decision = "可以小批量手工上架测试"
    else:
        decision = "暂不建议做多 PCS，先验证单件或换关键词"

    positive_reasons = []
    if consumable_hits:
        positive_reasons.append(f"耗材/替换件词明显：{', '.join(consumable_hits[:6])}")
    if repeat_hits:
        positive_reasons.append(f"存在复购场景信号：{', '.join(repeat_hits[:6])}")
    if bundle.get("single_ratio", 0) >= 55:
        positive_reasons.append(f"当前样本约 {bundle.get('single_ratio')}% 是单件或未标注组合，仍有组合装差异化空间")
    if competition.get("score", 0) < 60:
        positive_reasons.append("竞争评分未到高压区，适合用 FBM/小批量快速试错")
    if fbm_score >= 58:
        positive_reasons.append("产品形态初步判断对 FBM 友好，可先手工上架测需求")

    next_steps = [
        "先挑 3-5 个候选 ASIN 做标题、主图、规格和价格对照",
        "手工上架 3pcs 和 5pcs 两个变体或独立 Listing，先不大批量备货",
        "主图明确展示数量和使用场景，标题加入 Pack/Count/Pieces 等数量词",
        "用 FBM 测 7-14 天点击、加购和转化，再决定是否扩展 10pcs 或转 FBA",
    ]

    return {
        "score": bulk_score,
        "decision": decision,
        "is_suitable": is_suitable,
        "is_consumable": consumable_score >= 55,
        "repeat_purchase_fit": repeat_score >= 55,
        "fbm_fit": fbm_score >= 55,
        "consumable_score": round(consumable_score),
        "repeat_score": round(repeat_score),
        "fbm_score": round(fbm_score),
        "market_gap_score": round(market_gap_score),
        "positive_reasons": positive_reasons or ["暂未发现足够强的批量销售正向信号"],
        "blockers": blockers,
        "recommended_packs": recommended_packs if is_suitable else [],
        "candidate_asins": candidate_rows[:12] if is_suitable else [],
        "single_count": len(single_products),
        "multipack_count": len(multipack_products),
        "next_steps": next_steps if is_suitable else ["建议先换更明确的耗材关键词，或先用单件低成本验证需求"],
    }



def build_pack_recommendations(base_price: float, source: str = "product") -> List[Dict]:
    base_price = base_price or 19.99
    pack_rules = [
        (3, 0.94, "低门槛测试，先验证点击和转化"),
        (5, 0.90, "兼顾折扣感和客单价，适合耗材复购"),
        (10, 0.84, "面向工厂/工作室/高频用户，客单价更高但转化门槛也更高"),
    ]
    rows = []
    for count, discount, logic in pack_rules:
        rows.append(
            {
                "pack": f"{count}pcs",
                "target_price": round(base_price * count * discount, 2),
                "unit_price": round(base_price * discount, 2),
                "discount_vs_single": f"约 {round((1 - discount) * 100)}% 单件折扣",
                "logic": logic,
                "price_basis": "按该 ASIN 当前单件价估算" if source == "product" else "按 Top10 均价估算",
            }
        )
    return rows


def analyze_product_bundle_fit(product: Dict, keyword: str, context: Dict) -> Dict:
    keyword_terms = text_terms(keyword)
    product_terms = text_terms(product.get("title"), product.get("category"), product.get("sales"))
    score_info = compute_candidate_score(product, keyword_terms)
    score = score_info["score"]
    reasons = list(score_info["reasons"])
    blockers = []
    price = product.get("price", 0)
    pack_count = product.get("pack_count", 1)
    context_consumable = bool(context.get("is_consumable"))
    context_repeat = bool(context.get("repeat_purchase_fit"))
    context_fbm = bool(context.get("fbm_fit"))

    has_consumable_signal = has_any_term(product_terms, CONSUMABLE_TERMS) or context_consumable
    has_repeat_signal = has_any_term(product_terms, REPEAT_TERMS) or context_repeat
    has_fbm_risk = has_any_term(product_terms, FBM_RISK_TERMS)

    if pack_count > 1:
        blockers.append(f"当前标题已显示 {pack_count}pcs/pack，优先作为竞品参考，不是单件改多件的第一候选")
    if not price:
        blockers.append("缺少价格，无法估算 3/5/10pcs 的合理售价")
    elif price > 65:
        blockers.append("单价偏高，多件装客单价会过高，FBM 测试转化门槛较大")
    if not has_consumable_signal:
        blockers.append("耗材/替换件属性不明显，多件购买动机不足")
    if not has_repeat_signal:
        blockers.append("复购场景信号不足，可能不适合直接做多件装")
    if has_fbm_risk and not context_fbm:
        blockers.append("标题含大件/易碎/液体/化学品等风险词，FBM 需谨慎")
    if product.get("reviews", 0) > 2500:
        blockers.append("该竞品评论量很高，直接对标难度较大")

    can_bundle = score >= 68 and not blockers and pack_count == 1
    if can_bundle:
        label = "可以做多PCS"
        status = "yes"
        summary = "适合拿来做 3pcs/5pcs/10pcs 手工上架测试。"
    elif pack_count > 1 and score >= 55:
        label = "已有多件装参考"
        status = "reference"
        summary = "它本身已是多件装，更适合参考数量、标题和价格，不建议当作单件改造对象。"
    else:
        label = "不建议"
        status = "no"
        summary = blockers[0] if blockers else "当前信号不足，不建议优先做多 PCS。"

    test_plan = [
        "先手工创建 3pcs 和 5pcs 两个测试款，10pcs 等有点击/加购后再上",
        "标题加入 Pack / Pieces / Count，并把数量放在主图可见位置",
        "价格按单件价给 6%-10% 阶梯折扣，避免一开始利润被打穿",
        "用 FBM 小批量测 7-14 天，看点击、加购、转化和买家问题",
    ]

    return {
        "status": status,
        "label": label,
        "can_bundle": can_bundle,
        "score": min(score, 100),
        "summary": summary,
        "reasons": reasons,
        "blockers": blockers,
        "recommended_packs": build_pack_recommendations(price, source="product") if can_bundle else [],
        "test_plan": test_plan if can_bundle else [],
        "context": {
            "keyword_competition": context.get("competition_level"),
            "top10_avg_price": context.get("top10_avg_price"),
            "top10_avg_reviews": context.get("top10_avg_reviews"),
            "single_ratio": context.get("single_ratio"),
            "estimated_cpc": context.get("estimated_cpc"),
        },
    }


def apply_product_bundle_analysis(keyword: str, products: List[Dict], competition: Dict, bundle: Dict, bulk_strategy: Dict) -> List[Dict]:
    context = {
        "is_consumable": bulk_strategy.get("is_consumable"),
        "repeat_purchase_fit": bulk_strategy.get("repeat_purchase_fit"),
        "fbm_fit": bulk_strategy.get("fbm_fit"),
        "competition_level": competition.get("level"),
        "top10_avg_price": competition.get("top10_avg_price"),
        "top10_avg_reviews": competition.get("top10_avg_reviews"),
        "single_ratio": bundle.get("single_ratio"),
        "estimated_cpc": "暂未接入 Amazon Ads 数据",
    }
    analyzed = []
    for product in products:
        analyzed.append({**product, "bundle_fit": analyze_product_bundle_fit(product, keyword, context)})
    return analyzed


def compute_keyword_metrics(page_payload: Dict, products: List[Dict], competition: Dict, bundle: Dict) -> Dict:
    viable_count = sum(1 for item in products if (item.get("bundle_fit") or {}).get("can_bundle"))
    reference_count = sum(1 for item in products if (item.get("bundle_fit") or {}).get("status") == "reference")
    return {
        "total_results": page_payload.get("total_results", 0),
        "sample_size": len(products),
        "competition_score": competition.get("score", 0),
        "competition_level": competition.get("level", ""),
        "top10_avg_price": competition.get("top10_avg_price", 0),
        "top10_avg_reviews": competition.get("top10_avg_reviews", 0),
        "single_ratio": bundle.get("single_ratio", 0),
        "viable_bundle_count": viable_count,
        "reference_bundle_count": reference_count,
        "estimated_cpc": "暂未接入 Amazon Ads 数据",
        "cpc_note": "SerpApi Amazon Search 不直接返回 CPC；后续可接 Amazon Ads 或第三方关键词库。",
    }



def product_from_params(params: Dict) -> Dict:
    title = to_text(params.get("title"))
    return {
        "asin": to_text(params.get("asin")),
        "title": title,
        "price": to_number(params.get("price")),
        "rating": to_number(params.get("rating")),
        "reviews": int(to_number(params.get("reviews"))),
        "brand": to_text(params.get("brand")) or infer_brand(title),
        "seller_name": to_text(params.get("seller_name")),
        "product_url": to_text(params.get("product_url")),
        "image_url": to_text(params.get("image_url")),
        "pack_count": int(to_number(params.get("pack_count"))) or detect_pack_count(title),
        "category": to_text(params.get("category")),
    }


def compact_query_terms(title: str, keyword: str) -> str:
    terms = [term for term in re.findall(r"[a-z0-9]+", f"{keyword} {title}".lower()) if len(term) > 2]
    blocked = {"with", "for", "the", "and", "inch", "pack", "pcs", "piece", "pieces", "grit", "brand", "store"}
    picked = []
    for term in terms:
        if term in blocked or term in picked:
            continue
        picked.append(term)
        if len(picked) >= 4:
            break
    return " ".join(picked) or keyword or title[:50]


def accessory_terms_for_product(title: str, keyword: str) -> List[str]:
    terms = text_terms(title, keyword)
    suggestions = []
    if terms & {"grinding", "wheel", "disc", "disk", "diamond", "abrasive"}:
        suggestions.extend(["arbor adapter", "backing pad", "mandrel", "flange nut", "spanner wrench", "storage case"])
    if terms & {"sanding", "polishing", "pad"}:
        suggestions.extend(["hook loop backing pad", "sanding pad holder", "buffing pad", "storage pouch"])
    if terms & {"drill", "bit", "hole"}:
        suggestions.extend(["drill bit case", "mandrel set", "chuck adapter", "depth stop collar"])
    if terms & {"blade", "cutting"}:
        suggestions.extend(["blade storage case", "arbor bushing", "cut resistant gloves", "marker pencil"])
    suggestions.extend(["storage case", "adapter", "gloves"])

    unique = []
    for item in suggestions:
        if item not in unique:
            unique.append(item)
    return unique[:6]


def search_accessory_products(keyword: str, product: Dict, limit: int = 6) -> List[Dict]:
    base_query = compact_query_terms(product.get("title", ""), keyword)
    accessories = []
    seen = set()
    strong_accessory_terms = {
        "adapter", "adapters", "adaptor", "adaptors", "backing", "mandrel",
        "flange", "nut", "nuts", "spanner", "wrench", "case", "storage",
        "pouch", "holder", "glove", "gloves", "bushing", "bushings",
        "collar", "chuck",
    }
    for accessory in accessory_terms_for_product(product.get("title", ""), keyword)[:6]:
        query = f"{base_query} {accessory}"
        accessory_terms = text_terms(accessory)
        try:
            payload = search_amazon_page(
                keyword=query,
                page=1,
                amazon_domain="amazon.com",
                language="en_US",
                sort="price-asc-rank",
                device="desktop",
                dc="true",
            )
        except SerpApiAmazonError:
            continue
        for row in payload.get("rows", []):
            asin = row.get("asin")
            price = to_number(row.get("price"))
            title_terms = text_terms(row.get("title"))
            if not asin or asin in seen or not price or price > 25:
                continue
            if not (title_terms & accessory_terms):
                continue
            if not (title_terms & strong_accessory_terms):
                continue
            seen.add(asin)
            accessories.append(
                {
                    "asin": asin,
                    "title": row.get("title"),
                    "price": price,
                    "rating": to_number(row.get("rating")),
                    "reviews": int(to_number(row.get("reviews"))),
                    "image_url": row.get("image_url"),
                    "product_url": row.get("product_url"),
                    "query": query,
                    "why": "低价、小件、适合作为赠品或套装配件参考",
                }
            )
            if len(accessories) >= limit:
                return accessories
    return accessories


def scenario_bundle_idea(product: Dict, keyword: str) -> Dict:
    terms = text_terms(product.get("title"), keyword)
    price = product.get("price") or 19.99
    if terms & {"grit", "sanding", "polishing", "pad"}:
        title = "规格阶梯组合"
        description = "用粗/中/细不同 grit 或不同规格做一个流程型套装，卖点是一次买齐从打磨到抛光。"
        includes = ["1 个主 ASIN 同类产品", "搭配不同 grit/规格", "附带收纳袋或标签贴"]
        target_price = round(price * 3.2, 2)
    elif terms & {"grinding", "wheel", "disc", "disk", "blade"}:
        title = "工位备货组合"
        description = "面向小工厂、维修店、工作室，一次购买多个常用耗材并附一个低价收纳/转接件。"
        includes = ["3-5 个主 ASIN 同类耗材", "1 个低价 adapter/backing pad/收纳件", "主图突出 Shop Pack / Workshop Pack"]
        target_price = round(price * 4.6, 2)
    else:
        title = "入门测试组合"
        description = "把主产品做成低门槛 starter kit，用轻小配件提升感知价值，先验证是否有人愿意买套装。"
        includes = ["2-3 个主 ASIN", "1 个低价相关配件", "小包装，适合 FBM 先测"]
        target_price = round(price * 3.0, 2)
    return {
        "type": "scenario",
        "title": title,
        "description": description,
        "includes": includes,
        "target_price": target_price,
        "reason": "不是单纯加数量，而是围绕使用场景提升客单价和差异化。",
    }


def build_bundle_plan(keyword: str, params: Dict) -> Dict:
    product = product_from_params(params)
    if not product.get("asin") or not product.get("title"):
        raise ValueError("缺少 ASIN 或标题，无法生成组合方案。")

    bundle_fit = analyze_product_bundle_fit(
        product,
        keyword,
        {
            "is_consumable": True,
            "repeat_purchase_fit": True,
            "fbm_fit": True,
            "competition_level": "按当前点击 ASIN 分析",
            "top10_avg_price": product.get("price"),
            "top10_avg_reviews": product.get("reviews"),
            "single_ratio": "",
            "estimated_cpc": "暂未接入 Amazon Ads 数据",
        },
    )
    quantity_plan = {
        "type": "quantity",
        "title": "按数量组合",
        "description": "直接把单件装改成 3pcs / 5pcs / 10pcs，适合先手工上架快速验证需求。",
        "packs": build_pack_recommendations(product.get("price") or 19.99, source="product"),
        "reason": "最容易执行，不需要找新配件；适合耗材、复购、小件产品先做 FBM 测试。",
    }

    accessories = search_accessory_products(keyword, product, limit=6)
    selected_accessories = accessories[:3]
    accessory_total = sum(item.get("price", 0) for item in selected_accessories[:1])
    accessory_plan = {
        "type": "accessory",
        "title": "按赠配件组合",
        "description": "主产品 + 低价小配件，重点选择便宜、轻、小、方便邮寄、不明显增加售后风险的东西。",
        "target_price": round((product.get("price") or 19.99) * 3 + accessory_total * 0.85, 2),
        "includes": ["3pcs 主产品", "1 个低价配件或收纳件", "主图展示配件但标题不要夸大功能"],
        "accessories": selected_accessories,
        "reason": "赠配件可以提升套装感知价值，比单纯低价更容易做差异化。",
    }

    scenario_plan = scenario_bundle_idea(product, keyword)
    return {
        "keyword": keyword,
        "product": product,
        "bundle_fit": bundle_fit,
        "plans": [quantity_plan, accessory_plan, scenario_plan],
        "accessory_candidates": accessories,
        "notes": [
            "这些方案用于手工创建新 ASIN 前的测试参考，不代表 Amazon 官方建议。",
            "配件来自 Amazon 搜索结果，优先筛选低价小件；实际上架前仍需确认兼容性、侵权和物流限制。",
        ],
    }


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


def local_ai_report(keyword: str, products: List[Dict], competition: Dict, bundle: Dict, profit: Dict, bulk_strategy: Dict) -> Dict:
    opportunity_score = max(0, min(100, round((100 - competition["score"]) * 0.34 + bulk_strategy["score"] * 0.42 + (profit["best_bundle"]["margin"] * 0.24))))
    should_enter = bulk_strategy["is_suitable"] and opportunity_score >= 58 and competition["score"] < 78
    return {
        "opportunity_score": opportunity_score,
        "competition_level": competition["level"],
        "recommend_enter": "建议进入：先手工上架多 PCS 做 FBM 测款" if should_enter else "暂不建议直接做多 PCS，先看下方原因",
        "recommended_playbook": bulk_strategy.get("next_steps", []),
        "price_strategy": f"以 Top10 均价 ${competition['top10_avg_price']} 为锚点，组合装按单件价 8%~12% 折扣呈现更划算。",
        "bulk_sales_fit": bulk_strategy["decision"],
        "summary": f"{keyword} 当前竞争为 {competition['level']}，Top10 平均评论 {competition['top10_avg_reviews']}，Top10 平均价格 ${competition['top10_avg_price']}。批量测款判断：{bulk_strategy['decision']}。",
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
        "你是一个务实的 Amazon 跨境选品和 FBM 测款顾问。请专注判断这个关键词产品"
        "是否适合做 3pcs/5pcs/10pcs 等多件装批量销售测试。"
        "必须说明是否耗材、是否复购、是否适合 FBM、若不适合给出具体理由；"
        "若适合，请结合竞品 ASIN 给出手工上架测试建议。不要夸大结论。"
    )
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            "input": [
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": "请输出结构化中文报告，包含：是否适合多PCS、耗材/复购/FBM判断、候选ASIN参考、3/5/10pcs建议、手工上架测试步骤、风险提醒。\n"
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
    bulk_strategy = compute_bulk_strategy(keyword, products, competition, bundle, profit)
    products = apply_product_bundle_analysis(keyword, products, competition, bundle, bulk_strategy)
    keyword_metrics = compute_keyword_metrics(page_payload, products, competition, bundle)
    report = local_ai_report(keyword, products, competition, bundle, profit, bulk_strategy)
    openai_result = openai_enhance_report(keyword, products, {"competition": competition, "bundle": bundle, "profit": profit, "bulk_strategy": bulk_strategy, "keyword_metrics": keyword_metrics, "report": report})
    enhanced = openai_result.get("text", "")
    return {
        "keyword": keyword,
        "total_results": page_payload.get("total_results", 0),
        "products": products,
        "keyword_metrics": keyword_metrics,
        "competition": competition,
        "bundle": bundle,
        "profit": profit,
        "bulk_strategy": bulk_strategy,
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
