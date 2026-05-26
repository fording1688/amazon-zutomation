from typing import Literal

from pydantic import BaseModel, Field


class ProductInput(BaseModel):
    brand: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    included_items: str = Field(..., min_length=1)
    material: str = ""
    size: str = ""
    main_keyword: str = Field(..., min_length=1)
    target_buyer: str = ""
    price_range: str = ""
    reference_image_urls: list[str] = Field(default_factory=list)
    image_style: str = "clean Amazon listing photography and infographic"


class ImagePrompt(BaseModel):
    slot: str
    file_name: str
    title: str
    generation_method: str = "image_model"
    provider_role: str = "image_generation"
    model_preference: dict = Field(default_factory=dict)
    layout_template: str | None = None
    prompt: str
    negative_prompt: str
    image_text_copy: list[str] = Field(default_factory=list, alias="copy")
    qc_rules: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PromptPlan(BaseModel):
    sku: str
    brand: str
    product_name: str
    provider_stack: dict = Field(default_factory=dict)
    text_rendering_policy: dict = Field(default_factory=dict)
    main_image_prompt: ImagePrompt
    secondary_images: list[ImagePrompt]
    a_plus_modules: list[ImagePrompt]
    global_compliance_rules: list[str]


class GeneratePromptsResponse(BaseModel):
    ok: bool = True
    sku: str
    prompts_path: str
    plan: PromptPlan


class GenerateImagesRequest(BaseModel):
    sku: str
    versions_per_image: int = 1
    mode: Literal["prompts_only", "placeholder"] = "prompts_only"


class QcImageResult(BaseModel):
    image_name: str
    pass_: bool = Field(alias="pass")
    issues: list[str] = Field(default_factory=list)
    suggested_fix_prompt: str = ""

    model_config = {"populate_by_name": True}


class QcReport(BaseModel):
    sku: str
    images: list[QcImageResult]


class StatusResponse(BaseModel):
    ok: bool = True
    sku: str
    exists: bool
    status: dict
    files: list[str]


class ExportPackageRequest(BaseModel):
    sku: str
