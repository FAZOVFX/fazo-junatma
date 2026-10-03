export function telegram() {
  return window.Telegram?.WebApp || null;
}

export function setupTelegram() {
  const app = telegram();
  if (!app) return null;
  app.ready();
  app.expand();
  const theme = app.themeParams || {};
  const root = document.documentElement;
  const map = {
    "--bg": theme.bg_color,
    "--text": theme.text_color,
    "--muted": theme.hint_color,
    "--card": theme.secondary_bg_color,
    "--accent": theme.button_color,
    "--accent-ink": theme.button_text_color,
  };
  Object.entries(map).forEach(([key, value]) => {
    if (value) root.style.setProperty(key, value);
  });
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
