const platformGateway = document.querySelector("#platform-gateway");
const appShell = document.querySelector("#app-shell");
const gatewayStatus = document.querySelector("#gateway-status");
const gatewayBackButton = document.querySelector("#gateway-back-btn");
const tiktokShell = document.querySelector("#tiktok-shell");
const tiktokBackButton = document.querySelector("#tiktok-back-btn");
const videoRemixForm = document.querySelector("#video-remix-form");
const videoRemixStatus = document.querySelector("#video-remix-status");
const videoRemixResult = document.querySelector("#video-remix-result");
const visualDedupeForm = document.querySelector("#visual-dedupe-form");
const visualDedupeStatus = document.querySelector("#visual-dedupe-status");
const visualDedupeResult = document.querySelector("#visual-dedupe-result");
const tiktokModeTabs = document.querySelectorAll("[data-tiktok-target]");
const tiktokModePanels = document.querySelectorAll(".tiktok-mode-panel");
const videoServiceState = document.querySelector("#video-service-state");
const videoServiceStartButton = document.querySelector("#video-service-start-btn");
const videoServiceStopButton = document.querySelector("#video-service-stop-btn");
const platformEntryButtons = document.querySelectorAll("[data-platform-entry]");
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
const pdfOriginForm = document.querySelector("#pdf-origin-form");
const pdfOriginResult = document.querySelector("#pdf-origin-result");
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
const aiBulkCandidates = document.querySelector("#ai-bulk-candidates");
const aiBundleDetail = document.querySelector("#ai-bundle-detail");
const productHunterForm = document.querySelector("#product-hunter-form");
const hunterStatus = document.querySelector("#hunter-status");
const hunterResults = document.querySelector("#hunter-results");
const hunterProductsBody = document.querySelector("#hunter-products-body");
const hunterExportButton = document.querySelector("#hunter-export-btn");
const hunterTotalResults = document.querySelector("#hunter-total-results");
const hunterSampleSize = document.querySelector("#hunter-sample-size");
const hunterAvgPrice = document.querySelector("#hunter-avg-price");
const hunterAvgReview = document.querySelector("#hunter-avg-review");
const hunterBundleCount = document.querySelector("#hunter-bundle-count");
const hunterCompetitionLevel = document.querySelector("#hunter-competition-level");
const hunterNote = document.querySelector("#hunter-note");
const marketGapForm = document.querySelector("#market-gap-form");
const marketGapStatus = document.querySelector("#market-gap-status");
const marketGapResults = document.querySelector("#market-gap-results");
const marketGapBody = document.querySelector("#market-gap-body");
const gapTotalResults = document.querySelector("#gap-total-results");
const gapSampleSize = document.querySelector("#gap-sample-size");
const gapHighCount = document.querySelector("#gap-high-count");
const gapMultipackCount = document.querySelector("#gap-multipack-count");
const gapBundleCount = document.querySelector("#gap-bundle-count");
const gapReplacementCount = document.querySelector("#gap-replacement-count");
const gapTopList = document.querySelector("#gap-top-list");
const gapNote = document.querySelector("#gap-note");
const asinReviewsForm = document.querySelector("#asin-reviews-form");
const reviewsStatus = document.querySelector("#reviews-status");
const reviewsResults = document.querySelector("#reviews-results");
const reviewsBody = document.querySelector("#reviews-body");
const reviewsExportButton = document.querySelector("#reviews-export-btn");
const reviewsAsin = document.querySelector("#reviews-asin");
const reviewsCount = document.querySelector("#reviews-count");
const reviewsPages = document.querySelector("#reviews-pages");
const reviewsAverage = document.querySelector("#reviews-average");
const reviewsLowCount = document.querySelector("#reviews-low-count");
const reviewsVerifiedCount = document.querySelector("#reviews-verified-count");
const reviewsNote = document.querySelector("#reviews-note");
let latestReviews = [];
let latestReviewsAsin = "";
let latestAiProducts = [];
let latestAiKeyword = "";
let latestHunterProducts = [];
let latestHunterKeyword = "";

let pageSize = Number(pageSizeSelect.value || 30);
let activeRequestId = 0;
let currentPage = 1;
let lastQueryString = "";
let hasLoadedAmazonWorkspace = false;



const GRAMS_PER_POUND = 453.59237;
const MILLIMETERS_PER_INCH = 25.4;
let weightInputMode = "grams";
let dimensionInputMode = "millimeters";

function showOnlyWorkspace(target) {
  const pages = {
    gateway: platformGateway,
    amazon: appShell,
    tiktok: tiktokShell,
  };

  Object.entries(pages).forEach(([name, element]) => {
    if (!element) {
      return;
    }
    const isActive = name === target;
    element.hidden = !isActive;
    element.style.display = isActive ? "" : "none";
  });

  document.body.dataset.workspace = target;
  window.scrollTo({ top: 0, behavior: "auto" });
}

function enterAmazonWorkspace() {
  showOnlyWorkspace("amazon");
  if (!hasLoadedAmazonWorkspace) {
    hasLoadedAmazonWorkspace = true;
    updatePagination();
    loadProducts(1);
  }
}

function enterTiktokWorkspace() {
  showOnlyWorkspace("tiktok");
  refreshVideoRemixServiceStatus();
}

function showPlatformGateway() {
  showOnlyWorkspace("gateway");
}

function handlePlatformEntry(platform) {
  if (platform === "amazon") {
    enterAmazonWorkspace();
    return;
  }
  if (platform === "tiktok") {
    enterTiktokWorkspace();
    return;
  }
  gatewayStatus.textContent = "Facebook 模块正在规划中，后续可以接入广告素材、受众测试和投放数据工具。";
}



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

