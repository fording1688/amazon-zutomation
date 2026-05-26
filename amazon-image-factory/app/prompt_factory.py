import json

from app.models import ImagePrompt, ProductInput, PromptPlan
from app.providers import TEXT_RENDERING_POLICY, provider_stack_dict


GLOBAL_COMPLIANCE_RULES = [
    "Main image must use pure white background.",
    "Main image must not contain text, icons, badges, borders, packaging, hands, props, or lifestyle scene.",
    "Product quantity must exactly match included_items.",
    "No competitor logos.",
    "No website, email, phone number, QR code, social handle, or off-Amazon contact information.",
    "Secondary images and A+ modules may use text, but text must be short, accurate, and spelled correctly.",
    "Avoid unsupported claims and exaggerated terms such as best, No.1, guaranteed, official, FDA approved, or certified unless provided.",
]


NEGATIVE_PROMPT = (
    "extra products, wrong quantity, competitor logo, website, email, phone number, QR code, "
    "social media handle, misspelled text, exaggerated claims, watermark, low resolution, blurry image"
)


def _base_context(product: ProductInput) -> str:
    return (
        f"Brand: {product.brand}. SKU: {product.sku}. Product: {product.product_name}. "
        f"Included items: {product.included_items}. Material: {product.material or 'not specified'}. "
        f"Size: {product.size or 'not specified'}. Main keyword: {product.main_keyword}. "
        f"Target buyer: {product.target_buyer or 'Amazon buyers'}. "
        f"Price range: {product.price_range or 'not specified'}. "
        f"Style: {product.image_style}."
    )


def _rules(*extra: str) -> list[str]:
    return [*GLOBAL_COMPLIANCE_RULES, *extra]


