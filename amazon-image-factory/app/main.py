import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import storage_root
from app.image_processing import SLOT_FILE_NAMES, process_upload
from app.models import (
    ExportPackageRequest,
    GenerateImagesRequest,
    GeneratePromptsResponse,
    ProductInput,
)
from app.prompt_factory import build_prompt_plan
from app.qc import run_basic_qc
from app.storage import (
    export_zip,
    list_files,
    load_prompt_plan,
    package_path,
    prompts_path,
    save_prompt_plan,
    sku_dir,
    status_path,
    update_status,
    read_json,
)


app = FastAPI(title="Amazon Product Image Factory", version="0.1.0")


@app.on_event("startup")
def ensure_storage() -> None:
    storage_root()


app.mount("/files", StaticFiles(directory=str(storage_root())), name="files")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "amazon-product-image-factory"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Amazon Product Image Factory</title>
    <style>
      body { margin: 0; font-family: Arial, "PingFang SC", sans-serif; color: #17212b; background: #f5f1e8; }
      main { width: min(1120px, calc(100% - 32px)); margin: 32px auto; display: grid; gap: 18px; }
      section { background: #fffaf0; border: 1px solid rgba(23,33,43,.12); border-radius: 18px; padding: 22px; box-shadow: 0 18px 50px rgba(55,44,31,.08); }
      h1, h2 { margin: 0; }
      p { color: #667085; line-height: 1.6; }
      form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
      label { display: grid; gap: 7px; color: #667085; font-size: 14px; }
      input, textarea, select, button { font: inherit; }
      input, textarea, select { border: 1px solid rgba(23,33,43,.14); border-radius: 12px; padding: 11px 12px; background: #fff; color: #17212b; }
      textarea { min-height: 90px; resize: vertical; }
      .wide { grid-column: 1 / -1; }
      button { border: 0; border-radius: 12px; padding: 13px 16px; color: #fff; background: #d8742f; cursor: pointer; }
      pre { white-space: pre-wrap; word-break: break-word; background: #17212b; color: #fff8ec; border-radius: 14px; padding: 16px; max-height: 420px; overflow: auto; }
      .upload-grid { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 12px; align-items: end; }
      @media (max-width: 760px) { form, .upload-grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } }
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>Amazon Product Image Factory</h1>
        <p>第一版 MVP：生成 Prompt、保存 prompts.json、上传手工生成图片、自动裁剪为 1500x1500、命名归档、打包 ZIP。</p>
      </section>
      <section>
        <h2>生成 Prompt</h2>
        <form id="prompt-form">
          <label>Brand <input name="brand" value="DMSPHD" required /></label>
          <label>SKU <input name="sku" value="DMSPHD-CBN-001" required /></label>
          <label class="wide">Product name <input name="product_name" value="CBN Grinding Wheel for Chainsaw Sharpening" required /></label>
          <label class="wide">Included items <textarea name="included_items" required>1 x CBN grinding wheel, 1 x bushing kit</textarea></label>
          <label>Material <input name="material" value="CBN abrasive, steel core" /></label>
          <label>Size <input name="size" value="145 mm x 22.2 mm bore" /></label>
          <label>Main keyword <input name="main_keyword" value="cbn grinding wheel for chainsaw" required /></label>
          <label>Target buyer <input name="target_buyer" value="chainsaw sharpening shops" /></label>
          <label>Price range <input name="price_range" value="$30-$60" /></label>
          <label>Image style <input name="image_style" value="clean premium industrial Amazon infographic" /></label>
          <label class="wide">Reference image URLs <textarea name="reference_image_urls" placeholder="每行一个 URL"></textarea></label>
          <button class="wide" type="submit">生成并保存 prompts.json</button>
        </form>
      </section>
      <section>
        <h2>上传图片并归档</h2>
        <form id="upload-form" class="upload-grid">
          <label>SKU <input name="sku" value="DMSPHD-CBN-001" required /></label>
          <label>Slot
            <select name="slot">
              <option value="01-main-image">01-main-image</option>
              <option value="02-whats-included">02-whats-included</option>
              <option value="03-key-features">03-key-features</option>
              <option value="04-how-to-use">04-how-to-use</option>
              <option value="05-size-spec">05-size-spec</option>
              <option value="06-lifestyle">06-lifestyle</option>
              <option value="07-brand-bulk-support">07-brand-bulk-support</option>
              <option value="a-plus-01-hero-banner">A+ 01 hero banner</option>
              <option value="a-plus-02-included-items">A+ 02 included items</option>
              <option value="a-plus-03-usage-steps">A+ 03 usage steps</option>
              <option value="a-plus-04-benefits">A+ 04 benefits</option>
              <option value="a-plus-05-brand-story">A+ 05 brand story</option>
            </select>
          </label>
          <label>Image <input name="file" type="file" accept="image/*" required /></label>
          <button type="submit">上传处理</button>
        </form>
      </section>
      <section>
        <h2>操作</h2>
        <form id="action-form" class="upload-grid">
          <label>SKU <input name="sku" value="DMSPHD-CBN-001" required /></label>
          <button type="button" data-action="status">查询状态</button>
          <button type="button" data-action="qc">基础质检</button>
          <button type="button" data-action="export">导出 ZIP</button>
        </form>
      </section>
      <section>
        <h2>结果</h2>
        <pre id="result">等待操作</pre>
      </section>
    </main>
    <script>
      const result = document.querySelector("#result");
      const show = (payload) => result.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
      document.querySelector("#prompt-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target).entries());
        data.reference_image_urls = String(data.reference_image_urls || "").split(/\\r?\\n|,/).map(v => v.trim()).filter(Boolean);
        const response = await fetch("/generate-prompts", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) });
        show(await response.json());
      });
      document.querySelector("#upload-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        const sku = data.get("sku");
        const slot = data.get("slot");
        const response = await fetch(`/upload-image/${encodeURIComponent(sku)}/${encodeURIComponent(slot)}`, { method: "POST", body: data });
        show(await response.json());
      });
      document.querySelector("#action-form").addEventListener("click", async (event) => {
        if (!event.target.dataset.action) return;
        const sku = new FormData(event.currentTarget).get("sku");
        if (event.target.dataset.action === "status") {
          show(await (await fetch(`/status/${encodeURIComponent(sku)}`)).json());
        }
        if (event.target.dataset.action === "qc") {
          show(await (await fetch("/qc-images", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({sku}) })).json());
        }
        if (event.target.dataset.action === "export") {
          show(await (await fetch("/export-package", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({sku}) })).json());
        }
      });
    </script>
  </body>
