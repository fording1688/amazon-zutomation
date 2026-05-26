#!/usr/bin/env python3

import argparse
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
import tempfile
from urllib.error import HTTPError, URLError
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, build_opener, ProxyHandler, urlopen

from ai_opportunity import analyze_ai_opportunity, build_bundle_plan
from amazon_reviews import fetch_asin_reviews
from amazon_scraper import AmazonScraperError, fetch_amazon_rows
from database import count_operation_logs, check_database_connection, ensure_operation_logs_table, log_operation
from market_gap import discover_market_gaps
from pdf_made_in_china import add_made_in_china_to_pdf
from product_hunter import analyze_product_hunter
from serpapi_amazon import SerpApiAmazonError, enrich_rows_with_seller_info, request_serpapi_json, search_display_page, to_text


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "sample_products.csv"
GENERATED_DIR = WEB_DIR / "generated"
IMAGE_PRODUCTION_JOBS_FILE = ROOT / "image_production_jobs.json"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_FACTORY_DIR = ROOT / "amazon-image-factory"
IMAGE_FACTORY_STORAGE_DIR = IMAGE_FACTORY_DIR / "storage" / "Amazon-Images"
IMAGE_FACTORY_VENV_PYTHON = IMAGE_FACTORY_DIR / ".venv" / "bin" / "python"
VIDEO_REMIX_DIR = ROOT / "video-remix-api"
VIDEO_REMIX_PORT = int(os.environ.get("VIDEO_REMIX_PORT", "8010"))
VIDEO_REMIX_PROCESS = None
VIDEO_REMIX_LOG = VIDEO_REMIX_DIR / "outputs" / "service.log"


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


def read_json_body(handler):
    content_length = int(handler.headers.get("Content-Length", "0") or 0)
    body = handler.rfile.read(content_length) if content_length else b"{}"
    try:
        return json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON 格式不正确：{error}") from error


def load_image_production_jobs():
    if not IMAGE_PRODUCTION_JOBS_FILE.exists():
        return []
    try:
        with IMAGE_PRODUCTION_JOBS_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_image_production_job(job):
    jobs = load_image_production_jobs()
    jobs.insert(0, job)
    with IMAGE_PRODUCTION_JOBS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(jobs[:80], handle, ensure_ascii=False, indent=2)


IMAGE_FACTORY_SLOT_FILES = {
    "01-main-image": "01-main-image.png",
    "02-whats-included": "02-whats-included.png",
    "03-key-features": "03-key-features.png",
    "04-how-to-use": "04-how-to-use.png",
    "05-size-spec": "05-size-spec.png",
    "06-lifestyle": "06-lifestyle.png",
    "07-brand-bulk-support": "07-brand-bulk-support.png",
    "a-plus-01-hero-banner": "A+/01-hero-banner.png",
    "a-plus-02-included-items": "A+/02-included-items.png",
    "a-plus-03-usage-steps": "A+/03-usage-steps.png",
    "a-plus-04-benefits": "A+/04-benefits.png",
    "a-plus-05-brand-story": "A+/05-brand-story.png",
    "01-hero-banner": "A+/01-hero-banner.png",
    "02-included-items": "A+/02-included-items.png",
    "03-usage-steps": "A+/03-usage-steps.png",
    "04-benefits": "A+/04-benefits.png",
    "05-brand-story": "A+/05-brand-story.png",
}

IMAGE_FACTORY_PROVIDER_STACK = {
    "text_planning": {
        "provider": "openrouter",
        "primary_model": "openai/gpt-4.1",
        "fallback_model": "anthropic/claude-3.5-sonnet",
        "purpose": "Generate Amazon image strategy, prompts, copy, and compliance rules.",
    },
    "image_generation": {
        "provider": "openrouter",
        "primary_model": "openai/gpt-image-2",
        "fallback_model": "openai/gpt-image-1",
        "purpose": "Generate product/lifestyle image assets; do not render long text.",
    },
    "image_editing": {
        "provider": "openrouter",
        "primary_model": "openai/image-edit",
        "fallback_model": "stability-ai-stable-image",
        "purpose": "Edit product images or compose product visuals when needed.",
    },
    "layout_generation": {
        "provider": "playwright",
        "primary_model": "html-css-renderer",
        "fallback_model": None,
        "purpose": "Render text-heavy Amazon secondary images and A+ modules from HTML/CSS templates.",
    },
    "image_processing": {
        "provider": "pillow",
        "primary_model": "pillow",
        "fallback_model": None,
        "purpose": "Crop, pad, compress, normalize, and archive images.",
    },
    "quality_check": {
        "provider": "openrouter",
        "primary_model": "openai/gpt-4.1",
        "fallback_model": "google/gemini-2.5-pro",
        "purpose": "Check product quantity, compliance, off-Amazon contact, logos, and spelling.",
    },
}

IMAGE_FACTORY_TEXT_RENDERING_POLICY = {
    "rule": "Do not rely on image generation models to render long text inside images.",
    "main_image": "No text is allowed.",
    "secondary_images": "Use HTML/CSS templates for text layers; image generation should produce only product or background visuals.",
    "a_plus": "Use HTML/CSS templates for text-heavy modules and compose product visuals into the layout.",
}


def image_factory_safe_sku(sku):
    safe = "".join(ch for ch in sku if ch.isalnum() or ch in {"-", "_", "."}).strip()
    if not safe:
        raise ValueError("SKU 不合法。")
    return safe


def image_factory_sku_dir(sku):
    path = IMAGE_FACTORY_STORAGE_DIR / image_factory_safe_sku(sku)
    path.mkdir(parents=True, exist_ok=True)
    (path / "A+").mkdir(exist_ok=True)
    return path


