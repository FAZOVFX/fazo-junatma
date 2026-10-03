export function telegram() {
  return window.Telegram?.WebApp || null;
}

export function setupTelegram() {
  const app = telegram();
  if (!app) return null;
  app.ready();
  app.expand();
  return app;
}

function fromPageUrl() {
  const hash = new URLSearchParams((location.hash || "").replace(/^#/, ""));
  const search = new URLSearchParams(location.search);
  return hash.get("tgWebAppData") || search.get("tgWebAppData") || "";
}

export function initData() {
  const app = telegram();
  if (app?.ready) app.ready();
  return app?.initData || fromPageUrl();
}

export function showPopup(message) {
  const app = telegram();
  if (app?.showAlert) {
    app.showAlert(message);
    return;
  }
  window.alert(message);
}
