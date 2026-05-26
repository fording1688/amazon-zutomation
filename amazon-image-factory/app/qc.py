import re
from pathlib import Path

from PIL import Image

from app.image_processing import CANVAS_SIZE
from app.models import QcImageResult, QcReport
from app.storage import save_qc_report, sku_dir


FORBIDDEN_TEXT_TERMS = [
    "best",
    "no.1",
    "#1",
    "guaranteed",
    "official",
    "website",
    "www.",
    "http://",
    "https://",
    "@",
    "qr code",
]


def _check_image_file(path: Path) -> QcImageResult:
    issues = []
    try:
        with Image.open(path) as image:
            if image.size != CANVAS_SIZE:
                issues.append(f"Image size is {image.size[0]}x{image.size[1]}, expected 1500x1500.")
    except Exception as error:
        issues.append(f"Cannot open image: {error}")

    lower_name = path.name.lower()
    if re.search(r"(best|no1|guaranteed|official)", lower_name):
        issues.append("File name contains a potentially exaggerated claim.")

    suggested = ""
    if issues:
        suggested = "Regenerate or reprocess this image with correct 1500x1500 canvas and stricter Amazon compliance rules."

    return QcImageResult(
        image_name=str(path.name),
        pass_=not issues,
        issues=issues,
        suggested_fix_prompt=suggested,
    )


def run_basic_qc(sku: str) -> QcReport:
    root = sku_dir(sku)
    images = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            images.append(_check_image_file(path))
    report = QcReport(sku=sku, images=images)
    save_qc_report(report)
    return report