def image_factory_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def image_factory_read_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def image_factory_load_plan(sku):
    sku = str(sku or "").strip()
    if not sku:
        raise ValueError("sku 不能为空。")
    root = image_factory_sku_dir(sku)
    prompts_path = root / "prompts.json"
    if not prompts_path.exists():
        raise ValueError(f"没有找到 SKU {sku} 的 prompts.json。请先生成 Prompt 方案。")
    plan = image_factory_read_json(prompts_path)
    return {
        "ok": True,
        "sku": sku,
        "prompts_path": str(prompts_path),
        "folder_path": str(root),
        "plan": plan,
    }


def image_factory_hydrate_job(job):
    hydrated = dict(job)
    sku = hydrated.get("sku")
    factory_response = dict(hydrated.get("factory_response") or {})
    if sku and not factory_response.get("plan"):
        prompts_path = image_factory_sku_dir(sku) / "prompts.json"
        if prompts_path.exists():
            try:
                factory_response["sku"] = sku
                factory_response["prompts_path"] = str(prompts_path)
                factory_response["plan"] = image_factory_read_json(prompts_path)
            except (OSError, json.JSONDecodeError):
                pass
    hydrated["factory_response"] = factory_response
    return hydrated


def image_factory_status_path(sku):
    return image_factory_sku_dir(sku) / "status.json"


def image_factory_update_status(sku, values):
    path = image_factory_status_path(sku)
    status = image_factory_read_json(path)
    status.update(values)
    status.setdefault("sku", sku)
    status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    image_factory_write_json(path, status)
    return status


def image_factory_prompt_item(
    slot,
    file_name,
    title,
    prompt,
    copy=None,
    qc_rules=None,
    negative_prompt="",
    generation_method="image_model",
    provider_role="image_generation",
    layout_template=None,
):
    return {
        "slot": slot,
        "file_name": file_name,
        "title": title,
        "generation_method": generation_method,
        "provider_role": provider_role,
        "model_preference": IMAGE_FACTORY_PROVIDER_STACK.get(provider_role, {}),
        "layout_template": layout_template,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "copy": copy or [],
        "qc_rules": qc_rules or [],
    }


def image_factory_generate_prompts(product):
    sku = product["sku"]
    context = (
        f"Brand: {product['brand']}. SKU: {sku}. Product: {product['product_name']}. "
        f"Included items: {product['included_items']}. Material: {product.get('material') or 'not specified'}. "
        f"Size: {product.get('size') or 'not specified'}. Main keyword: {product['main_keyword']}. "
        f"Target buyer: {product.get('target_buyer') or 'Amazon buyers'}. "
        f"Price range: {product.get('price_range') or 'not specified'}. "
        f"Style: {product.get('image_style') or 'clean Amazon listing photography and infographic'}."
    )
    global_rules = [
        "Main image must use pure white background.",
        "Main image must not contain text, icons, badges, borders, packaging, hands, props, or lifestyle scene.",
        "Product quantity must exactly match included_items.",
        "No competitor logos.",
        "No website, email, phone number, QR code, social handle, or off-Amazon contact information.",
        "Secondary images and A+ modules may use text, but text must be short, accurate, and spelled correctly.",
        "Avoid unsupported claims and exaggerated terms such as best, No.1, guaranteed, official, FDA approved, or certified unless provided.",
    ]
    negative = "extra products, wrong quantity, competitor logo, website, email, phone number, QR code, social media handle, misspelled text, exaggerated claims, watermark, low resolution, blurry image"
    main_prompt = image_factory_prompt_item(
        "01-main-image",
        "01-main-image.png",
        "White Background Main Image",
        f"Create a 1500x1500 Amazon main image for {product['product_name']}. {context} Use a pure white #FFFFFF background. Show only the actual purchased contents exactly as listed in included items. Use realistic product photography, centered composition, clean lighting, natural product scale, sharp details. No text, no icon, no badge, no packaging, no hands, no props, no shadows that look like extra objects.",
        [],
        [*global_rules, "Main image canvas must be 1500x1500.", "Main image background must be pure white.", "Main image must contain no visible text."],
        negative + ", text, icon, badge, packaging, hands, props, lifestyle background",
        "image_model",
        "image_generation",
        None,
    )
    secondary_specs = [
        ("02-whats-included", "02-whats-included.png", "What's Included", ["What's Included", product["included_items"], "Ready for accurate Amazon listing display"], "Create a clean Amazon infographic showing the exact included items with simple labels and separated product callouts."),
        ("03-key-features", "03-key-features.png", "Key Features", ["Key Features", product.get("material") or "Durable material", "Built for consistent performance"], "Create a feature-focused Amazon secondary image with three clear callouts for material, build quality, and use value."),
        ("04-how-to-use", "04-how-to-use.png", "How To Use", ["How To Use", "1. Install", "2. Align", "3. Use safely"], "Create a simple step-by-step usage infographic with clean numbered sections and product-focused visuals."),
        ("05-size-spec", "05-size-spec.png", "Size Specification", ["Size Specification", product.get("size") or "Check actual listing size", "Confirm fit before purchase"], "Create a technical size-spec image with dimension arrows and clean readable specification labels."),
        ("06-lifestyle", "06-lifestyle.png", "Lifestyle Scene", ["Built for Work", product.get("target_buyer") or "For practical buyers", "Clean, reliable product presentation"], "Create a realistic lifestyle scene showing the product in an appropriate use environment without adding unsupported accessories."),
        ("07-brand-bulk-support", "07-brand-bulk-support.png", "Brand and Bulk Support", [product["brand"], "Bulk order support", "Consistent supply for business buyers"], "Create a professional brand support image for B2B buyers, clean industrial style, no external contact information."),
    ]
    secondary = [
        image_factory_prompt_item(
            slot,
            file_name,
            title,
            f"{instruction} {context} Create only product/background visual elements. Do not render long text inside the image model output. Text copy will be rendered separately with HTML/CSS. Approved text copy: {json.dumps(copy, ensure_ascii=False)}.",
            copy,
            [*global_rules, "Secondary image canvas must be 1500x1500.", "Visible text must match approved copy.", "No off-Amazon contact information."],
            negative,
            "html_css_layout",
            "layout_generation",
            "secondary-square.html",
        )
        for slot, file_name, title, copy, instruction in secondary_specs
    ]
    aplus_specs = [
        ("01-hero-banner", "01-hero-banner.png", "A+ Hero Banner", [product["brand"], product["product_name"], product["main_keyword"]], "Create a premium A+ hero banner visual with brand-led product presentation and concise headline area."),
        ("02-included-items", "02-included-items.png", "A+ Included Items Module", ["Package Contents", product["included_items"]], "Create an A+ module that clearly explains the package contents and quantity."),
        ("03-usage-steps", "03-usage-steps.png", "A+ Usage Steps Module", ["Simple Setup", "Use with care", "Check compatibility"], "Create an A+ usage steps module with structured visual steps."),
        ("04-benefits", "04-benefits.png", "A+ Benefits Module", ["Practical design", "Reliable material", "Clear fit information"], "Create an A+ benefits module that explains practical buyer value without exaggerated claims."),
        ("05-brand-story", "05-brand-story.png", "A+ Application and Brand Story Module", [product["brand"], "For business and practical users", "Focused on product consistency"], "Create an A+ application and brand story module with professional brand tone and product context."),
    ]
    aplus = [
        image_factory_prompt_item(
            slot,
            file_name,
            title,
            f"{instruction} {context} Create only product/background visual elements. Do not render long text inside the image model output. Text copy will be rendered separately with HTML/CSS. Approved text copy: {json.dumps(copy, ensure_ascii=False)}.",
            copy,
            [*global_rules, "No off-Amazon contact information.", "Visible text must be spelled correctly.", "Avoid exaggerated or unsupported claims."],
            negative,
            "html_css_layout",
            "layout_generation",
            "aplus-module.html",
        )
        for slot, file_name, title, copy, instruction in aplus_specs
    ]
    plan = {
        "sku": sku,
        "brand": product["brand"],
        "product_name": product["product_name"],
        "provider_stack": IMAGE_FACTORY_PROVIDER_STACK,
        "text_rendering_policy": IMAGE_FACTORY_TEXT_RENDERING_POLICY,
        "main_image_prompt": main_prompt,
        "secondary_images": secondary,
        "a_plus_modules": aplus,
        "global_compliance_rules": global_rules,
    }
    path = image_factory_sku_dir(sku) / "prompts.json"
    image_factory_write_json(path, plan)
    image_factory_update_status(sku, {"prompt_status": "generated"})
    return {"ok": True, "sku": sku, "prompts_path": str(path), "plan": plan}


