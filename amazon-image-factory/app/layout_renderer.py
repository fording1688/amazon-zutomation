from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def render_template(template_name: str, values: dict) -> str:
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Layout template not found: {template_name}")
    html = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", str(value or ""))
    return html


def render_html_to_image_with_playwright(html: str, output_path: Path, width: int = 1500, height: int = 1500) -> Path:
    """Render HTML/CSS to an image.

    This is intentionally an integration boundary. The first MVP stores prompts and
    accepts uploaded images; when automatic layout rendering is enabled, call this
    from the worker/API layer after installing Playwright browsers.
    """
    raise NotImplementedError(
        "Playwright rendering is planned for v2. Keep text-heavy image content in HTML/CSS templates."
    )
