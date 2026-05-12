#!/usr/bin/env python3

from __future__ import annotations

import re
import time
from pathlib import Path


ASIN_LIKE_RE = re.compile(r"^[A-Z0-9]{8,14}$")


def _load_fitz():
    try:
        import fitz  # type: ignore
    except ImportError as error:
        raise RuntimeError(
            "PDF 处理依赖 PyMuPDF 未安装。请先运行 pip install -r requirements.txt。"
        ) from error
    return fitz


def _clean_word(value: str) -> str:
    return (value or "").strip().replace(" ", "")


def _dedupe_anchors(anchors):
    seen = set()
    unique = []
    for page_index, rect, mode in anchors:
        key = (page_index, round(rect.x0 / 8), round(rect.y0 / 8), mode)
        if key in seen:
            continue
        seen.add(key)
        unique.append((page_index, rect, mode))
    return unique


def _find_label_anchors(doc, fitz):
    condition_anchors = []
    fallback_anchors = []
    for page_index, page in enumerate(doc):
        words = page.get_text("words") or []
        for word in words:
            x0, y0, x1, y1, text = word[:5]
            cleaned = _clean_word(text)
            rect = fitz.Rect(x0, y0, x1, y1)
            if "新品" in cleaned:
                condition_anchors.append((page_index, rect, "condition"))
                continue
            if ASIN_LIKE_RE.match(cleaned):
                fallback_anchors.append((page_index, rect, "asin"))

    return _dedupe_anchors(condition_anchors or fallback_anchors)


def _insert_position(anchor_rect, mode, page_rect):
    if mode == "condition":
        # The Amazon label has blank space immediately to the right of 新品.
        x = anchor_rect.x1 + 8
        y = anchor_rect.y1 - 1
    else:
        # Fallback: place text below the barcode/ASIN line when condition text is unavailable.
        x = anchor_rect.x0
        y = anchor_rect.y1 + 34

    x = min(max(x, page_rect.x0 + 8), page_rect.x1 - 120)
    y = min(max(y, page_rect.y0 + 8), page_rect.y1 - 8)
    return x, y


def add_made_in_china_to_pdf(
    pdf_bytes: bytes,
    output_dir: Path,
    text: str = "Made In China",
    font_size: float = 8.0,
):
    if not pdf_bytes:
        raise ValueError("请上传 PDF 文件。")

    label_text = (text or "Made In China").strip()[:80] or "Made In China"
    safe_font_size = min(max(float(font_size or 8), 5), 16)

    fitz = _load_fitz()
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    anchors = _find_label_anchors(doc, fitz)
    if not anchors:
        doc.close()
        raise ValueError("没有识别到标签里的 新品 或 ASIN/条码编号位置。")

    for page_index, rect, mode in anchors:
        page = doc[page_index]
        x, y = _insert_position(rect, mode, page.rect)
        page.insert_text(
            (x, y),
            label_text,
            fontsize=safe_font_size,
            fontname="helv",
            color=(0, 0, 0),
            overlay=True,
        )

    output_name = f"made_in_china_labels_{int(time.time())}.pdf"
    output_path = output_dir / output_name
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    return {
        "labels_detected": len(anchors),
        "pages": page_count,
        "output_name": output_name,
    }