def image_factory_process_upload(sku, slot, file_payload):
    if slot not in IMAGE_FACTORY_SLOT_FILES:
        raise ValueError(f"未知图片位置：{slot}")
    root = image_factory_sku_dir(sku)
    output_path = root / IMAGE_FACTORY_SLOT_FILES[slot]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = Path(file_payload.get("filename") or "image.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(file_payload.get("content") or b"")
        source_path = Path(temp.name)
    try:
        script = (
            "from PIL import Image, ImageOps\n"
            "from pathlib import Path\n"
            "src=Path(r'%s')\n"
            "dst=Path(r'%s')\n"
            "img=ImageOps.exif_transpose(Image.open(src)).convert('RGBA')\n"
            "img.thumbnail((1500,1500), Image.Resampling.LANCZOS)\n"
            "canvas=Image.new('RGBA',(1500,1500),(255,255,255,255))\n"
            "canvas.alpha_composite(img,((1500-img.width)//2,(1500-img.height)//2))\n"
            "dst.parent.mkdir(parents=True, exist_ok=True)\n"
            "canvas.convert('RGB').save(dst,'PNG',optimize=True)\n"
        ) % (str(source_path), str(output_path))
        python_bin = str(IMAGE_FACTORY_VENV_PYTHON if IMAGE_FACTORY_VENV_PYTHON.exists() else sys.executable)
        subprocess.run([python_bin, "-c", script], check=True, capture_output=True, text=True)
    finally:
        source_path.unlink(missing_ok=True)
    image_factory_update_status(sku, {"image_status": "uploaded", "last_uploaded_slot": slot})
    return {
        "ok": True,
        "sku": sku,
        "slot": slot,
        "file": str(output_path.relative_to(root)),
        "path": str(output_path),
    }


def image_factory_download_image(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入有效的 http/https 图片地址。")
    if parsed.netloc.endswith("chatgpt.com") and parsed.path.startswith("/s/"):
        raise ValueError("这是 ChatGPT 分享页链接，不是图片直链。请在图片上右键复制图片地址，或下载图片后用“上传成图”。")
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AmazonZutomationImageFactory/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=25) as response:
            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_UPLOAD_BYTES:
                raise ValueError("图片太大，请控制在 25MB 以内。")
            content = response.read(MAX_UPLOAD_BYTES + 1)
    except HTTPError as error:
        raise ValueError(f"图片地址无法下载：HTTP {error.code}") from error
    except URLError as error:
        raise ValueError(f"图片地址无法下载：{error.reason}") from error
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("图片太大，请控制在 25MB 以内。")
    normalized_type = content_type.split(";")[0].strip().lower()
    suffix = Path(parsed.path).suffix.lower()
    suffix_is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
    content_looks_like_html = content.lstrip()[:20].lower().startswith((b"<!doctype", b"<html"))
    if normalized_type and not normalized_type.startswith("image/") and not suffix_is_image:
        raise ValueError("这个链接不是直接图片地址。请右键图片选择“复制图片地址”，或先下载图片后用“上传成图”。")
    if content_looks_like_html:
        raise ValueError("这个链接打开的是网页，不是图片文件。请复制图片本身的地址，或下载后上传。")
    if not suffix_is_image:
        if "png" in content_type:
            suffix = ".png"
        elif "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"
    return {
        "filename": f"remote-image{suffix}",
        "content": content,
    }


def image_factory_process_url_import(sku, slot, image_url):
    file_payload = image_factory_download_image(image_url)
    result = image_factory_process_upload(sku, slot, file_payload)
    result["source_url"] = image_url
    return result


def image_factory_find_product_visual(root):
    preferred = [
        root / "01-main-image.png",
        root / "02-whats-included.png",
        root / "03-key-features.png",
    ]
    for path in preferred:
        if path.exists():
            return path
    for path in sorted(root.rglob("*")):
        if path.is_file() and image_factory_is_deliverable_image(path, root):
            return path
    return None


def image_factory_is_deliverable_image(path, root):
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return False
    relative_parts = path.relative_to(root).parts
    return not relative_parts or relative_parts[0] != "final-package"


def image_factory_render_layouts(sku, overwrite=False):
    root = image_factory_sku_dir(sku)
    plan_payload = image_factory_load_plan(sku)
    plan = plan_payload["plan"]
    product_visual = image_factory_find_product_visual(root)
    if not product_visual:
        raise ValueError("还没有可用产品图。请先上传 01-main-image，或至少上传一张产品素材图。")

    tasks = []
    for item in [*(plan.get("secondary_images") or []), *(plan.get("a_plus_modules") or [])]:
        if item.get("generation_method") != "html_css_layout":
            continue
        slot = item.get("slot")
        if slot not in IMAGE_FACTORY_SLOT_FILES:
            continue
        output_path = root / IMAGE_FACTORY_SLOT_FILES[slot]
        if output_path.exists() and not overwrite:
            continue
        tasks.append({
            "slot": slot,
            "file": str(output_path.relative_to(root)),
            "output_path": str(output_path),
            "title": item.get("title") or item.get("file_name") or slot,
            "copy": item.get("copy") or [],
            "layout_template": item.get("layout_template") or "",
            "brand": plan.get("brand") or "",
            "product_name": plan.get("product_name") or "",
        })

    if not tasks:
        return {
            "ok": True,
            "sku": sku,
            "source_image": str(product_visual),
            "created": [],
            "skipped": "没有需要生成的模板图，或目标文件已存在。",
        }

    script = r'''
import json
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

payload = json.loads(r"""__PAYLOAD__""")
source = Path(payload["source_image"])
tasks = payload["tasks"]

font_candidates = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def font(size, bold=False):
    candidates = font_candidates
    if bold:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            *font_candidates,
        ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()

def wrap_text(text, width=24):
    text = str(text or "").strip()
    if not text:
        return ""
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False))

def paste_product(canvas, box):
    img = ImageOps.exif_transpose(Image.open(source)).convert("RGBA")
    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    left = box[0] + (max_w - img.width) // 2
    top = box[1] + (max_h - img.height) // 2
    canvas.alpha_composite(img, (left, top))

def draw_secondary(task):
    canvas = Image.new("RGBA", (1500, 1500), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((80, 80, 1420, 1420), radius=36, fill=(248, 250, 250, 255), outline=(219, 225, 231, 255), width=3)
    draw.rounded_rectangle((130, 180, 690, 1320), radius=26, fill=(255, 255, 255, 255), outline=(220, 226, 232, 255), width=3)
    paste_product(canvas, (170, 230, 650, 1260))
    draw.text((760, 190), wrap_text(task["title"], 17), fill=(23, 33, 43), font=font(72, True), spacing=8)
    y = 470
    for point in (task.get("copy") or [])[:4]:
        draw.rounded_rectangle((760, y, 1345, y + 150), radius=26, fill=(255, 255, 255, 255), outline=(226, 231, 236, 255), width=2)
        draw.ellipse((795, y + 52, 825, y + 82), fill=(36, 106, 95, 255))
        draw.text((850, y + 36), wrap_text(point, 26), fill=(48, 58, 72), font=font(34, False), spacing=4)
        y += 184
    if task.get("brand"):
        draw.text((760, 1240), str(task["brand"]), fill=(36, 106, 95), font=font(34, True))
    return canvas

def draw_aplus(task):
    canvas = Image.new("RGBA", (1500, 1500), (247, 248, 248, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((96, 90), str(task.get("brand") or "").upper(), fill=(36, 106, 95), font=font(32, True))
    draw.text((96, 145), wrap_text(task["title"], 24), fill=(23, 33, 43), font=font(76, True), spacing=8)
    draw.rounded_rectangle((96, 390, 720, 1320), radius=28, fill=(255, 255, 255, 255), outline=(217, 224, 230, 255), width=3)
    paste_product(canvas, (150, 455, 666, 1260))
    y = 430
    for point in (task.get("copy") or [])[:4]:
        draw.rounded_rectangle((790, y, 1388, y + 165), radius=18, fill=(255, 255, 255, 255))
        draw.rectangle((790, y, 805, y + 165), fill=(36, 106, 95))
        draw.text((840, y + 38), wrap_text(point, 28), fill=(48, 58, 72), font=font(34), spacing=4)
        y += 205
    return canvas

created = []
for task in tasks:
    output = Path(task["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas = draw_aplus(task) if "aplus" in task.get("layout_template", "") else draw_secondary(task)
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    created.append({"slot": task["slot"], "file": task["file"], "path": str(output)})

print(json.dumps({"created": created}, ensure_ascii=False))
'''
    payload = {
        "source_image": str(product_visual),
        "tasks": tasks,
    }
    script = script.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("\\", "\\\\").replace('"""', '\\"\\"\\"'))
    python_bin = str(IMAGE_FACTORY_VENV_PYTHON if IMAGE_FACTORY_VENV_PYTHON.exists() else sys.executable)
    result = subprocess.run([python_bin, "-c", script], check=True, capture_output=True, text=True)
    rendered = json.loads(result.stdout or "{}")
    created = rendered.get("created") or []
    image_factory_update_status(sku, {
        "layout_status": "rendered",
        "layout_rendered_count": len(created),
        "layout_source_image": str(product_visual),
    })
    return {
        "ok": True,
        "sku": sku,
        "source_image": str(product_visual),
        "created": created,
    }