async function generateMadeInChinaPdf() {
  const file = pdfOriginForm.elements.pdf.files[0];
  if (!file) {
    pdfOriginResult.innerHTML = `
      <span>还没有选择文件</span>
      <strong>请选择 PDF</strong>
      <p>上传 Amazon 标签 PDF 后再生成。</p>
    `;
    return;
  }

  const data = new FormData(pdfOriginForm);
  pdfOriginResult.classList.add("is-loading");
  pdfOriginResult.innerHTML = `
    <span>正在处理 PDF...</span>
    <strong>请稍等</strong>
    <p>系统正在识别标签位置并写入 Made In China。</p>
  `;

  try {
    const response = await fetch("/api/pdf-made-in-china", {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    const result = payload.result;
    pdfOriginResult.classList.remove("is-loading");
    pdfOriginResult.innerHTML = `
      <span>生成完成</span>
      <strong>${Number(result.labels_detected || 0).toLocaleString()} 个标签</strong>
      <p>${escapeHTML(result.message || "已生成新 PDF。")}</p>
      <a class="download-link" href="${escapeHTML(result.file_url)}" target="_blank" rel="noreferrer" download>下载新 PDF</a>
    `;
  } catch (error) {
    pdfOriginResult.classList.remove("is-loading");
    pdfOriginResult.innerHTML = `
      <span>PDF 处理失败</span>
      <strong>--</strong>
      <p>${escapeHTML(error.message)}</p>
    `;
  }
}


function renderList(items = []) {
  return `<ul>${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
}

function renderBoolean(value, label) {
  return `<span class="signal-pill ${value ? "is-good" : "is-risk"}">${value ? "适合" : "谨慎"} · ${escapeHTML(label)}</span>`;
}

function renderPackTable(packs = []) {
  if (!packs.length) {
    return `<p class="muted-note">当前不建议直接做多 PCS，因此暂不生成 3/5/10pcs 价格建议。</p>`;
  }
  return `
    <div class="profit-table-wrap">
      <table class="profit-table">
        <thead><tr><th>组合</th><th>建议售价</th><th>单件价</th><th>逻辑</th></tr></thead>
        <tbody>
          ${packs.map((pack) => `<tr><td>${escapeHTML(pack.pack)}</td><td>$${escapeHTML(pack.target_price)}</td><td>$${escapeHTML(pack.unit_price)} · ${escapeHTML(pack.discount_vs_single)}</td><td>${escapeHTML(pack.logic)}</td></tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderBundleFlag(bundleFit = {}) {
  const status = bundleFit.status || "no";
  const className = status === "yes" ? "is-good" : status === "reference" ? "is-reference" : "is-risk";
  return `<span class="bundle-flag ${className}">${escapeHTML(bundleFit.label || "不建议")}</span><small class="bundle-score">${escapeHTML(bundleFit.score || 0)}分</small>`;
}

function renderBundleAction(item) {
  const bundleFit = item.bundle_fit || {};
  if (!bundleFit.can_bundle) {
    return `<span class="muted-note compact-note">${escapeHTML(bundleFit.summary || "不建议")}</span>`;
  }
  return `<button type="button" class="mini-btn bundle-detail-btn" data-asin="${escapeHTML(item.asin)}">查看组合方案</button>`;
}

function renderKeywordMetrics(metrics = {}, competition = {}, bundle = {}) {
  return `
    <div class="keyword-metrics-grid">
      <span>样本数：<strong>${escapeHTML(metrics.sample_size || 0)}</strong></span>
      <span>Top10 平均评论：<strong>${escapeHTML(metrics.top10_avg_reviews || 0)}</strong></span>
      <span>单件占比：<strong>${escapeHTML(metrics.single_ratio || bundle.single_ratio || 0)}%</strong></span>
      <span>竞争分：<strong>${escapeHTML(metrics.competition_score || competition.score || 0)}</strong></span>
      <span>平均 CPC：<strong>${escapeHTML(metrics.estimated_cpc || "暂未接入")}</strong></span>
      <span>可做多 PCS：<strong>${escapeHTML(metrics.viable_bundle_count || 0)}</strong></span>
    </div>
    <p class="muted-note">${escapeHTML(metrics.cpc_note || "CPC 需要接 Amazon Ads 或第三方关键词库；当前先根据 SERP、价格、评论和 Listing 形态判断。")}</p>
  `;
}

function productToBundleParams(item) {
  const params = new URLSearchParams();
  params.set("keyword", latestAiKeyword || "");
  ["asin", "title", "price", "rating", "reviews", "brand", "seller_name", "product_url", "image_url", "pack_count", "category"].forEach((key) => {
    if (item[key] !== undefined && item[key] !== null && item[key] !== "") {
      params.set(key, item[key]);
    }
  });
  return params;
}

function renderAccessoryCards(accessories = []) {
  if (!accessories.length) {
    return `<p class="muted-note">暂时没有搜到合适的低价小配件，可以先用数量组合方案测试。</p>`;
  }
  return `
    <div class="accessory-grid">
      ${accessories.map((item) => `
        <article class="accessory-card">
          ${item.image_url ? `<img src="${escapeHTML(item.image_url)}" alt="">` : ""}
          <div>
            <strong>${item.product_url ? `<a class="product-title-link" href="${escapeHTML(item.product_url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</strong>
            <span>$${escapeHTML(item.price || 0)} · ${escapeHTML(item.asin || "")}</span>
            <p>${escapeHTML(item.why || "低价小件，适合作为配件参考")}</p>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderPlanCard(plan) {
  if (plan.type === "quantity") {
    return `
      <article class="bundle-plan-card">
        <span>方案一</span>
        <h3>${escapeHTML(plan.title)}</h3>
        <p>${escapeHTML(plan.description)}</p>
        ${renderPackTable(plan.packs || [])}
        <p class="plan-reason">${escapeHTML(plan.reason)}</p>
      </article>
    `;
  }
  if (plan.type === "accessory") {
    return `
      <article class="bundle-plan-card">
        <span>方案二</span>
        <h3>${escapeHTML(plan.title)}</h3>
        <p>${escapeHTML(plan.description)}</p>
        <div class="signal-row">
          <span class="signal-pill">建议套装价 $${escapeHTML(plan.target_price || 0)}</span>
          ${(plan.includes || []).map((item) => `<span class="signal-pill">${escapeHTML(item)}</span>`).join("")}
        </div>
        ${renderAccessoryCards(plan.accessories || [])}
        <p class="plan-reason">${escapeHTML(plan.reason)}</p>
      </article>
    `;
  }
  return `
    <article class="bundle-plan-card">
      <span>方案三</span>
      <h3>${escapeHTML(plan.title)}</h3>
      <p>${escapeHTML(plan.description)}</p>
      <div class="signal-row">
        <span class="signal-pill">建议套装价 $${escapeHTML(plan.target_price || 0)}</span>
        ${(plan.includes || []).map((item) => `<span class="signal-pill">${escapeHTML(item)}</span>`).join("")}
      </div>
      <p class="plan-reason">${escapeHTML(plan.reason)}</p>
    </article>
  `;
}

function renderBundlePlan(result) {
  const product = result.product || {};
  bundlePlanStatus.textContent = `已生成 ${escapeHTML(product.asin)} 的组合方案。`;
  bundlePlanContent.innerHTML = `
    <article class="bundle-plan-hero">
      ${product.image_url ? `<img src="${escapeHTML(product.image_url)}" alt="">` : ""}
      <div>
        <span>Selected ASIN</span>
        <h3>${escapeHTML(product.asin)} · ${escapeHTML(product.title)}</h3>
        <p>当前价格 $${escapeHTML(product.price || 0)} · Rating ${escapeHTML(product.rating || 0)} · Review ${Number(product.reviews || 0).toLocaleString()}</p>
      </div>
    </article>
    <div class="bundle-plan-grid">
      ${(result.plans || []).map(renderPlanCard).join("")}
    </div>
    <article class="bundle-plan-card bundle-plan-notes">
      <h3>注意事项</h3>
      ${renderList(result.notes || [])}
    </article>
  `;
}

function openBundlePlan(item) {
  const url = `/bundle_plan.html?${productToBundleParams(item).toString()}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function renderBundleDetail(item) {
  const bundleFit = item.bundle_fit || {};
  aiBundleDetail.hidden = false;
  aiBulkCandidates.innerHTML = `
    <div class="bundle-detail-head">
      <div>
        <span class="bundle-flag is-good">${escapeHTML(bundleFit.label || "可以做多PCS")}</span>
        <h4>${escapeHTML(item.asin)} · ${escapeHTML(item.title)}</h4>
        <p>${escapeHTML(bundleFit.summary || "适合做多件装测试。")}</p>
      </div>
      ${item.image_url ? `<img class="detail-thumb" src="${escapeHTML(item.image_url)}" alt="">` : ""}
    </div>
    <div class="signal-row">
      <span class="signal-pill">当前价格 $${escapeHTML(item.price || 0)}</span>
      <span class="signal-pill">Rating ${escapeHTML(item.rating || 0)}</span>
      <span class="signal-pill">Review ${Number(item.reviews || 0).toLocaleString()}</span>
      <span class="signal-pill">当前 ${escapeHTML(item.pack_count || 1)}pc</span>
    </div>
    <h4>为什么可以尝试</h4>
    ${renderList(bundleFit.reasons || [])}
    ${bundleFit.blockers && bundleFit.blockers.length ? `<h4>仍需注意</h4>${renderList(bundleFit.blockers)}` : ""}
    <h4>建议组合方式</h4>
    ${renderPackTable(bundleFit.recommended_packs || [])}
    <h4>手工上架测试步骤</h4>
    ${renderList(bundleFit.test_plan || [])}
  `;
  aiBundleDetail.scrollIntoView({ behavior: "smooth", block: "start" });
}

function bindBundleDetailButtons() {
  document.querySelectorAll(".bundle-detail-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const item = latestAiProducts.find((product) => product.asin === button.dataset.asin);
      if (item) {
        openBundlePlan(item);
      }
    });
  });
}

function renderCandidateAsins(candidates = []) {
  if (!candidates.length) {
    aiBulkCandidates.innerHTML = `<p class="muted-note">当前没有筛出足够适合做多 PCS 参考的 ASIN。可以先换更明确的耗材关键词，或先手工验证单件需求。</p>`;
    return;
  }
  aiBulkCandidates.innerHTML = `
    <p>这些 ASIN 更适合作为手工上架多件装时的标题、主图、规格和价格参考。</p>
    <div class="ai-product-table-wrap">
      <table class="ai-candidate-table">
        <thead><tr><th>候选分</th><th>ASIN</th><th>标题</th><th>价格</th><th>Review</th><th>当前数量</th><th>为什么可参考</th></tr></thead>
        <tbody>
          ${candidates.map((item) => `
            <tr>
              <td>${escapeHTML(item.score)}</td>
              <td>${escapeHTML(item.asin)}</td>
              <td class="title-cell">${item.product_url ? `<a class="product-title-link" href="${escapeHTML(item.product_url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</td>
              <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
              <td>${Number(item.reviews || 0).toLocaleString()}</td>
              <td>${escapeHTML(item.pack_count || 1)}pc</td>
              <td>${renderList(item.reasons || [])}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAiProducts(products = []) {
  latestAiProducts = products;
  aiProductsBody.innerHTML = products
    .map(
      (item) => `
        <tr class="${item.bundle_fit?.can_bundle ? "bundle-row-yes" : ""}">
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
          <td>${renderBundleFlag(item.bundle_fit || {})}</td>
          <td>${renderBundleAction(item)}</td>
        </tr>
      `
    )
    .join("");
  bindBundleDetailButtons();
}

function renderAiOpportunity(result) {
  latestAiKeyword = result.keyword || latestAiKeyword;
  const competition = result.competition || {};
  const bundle = result.bundle || {};
  const metrics = result.keyword_metrics || {};
  aiResults.hidden = false;
  aiBundleDetail.hidden = true;
  aiOpportunityScore.textContent = Number(metrics.total_results || result.total_results || 0).toLocaleString();
  aiCompetitionScore.textContent = `$${escapeHTML(metrics.top10_avg_price || 0)}`;
  aiCompetitionLevel.textContent = `${escapeHTML(metrics.competition_level || competition.level || "--")} · ${escapeHTML(metrics.competition_score || competition.score || 0)}分`;
  aiRecommendedBundle.textContent = `${escapeHTML(metrics.viable_bundle_count || 0)} 个`;
  aiBundleAnalysis.innerHTML = renderKeywordMetrics(metrics, competition, bundle);
  renderAiProducts(result.products || []);
}

async function runAiOpportunity() {
  const keyword = (new FormData(aiOpportunityForm).get("keyword") || "").trim();
  latestAiKeyword = keyword;
  if (!keyword) {
    aiStatus.textContent = "请输入 Amazon 关键词。";
    return;
  }
  aiResults.hidden = true;
  if (aiBundleDetail) {
    aiBundleDetail.hidden = true;
  }
  aiStatus.textContent = "正在抓取前 50 个商品，并逐个判断是否适合多 PCS 组合装，请稍等...";
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


function renderHunterPriceMap(priceMap = {}) {
  const rows = [
    ["3件装", priceMap["3_pack"]],
    ["5件装", priceMap["5_pack"]],
    ["10件装", priceMap["10_pack"]],
  ].filter(([, value]) => value);
  if (!rows.length) {
    return "--";
  }
  return `<div class="hunter-price-stack">${rows.map(([label, value]) => `<span>${escapeHTML(label)} ${escapeHTML(value)}</span>`).join("")}</div>`;
}

function renderHunterRows(products = []) {
  if (!products.length) {
    hunterProductsBody.innerHTML = `<tr><td colspan="13" class="empty-row">没有获取到产品，请换一个更明确的关键词。</td></tr>`;
    return;
  }
  hunterProductsBody.innerHTML = products.map((item) => {
    const analysis = item.analysis || {};
    const score = Number(analysis.opportunity_score || 0);
    const scoreClass = score >= 75 ? "is-high" : score >= 60 ? "is-mid" : "is-low";
    return `
      <tr class="${analysis.is_good_for_bundle ? "hunter-row-good" : ""}">
        <td>${item.thumbnail ? `<img class="product-thumb" src="${escapeHTML(item.thumbnail)}" alt="">` : ""}</td>
        <td class="title-cell">${item.link ? `<a class="product-title-link" href="${escapeHTML(item.link)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</td>
        <td>${escapeHTML(item.asin)}</td>
        <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
        <td>${escapeHTML(item.rating || "")}</td>
        <td>${Number(item.reviews || 0).toLocaleString()}</td>
        <td>${item.link ? `<a class="mini-link" href="${escapeHTML(item.link)}" target="_blank" rel="noreferrer">打开</a>` : "--"}</td>
        <td><span class="hunter-score ${scoreClass}">${score}</span></td>
        <td><span class="bundle-flag ${analysis.is_good_for_bundle ? "is-good" : "is-risk"}">${analysis.is_good_for_bundle ? "适合" : "谨慎"}</span></td>
        <td>${escapeHTML(analysis.bundle_suggestion || "--")}</td>
        <td>${renderHunterPriceMap(analysis.suggested_price || {})}</td>
        <td>${escapeHTML(analysis.estimated_profit_margin || "--")}</td>
        <td><strong>${escapeHTML(analysis.ai_reason || "")}</strong><p>${escapeHTML(analysis.risk || "")}</p></td>
      </tr>
    `;
  }).join("");
}

function renderHunterResult(result = {}) {
  const summary = result.summary || {};
  latestHunterProducts = result.products || [];
  latestHunterKeyword = result.keyword || latestHunterKeyword;
  hunterResults.hidden = false;
  hunterExportButton.disabled = latestHunterProducts.length === 0;
  hunterTotalResults.textContent = Number(summary.total_results || 0).toLocaleString();
  hunterSampleSize.textContent = Number(summary.sample_size || 0).toLocaleString();
  hunterAvgPrice.textContent = `$${escapeHTML(summary.top10_avg_price || 0)}`;
  hunterAvgReview.textContent = Number(summary.top10_avg_reviews || 0).toLocaleString();
  hunterBundleCount.textContent = Number(summary.bundle_candidate_count || 0).toLocaleString();
  hunterCompetitionLevel.textContent = escapeHTML(summary.competition_level || "--");
  hunterNote.textContent = `单件占比 ${summary.single_ratio || 0}% · 平均 CPC：${summary.estimated_cpc || "暂未接入"} · ${result.notes ? result.notes[0] : ""}`;
  renderHunterRows(latestHunterProducts);
}

async function runProductHunter() {
  const keyword = (new FormData(productHunterForm).get("keyword") || "").trim();
  latestHunterKeyword = keyword;
  if (!keyword) {
    hunterStatus.textContent = "请输入关键词，例如 phone case。";
    return;
  }
  hunterResults.hidden = true;
  hunterExportButton.disabled = true;
  hunterStatus.textContent = "正在执行：关键词搜索 → 获取亚马逊产品 → AI评分 → 输出机会表格...";
  try {
    const response = await fetch(`/api/product-hunter?keyword=${encodeURIComponent(keyword)}&limit=20`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderHunterResult(payload.result);
    hunterStatus.textContent = `分析完成：${keyword}，已输出 ${payload.result.products.length} 个产品机会。`;
  } catch (error) {
    hunterStatus.textContent = `Product Hunter 分析失败：${error.message}`;
  }
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

function exportHunterCsv() {
  if (!latestHunterProducts.length) {
    return;
  }
  const headers = ["图片", "标题", "ASIN", "价格", "评分", "评论数", "链接", "机会评分", "是否适合多件装", "建议组合方式", "3件装", "5件装", "10件装", "预估利润率", "AI分析理由", "风险"];
  const rows = latestHunterProducts.map((item) => {
    const analysis = item.analysis || {};
    const prices = analysis.suggested_price || {};
    return [
      item.thumbnail,
      item.title,
      item.asin,
      item.price ? `$${item.price}` : "",
      item.rating,
      item.reviews,
      item.link,
      analysis.opportunity_score,
      analysis.is_good_for_bundle ? "是" : "否",
      analysis.bundle_suggestion,
      prices["3_pack"],
      prices["5_pack"],
      prices["10_pack"],
      analysis.estimated_profit_margin,
      analysis.ai_reason,
      analysis.risk,
    ];
  });
  const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `amazon_product_hunter_${latestHunterKeyword || "results"}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}


function renderGapBoolean(value) {
  return `<span class="gap-signal ${value ? "is-yes" : "is-no"}">${value ? "有机会" : "一般"}</span>`;
}

function renderGapList(items = []) {
  if (!items.length) {
    return "--";
  }
  return `<ul class="gap-mini-list">${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
}

function renderGapScore(score = 0) {
  const value = Number(score || 0);
  const className = value >= 80 ? "is-hot" : value >= 65 ? "is-good" : value >= 45 ? "is-watch" : "is-cold";
  return `<span class="gap-score ${className}">${value}</span>`;
}

function renderMarketGapRows(products = []) {
  if (!products.length) {
    marketGapBody.innerHTML = `<tr><td colspan="12" class="empty-row">没有识别到商品，请换一个更明确的关键词。</td></tr>`;
    return;
  }
  marketGapBody.innerHTML = products.map((item) => {
    const gap = item.gap || {};
    return `
      <tr class="${Number(gap.score || 0) >= 70 ? "gap-row-strong" : ""}">
        <td>${item.thumbnail ? `<img class="product-thumb" src="${escapeHTML(item.thumbnail)}" alt="">` : ""}</td>
        <td class="title-cell">${item.link ? `<a class="product-title-link" href="${escapeHTML(item.link)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}</td>
        <td>${escapeHTML(item.asin)}</td>
        <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
        <td>${Number(item.reviews || 0).toLocaleString()}</td>
        <td>${renderGapScore(gap.score)}</td>
        <td>${renderGapBoolean(gap.multipack_opportunity)}</td>
        <td>${renderGapBoolean(gap.bundle_opportunity)}</td>
        <td>${renderGapBoolean(gap.replacement_opportunity)}</td>
        <td>${renderGapList(gap.market_gap || [])}</td>
        <td>${renderGapList(gap.risk || [])}</td>
        <td>${renderGapList(gap.recommendation || [])}</td>
      </tr>
    `;
  }).join("");
}

function renderMarketGapResult(result = {}) {
  const summary = result.summary || {};
  marketGapResults.hidden = false;
  gapTotalResults.textContent = Number(summary.total_results || 0).toLocaleString();
  gapSampleSize.textContent = Number(summary.sample_size || 0).toLocaleString();
  gapHighCount.textContent = Number(summary.high_score_count || 0).toLocaleString();
  gapMultipackCount.textContent = Number(summary.multipack_count || 0).toLocaleString();
  gapBundleCount.textContent = Number(summary.bundle_count || 0).toLocaleString();
  gapReplacementCount.textContent = Number(summary.replacement_count || 0).toLocaleString();
  const topGaps = summary.top_market_gaps || [];
  gapTopList.innerHTML = topGaps.length
    ? topGaps.map((item) => `<span>${escapeHTML(item)}</span>`).join("")
    : `<span>暂未发现强供给缺陷，可换更细分关键词</span>`;
  const reviewErrorNote = result.review_errors && result.review_errors.length
    ? ` Review 增强有部分失败，但已自动回退本地规则。`
    : "";
  gapNote.textContent = `单件占比 ${summary.single_ratio || 0}% · Top10 均价 $${summary.avg_price || 0} · Top10 均 Review ${summary.avg_reviews || 0} · 已尝试分析 ${summary.review_analyzed_count || 0} 个 ASIN 的 Review。${reviewErrorNote}`;
  renderMarketGapRows(result.products || []);
}

async function runMarketGapDiscovery() {
  const keyword = (new FormData(marketGapForm).get("keyword") || "").trim();
  if (!keyword) {
    marketGapStatus.textContent = "请输入关键词，例如 phone case。";
    return;
  }
  marketGapResults.hidden = true;
  marketGapStatus.textContent = "正在抓取 Amazon 搜索结果，并分析多件装、组合装、OEM 替代、特殊规格和 Review 痛点...";
  try {
    const response = await fetch(`/api/market-gaps?keyword=${encodeURIComponent(keyword)}&limit=20&review_limit=5`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderMarketGapResult(payload.result);
    marketGapStatus.textContent = `市场空缺分析完成：${keyword}，已分析 ${payload.result.products.length} 个商品。`;
  } catch (error) {
    marketGapStatus.textContent = `市场空缺分析失败：${error.message}`;
  }
}


function renderReviewStars(rating = 0) {
  const value = Number(rating || 0);
  const className = value <= 2 ? "is-bad" : value <= 3 ? "is-mid" : "is-good";
  return `<span class="review-rating ${className}">${value || "--"}</span>`;
}

function renderReviewsRows(reviews = []) {
  if (!reviews.length) {
    reviewsBody.innerHTML = `<tr><td colspan="10" class="empty-row">没有抓到评论。可以换成 Critical/Positive 筛选，或确认 ASIN 是否正确。</td></tr>`;
    return;
  }
  reviewsBody.innerHTML = reviews.map((review) => `
    <tr>
      <td>${escapeHTML(review.page || "")}</td>
      <td>${renderReviewStars(review.rating)}</td>
      <td><strong>${escapeHTML(review.title || "")}</strong></td>
      <td class="review-body-cell">${escapeHTML(review.body || "")}${review.images && review.images.length ? `<p>${review.images.length} 张图片</p>` : ""}</td>
      <td class="review-body-cell review-body-zh-cell">${escapeHTML(review.body_zh || "")}</td>
      <td>${escapeHTML(review.date || "")}</td>
      <td>${escapeHTML(review.author || "")}</td>
      <td>${escapeHTML(review.verified_purchase || "")}</td>
      <td>${escapeHTML(review.helpful_votes || "")}</td>
      <td>${escapeHTML(review.variant || "")}</td>
    </tr>
  `).join("");
}

function renderReviewsResult(result = {}) {
  const summary = result.summary || {};
  latestReviews = result.reviews || [];
  latestReviewsAsin = result.asin || latestReviewsAsin;
  reviewsResults.hidden = false;
  reviewsExportButton.disabled = latestReviews.length === 0;
  reviewsAsin.textContent = escapeHTML(result.asin || "--");
  reviewsCount.textContent = Number(summary.fetched_count || 0).toLocaleString();
  reviewsPages.textContent = `${Number(summary.pages_fetched || 0).toLocaleString()} / ${Number(summary.max_pages || 0).toLocaleString()}`;
  reviewsAverage.textContent = escapeHTML(summary.average_rating || 0);
  reviewsLowCount.textContent = Number(summary.low_rating_count || 0).toLocaleString();
  reviewsVerifiedCount.textContent = Number(summary.verified_count || 0).toLocaleString();
  const moreText = summary.has_more ? "当前达到最大页数但仍可能有更多评论；可提高最大页数继续抓。" : "已抓到当前可分页范围内的评论，或没有下一页。";
  const unsupportedReviewsEngine = summary.reviews_engine_supported === false;
  const sourceText = summary.source === "amazon_product_fallback"
    ? "当前 SerpApi 不支持完整 Reviews 接口，已自动使用商品详情页评论片段兜底"
    : "数据源：amazon_reviews 完整评论接口";
  const translateText = summary.translation_enabled ? "已生成中文评论内容" : "未启用中文翻译";
  const errorText = result.errors && result.errors.length && !unsupportedReviewsEngine
    ? ` 部分页面暂时失败，已展示成功抓到的评论。`
    : "";
  reviewsNote.textContent = `${sourceText} · ${translateText} · 当前展示 ${Number(summary.fetched_count || 0).toLocaleString()} 条 · 筛选：${summary.filter_by_star || "all"} · 排序：${summary.sort_by || "recent"}。${moreText}${errorText}`;
  renderReviewsRows(latestReviews);
}

async function runAsinReviews() {
  const data = new FormData(asinReviewsForm);
  const asin = (data.get("asin") || "").trim();
  if (!asin) {
    reviewsStatus.textContent = "请输入产品 ASIN。";
    return;
  }
  const params = new URLSearchParams();
  for (const [key, value] of data.entries()) {
    if (value) {
      params.set(key, value);
    }
  }
  reviewsResults.hidden = true;
  reviewsExportButton.disabled = true;
  reviewsStatus.textContent = "正在抓取 Amazon 评论，请稍等。页数越多会越慢，也会消耗更多 SerpApi 次数...";
  try {
    const response = await fetch(`/api/asin-reviews?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderReviewsResult(payload.result);
    reviewsStatus.textContent = `评论抓取完成：${payload.result.asin}，共抓到 ${payload.result.reviews.length} 条。`;
  } catch (error) {
    reviewsStatus.textContent = `评论抓取失败：${error.message}`;
  }
}

function exportReviewsCsv() {
  if (!latestReviews.length) {
    return;
  }
  const headers = ["ASIN", "页", "评分", "标题", "评论内容", "中文评论内容", "日期", "作者", "Verified", "Helpful", "变体", "图片数"];
  const rows = latestReviews.map((review) => [
    latestReviewsAsin,
    review.page,
    review.rating,
    review.title,
    review.body,
    review.body_zh,
    review.date,
    review.author,
    review.verified_purchase,
    review.helpful_votes,
    review.variant,
    (review.images || []).length,
  ]);
  const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `amazon_reviews_${latestReviewsAsin || "asin"}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
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
    let payload = {};
    try {
      payload = await response.json();
    } catch (jsonError) {
      payload = {};
    }
    if (!response.ok) {
      throw new Error(payload.error || payload.summary?.error || `HTTP ${response.status}`);
    }
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

async function refreshVideoRemixServiceStatus() {
  if (!videoServiceState) {
    return;
  }
  try {
    const response = await fetch("/api/video-remix-service");
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    const result = payload.result || {};
    videoServiceState.textContent = result.running ? "运行中" : "未启动";
    videoServiceState.classList.toggle("is-running", Boolean(result.running));
    videoServiceState.classList.toggle("is-stopped", !result.running);
    if (videoServiceStartButton) {
      videoServiceStartButton.disabled = Boolean(result.running);
    }
    if (videoServiceStopButton) {
      videoServiceStopButton.disabled = !result.running || !result.managed;
      videoServiceStopButton.title = result.running && !result.managed ? "这个 8010 服务不是页面启动的，不能安全关闭" : "";
    }
  } catch (error) {
    videoServiceState.textContent = "状态未知";
    videoServiceState.classList.remove("is-running");
    videoServiceState.classList.add("is-stopped");
  }
}

async function controlVideoRemixService(action) {
  const label = action === "start" ? "启动中..." : "关闭中...";
  if (videoServiceState) {
    videoServiceState.textContent = label;
  }
  if (videoServiceStartButton) {
    videoServiceStartButton.disabled = true;
  }
  if (videoServiceStopButton) {
    videoServiceStopButton.disabled = true;
  }
  try {
    const response = await fetch("/api/video-remix-service", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    await refreshVideoRemixServiceStatus();
    renderVideoRemixStatus(
      action === "start" ? "8010 已启动" : "8010 已关闭",
      payload.message || "服务状态已更新",
      action === "start" ? "现在可以上传视频进行二创处理。" : "需要处理视频时再启动即可。"
    );
  } catch (error) {
    await refreshVideoRemixServiceStatus();
    renderVideoRemixStatus(
      action === "start" ? "启动失败" : "关闭失败",
      error.message,
      "如果是第一次使用，请先安装依赖：cd video-remix-api && pip install -r requirements.txt，并安装 FFmpeg。"
    );
  }
}

const VIDEO_REMIX_API_BASE = "http://127.0.0.1:8010";
let activeVideoRemixTask = "";
let videoRemixPollTimer = null;
let activeVisualDedupeTasks = [];
let visualDedupePollTimers = {};

function renderVideoRemixStatus(title, message, detail = "") {
  if (!videoRemixStatus) {
    return;
  }
  videoRemixStatus.innerHTML = `
    <span>${escapeHTML(title)}</span>
    <strong>${escapeHTML(message)}</strong>
    ${detail ? `<p>${escapeHTML(detail)}</p>` : ""}
  `;
}

function renderVideoRemixResult(task) {
  if (!videoRemixResult) {
    return;
  }
  const info = task.video_info || {};
  const downloadUrl = task.download_url ? `${VIDEO_REMIX_API_BASE}${task.download_url}` : "";
  videoRemixResult.hidden = false;
  videoRemixResult.innerHTML = `
    <div class="remix-output-grid">
      <article><span>任务 ID</span><strong>${escapeHTML(task.task_id || "--")}</strong></article>
      <article><span>状态</span><strong>${escapeHTML(task.status || "--")}</strong></article>
      <article><span>时长</span><strong>${escapeHTML(info.duration || 0)}s</strong></article>
      <article><span>分辨率</span><strong>${escapeHTML(info.width || 0)}×${escapeHTML(info.height || 0)}</strong></article>
    </div>
    <div class="remix-script-card">
      <span>AI 新英文脚本</span>
      <p>${escapeHTML(task.script || "脚本生成后会显示在这里。")}</p>
    </div>
    ${downloadUrl ? `<a class="primary-btn remix-download" href="${escapeHTML(downloadUrl)}" target="_blank" rel="noreferrer">下载生成视频</a>` : ""}
  `;
}

async function pollVideoRemixTask(taskId) {
  if (!taskId || taskId !== activeVideoRemixTask) {
    return;
  }

  try {
    const response = await fetch(`${VIDEO_REMIX_API_BASE}/task/${encodeURIComponent(taskId)}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    const task = payload.task;
    renderVideoRemixStatus(`进度 ${task.progress || 0}%`, task.message || "正在处理", task.status || "processing");
    renderVideoRemixResult(task);

    if (task.status === "completed") {
      return;
    }
    if (task.status === "failed") {
      renderVideoRemixStatus("处理失败", task.error || task.message || "请查看后端日志", "常见原因：FFmpeg 未安装、依赖未安装、视频格式异常或 TTS 网络不可用。");
      return;
    }
    videoRemixPollTimer = window.setTimeout(() => pollVideoRemixTask(taskId), 1800);
  } catch (error) {
    renderVideoRemixStatus("连接失败", "无法连接 TikTok 视频工厂服务", `${error.message}。请确认 8010 服务已启动。`);
  }
}

function activateTiktokMode(targetId) {
  tiktokModeTabs.forEach((button) => {
    const isActive = button.dataset.tiktokTarget === targetId;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  tiktokModePanels.forEach((panel) => {
    const isActive = panel.id === targetId;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });
}

function renderVisualDedupeStatus(title, message, detail = "") {
  if (!visualDedupeStatus) {
    return;
  }
  visualDedupeStatus.innerHTML = `
    <span>${escapeHTML(title)}</span>
    <strong>${escapeHTML(message)}</strong>
    ${detail ? `<p>${escapeHTML(detail)}</p>` : ""}
  `;
}

function visualTaskCardId(taskId) {
  return `visual-task-${String(taskId || "").replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

function ensureVisualBatchShell() {
  if (!visualDedupeResult) {
    return null;
  }
  visualDedupeResult.hidden = false;
  if (!visualDedupeResult.querySelector(".visual-batch-list")) {
    visualDedupeResult.innerHTML = `
      <div class="visual-batch-header">
        <span>批量处理队列</span>
        <strong>每个视频会独立生成一个 MP4</strong>
        <p>下载时会使用原文件名，并追加 _visual_variant 后缀。</p>
      </div>
      <div class="visual-batch-list"></div>
    `;
  }
  return visualDedupeResult.querySelector(".visual-batch-list");
}

function renderVisualDedupeResult(task) {
  const batchList = ensureVisualBatchShell();
  if (!batchList) {
    return;
  }
  const cardId = visualTaskCardId(task.task_id);
  const info = task.video_info || {};
  const effects = task.effects || {};
  const downloadUrl = task.download_url ? `${VIDEO_REMIX_API_BASE}${task.download_url}` : "";
  const downloadName = task.metadata?.download_filename || "";
  const enabledEffects = [
    effects.effect_zoom ? "微缩放/轻裁切" : "",
    effects.effect_background ? "动态模糊背景" : "",
    effects.effect_color ? "色彩微调" : "",
    effects.effect_speed ? "轻微变速" : "",
    effects.effect_texture ? "颗粒质感" : "",
    effects.effect_vignette ? "暗角光影" : "",
  ].filter(Boolean);
  const cardHTML = `
    <article class="visual-task-card ${task.status === "completed" ? "is-completed" : ""} ${task.status === "failed" ? "is-failed" : ""}" id="${escapeHTML(cardId)}">
      <div class="visual-task-card-head">
        <div>
          <span>${escapeHTML(task.status || "queued")}</span>
          <strong>${escapeHTML(task.original_filename || task.task_id || "--")}</strong>
          ${downloadName ? `<p>输出文件：${escapeHTML(downloadName)}</p>` : ""}
        </div>
        <b>${escapeHTML(task.progress || 0)}%</b>
      </div>
    <div class="remix-output-grid">
      <article><span>任务 ID</span><strong>${escapeHTML(task.task_id || "--")}</strong></article>
      <article><span>原片时长</span><strong>${escapeHTML(info.duration || 0)}s</strong></article>
      <article><span>原片分辨率</span><strong>${escapeHTML(info.width || 0)}×${escapeHTML(info.height || 0)}</strong></article>
      <article><span>当前状态</span><strong>${escapeHTML(task.message || task.status || "--")}</strong></article>
    </div>
    <div class="remix-script-card">
      <span>本次已启用处理</span>
      <div class="effects-chips">
        ${enabledEffects.length ? enabledEffects.map((label) => `<b>${escapeHTML(label)}</b>`).join("") : "<b>仅转码输出</b>"}
      </div>
      <p>系统已按你打开的开关自动随机处理并导出 1080×1920 H264 MP4。建议同一个素材生成多个版本，用于正常的素材 A/B 测试和创意改版。</p>
    </div>
    ${task.error ? `<p class="visual-task-error">${escapeHTML(task.error)}</p>` : ""}
    ${downloadUrl ? `<a class="primary-btn remix-download" href="${escapeHTML(downloadUrl)}" target="_blank" rel="noreferrer" download="${escapeHTML(downloadName)}">下载差异化视频</a>` : ""}
    </article>
  `;
  const existing = batchList.querySelector(`#${CSS.escape(cardId)}`);
  if (existing) {
    existing.outerHTML = cardHTML;
  } else {
    batchList.insertAdjacentHTML("beforeend", cardHTML);
  }
}

async function pollVisualDedupeTask(taskId) {
  if (!taskId || !activeVisualDedupeTasks.includes(taskId)) {
    return;
  }

  try {
    const response = await fetch(`${VIDEO_REMIX_API_BASE}/dedupe-task/${encodeURIComponent(taskId)}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    const task = payload.task;
    renderVisualDedupeStatus(`进度 ${task.progress || 0}%`, task.message || "正在处理", task.status || "processing");
    renderVisualDedupeResult(task);

    if (task.status === "completed") {
      return;
    }
    if (task.status === "failed") {
      return;
    }
    visualDedupePollTimers[taskId] = window.setTimeout(() => pollVisualDedupeTask(taskId), 1600);
  } catch (error) {
    renderVisualDedupeStatus("连接失败", "无法连接 TikTok 视觉差异化服务", `${error.message}。请确认 8010 服务已启动。`);
  }
}

async function submitVisualDedupe(event) {
  event.preventDefault();
  Object.values(visualDedupePollTimers).forEach((timer) => window.clearTimeout(timer));
  visualDedupePollTimers = {};
  const files = Array.from(visualDedupeForm.elements.file.files || []);
  if (!files.length) {
    renderVisualDedupeStatus("缺少视频", "请先选择一个或多个视频", "支持 mp4 / mov / avi / webm。 ");
    return;
  }

  const sourceData = new FormData(visualDedupeForm);
  const data = new FormData();
  for (const [key, value] of sourceData.entries()) {
    if (key !== "file") {
      data.append(key, value);
    }
  }
  files.forEach((file) => data.append("files", file, file.name));

  visualDedupeResult.hidden = true;
  visualDedupeResult.innerHTML = "";
  renderVisualDedupeStatus("正在上传", `${files.length} 个视频正在发送到 8010 服务`, "上传完成后会为每个视频创建独立处理任务。 ");

  try {
    const response = await fetch(`${VIDEO_REMIX_API_BASE}/dedupe-upload-batch`, {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    activeVisualDedupeTasks = (payload.tasks || []).map((task) => task.task_id).filter(Boolean);
    renderVisualDedupeStatus("批量任务已创建", `${activeVisualDedupeTasks.length} 个视频已进入队列`, "正在执行微缩放、背景、色彩、质感层和微变速处理。 ");
    ensureVisualBatchShell();
    activeVisualDedupeTasks.forEach((taskId) => pollVisualDedupeTask(taskId));
  } catch (error) {
    renderVisualDedupeStatus("上传失败", "请确认 TikTok 视频工厂服务正在运行", `${error.message}。可点击右上角启动 8010。`);
  }
}

async function submitVideoRemix(event) {
  event.preventDefault();
  if (videoRemixPollTimer) {
    window.clearTimeout(videoRemixPollTimer);
  }
  const file = videoRemixForm.elements.file.files[0];
  if (!file) {
    renderVideoRemixStatus("缺少视频", "请先选择一个产品视频", "支持 mp4 / mov / webm。 ");
    return;
  }

  const data = new FormData(videoRemixForm);
  videoRemixResult.hidden = true;
  renderVideoRemixStatus("正在上传", "视频正在发送到 8010 服务", "上传完成后会自动轮询处理进度。 ");

  try {
    const response = await fetch(`${VIDEO_REMIX_API_BASE}/upload`, {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    activeVideoRemixTask = payload.task_id;
    renderVideoRemixStatus("任务已创建", `任务 ${payload.task_id} 已进入队列`, "正在开始 AI 脚本、TTS 和视频合成流程。 ");
    pollVideoRemixTask(payload.task_id);
  } catch (error) {
    renderVideoRemixStatus("上传失败", "请确认 TikTok 视频工厂服务正在运行", `${error.message}。启动：cd video-remix-api && uvicorn app.main:app --host 127.0.0.1 --port 8010`);
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

productHunterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runProductHunter();
});

hunterExportButton.addEventListener("click", exportHunterCsv);

marketGapForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runMarketGapDiscovery();
});

asinReviewsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAsinReviews();
});

reviewsExportButton.addEventListener("click", exportReviewsCsv);

exchangeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  convertExchangeRate();
});

pdfOriginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  generateMadeInChinaPdf();
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

platformEntryButtons.forEach((button) => {
  button.addEventListener("click", () => handlePlatformEntry(button.dataset.platformEntry));
});

gatewayBackButton.addEventListener("click", showPlatformGateway);

if (tiktokBackButton) {
  tiktokBackButton.addEventListener("click", showPlatformGateway);
}

if (videoRemixForm) {
  videoRemixForm.addEventListener("submit", submitVideoRemix);
}

if (visualDedupeForm) {
  visualDedupeForm.addEventListener("submit", submitVisualDedupe);
}

tiktokModeTabs.forEach((button) => {
  button.addEventListener("click", () => activateTiktokMode(button.dataset.tiktokTarget));
});

if (videoServiceStartButton) {
  videoServiceStartButton.addEventListener("click", () => controlVideoRemixService("start"));
}

if (videoServiceStopButton) {
  videoServiceStopButton.addEventListener("click", () => controlVideoRemixService("stop"));
}

refreshVideoRemixServiceStatus();

updatePagination();
