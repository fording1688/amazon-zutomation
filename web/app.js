const form = document.querySelector("#filter-form");
const resetButton = document.querySelector("#reset-btn");
const statusText = document.querySelector("#status-text");
const resultsBody = document.querySelector("#results-body");
const dataNote = document.querySelector("#data-note");

const statCount = document.querySelector("#stat-count");
const statPrice = document.querySelector("#stat-price");
const statRating = document.querySelector("#stat-rating");
const statPrime = document.querySelector("#stat-prime");
const statTotal = document.querySelector("#stat-total");
const statPages = document.querySelector("#stat-pages");
const prevPageButton = document.querySelector("#prev-page-btn");
const nextPageButton = document.querySelector("#next-page-btn");
const pageIndicator = document.querySelector("#page-indicator");
const pageSizeSelect = document.querySelector("#page-size-select");
const tabButtons = document.querySelectorAll("[data-tab-target]");
const tabPanels = document.querySelectorAll(".tab-panel");
const amazonResultsPanel = document.querySelector("#amazon-results-panel");
const exchangeForm = document.querySelector("#exchange-form");
const exchangeResult = document.querySelector("#exchange-result");
const swapCurrencyButton = document.querySelector("#swap-currency-btn");
const weightForm = document.querySelector("#weight-form");
const weightResult = document.querySelector("#weight-result");
const swapWeightButton = document.querySelector("#swap-weight-btn");
const dimensionForm = document.querySelector("#dimension-form");
const dimensionResult = document.querySelector("#dimension-result");
const swapDimensionButton = document.querySelector("#swap-dimension-btn");
const aiOpportunityForm = document.querySelector("#ai-opportunity-form");
const aiStatus = document.querySelector("#ai-status");
const aiResults = document.querySelector("#ai-results");
const aiProductsBody = document.querySelector("#ai-products-body");
const aiOpportunityScore = document.querySelector("#ai-opportunity-score");
const aiCompetitionScore = document.querySelector("#ai-competition-score");
const aiCompetitionLevel = document.querySelector("#ai-competition-level");
const aiRecommendedBundle = document.querySelector("#ai-recommended-bundle");
const aiBundleAnalysis = document.querySelector("#ai-bundle-analysis");
const aiProfitAnalysis = document.querySelector("#ai-profit-analysis");
const aiSummary = document.querySelector("#ai-summary");

let pageSize = Number(pageSizeSelect.value || 30);
let activeRequestId = 0;
let currentPage = 1;
let lastQueryString = "";



const GRAMS_PER_POUND = 453.59237;
const MILLIMETERS_PER_INCH = 25.4;
let weightInputMode = "grams";
let dimensionInputMode = "millimeters";

function formatWeight(value, maximumFractionDigits = 4) {
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits,
  });
}

function convertWeight(source = weightInputMode) {
  const gramsInput = weightForm.elements.grams;
  const poundsInput = weightForm.elements.pounds;
  let grams = Number(gramsInput.value || 0);
  let pounds = Number(poundsInput.value || 0);

  if (source === "pounds") {
    grams = pounds * GRAMS_PER_POUND;
    gramsInput.value = grams ? grams.toFixed(2) : "";
  } else {
    pounds = grams / GRAMS_PER_POUND;
    poundsInput.value = pounds ? pounds.toFixed(4) : "";
  }

  weightResult.innerHTML = `
    <span>重量换算结果</span>
    <strong>${formatWeight(grams, 2)} g ≈ ${formatWeight(pounds, 4)} lb</strong>
    <p>换算公式：1 lb = 453.59237 g；1 g = 0.00220462 lb。</p>
  `;
}


function convertDimension(source = dimensionInputMode) {
  const millimetersInput = dimensionForm.elements.millimeters;
  const inchesInput = dimensionForm.elements.inches;
  let millimeters = Number(millimetersInput.value || 0);
  let inches = Number(inchesInput.value || 0);

  if (source === "inches") {
    millimeters = inches * MILLIMETERS_PER_INCH;
    millimetersInput.value = millimeters ? millimeters.toFixed(2) : "";
  } else {
    inches = millimeters / MILLIMETERS_PER_INCH;
    inchesInput.value = inches ? inches.toFixed(4) : "";
  }

  dimensionResult.innerHTML = `
    <span>尺寸换算结果</span>
    <strong>${formatWeight(millimeters, 2)} mm ≈ ${formatWeight(inches, 4)} inch</strong>
    <p>换算公式：1 inch = 25.4 mm。</p>
  `;
}

function activateTab(targetId) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tabTarget === targetId;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  tabPanels.forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === targetId);
  });

  amazonResultsPanel.hidden = targetId !== "amazon-search-panel";
}

function formatCurrencyValue(value) {
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 4,
  });
}