def image_factory_qc(sku):
    root = image_factory_sku_dir(sku)
    images = []
    expected_images = sorted(set(IMAGE_FACTORY_SLOT_FILES.values()))
    existing_image_names = set()
    for path in sorted(root.rglob("*")):
        if not image_factory_is_deliverable_image(path, root):
            continue
        relative_name = str(path.relative_to(root))
        existing_image_names.add(relative_name)
        issues = []
        try:
            script = (
                "from PIL import Image\n"
                "img=Image.open(r'%s')\n"
                "print(f'{img.size[0]}x{img.size[1]}')\n"
            ) % str(path)
            python_bin = str(IMAGE_FACTORY_VENV_PYTHON if IMAGE_FACTORY_VENV_PYTHON.exists() else sys.executable)
            result = subprocess.run([python_bin, "-c", script], check=True, capture_output=True, text=True)
            if result.stdout.strip() != "1500x1500":
                issues.append(f"Image size is {result.stdout.strip()}, expected 1500x1500.")
        except Exception as error:
            issues.append(f"Cannot inspect image: {error}")
        images.append({
            "image_name": relative_name,
            "pass": not issues,
            "issues": issues,
            "suggested_fix_prompt": "" if not issues else "Reprocess this image as 1500x1500 with stricter Amazon compliance rules.",
        })
    missing_images = [name for name in expected_images if name not in existing_image_names]
    report = {
        "sku": sku,
        "pass": bool(images) and not missing_images and all(item["pass"] for item in images),
        "message": "已找到图片并完成基础质检。" if images else "未找到已归档图片。请先在图片清单卡片里上传成图，或粘贴图片链接后点“链接归档”。",
        "folder_path": str(root),
        "image_count": len(images),
        "expected_count": len(expected_images),
        "missing_images": missing_images,
        "images": images,
    }
    image_factory_write_json(root / "qc-report.json", report)
    image_factory_update_status(sku, {"qc_status": "completed" if images else "no_images"})
    return {"ok": True, "report": report}


