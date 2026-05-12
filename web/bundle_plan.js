const statusEl = document.querySelector("#bundle-plan-status");
const contentEl = document.querySelector("#bundle-plan-content");

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderList(items = []) {
  return `<ul>${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
}

function renderPackTable(packs = []) {
  if (!packs.length) {
    return `<p class="muted-note">当前没有生成数量组合建议。</p>`;
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

function renderAccessoryCards(accessories = []) {
  if (!accessories.length) {
    return `<p class="muted-note">暂时没有搜到足够干净的低价小配件，可以先用数量组合或场景组合测试。</p>`;
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
  statusEl.textContent = `已生成 ${product.asin || "当前 ASIN"} 的组合方案。`;
  contentEl.innerHTML = `
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

async function loadBundlePlan() {
  const params = new URLSearchParams(window.location.search);
  if (!params.get("asin") || !params.get("title")) {
    statusEl.textContent = "缺少 ASIN 或标题，请从 AI发现机会列表点击查看组合方案。";
    return;
  }
  statusEl.textContent = `正在围绕 ${params.get("asin")} 搜索配件并生成组合方案...`;
  try {
    const response = await fetch(`/api/bundle-plan?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    renderBundlePlan(payload.result);
  } catch (error) {
    statusEl.textContent = `组合方案生成失败：${error.message}`;
  }
}

loadBundlePlan();