async function convertExchangeRate() {
  const data = new FormData(exchangeForm);
  const params = new URLSearchParams();
  for (const [key, value] of data.entries()) {
    if (value) {
      params.set(key, value);
    }
  }

  exchangeResult.classList.add("is-loading");
  exchangeResult.innerHTML = `
    <span>正在获取汇率...</span>
    <strong>请稍等</strong>
    <p>正在请求实时汇率接口。</p>
  `;

  try {
    const response = await fetch(`/api/exchange?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    const result = payload.result;
    exchangeResult.classList.remove("is-loading");
    exchangeResult.innerHTML = `
      <span>${escapeHTML(result.amount)} ${escapeHTML(result.from)} 可兑换</span>
      <strong>${formatCurrencyValue(result.converted)} ${escapeHTML(result.to)}</strong>
      <p>1 ${escapeHTML(result.from)} = ${formatCurrencyValue(result.rate)} ${escapeHTML(result.to)} · 更新时间 ${escapeHTML(result.timestamp || "未知")}</p>
    `;
  } catch (error) {
    exchangeResult.classList.remove("is-loading");
    exchangeResult.innerHTML = `
      <span>汇率获取失败</span>
      <strong>--</strong>
      <p>${escapeHTML(error.message)}</p>
    `;
  }
}


function renderList(items = []) {
  return `<ul>${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
}

function renderAiProducts(products = []) {
  aiProductsBody.innerHTML = products
    .map(
      (item) => `
        <tr>
          <td>${escapeHTML(item.asin)}</td>
          <td>${item.image_url ? `<img class="product-thumb" src="${escapeHTML(item.image_url)}" alt="">` : ""}</td>
          <td class="title-cell">${item.product_url ? `<a class="product-title-link" href="${escapeHTML(item.product_url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</td>
          <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
          <td>${escapeHTML(item.rating)}</td>
          <td>${Number(item.reviews || 0).toLocaleString()}</td>
          <td>${escapeHTML(item.brand)}</td>
          <td>${escapeHTML(item.seller_name)}</td>
          <td>${escapeHTML(item.seller_id)}</td>
          <td>${item.is_prime ? "Yes" : "No"}</td>
          <td>${escapeHTML(item.bsr)}</td>
          <td>${escapeHTML(item.variant_count || 0)}</td>
          <td>${item.has_multipack ? `${escapeHTML(item.pack_count)}pcs` : "1pc"}</td>
          <td>${escapeHTML(item.category)}</td>
        </tr>
      `
    )
    .join("");
}

function renderAiOpportunity(result) {
  const report = result.report;
  const competition = result.competition;
  const bundle = result.bundle;
  const profit = result.profit;
  aiResults.hidden = false;
  aiOpportunityScore.textContent = String(report.opportunity_score);
  aiCompetitionScore.textContent = String(competition.score);
  aiCompetitionLevel.textContent = competition.level;
  aiRecommendedBundle.textContent = bundle.recommended_bundles.map((item) => `${item}pcs`).join(" / ");

  aiBundleAnalysis.innerHTML = `
    <p><strong>${bundle.has_bundle_gap ? "存在 Bundle 空白市场" : "Bundle 机会需验证"}</strong></p>
    <p>单件/未标注组合占比：${escapeHTML(bundle.single_ratio)}%。</p>
    ${renderList(bundle.reasons)}
  `;

  aiProfitAnalysis.innerHTML = `
    <p>预估基础售价：$${escapeHTML(profit.assumptions.base_price)}；广告费按 ${escapeHTML(profit.assumptions.ad_rate_estimate)} 估算。</p>
    <div class="profit-table-wrap">
      <table class="profit-table">
        <thead><tr><th>组合</th><th>售价</th><th>利润</th><th>利润率</th></tr></thead>
        <tbody>
          ${profit.rows.map((row) => `<tr><td>${escapeHTML(row.bundle)}</td><td>$${escapeHTML(row.price)}</td><td>$${escapeHTML(row.profit)}</td><td>${escapeHTML(row.margin)}%</td></tr>`).join("")}
        </tbody>
      </table>
    </div>
    <p><strong>利润最高：</strong>${escapeHTML(profit.best_bundle.bundle)}，约 $${escapeHTML(profit.best_bundle.profit)}。</p>
  `;

  aiSummary.innerHTML = `
    <p><strong>${escapeHTML(report.recommend_enter)}</strong></p>
    <p>${escapeHTML(report.summary)}</p>
    <p>${escapeHTML(report.price_strategy)}</p>
    ${renderList(report.recommended_playbook)}
    ${result.openai_report ? `<div class="openai-report"><h4>OpenAI 增强报告</h4><p>${escapeHTML(result.openai_report)}</p></div>` : `<p class="muted-note">${escapeHTML(result.openai_error || "当前使用本地规则分析；配置 OPENAI_API_KEY 后可生成更自然的 AI 报告。")}</p>`}
  `;

  renderAiProducts(result.products || []);
}

async function runAiOpportunity() {
  const keyword = (new FormData(aiOpportunityForm).get("keyword") || "").trim();
  if (!keyword) {
    aiStatus.textContent = "请输入 Amazon 关键词。";
    return;
  }
  aiResults.hidden = true;
  aiStatus.textContent = "正在抓取前 50 个商品并进行 AI 机会分析，请稍等...";
  try {
    const response = await fetch(`/api/ai-opportunity?keyword=${encodeURIComponent(keyword)}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderAiOpportunity(payload.result);
    aiStatus.textContent = `分析完成：${keyword}，共分析 ${payload.result.products.length} 个商品。`;
  } catch (error) {
    aiStatus.textContent = `AI发现机会失败：${error.message}`;
  }
}

function renderError(message) {
  statusText.textContent = message;
  resultsBody.innerHTML = `
    <tr>
      <td colspan="12" class="empty-row">${escapeHTML(message)}</td>
    </tr>
  `;
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function ensureServerMode() {
  if (window.location.protocol === "file:") {
    renderError(
      "当前页面是直接打开的 HTML 文件，查询接口不会生效。请先运行 python3 web_app.py，再通过 http://127.0.0.1:8000 打开页面。"
    );
    return false;
  }
  return true;
}

function formToQueryString(page = currentPage) {
  const data = new FormData(form);
  const params = new URLSearchParams();

  for (const [key, value] of data.entries()) {
    if (!value) {
      continue;
    }
    params.set(key, value);
  }

  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return params.toString();
}

function updatePagination(summary = {}) {
  const totalPages = Number(summary.total_pages || 0);
  const totalResults = Number(summary.total_results || 0);
  pageIndicator.textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页 · ${totalResults.toLocaleString()} 条`;
  prevPageButton.disabled = currentPage <= 1;
  nextPageButton.disabled = Boolean(summary.error) || summary.count === 0 || (totalPages > 0 && currentPage >= totalPages);
}

function renderSummary(summary) {
  statCount.textContent = String(summary.count);
  statPrice.textContent = `$${Number(summary.average_price).toFixed(2)}`;
  statRating.textContent = Number(summary.average_rating).toFixed(1);
  statTotal.textContent = Number(summary.total_results || 0).toLocaleString();
  statPages.textContent = String(summary.total_pages || 0);
  statPrime.textContent = `${summary.prime_ratio}%`;
  if (summary.mode === "serpapi") {
    const sellerNote = summary.seller_filter_applied
      ? "已启用卖家分析：系统会逐个 ASIN 查询商品详情，并根据 sold_by / ship_from / other_sellers，并用汉字/拼音关键词匹配卖家信息。"
      : "未启用卖家分析，搜索更快且更省 SerpApi 次数。";
    const noMatchNote = summary.seller_filter_no_match
      ? " 当前没有商品命中卖家地区/城市筛选，下面展示的是已分析过但未命中的卖家信息，方便排查。"
      : "";
    dataNote.textContent = `当前数据源：${summary.data_source}。总共约 ${Number(summary.total_results || 0).toLocaleString()} 条，按每页 ${summary.page_size || pageSize} 条共 ${summary.total_pages || 0} 页；当前第 ${summary.page || currentPage} 页返回 ${summary.dataset_count} 条。${sellerNote}${noMatchNote}`;
    return;
  }

  if (summary.mode === "amazon_live") {
    dataNote.textContent = `当前数据源：${summary.data_source}。本次抓取到 ${summary.dataset_count} 条搜索结果。若 Amazon 返回验证页，页面会提示你稍后重试。`;
    return;
  }

  dataNote.textContent = `当前数据源：${summary.data_source}，共 ${summary.dataset_count} 条演示商品。可试试关键词：${summary.sample_keywords.join(" / ")}`;
}


function renderSellerRegion(item) {
  const regionMap = {
    china: "中国卖家",
    us: "美国卖家",
    unknown: "未知",
  };
  const label = regionMap[item.seller_region] || "";
  const city = item.seller_city ? ` / ${escapeHTML(item.seller_city)}` : "";
  const basis = item.seller_match_basis ? ` title="${escapeHTML(item.seller_match_basis)}"` : "";
  return label ? `<span class="region-pill region-${escapeHTML(item.seller_region)}"${basis}>${label}${city}</span>` : "";
}

function renderRows(items, summary) {
  if (!items.length) {
    resultsBody.innerHTML = `
      <tr>
        <td colspan="12" class="empty-row">${escapeHTML(summary.error || `没有找到符合条件的商品。当前只在 ${summary.dataset_count} 条本地演示数据里查询，可试试：${summary.sample_keywords.join(" / ")}`)}</td>
      </tr>
    `;
    return;
  }

  resultsBody.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHTML(item.asin)}</td>
          <td>${item.image_url ? `<img class="product-thumb" src="${escapeHTML(item.image_url)}" alt="">` : ""}</td>
          <td class="title-cell">${item.product_url ? `<a class="product-title-link" href="${escapeHTML(item.product_url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</td>
          <td>${escapeHTML(item.category)}</td>
          <td>${escapeHTML(item.seller)}</td>
          <td>${escapeHTML(item.ship_from)}</td>
          <td>${renderSellerRegion(item)}</td>
          <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
          <td>${escapeHTML(item.rating)}</td>
          <td>${escapeHTML(item.reviews)}</td>
          <td>${escapeHTML(item.sales)}</td>
          <td>${escapeHTML(item.is_prime)}</td>
        </tr>
      `
    )
    .join("");
}

async function loadProducts(page = currentPage) {
  if (!ensureServerMode()) {
    return;
  }

  currentPage = page;
  const query = formToQueryString(currentPage);
  lastQueryString = query;
  const params = new URLSearchParams(query);
  updatePagination();
  const requestId = ++activeRequestId;
  statusText.textContent = params.get("seller_region") || params.get("seller_city")
    ? "正在查询商品并分析卖家信息，这会比普通搜索慢一点..."
    : "正在查询商品列表...";

  try {
    const response = await fetch(`/api/products?${query}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (requestId !== activeRequestId) {
      return;
    }
    renderSummary(payload.summary);
    renderRows(payload.items, payload.summary);
    updatePagination(payload.summary);
    statusText.textContent = payload.summary.seller_filter_no_match
      ? `查询完成，但当前卖家筛选没有命中；下方展示已分析样本。`
      : payload.summary.error
        ? `查询完成，但当前没有可展示结果。`
        : `第 ${currentPage} 页显示 ${payload.summary.count} 个商品，共约 ${Number(payload.summary.total_results || 0).toLocaleString()} 个结果。`;
  } catch (error) {
    if (requestId !== activeRequestId) {
      return;
    }
    renderError(
      `查询失败。请确认本地服务正在运行，并且你是通过当前本地服务地址打开的页面。错误信息：${error.message}`
    );
  }
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activateTab(button.dataset.tabTarget);
    if (button.dataset.tabTarget === "utility-panel") {
      convertExchangeRate();
      convertWeight();
      convertDimension();
    }
  });
});

aiOpportunityForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAiOpportunity();
});

exchangeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  convertExchangeRate();
});

swapCurrencyButton.addEventListener("click", () => {
  const from = exchangeForm.elements.from;
  const to = exchangeForm.elements.to;
  const nextFrom = to.value;
  to.value = from.value;
  from.value = nextFrom;
  convertExchangeRate();
});

weightForm.elements.grams.addEventListener("input", () => {
  weightInputMode = "grams";
  convertWeight("grams");
});

weightForm.elements.pounds.addEventListener("input", () => {
  weightInputMode = "pounds";
  convertWeight("pounds");
});

swapWeightButton.addEventListener("click", () => {
  weightInputMode = weightInputMode === "grams" ? "pounds" : "grams";
  const input = weightInputMode === "grams" ? weightForm.elements.grams : weightForm.elements.pounds;
  input.focus();
  convertWeight(weightInputMode);
});

dimensionForm.elements.millimeters.addEventListener("input", () => {
  dimensionInputMode = "millimeters";
  convertDimension("millimeters");
});

dimensionForm.elements.inches.addEventListener("input", () => {
  dimensionInputMode = "inches";
  convertDimension("inches");
});

swapDimensionButton.addEventListener("click", () => {
  dimensionInputMode = dimensionInputMode === "millimeters" ? "inches" : "millimeters";
  const input = dimensionInputMode === "millimeters" ? dimensionForm.elements.millimeters : dimensionForm.elements.inches;
  input.focus();
  convertDimension(dimensionInputMode);
});

convertWeight();
convertDimension();

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadProducts(1);
});

resetButton.addEventListener("click", () => {
  form.reset();
  activeRequestId += 1;
  currentPage = 1;
  loadProducts(1);
});

prevPageButton.addEventListener("click", () => {
  if (currentPage <= 1) {
    return;
  }
  loadProducts(currentPage - 1);
});

nextPageButton.addEventListener("click", () => {
  loadProducts(currentPage + 1);
});

pageSizeSelect.addEventListener("change", () => {
  pageSize = Number(pageSizeSelect.value || 30);
  loadProducts(1);
});

updatePagination();
loadProducts(1);