def image_factory_export(sku):
    import zipfile
    root = image_factory_sku_dir(sku)
    image_files = [
        path for path in sorted(root.rglob("*"))
        if path.is_file() and image_factory_is_deliverable_image(path, root)
    ]
    if not image_files:
        raise ValueError(f"SKU {sku} 还没有已归档图片，不能导出 ZIP。请先上传图片或使用链接归档。")
    zip_path = root / "final-package.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != zip_path and (path.relative_to(root).parts or [""])[0] != "final-package":
                archive.write(path, path.relative_to(root))
    image_factory_update_status(sku, {"package_status": "exported", "package_path": str(zip_path)})
    return {"ok": True, "sku": sku, "zip_path": str(zip_path)}


def submit_image_production_job(payload):
    required_fields = ["sku", "brand", "product_name", "included_items"]
    missing = [field for field in required_fields if not str(payload.get(field) or "").strip()]
    if not str(payload.get("main_keyword") or payload.get("target_keyword") or "").strip():
        missing.append("main_keyword")
    if missing:
        raise ValueError("缺少必填字段：" + ", ".join(missing))

    reference_images = payload.get("reference_images") or []
    if isinstance(reference_images, str):
        reference_images = [
            item.strip()
            for item in re.split(r"[\n,]+", reference_images)
            if item.strip()
        ]

    job_payload = {
        "job_id": payload.get("job_id") or f"{payload.get('sku')}-{int(time.time())}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sku": str(payload.get("sku") or "").strip(),
        "brand": str(payload.get("brand") or "").strip(),
        "product_name": str(payload.get("product_name") or "").strip(),
        "included_items": str(payload.get("included_items") or "").strip(),
        "material": str(payload.get("material") or "").strip(),
        "size": str(payload.get("size") or "").strip(),
        "main_keyword": str(payload.get("main_keyword") or payload.get("target_keyword") or "").strip(),
        "target_buyer": str(payload.get("target_buyer") or "").strip(),
        "price_range": str(payload.get("price_range") or "").strip(),
        "image_style": str(payload.get("image_style") or "clean Amazon listing photography and infographic").strip(),
        "reference_images": reference_images,
        "reference_image_urls": reference_images,
    }

    job_record = {
        **job_payload,
        "status": "queued_locally",
        "image_factory_mode": "in_process",
        "factory_response": {},
    }

    try:
        factory_payload = {key: value for key, value in job_payload.items() if key not in {"job_id", "created_at", "reference_images"}}
        response_payload = image_factory_generate_prompts(factory_payload)
        job_record["status"] = "prompts_generated"
        job_record["factory_response"] = {
            "sku": response_payload.get("sku"),
            "prompts_path": response_payload.get("prompts_path"),
            "plan": response_payload.get("plan"),
        }
    except Exception as error:
        job_record["status"] = "image_factory_failed"
        job_record["error"] = str(error)

    save_image_production_job(job_record)
    return job_record



