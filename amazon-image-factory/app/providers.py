from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelProvider:
    provider: str
    primary_model: str
    fallback_model: str | None = None
    purpose: str = ""


DEFAULT_PROVIDER_STACK = {
    "text_planning": ModelProvider(
        provider="openrouter",
        primary_model="openai/gpt-4.1",
        fallback_model="anthropic/claude-3.5-sonnet",
        purpose="Generate Amazon image strategy, prompts, copy, and compliance rules.",
    ),
    "image_generation": ModelProvider(
        provider="openrouter",
        primary_model="openai/gpt-image-2",
        fallback_model="openai/gpt-image-1",
        purpose="Generate product/lifestyle image assets; do not render long text.",
    ),
    "image_editing": ModelProvider(
        provider="openrouter",
        primary_model="openai/image-edit",
        fallback_model="stability-ai-stable-image",
        purpose="Edit product images or compose product visuals when needed.",
    ),
    "layout_generation": ModelProvider(
        provider="playwright",
        primary_model="html-css-renderer",
        fallback_model=None,
        purpose="Render text-heavy Amazon secondary images and A+ modules from HTML/CSS templates.",
    ),
    "image_processing": ModelProvider(
        provider="pillow",
        primary_model="pillow",
        fallback_model=None,
        purpose="Crop, pad, compress, normalize, and archive images.",
    ),
    "quality_check": ModelProvider(
        provider="openrouter",
        primary_model="openai/gpt-4.1",
        fallback_model="google/gemini-2.5-pro",
        purpose="Check product quantity, compliance, off-Amazon contact, logos, and spelling.",
    ),
}


TEXT_RENDERING_POLICY = {
    "rule": "Do not rely on image generation models to render long text inside images.",
    "main_image": "No text is allowed.",
    "secondary_images": "Use HTML/CSS templates for text layers; image generation should produce only product or background visuals.",
    "a_plus": "Use HTML/CSS templates for text-heavy modules and compose product visuals into the layout.",
}


def provider_stack_dict() -> dict:
    return {key: asdict(value) for key, value in DEFAULT_PROVIDER_STACK.items()}
