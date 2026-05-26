from pathlib import Path

from PIL import Image, ImageOps

from app.storage import sku_dir, update_status


CANVAS_SIZE = (1500, 1500)


SLOT_FILE_NAMES = {
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
}


def target_path_for_slot(sku: str, slot: str) -> Path:
    file_name = SLOT_FILE_NAMES.get(slot, f"{slot}.png")
    return sku_dir(sku) / file_name


def normalize_to_square(input_path: Path, output_path: Path) -> Path:
    with Image.open(input_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGBA")
        image.thumbnail(CANVAS_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 255))
        left = (CANVAS_SIZE[0] - image.width) // 2
        top = (CANVAS_SIZE[1] - image.height) // 2
        canvas.alpha_composite(image, (left, top))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(output_path, "PNG", optimize=True)
    return output_path


def process_upload(sku: str, slot: str, source_path: Path) -> Path:
    output_path = target_path_for_slot(sku, slot)
    normalize_to_square(source_path, output_path)
    update_status(sku, {"image_status": "uploaded", "last_uploaded_slot": slot})
    return output_path
