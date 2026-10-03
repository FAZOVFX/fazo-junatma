import { initData, setupTelegram, showPopup, telegram } from "./telegram.js";
import { formatSize, uploadFile } from "./upload.js";

const screen = document.querySelector("#screen");
const title = document.querySelector("#title");
const back = document.querySelector("#back");
const modal = document.querySelector("#modal");
const modalBody = document.querySelector("#modal-body");
const modalYes = document.querySelector("#modal-yes");
const modalNo = document.querySelector("#modal-no");

const state = { me: null, screen: "home" };
let uploadCancel = null;

setupTelegram();

function money(amount) {
  const sign = amount < 0 ? "-" : "";
  const body = Math.abs(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${body} so‘m`;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const data = initData();
  if (data) {
    headers.set("X-Telegram-Init-Data", data);
    headers.set("Authorization", `tma ${data}`);
  }
  let body = options.body;
  if (options.json) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { method: options.method || "GET", headers, body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload.detail === "string" ? payload.detail : "Xatolik yuz berdi.";
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function ask(text, yes, no) {
  modalBody.textContent = text;
  modalYes.textContent = yes;
  modalNo.textContent = no;
  modal.hidden = false;
  return new Promise((resolve) => {
    const close = (value) => {
      modal.hidden = true;
      modalYes.onclick = null;
      modalNo.onclick = null;
      resolve(value);
    };
    modalYes.onclick = () => close(true);
    modalNo.onclick = () => close(false);
  });
}

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function show(name, label) {
  state.screen = name;
  title.textContent = label;
  back.hidden = name === "home";
  screen.replaceChildren();
}

function menuButton(label, target) {
  const button = h("button", "menu-btn", label);
  button.type = "button";
  button.onclick = () => openScreen(target);
  return button;
}

function home() {
  show("home", "Bosh sahifa");
  const me = state.me;
  const card = h("section", "card");
  card.append(
    h("p", "muted", "👤 User"),
    h("div", "stat", ""),
  );
  const name = h("strong", "", me.first_name || "Foydalanuvchi");
  card.append(name);
  card.append(h("p", "", `💰 Balans: ${me.balance_text}`));
  card.append(h("p", "", `💎 Obuna: ${me.remaining_text} qoldi`));
  card.append(h("p", "muted", me.subscription_label));
  if (me.is_trial) card.append(h("p", "", "🆓 Bepul muddat"));
  const menu = h("div", "menu");
  [
    ["📤 Fayl yuklash", "upload"],
    ["📁 Mening fayllarim", "files"],
    ["💰 Balans", "wallet"],
    ["💎 Premium", "premium"],
    ["👥 Referal", "referral"],
    ["💳 To‘lov", "payment"],
    ["ℹ️ Yordam", "help"],
  ].forEach(([label, target]) => menu.append(menuButton(label, target)));
  if (me.is_admin) menu.append(menuButton("👑 Admin panel", "admin"));
  screen.append(card, menu);
}

async function uploadScreen() {
  show("upload", "Fayl yuklash");
  const card = h("section", "card");
  card.append(h("h2", "", "📤 Fayl yuklash"));
  const picker = h("button", "btn primary", "Fayl tanlash");
  const input = document.createElement("input");
  input.type = "file";
  const progress = h("div", "stack");
  progress.hidden = true;
  const name = h("p", "file-name", "");
  const meta = h("p", "muted", "");
  const bar = h("div", "bar");
  const fill = document.createElement("span");
  bar.append(fill);
  const cancel = h("button", "btn ghost", "Bekor qilish");
  progress.append(name, meta, bar, cancel);
  picker.onclick = () => input.click();
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    picker.hidden = true;
    progress.hidden = false;
    name.textContent = file.name;
    const tracker = {};
    cancel.onclick = () => uploadCancel?.();
    try {
      const result = await uploadFile(file, (event) => {
        uploadCancel = event.cancel;
        fill.style.width = `${event.percent}%`;
        meta.textContent = `${formatSize(event.loaded)} / ${formatSize(event.total)} · ${event.percent}% · ${formatSize(event.speed)}/s · ${Math.ceil(event.left)} s`;
      });
      tracker.done = result;
      success(result);
    } catch (error) {
      card.append(h("p", "error", error.message));
      picker.hidden = false;
    }
  };
  card.append(picker, input, progress);
  screen.append(card);
}

function success(file) {
  show("done", "Tayyor");
  const card = h("section", "card");
  card.append(h("h2", "", "✅ Fayl muvaffaqiyatli yuklandi!"));
  card.append(h("p", "", "📄 Fayl:"));
  card.append(h("p", "file-name", file.file_name));
  card.append(h("p", "", "📦 Hajmi:"));
  card.append(h("p", "", file.file_size_text));
  card.append(h("p", "", "⏳ Amal qilish muddati:"));
  card.append(h("p", "", "24 soat"));
  const actions = h("div", "stack");
  actions.append(linkButton("⬇️ Yuklab olish", file.download_url));
  actions.append(linkButton("🌐 Brauzerda ochish", file.browser_url || file.download_url));
  const mine = h("button", "btn ghost", "📁 Mening fayllarim");
  mine.onclick = () => openScreen("files");
  actions.append(mine);
  card.append(actions);
  screen.append(card);
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && (parsed.hostname === "gofile.io" || parsed.hostname.endsWith(".gofile.io"));
  } catch (_error) {
    return false;
  }
}

function linkButton(label, url) {
  const button = h("button", "btn primary", label);
  button.disabled = !safeUrl(url);
  button.onclick = () => {
    if (!safeUrl(url)) return;
    const app = telegram();
    if (app?.openLink) app.openLink(url);
    else window.open(url, "_blank", "noopener");
  };
  return button;
}

async function filesScreen() {
  show("files", "Mening fayllarim");
  const data = await api("/api/files");
  const card = h("section", "card");
  card.append(h("h2", "", "📁 Mening fayllarim"));
  card.append(h("p", "", `💰 Balans: ${money(data.balance_uzs)}`));
  screen.append(card);
  const selected = new Set();
  const list = h("div", "stack");
  data.items.forEach((file) => {
    const item = h("article", "card");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "check";
    box.onchange = () => {
      if (box.checked) selected.add(file.id);
      else selected.delete(file.id);
    };
    item.append(h("p", "file-name", `📄 ${file.file_name}`));
    item.append(h("p", "", `📦 Hajmi: ${file.file_size_text}`));
    item.append(h("p", "", `⏳ Qolgan vaqt: ${file.remaining_text}`));
    item.append(h("p", "", `🟢 Status: ${file.status_label}`));
    const row = h("div", "stack");
    if (file.status === "active") {
      const open = h("button", "btn primary", "🔗 Ochish");
      open.onclick = () => openFile(file.id);
      const extend = h("button", "btn ghost", "⏰ 1 KUNGA UZAYTIRISH");
      extend.onclick = () => extendFile(file.id);
      row.append(open, extend);
    }
    const remove = h("button", "btn danger", "🗑️ O‘chirish");
    remove.onclick = () => removeOne(file.id);
    row.append(remove, box);
    item.append(row);
    list.append(item);
  });
  if (!data.items.length) screen.append(h("p", "muted", "Hozircha fayl yo‘q."));
  const manage = h("button", "btn ghost", "🗑️ Fayllarni boshqarish");
  const all = h("button", "btn danger", "🗑️ Barchasini o‘chirish");
  all.onclick = () => removeMany([...data.items.map((file) => file.id)]);
  manage.onclick = () => removeMany([...selected]);
  screen.append(list, manage, all);
}

async function openFile(id) {
  const file = await api(`/api/files/${id}`);
  show("open", "Fayl");
  const card = h("section", "card");
  card.append(h("p", "file-name", file.file_name));
  card.append(linkButton("⬇️ Yuklab olish", file.download_url));
  card.append(linkButton("🌐 Brauzerda ochish", file.browser_url));
  screen.append(card);
}

async function removeOne(id) {
  const ok = await ask("⚠️ Faylni o‘chirishni tasdiqlaysizmi?", "✅ Ha, o‘chirish", "❌ Bekor qilish");
  if (!ok) return;
  const result = await api(`/api/files/${id}?confirm=true`, { method: "DELETE" });
  showPopup(result.message || "Fayl yopildi.");
  await filesScreen();
}

async function removeMany(ids) {
  if (!ids.length) {
    showPopup("Fayl tanlanmagan.");
    return;
  }
  const ok = await ask("Tanlangan fayllarni o‘chirishni tasdiqlaysizmi?", "✅ Ha, o‘chirish", "❌ Bekor qilish");
  if (!ok) return;
  await api("/api/files/delete-multiple", { method: "POST", json: { file_ids: ids, confirm: true } });
  await filesScreen();
}

async function extendFile(id) {
  const quote = await api(`/api/files/${id}/extend`, { method: "POST", json: { confirm: false } });
  if (!quote.enough) {
    const card = h("section", "card");
    show("extend", "Uzaytirish");
    card.append(h("pre", "", quote.message));
    const pay = h("button", "btn primary", "💳 Balansni to‘ldirish");
    pay.onclick = () => openScreen("payment");
    card.append(pay);
    screen.append(card);
    return;
  }
  const ok = await ask(quote.confirm_text, "✅ Tasdiqlash", "❌ Bekor qilish");
  if (!ok) return;
  await api(`/api/files/${id}/extend`, {
    method: "POST",
    json: { confirm: true, idempotency_key: quote.idempotency_key },
  });
  showPopup("Fayl 24 soatga uzaytirildi.");
  await filesScreen();
}

async function walletScreen() {
  show("wallet", "Balans");
  const wallet = await api("/api/wallet");
  const tx = await api("/api/wallet/transactions");
  const card = h("section", "card");
  card.append(h("h2", "", "💰 Balans"));
  card.append(h("p", "", wallet.balance_text));
  card.append(h("p", "muted", `Uzaytirish: ${wallet.extension_price_text}`));
  const pay = h("button", "btn primary", "💳 Balansni to‘ldirish");
  pay.onclick = () => openScreen("payment");
  card.append(pay);
  screen.append(card);
  tx.items.forEach((item) => {
    const row = h("article", "card");
    row.append(h("p", "", `${item.type}: ${item.amount_text}`));
    row.append(h("p", "muted", item.description || ""));
    screen.append(row);
  });
}

async function premiumScreen() {
  show("premium", "Premium");
  const card = h("section", "card");
  card.append(h("h2", "", "💎 Premium"));
  card.append(h("p", "", "15 000 so‘m / 30 kun"));
  card.append(h("p", "", `Status: ${state.me.subscription_label}`));
  card.append(h("p", "", `⏳ ${state.me.remaining_text}`));
  if (state.me.is_trial) {
    card.append(h("p", "", "🆓 Bepul muddat"));
    card.append(h("p", "", "7 kun"));
  }
  const pay = h("button", "btn primary", "💳 Premium uchun to‘lash");
  pay.onclick = async () => {
    await api("/api/payments", { method: "POST", json: { type: "premium" } });
    showPopup("To‘lov yaratildi. Chekni bot chatiga yuboring.");
    await paymentScreen();
  };
  card.append(pay);
  screen.append(card);
}

async function referralScreen() {
  show("referral", "Referal");
  const data = await api("/api/referral");
  const card = h("section", "card");
  card.append(h("h2", "", "👥 Referal"));
  card.append(h("pre", "", `🎁 Har bir yangi odam uchun:\n+1 kun\n\n👤 Taklif qilinganlar:\n${data.invited_count} ta\n\n🎁 Olingan bonus:\n${data.bonus_days} kun\n\n🔗 Sizning referal havolangiz:\n\n${data.link}`));
  const share = h("button", "btn primary", "📤 Ulashish");
  const copy = h("button", "btn ghost", "📋 Nusxa olish");
  share.onclick = () => {
    const url = `https://t.me/share/url?url=${encodeURIComponent(data.link)}`;
    const app = telegram();
    if (app?.openTelegramLink) app.openTelegramLink(url);
    else window.open(url, "_blank", "noopener");
  };
  copy.onclick = async () => {
    await navigator.clipboard.writeText(data.link);
    showPopup("Havola nusxalandi.");
  };
  card.append(h("div", "row", ""));
  const row = h("div", "row");
  row.append(share, copy);
  card.append(row);
  screen.append(card);
}

