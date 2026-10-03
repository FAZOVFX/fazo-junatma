import { initData, setupTelegram, showPopup, telegram } from "./telegram.js";
import { formatSize, uploadFile } from "./upload.js";

const screen = document.querySelector("#screen");
const title = document.querySelector("#title");
const topbar = document.querySelector("#top");
const back = document.querySelector("#back");
const modal = document.querySelector("#modal");
const modalBody = document.querySelector("#modal-body");
const modalYes = document.querySelector("#modal-yes");
const modalNo = document.querySelector("#modal-no");

const state = { me: null };
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

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function ask(text, yes, no) {
  modalBody.textContent = text;
  modalYes.textContent = yes;
  modalNo.textContent = no;
  modal.classList.add("open");
  return new Promise((resolve) => {
    const close = (value) => {
      modal.classList.remove("open");
      modalYes.onclick = null;
      modalNo.onclick = null;
      resolve(value);
    };
    modalYes.onclick = () => close(true);
    modalNo.onclick = () => close(false);
  });
}

function show(name, label) {
  const bare = name === "upload" || name === "done" || name === "open";
  topbar.hidden = bare;
  title.textContent = label;
  screen.replaceChildren();
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && (parsed.hostname === "gofile.io" || parsed.hostname.endsWith(".gofile.io"));
  } catch (_error) {
    return false;
  }
}

function bindExternal(anchor, url) {
  anchor.addEventListener("click", (event) => {
    const app = telegram();
    if (!app) return;
    event.preventDefault();
    const desktop = ["tdesktop", "web", "weba", "macos", "unknown"].includes(app.platform || "");
    if (desktop) {
      window.open(url, "_blank", "noopener");
      return;
    }
    if (app.openLink) app.openLink(url);
    else window.open(url, "_blank", "noopener");
  });
}

function linkButton(label, url, primary) {
  const anchor = h("a", primary ? "btn primary" : "btn dark", label);
  if (!safeUrl(url)) {
    anchor.href = "#";
    anchor.addEventListener("click", (event) => event.preventDefault());
    return anchor;
  }
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  bindExternal(anchor, url);
  return anchor;
}

function fileCode() {
  const query = new URLSearchParams(location.search).get("file");
  if (query && /^[a-f0-9]{12}$/.test(query)) return query;
  const start = telegram()?.initDataUnsafe?.start_param || "";
  if (start.startsWith("f_") && /^[a-f0-9]{12}$/.test(start.slice(2))) return start.slice(2);
  return "";
}

function screenName() {
  const screen = new URLSearchParams(location.search).get("screen");
  if (screen) return screen;
  const hash = (location.hash || "").replace(/^#/, "");
  if (!hash || hash.includes("tgWebAppData=") || hash.includes("=")) return "upload";
  return hash;
}

function docIcon() {
  return h("div", "doc");
}

async function publicFile(code) {
  show("open", "Fayl");
  const panel = h("section", "panel center");
  try {
    const file = await api(`/api/share/${code}`);
    panel.append(docIcon());
    panel.append(h("h2", "file-name", file.file_name));
    panel.append(h("p", "size", file.file_size_text));
    const actions = h("div", "stack");
    if (file.download_url) actions.append(linkButton("⬇ Yuklab olish", file.download_url, true));
    if (file.browser_url) actions.append(linkButton("Brauzerda ochish", file.browser_url, false));
    if (!file.download_url) actions.append(h("p", "error", "Yuklab olish havolasi yo‘q."));
    panel.append(actions);
  } catch (error) {
    panel.append(h("p", "error", error.message));
  }
  screen.append(panel);
}

function renderUpload(me) {
  show("upload", "Fayl yuborish");
  const panel = h("section", "panel center");
  panel.append(h("p", "emoji", "🚀"));
  panel.append(h("h2", "", "Fayl yuborish"));
  panel.append(h("p", "lead", "Istalgan hajmdagi fayl. Yuklangach yuklab olish linki botga yuboriladi."));
  if (me?.access_text) panel.append(h("p", "pill", `🎁 ${me.access_text}`));

  const input = document.createElement("input");
  input.type = "file";
  input.className = "file-input";
  const drop = h("label", "drop", "Faylni shu yerga tashlang yoki bosib tanlang");
  drop.append(input);
  const progress = h("div", "stack");
  progress.hidden = true;
  const status = h("p", "ok", "");
  const bar = h("div", "bar");
  const fill = document.createElement("span");
  bar.append(fill);
  const cancel = h("button", "btn dark", "Bekor qilish");
  cancel.type = "button";
  progress.append(status, bar, cancel);

  async function begin(file) {
    if (!file) return;
    if (!initData()) {
      panel.append(h("p", "error", "Fayl yuborilmadi. Botdagi «Fayl yuborish» tugmasini bosing. Sayt manzilini brauzerda ochsangiz, fayl tanlash ishlamaydi."));
      return;
    }
    drop.hidden = true;
    progress.hidden = false;
    status.textContent = file.name;
    cancel.onclick = () => uploadCancel?.();
    try {
      const result = await uploadFile(file, (event) => {
        uploadCancel = event.cancel;
        fill.style.width = `${event.percent}%`;
        status.textContent = `${event.percent}% · ${formatSize(event.loaded)} / ${formatSize(event.total)}`;
      });
      success(result);
    } catch (error) {
      panel.append(h("p", "error", error.message));
      drop.hidden = false;
      progress.hidden = true;
    }
  }

  input.onchange = () => begin(input.files?.[0]);
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("over");
    begin(event.dataTransfer?.files?.[0]);
  });

  const files = h("button", "btn dark", "Mening fayllarim");
  files.type = "button";
  files.onclick = () => openScreen("files");
  panel.append(drop, progress, files);
  screen.append(panel);
}

