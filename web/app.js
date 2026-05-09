const form = document.querySelector("#filter-form");
const resetButton = document.querySelector("#reset-btn");
const statusText = document.querySelector("#status-text");
const resultsBody = document.querySelector("#results-body");
const dataNote = document.querySelector("#data-note");

const statCount = document.querySelector("#stat-count");
const statPrice = document.querySelector("#stat-price");
const statRating = document.querySelector("#stat-rating");
const statPrime = document.querySelector("#stat-prime");

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

function formToQueryString() {
  const data = new FormData(form);
  const params = new URLSearchParams();

  for (const [key, value] of data.entries()) {
    if (!value) {
      continue;
    }
    params.set(key, value);
  }

  const primeCheckbox = form.querySelector('input[name="prime_only"]');
  if (primeCheckbox.checked) {
    params.set("prime_only", "true");
  }

  return params.toString();
}

function renderSummary(summary) {
  statCount.textContent = String(summary.count);
  statPrice.textContent = `$${Number(summary.average_price).toFixed(2)}`;
  statRating.textContent = Number(summary.average_rating).toFixed(1);
  statPrime.textContent = `${summary.prime_ratio}%`;
  if (summary.mode === "serpapi") {
    dataNote.textContent = `当前数据源：${summary.data_source}。本次通过 SerpApi 返回 ${summary.dataset_count} 条 Amazon 商品。`;
    return;
  }

  if (summary.mode === "amazon_live") {
    dataNote.textContent = `当前数据源：${summary.data_source}。本次抓取到 ${summary.dataset_count} 条搜索结果。若 Amazon 返回验证页，页面会提示你稍后重试。`;
    return;
  }

  dataNote.textContent = `当前数据源：${summary.data_source}，共 ${summary.dataset_count} 条演示商品。可试试关键词：${summary.sample_keywords.join(" / ")}`;
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
          <td class="title-cell">${escapeHTML(item.title)}</td>
          <td>${escapeHTML(item.brand)}</td>
          <td>${escapeHTML(item.category)}</td>
          <td>${escapeHTML(item.seller)}</td>
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

async function loadProducts() {
  if (!ensureServerMode()) {
    return;
  }

  const query = formToQueryString();
  statusText.textContent = "正在查询商品列表...";

  try {
    const response = await fetch(`/api/products?${query}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderSummary(payload.summary);
    renderRows(payload.items, payload.summary);
    statusText.textContent = payload.summary.error
      ? `查询完成，但当前没有可展示结果。`
      : `本次共找到 ${payload.summary.count} 个匹配商品。`;
  } catch (error) {
    renderError(
      `查询失败。请确认本地服务正在运行，并且你是通过 http://127.0.0.1:8000 打开的页面。错误信息：${error.message}`
    );
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadProducts();
});

resetButton.addEventListener("click", () => {
  form.reset();
  loadProducts();
});

loadProducts();