</html>
"""


@app.post("/generate-prompts", response_model=GeneratePromptsResponse)
def generate_prompts(product: ProductInput) -> GeneratePromptsResponse:
    plan = build_prompt_plan(product)
    path = save_prompt_plan(plan)
    return GeneratePromptsResponse(sku=product.sku, prompts_path=str(path), plan=plan)


@app.post("/generate-images")
def generate_images(request: GenerateImagesRequest) -> dict:
    plan = load_prompt_plan(request.sku)
    if not plan:
        raise HTTPException(status_code=404, detail="prompts.json not found. Run /generate-prompts first.")
    update_status(
        request.sku,
        {
            "generation_status": "prompts_only",
            "versions_per_image": request.versions_per_image,
            "message": "MVP does not call image model yet. Use prompts.json and upload generated images manually.",
        },
    )
    return {
        "ok": True,
        "sku": request.sku,
        "mode": request.mode,
        "message": "Prompt plan is ready. Image model integration is planned for v2.",
        "prompts_path": str(prompts_path(request.sku)),
    }


@app.post("/upload-image/{sku}/{slot}")
async def upload_image(sku: str, slot: str, file: UploadFile = File(...)) -> dict:
    if slot not in SLOT_FILE_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")
    suffix = Path(file.filename or "").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        shutil.copyfileobj(file.file, temp)
        temp_path = Path(temp.name)
    try:
        output_path = process_upload(sku, slot, temp_path)
    finally:
        temp_path.unlink(missing_ok=True)
    relative = output_path.relative_to(sku_dir(sku))
    return {
        "ok": True,
        "sku": sku,
        "slot": slot,
        "file": str(relative),
        "path": str(output_path),
        "url": f"/files/{sku}/{relative.as_posix()}",
    }


@app.post("/qc-images")
async def qc_images(request: Request) -> JSONResponse:
    payload = await request.json()
    sku = payload.get("sku")
    if not sku:
        raise HTTPException(status_code=400, detail="sku is required")
    report = run_basic_qc(sku)
    return JSONResponse({"ok": True, "report": report.model_dump(by_alias=True)})


@app.post("/export-package")
def export_package(request: ExportPackageRequest) -> dict:
    zip_path = export_zip(request.sku)
    return {
        "ok": True,
        "sku": request.sku,
        "zip_path": str(zip_path),
        "download_url": f"/download/{request.sku}",
    }


@app.get("/download/{sku}")
def download_package(sku: str) -> FileResponse:
    zip_path = package_path(sku)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Package not found. Run /export-package first.")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{sku}-amazon-images.zip")


@app.get("/status/{sku}")
def status(sku: str) -> dict:
    root = sku_dir(sku)
    return {
        "ok": True,
        "sku": sku,
        "exists": root.exists(),
        "status": read_json(status_path(sku)),
        "files": list_files(sku),
    }