function success(file) {
  show("done", "Tayyor");
  const panel = h("section", "panel center");
  panel.append(h("p", "emoji", "🚀"));
  panel.append(h("h2", "", "Fayl yuborish"));
  if (state.me?.access_text) panel.append(h("p", "pill", `🎁 ${state.me.access_text}`));
  const bar = h("div", "bar");
  const fill = document.createElement("span");
  fill.style.width = "100%";
  bar.append(fill);
  panel.append(bar);
  panel.append(h("p", "ok", "✅ Yuklandi. Link botga yuborildi."));
  const link = file.share_url || file.page_url || "";
  if (link) panel.append(h("div", "link-box", link));
  const actions = h("div", "stack");
  const copy = h("button", "btn primary", "Nusxalash");
  copy.type = "button";
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(link);
    } catch (_error) {
      const area = document.createElement("textarea");
      area.value = link;
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    showPopup("Nusxalandi.");
  };
  const share = h("button", "btn dark", "Telegramda ulashish");
  share.type = "button";
  share.onclick = () => {
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent("Faylni oching")}`;
    const app = telegram();
    if (app?.openTelegramLink) app.openTelegramLink(url);
    else window.open(url, "_blank", "noopener");
  };
  const again = h("button", "btn dark", "Yana fayl");
  again.type = "button";
  again.onclick = () => renderUpload(state.me);
  if (link) actions.append(copy, share);
  actions.append(again);
  panel.append(actions);
  screen.append(panel);
}

async function filesScreen() {
  show("files", "Mening fayllarim");
  const data = await api("/api/files");
  screen.append(h("p", "muted", `Balans: ${money(data.balance_uzs)}`));
  if (!data.items.length) screen.append(h("p", "muted", "Hozircha fayl yo‘q."));
  data.items.forEach((file) => {
    const item = h("article", "card");
    item.append(h("p", "file-name", file.file_name));
    item.append(h("p", "muted", `${file.file_size_text} · ${file.remaining_text} · ${file.status_label}`));
    const row = h("div", "stack");
    if (file.status === "active") {
      const open = h("button", "btn primary", "Ochish");
      open.type = "button";
      open.onclick = () => openOwned(file.id);
      const extend = h("button", "btn dark", "1 kunga uzaytirish · 5 000 so‘m");
      extend.type = "button";
      extend.onclick = () => extendFile(file.id);
      row.append(open, extend);
    }
    const remove = h("button", "btn danger", "O‘chirish");
    remove.type = "button";
    remove.onclick = () => removeOne(file.id);
    row.append(remove);
    item.append(row);
    screen.append(item);
  });
}

async function openOwned(id) {
  const file = await api(`/api/files/${id}`);
  show("open", "Fayl");
  const panel = h("section", "panel center");
  panel.append(docIcon());
  panel.append(h("h2", "file-name", file.file_name));
  panel.append(h("p", "size", file.file_size_text));
  const actions = h("div", "stack");
  actions.append(linkButton("⬇ Yuklab olish", file.download_url, true));
  actions.append(linkButton("Brauzerda ochish", file.browser_url || file.download_url, false));
  panel.append(actions);
  screen.append(panel);
}

async function removeOne(id) {
  const ok = await ask("Faylni o‘chirishni tasdiqlaysizmi?", "Ha, o‘chirish", "Bekor qilish");
  if (!ok) return;
  await api(`/api/files/${id}?confirm=true`, { method: "DELETE" });
  showPopup("Fayl yopildi.");
  await filesScreen();
}

async function extendFile(id) {
  const quote = await api(`/api/files/${id}/extend`, { method: "POST", json: { confirm: false } });
  if (!quote.enough) {
    show("extend", "Uzaytirish");
    const card = h("section", "card");
    card.append(h("pre", "", quote.message));
    const pay = h("button", "btn primary", "Balansni to‘ldirish");
    pay.type = "button";
    pay.onclick = () => openScreen("payment");
    card.append(pay);
    screen.append(card);
    return;
  }
  const ok = await ask(quote.confirm_text, "Tasdiqlash", "Bekor qilish");
  if (!ok) return;
  await api(`/api/files/${id}/extend`, {
    method: "POST",
    json: { confirm: true, idempotency_key: quote.idempotency_key },
  });
  showPopup("Fayl 24 soatga uzaytirildi.");
  await filesScreen();
}

async function openScreen(name) {
  try {
    if (name === "upload" || name === "home") return renderUpload(state.me);
    if (!initData()) {
      show(name, "Junatma");
      screen.append(h("p", "", "Bu bo‘lim Telegram ichida ochiladi."));
      return;
    }
    if (!state.me) state.me = await api("/api/me");
    if (name === "files") return await filesScreen();
    if (name === "wallet" || name === "payment" || name === "premium") return renderUpload(state.me);
    if (name === "help" || name === "referral" || name === "admin") return renderUpload(state.me);
  } catch (error) {
    screen.append(h("p", "error", error.message));
  }
}

back.onclick = () => renderUpload(state.me);

async function boot() {
  const code = fileCode();
  if (code) {
    await publicFile(code);
    return;
  }
  if (initData()) {
    try {
      state.me = await api("/api/me");
    } catch (error) {
      renderUpload(null);
      screen.append(h("p", "error", error.message));
      return;
    }
  }
  const name = screenName();
  if (name === "files") await openScreen("files");
  else renderUpload(state.me);
}

boot();