async function paymentScreen() {
  show("payment", "To‘lov");
  const data = await api("/api/payments");
  const card = h("section", "card");
  card.append(h("pre", "", data.card_text));
  const presets = h("div", "stack");
  data.topup_presets_uzs.forEach((amount) => {
    const button = h("button", "btn ghost", money(amount));
    button.onclick = () => createTopup(amount);
    presets.append(button);
  });
  const custom = document.createElement("input");
  custom.type = "number";
  custom.min = "1000";
  custom.placeholder = "Boshqa summa";
  const customBtn = h("button", "btn primary", "Boshqa summa");
  customBtn.onclick = () => createTopup(Number(custom.value));
  card.append(presets, custom, customBtn);
  screen.append(card);
  data.payments.forEach((payment) => {
    const row = h("article", "card");
    row.append(h("p", "", `${payment.amount_text} · ${payment.status}`));
    row.append(h("p", "muted", payment.description || payment.type));
    screen.append(row);
  });
}

async function createTopup(amount) {
  if (!amount) return;
  await api("/api/payments", { method: "POST", json: { type: "wallet_topup", amount_uzs: amount } });
  showPopup("To‘lov kutilmoqda. Chek skrinshotini bot chatiga yuboring.");
  await paymentScreen();
}

async function helpScreen() {
  show("help", "Yordam");
  const card = h("section", "card");
  card.append(h("pre", "", `ℹ️ Yordam

Faylni Mini App orqali yuklang. Yangi fayl 24 soat saqlanadi.
Uzaytirish: 5 000 so‘m = +24 soat. Vaqt qolgan muddatga qo‘shiladi.
Premium: 15 000 so‘m / 30 kun.
Yangi foydalanuvchi bir marta 7 kun oladi.
Har bir yangi referal +1 kun.
Balans faqat fayl uzaytirish uchun.
To‘lov kartaga o‘tkaziladi va chek skrinshoti yuboriladi.
Admin tasdiqlaguncha to‘lov kutiladi. 30 daqiqa taxminiy vaqt.`));
  screen.append(card);
}

