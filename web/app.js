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

let pageSize = Number(pageSizeSelect.value || 30);
let activeRequestId = 0;
let currentPage = 1;
let lastQueryString = "";

function renderError(message) {
  statusText.textContent = message;
  resultsBody.innerHTML = `
    <tr>
      <td colspan="13" class="empty-row">${escapeHTML(message)}</td>
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
        <td colspan="13" class="empty-row">${escapeHTML(summary.error || `没有找到符合条件的商品。当前只在 ${summary.dataset_count} 条本地演示数据里查询，可试试：${summary.sample_keywords.join(" / ")}`)}</td>
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
          <td class="title-cell">${escapeHTML(item.title)}</td>
          <td>${escapeHTML(item.category)}</td>
          <td>${escapeHTML(item.seller)}</td>
          <td>${escapeHTML(item.ship_from)}</td>
          <td>${renderSellerRegion(item)}</td>
          <td>${item.price ? `$${escapeHTML(item.price)}` : ""}</td>
          <td>${escapeHTML(item.rating)}</td>
          <td>${escapeHTML(item.reviews)}</td>
          <td>${escapeHTML(item.sales)}</td>
          <td>${escapeHTML(item.is_prime)}</td>
          <td>${item.product_url ? `<a href="${escapeHTML(item.product_url)}" target="_blank" rel="noreferrer">打开</a>` : ""}</td>
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
        : `第 ${currentPage} 页共找到 ${payload.summary.count} 个商品。`;
  } catch (error) {
    if (requestId !== activeRequestId) {
      return;
    }
    renderError(
      `查询失败。请确认本地服务正在运行，并且你是通过当前本地服务地址打开的页面。错误信息：${error.message}`
    );
  }
}

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
