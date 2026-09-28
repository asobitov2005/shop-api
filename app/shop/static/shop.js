const products = new Map();
const quantities = new Map();
const grid = document.querySelector("#product-grid");
const notice = document.querySelector("#notice");
const checkoutButton = document.querySelector("#checkout-button");
const productImages = {
  choy: "/static/products/tea.svg",
  qahva: "/static/products/coffee.svg",
  asal: "/static/products/honey.svg",
};

const formatMoney = (value) => `${new Intl.NumberFormat("uz-UZ").format(Number(value))} so‘m`;
const escapeText = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function renderProducts() {
  const list = [...products.values()];
  document.querySelector("#catalog-count").textContent = `${list.length} ta mahsulot`;
  if (!list.length) {
    grid.innerHTML = '<p class="empty-state">Hozircha mahsulotlar yo‘q.</p>';
    return;
  }
  grid.innerHTML = list.map((product) => {
    const quantity = quantities.get(product.id) || 0;
    const stock = Number(product.stock);
    const stockLabel = stock === 0 ? "Tugagan" : stock < 5 ? `Faqat ${stock} ta qoldi` : "Mavjud";
    const image = productImages[String(product.name).toLocaleLowerCase("uz")] || "/static/products/item.svg";
    return `<article class="product-card">
      <div class="product-art"><img src="${image}" alt="${escapeText(product.name)}"><span class="stock ${stock > 0 && stock < 5 ? "low" : ""}">${stockLabel}</span></div>
      <h3>${escapeText(product.name)}</h3>
      <div class="product-bottom"><span class="price"><strong>${formatMoney(product.price)}</strong><del>${formatMoney(product.original_price)}</del><small>/ dona</small></span>
        <div class="stepper" aria-label="${escapeText(product.name)} miqdori">
          <button type="button" data-action="minus" data-id="${product.id}" aria-label="Kamaytirish" ${quantity === 0 ? "disabled" : ""}>−</button>
          <output>${quantity}</output>
          <button type="button" data-action="plus" data-id="${product.id}" aria-label="Qo‘shish" ${quantity >= stock ? "disabled" : ""}>+</button>
        </div>
      </div>
    </article>`;
  }).join("");
  updateSummary();
}

function updateSummary() {
  let total = 0;
  let count = 0;
  for (const [id, quantity] of quantities) {
    const product = products.get(id);
    if (product && quantity > 0) {
      total += Number(product.price) * quantity;
      count += quantity;
    }
  }
  document.querySelector("#order-total").textContent = formatMoney(total);
  document.querySelector("#item-count").textContent = count;
  checkoutButton.disabled = count === 0;
}

async function loadProducts() {
  try {
    const response = await fetch("/products?page=1&page_size=100");
    if (!response.ok) throw new Error("Mahsulotlarni yuklab bo‘lmadi.");
    const page = await response.json();
    page.items.forEach((product) => products.set(product.id, product));
    renderProducts();
  } catch (error) {
    grid.innerHTML = `<p class="empty-state">${escapeText(error.message)} Sahifani yangilab ko‘ring.</p>`;
    document.querySelector("#catalog-count").textContent = "";
  }
}

grid.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const product = products.get(id);
  if (!product) return;
  const current = quantities.get(id) || 0;
  const next = button.dataset.action === "plus" ? Math.min(current + 1, product.stock) : Math.max(current - 1, 0);
  quantities.set(id, next);
  notice.textContent = "";
  renderProducts();
});

checkoutButton.addEventListener("click", async () => {
  const items = [...quantities.entries()]
    .filter(([, quantity]) => quantity > 0)
    .map(([product_id, quantity]) => ({ product_id, quantity }));
  if (!items.length) return;
  checkoutButton.disabled = true;
  checkoutButton.classList.add("busy");
  checkoutButton.firstChild.textContent = "Buyurtma yuborilmoqda… ";
  notice.textContent = "";
  try {
    const response = await fetch("/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const order = await response.json();
    if (!response.ok) throw new Error(order.detail || "Buyurtma yaratilmadi. Mahsulot sonini tekshirib qayta urinib ko‘ring.");
    if (!order.payment_url) throw new Error("Buyurtma yaratildi, ammo Click to‘lovi hozircha sozlanmagan.");
    window.location.assign(order.payment_url);
  } catch (error) {
    notice.textContent = typeof error.message === "string" ? error.message : "Mahsulot soni o‘zgargan bo‘lishi mumkin. Qayta urinib ko‘ring.";
    checkoutButton.disabled = false;
    checkoutButton.classList.remove("busy");
    checkoutButton.firstChild.textContent = "Click orqali to‘lash ";
  }
});

loadProducts();