def _find_first_dict(payload, keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _extract_bullets(product):
    candidates = [
        product.get("feature_bullets"),
        product.get("feature_bullets_flat"),
        product.get("about_this_item"),
        product.get("features"),
        product.get("bullet_points"),
    ]
    bullets = []
    for candidate in candidates:
        if isinstance(candidate, list):
            bullets.extend(to_text(item) for item in candidate if to_text(item))
        elif isinstance(candidate, dict):
            for value in candidate.values():
                if isinstance(value, list):
                    bullets.extend(to_text(item) for item in value if to_text(item))
                elif to_text(value):
                    bullets.append(to_text(value))
        elif to_text(candidate):
            bullets.extend(part.strip() for part in re.split(r"[\n•]+", to_text(candidate)) if part.strip())
    seen = set()
    unique = []
    for bullet in bullets:
        key = bullet.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(bullet)
    return unique[:8]


def fetch_asin_product_detail(params):
    asin = (params.get("asin") or "").strip().upper()
    if not asin:
        raise ValueError("asin is required")
    payload = request_serpapi_json({
        "engine": "amazon_product",
        "asin": asin,
        "amazon_domain": params.get("amazon_domain") or "amazon.com",
        "language": params.get("language") or "en_US",
        "device": params.get("device") or "desktop",
    })
    product = _find_first_dict(payload, ["product_results", "product", "product_information"])
    title = to_text(product.get("title") or payload.get("title"))
    price = product.get("extracted_price") or product.get("price") or payload.get("price")
    rating = product.get("rating") or payload.get("rating")
    reviews = product.get("reviews") or product.get("reviews_count") or payload.get("reviews")
    description = to_text(product.get("description") or product.get("product_description") or payload.get("description"))
    return {
        "asin": asin,
        "title": title,
        "brand": to_text(product.get("brand") or product.get("manufacturer") or payload.get("brand")),
        "price": str(price or ""),
        "rating": str(rating or ""),
        "reviews": str(reviews or ""),
        "feature_bullets": _extract_bullets(product),
        "description": description,
        "category": to_text(product.get("category") or product.get("categories") or payload.get("category")),
        "product_url": to_text(product.get("link") or product.get("product_link") or payload.get("search_metadata", {}).get("amazon_url")),
        "image_url": to_text(product.get("main_image") or product.get("thumbnail") or product.get("image")),
        "data_source": "SerpApi amazon_product",
    }

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


def is_port_open(host="127.0.0.1", port=VIDEO_REMIX_PORT):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def tail_text(path, max_chars=3000):
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="ignore")
        return data[-max_chars:]
    except Exception:
        return ""


def video_remix_status_payload():
    global VIDEO_REMIX_PROCESS
    managed_running = bool(VIDEO_REMIX_PROCESS and VIDEO_REMIX_PROCESS.poll() is None)
    port_running = is_port_open(port=VIDEO_REMIX_PORT)
    if VIDEO_REMIX_PROCESS and VIDEO_REMIX_PROCESS.poll() is not None:
        VIDEO_REMIX_PROCESS = None
    return {
        "running": managed_running or port_running,
        "managed": managed_running,
        "port": VIDEO_REMIX_PORT,
        "url": f"http://127.0.0.1:{VIDEO_REMIX_PORT}",
        "log_tail": tail_text(VIDEO_REMIX_LOG),
    }


