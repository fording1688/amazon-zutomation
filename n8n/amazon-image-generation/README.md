# n8n Shell for Amazon Product Image Factory

新的架构中，n8n 不负责核心图片生产逻辑。

核心能力放在：

```text
amazon-image-factory/
```

n8n 只作为自动化外壳：

- 监听 Google Sheet 新增 SKU
- 调用 `POST /generate-prompts`
- 通知人工复制 Prompt 或等待图片生成
- 调用 `POST /generate-images`
- 把生成结果发到飞书/Telegram 审核
- 接收 approve / regenerate
- 调用 `POST /qc-images`
- 调用 `POST /export-package`
- 把 ZIP 链接、状态、错误信息写回 Google Sheet

## 推荐 n8n 流程

```text
Google Sheet Trigger
  -> HTTP Request: POST http://image-factory/generate-prompts
  -> HTTP Request: POST http://image-factory/generate-images
  -> Send Message: 飞书/Telegram 审核通知
  -> Wait / Webhook: 人工审核结果
  -> IF approve:
       HTTP Request: POST http://image-factory/qc-images
       HTTP Request: POST http://image-factory/export-package
       Google Sheet: 写回 final-package.zip 链接
     ELSE regenerate:
       HTTP Request: POST http://image-factory/generate-images
       Send Message: 重新审核
```

## 旧版草稿说明

`workflows/` 里的旧 JSON 是早期草稿，里面仍包含较多 Prompt 生成、图片生成和视觉质检逻辑。按照新架构，后续应重构为轻量 HTTP 调用，不再把复杂逻辑放在 n8n 节点里。

第一版请优先使用：

```text
amazon-image-factory/README.md
```
