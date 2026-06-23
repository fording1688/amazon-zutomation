# Amazon Product Filter

这是一个用于筛选亚马逊商品列表的小工具，适合处理从选品表、爬取结果或表格导出的 `CSV` 数据。

## 功能

- 按标题关键词筛选
- 按品牌、类目、卖家筛选
- 按价格、评分、评论数、月销量筛选
- 支持 `Prime` 商品筛选
- 支持排序、限制数量、导出为 `CSV` 或 `JSON`
- 支持本地图形界面网页查询
- 支持用关键词在线抓取 `Amazon.com` 搜索结果里的标题、价格、Review、Rating、ASIN
- 支持通过 `SerpApi Amazon Search API` 稳定获取真实 Amazon 搜索结果

## 数据格式

输入文件需要是 `CSV`，建议包含这些字段：

`asin,title,brand,category,seller,price,rating,reviews,sales,is_prime`

你可以直接参考 [sample_products.csv](/Users/fording/Documents/amazon-automation/sample_products.csv)。

## 关键词爬虫

推荐使用 SerpApi 版本。先在项目根目录创建 `.env`：

```bash
SERPAPI_API_KEY=你的_serpapi_private_api_key
```

然后运行：

```bash
python3 serpapi_amazon.py "iphone case" --limit 20 --output amazon_results.csv
```

也可以导出 JSON：

```bash
python3 serpapi_amazon.py "laptop stand" --pages 2 --limit 50 --output amazon_results.json
```

SerpApi 官方文档：<https://serpapi.com/amazon-search-api>

抓取 `Amazon.com` 搜索结果，并导出 CSV：

```bash
python3 amazon_scraper.py "laptop stand" --limit 20 --output amazon_results.csv
```

导出 JSON：

```bash
python3 amazon_scraper.py "wireless earbuds" --pages 2 --limit 50 --output amazon_results.json
```

终端会预览这些字段：

`asin,title,price,rating,reviews,product_url,image_url,is_prime`

说明：Amazon 对自动化访问限制很严格，真实请求可能返回 `HTTP 503`、验证码或机器人验证页。脚本会给出明确错误提示；如果要长期稳定抓取，建议使用合规的数据 API、代理服务，或控制频率并遵守 Amazon 的使用条款。

## 图形界面版本

启动本地网页服务：

```bash
python3 web_app.py
```

如果 `8000` 端口被占用，可以换一个端口：

```bash
python3 web_app.py --port 8001
```

启动后在浏览器打开：

```text
http://127.0.0.1:8000
```

这个界面支持直接填写筛选条件，然后返回商品结果、统计卡片和商品表格，效果上接近常见的亚马逊选品网站表单查询页面。

默认模式现在是 `Amazon 在线搜索`：

- 输入关键词后，会尝试抓取 `Amazon.com` 搜索结果
- 页面会展示标题、价格、评分、评论数、Prime 和商品链接
- 如果 Amazon 返回验证码、验证页或页面结构变化，页面会提示抓取失败
- 你也可以切回 `本地演示数据` 模式，继续测试界面和筛选逻辑

## 运行方式

查看帮助：

```bash
python3 amazon_filter.py --help
```

筛选电子类、评分不低于 4.3、评论不少于 500 的 Prime 商品：

```bash
python3 amazon_filter.py \
  --input sample_products.csv \
  --category "Electronics" \
  --min-rating 4.3 \
  --min-reviews 500 \
  --prime-only \
  --sort-by reviews \
  --descending
```

筛选标题里带 `Laptop` 的商品，并导出到新文件：

```bash
python3 amazon_filter.py \
  --input sample_products.csv \
  --keyword laptop \
  --output filtered_products.csv
```

导出为 `JSON`：

```bash
python3 amazon_filter.py \
  --input sample_products.csv \
  --brand SoundMax \
  --output filtered_products.json
```

## 后续可扩展

如果你愿意，我下一步可以继续帮你加这些能力：

- 图形界面版本
- 自动读取 Excel
- 自动抓取亚马逊页面数据
- 支持多个关键词组合筛选
- 支持利润率、佣金、重量等选品指标

## n8n 图片生产工作流

仓库新增了 Amazon listing 图片半自动生产能力。新的架构里，核心图片生产逻辑由独立程序/API 负责，n8n 只负责调度、通知、人工审核和状态更新。

核心程序位置：

```text
amazon-image-factory/
```

第一版 MVP 支持本地 Web 表单、生成 prompts.json、上传手工生成图片、自动裁剪为 1500x1500、固定命名归档、基础质检和 ZIP 导出。

图片工厂采用 provider-based 架构：

- 文本规划：通过 OpenRouter 调 OpenAI GPT 模型，fallback 到其它 OpenRouter 模型
- 图片生成：通过 OpenRouter 优先调 `openai/gpt-image-2`，fallback 到 `openai/gpt-image-1`
- 图片编辑：OpenRouter 可用模型优先，必要时 fallback 到 Stability AI Stable Image API
- 文本重的副图和 A+：HTML/CSS 模板 + Playwright 渲染
- 图片处理：Pillow
- 质检：通过 OpenRouter 调 Vision 模型

原则：不要依赖图片生成模型渲染长文字；副图和 A+ 的文字层由 HTML/CSS 负责。

n8n 外壳位置：

```text
n8n/amazon-image-generation/
```

它包含：

- n8n 外壳设计：监听表格、新增 SKU、调用 `amazon-image-factory` API、发送飞书/Telegram 通知、接收人工审核结果、回写状态。
- 旧版 n8n 草稿仍保留在目录中，后续应改成只调用图片工厂 API，不再把 Prompt、图片生成、质检逻辑写进 n8n 节点。
- Web 程序里的 Amazon 工作台已经内置 `图片工厂` 标签页，并在同一个后端进程内调用 `amazon-image-factory` 核心模块；日常使用只需要启动 TradeHarbor 一个服务。

详细配置见：

```text
amazon-image-factory/README.md
```
11
