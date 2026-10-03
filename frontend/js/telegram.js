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

export function initData() {
  return telegram()?.initData || "";
}

export function showPopup(message) {
  const app = telegram();
  if (app?.showAlert) {
    app.showAlert(message);
    return;
  }
  window.alert(message);
}
