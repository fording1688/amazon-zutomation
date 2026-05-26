import json
import shutil
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import storage_root
from app.models import PromptPlan, QcReport


def sku_dir(sku: str) -> Path:
    safe_sku = "".join(ch for ch in sku if ch.isalnum() or ch in {"-", "_", "."}).strip()
    if not safe_sku:
        raise ValueError("Invalid SKU")
    path = storage_root() / safe_sku
    path.mkdir(parents=True, exist_ok=True)
    (path / "A+").mkdir(exist_ok=True)
    return path


def prompts_path(sku: str) -> Path:
    return sku_dir(sku) / "prompts.json"


def status_path(sku: str) -> Path:
    return sku_dir(sku) / "status.json"


def qc_report_path(sku: str) -> Path:
    return sku_dir(sku) / "qc-report.json"


def package_path(sku: str) -> Path:
    return sku_dir(sku) / "final-package.zip"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_prompt_plan(plan: PromptPlan) -> Path:
    path = prompts_path(plan.sku)
    write_json(path, plan.model_dump())
    update_status(plan.sku, {"prompt_status": "generated", "updated_at": time.time()})
    return path


def load_prompt_plan(sku: str) -> dict:
    return read_json(prompts_path(sku))


def save_qc_report(report: QcReport) -> Path:
    path = qc_report_path(report.sku)
    write_json(path, report.model_dump(by_alias=True))
    update_status(report.sku, {"qc_status": "completed", "updated_at": time.time()})
    return path


def update_status(sku: str, values: dict) -> dict:
    current = read_json(status_path(sku))
    current.update(values)
    current.setdefault("sku", sku)
    write_json(status_path(sku), current)
    return current


def list_files(sku: str) -> list[str]:
    root = sku_dir(sku)
    return [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def export_zip(sku: str) -> Path:
    root = sku_dir(sku)
    zip_path = package_path(sku)
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == zip_path:
                continue
            archive.write(path, path.relative_to(root))
    update_status(sku, {"package_status": "exported", "package_path": str(zip_path), "updated_at": time.time()})
    return zip_path


def reset_sku_folder(sku: str) -> None:
    root = sku_dir(sku)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "A+").mkdir(exist_ok=True)
