# Amazon Product Image Factory

这是 `amazon-zutomation` 内部的图片生产核心模块。日常使用时它已经合并进 TradeHarbor / Amazon 工作台同一个后端进程；`amazon-image-factory/` 保留为核心能力、模板、存储和后续 API 化的代码目录。

n8n 只负责调度、通知、人工审核和状态更新，不承载核心图片生成和处理逻辑。

第一版 MVP 已实现：

- 本地 Web 表单
- `POST /generate-prompts` 生成标准图片 Prompt 方案
- 保存 `prompts.json`
- 手动上传生成后的图片
- 自动裁剪/填充为 `1500x1500`
- 按 SKU 和固定文件名归档
- 基础图片尺寸质检
- 导出 ZIP 图片包
- 提供 API 给 n8n 或现有工作台调用
- Provider-based 架构配置
- 副图和 A+ 的 HTML/CSS 模板目录

## Provider 架构

默认模型和能力分工：

```text
Text planning model:
  provider: OpenRouter
  primary: openai/gpt-4.1
  fallback: anthropic/claude-3.5-sonnet

Image generation model:
  provider: OpenRouter
  primary: openai/gpt-image-2
  fallback: openai/gpt-image-1

Image editing model:
  primary: OpenRouter routed image edit model when available
  fallback: Stability AI Stable Image API

Layout generation:
  HTML/CSS templates rendered with Playwright

Image processing:
  Pillow

Quality check:
  provider: OpenRouter
  primary: openai/gpt-4.1
  fallback: google/gemini-2.5-pro
```

OpenRouter API uses an OpenAI-compatible Chat Completions endpoint:

```text
https://openrouter.ai/api/v1/chat/completions
```

Configure:

```bash
OPENROUTER_API_KEY=...
OPENROUTER_HTTP_REFERER=http://127.0.0.1:8005
OPENROUTER_APP_TITLE=Amazon Product Image Factory
```

重要规则：

- 不依赖图片生成模型渲染长文字。
- 主图禁止任何文字。
- 副图和 A+ 的文字层使用 HTML/CSS 模板渲染。
- 图片生成模型只负责产品主体、背景视觉或场景素材。
- 生成的 `prompts.json` 会为每个图片位写明 `generation_method`、`provider_role`、`model_preference`、`layout_template`。

## 目录结构

```text
amazon-image-factory/
  app/
    main.py                 # FastAPI 入口和本地 Web 表单
    config.py               # 环境变量和存储路径
    models.py               # API 数据结构
    prompt_factory.py        # Prompt 生成逻辑
    image_processing.py      # 图片裁剪/填充/命名
    storage.py               # SKU 文件夹、JSON、ZIP
    qc.py                    # 第一版基础质检
    providers.py             # Provider 默认模型和 fallback 配置
    layout_renderer.py       # HTML/CSS -> image 的 Playwright 渲染边界
  templates/
    secondary-square.html    # 1500x1500 副图模板
    aplus-module.html        # A+ 模块模板
  storage/
    Amazon-Images/
      {sku}/
        prompts.json
        01-main-image.png
        02-whats-included.png
        03-key-features.png
        04-how-to-use.png
        05-size-spec.png
        06-lifestyle.png
        07-brand-bulk-support.png
        A+/
          01-hero-banner.png
          02-included-items.png
          03-usage-steps.png
          04-benefits.png
          05-brand-story.png
        qc-report.json
        final-package.zip
```

## 本地运行

当前推荐只启动 TradeHarbor 主程序，然后从 Amazon 工作台进入 `图片工厂`：

```bash
python3 web_app.py --port 8005
```

打开：

```text
http://127.0.0.1:8005
```

下面的 FastAPI 入口保留给后续独立部署或调试使用，不是日常必须启动：

```bash
cd amazon-image-factory
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

打开：

```text
http://127.0.0.1:8020
```

## API

### GET `/health`

检查服务状态。

### POST `/generate-prompts`

输入产品 JSON，生成并保存 `prompts.json`。

```bash
curl -X POST http://127.0.0.1:8020/generate-prompts \
  -H 'Content-Type: application/json' \
  -d @sample_input.json
```

### POST `/generate-images`

第一版不调用图片模型，只标记 Prompt 已准备好。

```json
{
  "sku": "DMSPHD-CBN-001",
  "versions_per_image": 2,
  "mode": "prompts_only"
}
```

### POST `/upload-image/{sku}/{slot}`

上传手工生成后的图片，程序会自动裁剪/填充为 `1500x1500` 并保存为固定文件名。

可用 slot：

```text
01-main-image
02-whats-included
03-key-features
04-how-to-use
05-size-spec
06-lifestyle
07-brand-bulk-support
a-plus-01-hero-banner
a-plus-02-included-items
a-plus-03-usage-steps
a-plus-04-benefits
a-plus-05-brand-story
```

### POST `/qc-images`

基础质检并保存 `qc-report.json`。

```json
{
  "sku": "DMSPHD-CBN-001"
}
```

第一版规则质检只做本地可判断项，例如图片尺寸。AI Vision 质检放到第二版。

### POST `/export-package`

导出最终 ZIP。

```json
{
  "sku": "DMSPHD-CBN-001"
}
```

### GET `/download/{sku}`

下载 ZIP。

### GET `/status/{sku}`

查询 SKU 文件、状态和生成进度。

## n8n 新架构角色

n8n 不再承担核心图片生成和图片处理逻辑，只做自动化外壳：

```text
Google Sheet Trigger
  -> HTTP Request /generate-prompts
  -> 通知人工复制 Prompt 或等待图片生成
  -> HTTP Request /generate-images
  -> 发送图片到 Telegram/飞书审核
  -> approve / regenerate
  -> HTTP Request /qc-images
  -> HTTP Request /export-package
  -> 写回 Google Sheet / Drive 链接
```

复杂逻辑应放在本服务里，而不是写进 n8n 节点。

## 第二版计划

- 通过 OpenRouter 调用文本/视觉模型优化 Prompt 和质检
- 通过 OpenRouter 可用的图片模型生成 A/B 版本；如当前模型不支持图片输出，再 fallback 到直连 OpenAI / Stability
- 用 Playwright/Puppeteer 渲染 HTML/CSS 副图和 A+ 图
- AI Vision 检查主图文字、额外物品、Logo、二维码、拼写
- 审核 API：approve / reject / regenerate
- Google Drive / S3 存储适配