def start_video_remix_service():
    global VIDEO_REMIX_PROCESS
    status = video_remix_status_payload()
    if status["running"]:
        return {"ok": True, "result": status, "message": "8010 服务已经在运行。"}
    if not VIDEO_REMIX_DIR.exists():
        raise RuntimeError("video-remix-api 目录不存在。")

    VIDEO_REMIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    python_bin = VIDEO_REMIX_DIR / ".venv" / "bin" / "python"
    python_cmd = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_cmd,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(VIDEO_REMIX_PORT),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    with VIDEO_REMIX_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write("\n--- starting video-remix-api ---\n")
        log_file.write(" ".join(command) + "\n")
        log_file.flush()
        VIDEO_REMIX_PROCESS = subprocess.Popen(
            command,
            cwd=str(VIDEO_REMIX_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

    time.sleep(1.0)
    if VIDEO_REMIX_PROCESS.poll() is not None and not is_port_open(port=VIDEO_REMIX_PORT):
        exit_code = VIDEO_REMIX_PROCESS.returncode
        VIDEO_REMIX_PROCESS = None
        raise RuntimeError(
            "8010 服务启动失败。请先安装依赖：cd video-remix-api && pip install -r requirements.txt。"
            f" 退出码：{exit_code}。日志：{tail_text(VIDEO_REMIX_LOG, 1200)}"
        )
    return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务已启动。"}


def stop_video_remix_service():
    global VIDEO_REMIX_PROCESS
    if not VIDEO_REMIX_PROCESS or VIDEO_REMIX_PROCESS.poll() is not None:
        VIDEO_REMIX_PROCESS = None
        if is_port_open(port=VIDEO_REMIX_PORT):
            return {
                "ok": False,
                "result": video_remix_status_payload(),
                "error": "检测到 8010 端口有服务在运行，但不是当前页面启动的进程，无法安全关闭。",
            }
        return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务当前未运行。"}

    VIDEO_REMIX_PROCESS.terminate()
    try:
        VIDEO_REMIX_PROCESS.wait(timeout=5)
    except subprocess.TimeoutExpired:
        VIDEO_REMIX_PROCESS.kill()
        VIDEO_REMIX_PROCESS.wait(timeout=3)
    VIDEO_REMIX_PROCESS = None
    return {"ok": True, "result": video_remix_status_payload(), "message": "8010 服务已关闭。"}


class AmazonProductHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_operation_log(self, action, params, payload, status, started_at):
        try:
            log_operation(
                action=action,
                method=self.command,
                path=urlparse(self.path).path,
                query_params=params,
                success=bool(payload.get("ok", status < HTTPStatus.BAD_REQUEST)) if isinstance(payload, dict) else status < HTTPStatus.BAD_REQUEST,
                status_code=int(status),
                duration_ms=round((time.monotonic() - started_at) * 1000),
                error=(payload.get("error", "") if isinstance(payload, dict) else ""),
                client_ip=self.client_address[0] if self.client_address else "",
                user_agent=self.headers.get("User-Agent", ""),
            )
        except Exception as error:
            print(f"Operation log skipped for {action}: {error}")

    def send_json_and_log(self, action, params, payload, status, started_at):
        self.send_json(payload, status)
        self.write_operation_log(action, params, payload, status, started_at)

    def parse_multipart_form(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("请使用表单上传 PDF 文件。")

        boundary_match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type)
        if not boundary_match:
            raise ValueError("上传请求缺少 multipart boundary。")
        boundary = (boundary_match.group(1) or boundary_match.group(2)).strip()

        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            raise ValueError("上传文件为空。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("PDF 文件过大，请控制在 25MB 以内。")

        body = self.rfile.read(content_length)
        fields = {}
        files = {}
        for raw_part in body.split(("--" + boundary).encode("utf-8")):
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if not part or part == b"--":
                continue
            if part.endswith(b"--"):
                part = part[:-2]
                if part.endswith(b"\r\n"):
                    part = part[:-2]

            header_blob, separator, value = part.partition(b"\r\n\r\n")
            if not separator:
                continue

            headers = header_blob.decode("utf-8", errors="ignore").split("\r\n")
            disposition = next(
                (line for line in headers if line.lower().startswith("content-disposition:")),
                "",
            )
            name_match = re.search(r'name="([^"]+)"', disposition)
            if not name_match:
                continue
            name = name_match.group(1)
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            if filename_match:
                files[name] = {
                    "filename": filename_match.group(1),
                    "content": value,
                }
            else:
                fields[name] = value.decode("utf-8", errors="ignore").strip()

        return fields, files

    def do_POST(self):
        started_at = time.monotonic()
        parsed = urlparse(self.path)
        if parsed.path == "/api/image-production":
            params = {}
            try:
                payload_in = read_json_body(self)
                params = {
                    "sku": payload_in.get("sku", ""),
                    "target_keyword": payload_in.get("target_keyword", ""),
                }
                result = submit_image_production_job(payload_in)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_submit", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/upload":
            params = {}
            try:
                fields, files = self.parse_multipart_form()
                sku = (fields.get("sku") or "").strip()
                slot = (fields.get("slot") or "").strip()
                uploaded_image = files.get("file") or files.get("image")
                params = {"sku": sku, "slot": slot}
                if not sku or not slot:
                    raise ValueError("sku 和 slot 都不能为空。")
                if not uploaded_image:
                    raise ValueError("请先选择图片文件。")
                result = image_factory_process_upload(sku, slot, uploaded_image)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_upload", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/import-url":
            params = {}
            try:
                payload_in = read_json_body(self)
                sku = (payload_in.get("sku") or "").strip()
                slot = (payload_in.get("slot") or "").strip()
                image_url = (payload_in.get("image_url") or payload_in.get("url") or "").strip()
                params = {"sku": sku, "slot": slot}
                if not sku or not slot:
                    raise ValueError("sku 和 slot 都不能为空。")
                if not image_url:
                    raise ValueError("请先粘贴图片链接。")
                result = image_factory_process_url_import(sku, slot, image_url)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_import_url", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/qc":
            params = {}
            try:
                payload_in = read_json_body(self)
                sku = (payload_in.get("sku") or "").strip()
                params = {"sku": sku}
                if not sku:
                    raise ValueError("sku 不能为空。")
                result = image_factory_qc(sku)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_qc", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/render-layouts":
            params = {}
            try:
                payload_in = read_json_body(self)
                sku = (payload_in.get("sku") or "").strip()
                overwrite = bool(payload_in.get("overwrite", False))
                params = {"sku": sku}
                if not sku:
                    raise ValueError("sku 不能为空。")
                result = image_factory_render_layouts(sku, overwrite=overwrite)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_render_layouts", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/export":
            params = {}
            try:
                payload_in = read_json_body(self)
                sku = (payload_in.get("sku") or "").strip()
                params = {"sku": sku}
                if not sku:
                    raise ValueError("sku 不能为空。")
                result = image_factory_export(sku)
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_export", params, payload, status, started_at)
            return

        if parsed.path == "/api/video-remix-service":
            params = {}
            try:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    payload_in = json.loads(body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    payload_in = {}
                action = (payload_in.get("action") or "status").strip().lower()
                params = {"action": action}
                if action == "start":
                    payload = start_video_remix_service()
                    status = HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST
                elif action == "stop":
                    payload = stop_video_remix_service()
                    status = HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST
                else:
                    payload = {"ok": True, "result": video_remix_status_payload()}
                    status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error), "result": video_remix_status_payload()}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("video_remix_service", params, payload, status, started_at)
            return

        if parsed.path == "/api/pdf-made-in-china":
            params = {}
            try:
                fields, files = self.parse_multipart_form()
                uploaded_pdf = files.get("pdf") or files.get("file")
                filename = (uploaded_pdf or {}).get("filename") or "labels.pdf"
                params = {
                    "filename": filename,
                    "file_size": len((uploaded_pdf or {}).get("content", b"")),
                    "text": fields.get("text") or "Made In China",
                    "font_size": fields.get("font_size") or "8",
                }
                if not uploaded_pdf:
                    raise ValueError("请先选择一个 PDF 文件。")
                if not filename.lower().endswith(".pdf"):
                    raise ValueError("当前只支持上传 PDF 文件。")

                result = add_made_in_china_to_pdf(
                    uploaded_pdf.get("content", b""),
                    GENERATED_DIR,
                    text=fields.get("text") or "Made In China",
                    font_size=to_float(fields.get("font_size")) or 8,
                )
                result["file_url"] = f"/generated/{result['output_name']}"
                result["message"] = f"已识别 {result['labels_detected']} 个标签，并写入 Made In China。"
                payload = {"ok": True, "result": result}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            self.send_json_and_log("pdf_made_in_china", params, payload, status, started_at)
            return

        self.send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/video-remix-service":
            started_at = time.monotonic()
            params = {}
            payload = {"ok": True, "result": video_remix_status_payload()}
            status = HTTPStatus.OK
            self.send_json_and_log("video_remix_service_status", params, payload, status, started_at)
            return

        if parsed.path == "/api/db-health":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {
                    "ok": True,
                    "result": check_database_connection(
                        use_direct=(params.get("direct") or "false").lower() == "true"
                    ),
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("db_health", params, payload, status, started_at)
            return

        if parsed.path == "/api/operation-logs/count":
            started_at = time.monotonic()
            params = {}
            try:
                payload = {"ok": True, "result": {"count": count_operation_logs()}}
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json(payload, status)
            return

        if parsed.path == "/api/image-production/jobs":
            started_at = time.monotonic()
            params = {}
            try:
                jobs = [image_factory_hydrate_job(job) for job in load_image_production_jobs()]
                payload = {
                    "ok": True,
                    "result": {
                        "jobs": jobs,
                        "image_factory_mode": "in_process",
                    },
                }
                status = HTTPStatus.OK
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_jobs", params, payload, status, started_at)
            return

        if parsed.path == "/api/image-production/plan":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": image_factory_load_plan(params.get("sku", ""))}
                status = HTTPStatus.OK
            except ValueError as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_REQUEST
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
                status = HTTPStatus.BAD_GATEWAY
            self.send_json_and_log("image_production_plan", params, payload, status, started_at)
            return

        if parsed.path == "/api/products":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, **filter_rows(params)}
            except Exception as error:
                payload = {
                    "ok": True,
                    "summary": {
                        "count": 0,
                        "dataset_count": 0,
                        "page": to_int(params.get("page")) or 1,
                        "page_size": to_int(params.get("page_size")) or 30,
                        "total_results": 0,
                        "total_pages": 0,
                        "has_next": False,
                        "average_price": 0,
                        "average_rating": 0,
                        "prime_ratio": 0,
                        "data_source": "SerpApi Amazon Search API",
                        "mode": params.get("data_source") or "serpapi",
                        "error": f"查询接口临时失败：{error}",
                        "seller_filter_applied": False,
                        "seller_filter_no_match": False,
                        "sample_keywords": ["earbuds", "laptop", "keyboard", "matcha", "projector", "bottle"],
                    },
                    "items": [],
                }
            status = HTTPStatus.OK
            self.send_json_and_log("products_search", params, payload, status, started_at)
            return

        if parsed.path == "/api/exchange":
            started_at = time.monotonic()
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
            self.send_json_and_log("exchange_rate", params, payload, status, started_at)
            return

        if parsed.path == "/api/ai-opportunity":
            started_at = time.monotonic()
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
            self.send_json_and_log("ai_opportunity", params, payload, status, started_at)
            return

        if parsed.path == "/api/bundle-plan":
            started_at = time.monotonic()
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
            self.send_json_and_log("bundle_plan", params, payload, status, started_at)
            return

        if parsed.path == "/api/product-hunter":
            started_at = time.monotonic()
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
            self.send_json_and_log("product_hunter", params, payload, status, started_at)
            return

        if parsed.path == "/api/market-gaps":
            started_at = time.monotonic()
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
            self.send_json_and_log("market_gaps", params, payload, status, started_at)
            return


        if parsed.path == "/api/asin-product":
            started_at = time.monotonic()
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            try:
                payload = {"ok": True, "result": fetch_asin_product_detail(params)}
            except Exception as error:
                fallback_asin = (params.get("asin") or "").strip().upper()
                payload = {
                    "ok": True,
                    "warning": f"ASIN 商品详情临时获取失败：{error}",
                    "result": {
                        "asin": fallback_asin,
                        "title": "",
                        "brand": "",
                        "price": "",
                        "rating": "",
                        "reviews": "",
                        "feature_bullets": [],
                        "description": "",
                        "category": "",
                        "product_url": "",
                        "image_url": "",
                        "data_source": "fallback",
                    },
                }
            status = HTTPStatus.OK
            self.send_json_and_log("asin_product", params, payload, status, started_at)
            return

        if parsed.path == "/api/asin-reviews":
            started_at = time.monotonic()
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
            self.send_json_and_log("asin_reviews", params, payload, status, started_at)
            return

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()


def main():
    args = parse_args()
    try:
        ensure_operation_logs_table()
        print("Operation logs table is ready.")
    except Exception as error:
        print(f"Operation logs table setup skipped: {error}")
    server = ThreadingHTTPServer((args.host, args.port), AmazonProductHandler)
    print(f"Amazon product web app running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