def build_prompt_plan(product: ProductInput) -> PromptPlan:
    context = _base_context(product)
    providers = provider_stack_dict()
    main_prompt = ImagePrompt(
        slot="01-main-image",
        file_name="01-main-image.png",
        title="White Background Main Image",
        generation_method="image_model",
        provider_role="image_generation",
        model_preference=providers["image_generation"],
        layout_template=None,
        prompt=(
            f"Create a 1500x1500 Amazon main image for {product.product_name}. {context} "
            "Use a pure white #FFFFFF background. Show only the actual purchased contents exactly as listed in included items. "
            "Use realistic product photography, centered composition, clean lighting, natural product scale, sharp details. "
            "No text, no icon, no badge, no packaging, no hands, no props, no shadows that look like extra objects."
        ),
        negative_prompt=NEGATIVE_PROMPT + ", text, icon, badge, packaging, hands, props, lifestyle background",
        copy=[],
        qc_rules=_rules(
            "Main image canvas must be 1500x1500.",
            "Main image background must be pure white.",
            "Main image must contain no visible text.",
        ),
    )

    secondary_specs = [
        (
            "02-whats-included",
            "02-whats-included.png",
            "What's Included",
            ["What's Included", product.included_items, "Ready for accurate Amazon listing display"],
            "Create a clean Amazon infographic showing the exact included items with simple labels and separated product callouts.",
        ),
        (
            "03-key-features",
            "03-key-features.png",
            "Key Features",
            ["Key Features", product.material or "Durable material", "Built for consistent performance"],
            "Create a feature-focused Amazon secondary image with three clear callouts for material, build quality, and use value.",
        ),
        (
            "04-how-to-use",
            "04-how-to-use.png",
            "How To Use",
            ["How To Use", "1. Install", "2. Align", "3. Use safely"],
            "Create a simple step-by-step usage infographic with clean numbered sections and product-focused visuals.",
        ),
        (
            "05-size-spec",
            "05-size-spec.png",
            "Size Specification",
            ["Size Specification", product.size or "Check actual listing size", "Confirm fit before purchase"],
            "Create a technical size-spec image with dimension arrows and clean readable specification labels.",
        ),
        (
            "06-lifestyle",
            "06-lifestyle.png",
            "Lifestyle Scene",
            ["Built for Work", product.target_buyer or "For practical buyers", "Clean, reliable product presentation"],
            "Create a realistic lifestyle scene showing the product in an appropriate use environment without adding unsupported accessories.",
        ),
        (
            "07-brand-bulk-support",
            "07-brand-bulk-support.png",
            "Brand and Bulk Support",
            [product.brand, "Bulk order support", "Consistent supply for business buyers"],
            "Create a professional brand support image for B2B buyers, clean industrial style, no external contact information.",
        ),
    ]

    secondary_images = [
        ImagePrompt(
            slot=slot,
            file_name=file_name,
            title=title,
            generation_method="html_css_layout",
            provider_role="layout_generation",
            model_preference=providers["layout_generation"],
            layout_template="secondary-square.html",
            prompt=(
                f"Create only the product/background visual asset for this Amazon secondary image. {instruction} {context} "
                "Do not render long text inside the image model output. The text layer will be rendered separately with HTML/CSS. "
                f"Approved text copy for the HTML layout: {json.dumps(copy, ensure_ascii=False)}."
            ),
            negative_prompt=NEGATIVE_PROMPT,
            copy=copy,
            qc_rules=_rules(
                "Secondary image canvas must be 1500x1500.",
                "Visible text must match approved copy.",
                "No off-Amazon contact information.",
            ),
        )
        for slot, file_name, title, copy, instruction in secondary_specs
    ]

    a_plus_specs = [
        (
            "01-hero-banner",
            "01-hero-banner.png",
            "A+ Hero Banner",
            [product.brand, product.product_name, product.main_keyword],
            "Create a premium A+ hero banner visual with brand-led product presentation and concise headline area.",
        ),
        (
            "02-included-items",
            "02-included-items.png",
            "A+ Included Items Module",
            ["Package Contents", product.included_items],
            "Create an A+ module that clearly explains the package contents and quantity.",
        ),
        (
            "03-usage-steps",
            "03-usage-steps.png",
            "A+ Usage Steps Module",
            ["Simple Setup", "Use with care", "Check compatibility"],
            "Create an A+ usage steps module with structured visual steps.",
        ),
        (
            "04-benefits",
            "04-benefits.png",
            "A+ Benefits Module",
            ["Practical design", "Reliable material", "Clear fit information"],
            "Create an A+ benefits module that explains practical buyer value without exaggerated claims.",
        ),
        (
            "05-brand-story",
            "05-brand-story.png",
            "A+ Application and Brand Story Module",
            [product.brand, "For business and practical users", "Focused on product consistency"],
            "Create an A+ application and brand story module with professional brand tone and product context.",
        ),
    ]

    a_plus_modules = [
        ImagePrompt(
            slot=slot,
            file_name=file_name,
            title=title,
            generation_method="html_css_layout",
            provider_role="layout_generation",
            model_preference=providers["layout_generation"],
            layout_template="aplus-module.html",
            prompt=(
                f"Create only the product/background visual asset for this Amazon A+ module. {instruction} {context} "
                "Do not render long text inside the image model output. The text layer will be rendered separately with HTML/CSS. "
                f"Approved text copy for the HTML layout: {json.dumps(copy, ensure_ascii=False)}."
            ),
            negative_prompt=NEGATIVE_PROMPT,
            copy=copy,
            qc_rules=_rules(
                "No off-Amazon contact information.",
                "Visible text must be spelled correctly.",
                "Avoid exaggerated or unsupported claims.",
            ),
        )
        for slot, file_name, title, copy, instruction in a_plus_specs
    ]

    return PromptPlan(
        sku=product.sku,
        brand=product.brand,
        product_name=product.product_name,
        provider_stack=providers,
        text_rendering_policy=TEXT_RENDERING_POLICY,
        main_image_prompt=main_prompt,
        secondary_images=secondary_images,
        a_plus_modules=a_plus_modules,
        global_compliance_rules=GLOBAL_COMPLIANCE_RULES,
    )