async function adminScreen() {
  show("admin", "Admin");
  const stats = await api("/api/admin/statistics");
  const storage = await api("/api/admin/storage");
  const card = h("section", "card");
  card.append(h("h2", "", "👑 Admin panel"));
  card.append(h("pre", "", `Foydalanuvchilar: ${stats.users_total}
Kutilayotgan to‘lov: ${stats.payments_pending}
Faol fayllar: ${storage.active_files}
Faol hajm: ${storage.active_size_text}
Limit: ${storage.configured_limit_text}
Usage: ${storage.usage_percent}%
Remaining: ${storage.remaining_text}`));
  screen.append(card);
}

async function openScreen(name) {
  try {
    if (name === "home") return home();
    if (name === "upload") return uploadScreen();
    if (name === "files") return await filesScreen();
    if (name === "wallet") return await walletScreen();
    if (name === "premium") return premiumScreen();
    if (name === "referral") return await referralScreen();
    if (name === "payment") return await paymentScreen();
    if (name === "help") return helpScreen();
    if (name === "admin") return await adminScreen();
  } catch (error) {
    screen.append(h("p", "error", error.message));
  }
}

back.onclick = () => openScreen("home");

async function boot() {
  if (!initData()) {
    show("home", "FAZO JUNATMA");
    screen.append(h("p", "", "Bu ilova Telegram ichida ochiladi."));
    return;
  }
  try {
    state.me = await api("/api/me");
    const hash = (location.hash || "#home").slice(1);
    await openScreen(hash || "home");
  } catch (error) {
    show("home", "FAZO JUNATMA");
    screen.append(h("p", "error", error.message));
  }
}

boot();
