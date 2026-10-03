import { initData } from "./telegram.js";

function formatSize(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${bytes} B`;
}

export function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.open("POST", "/api/files/upload");
    const data = initData();
    if (data) {
      xhr.setRequestHeader("X-Telegram-Init-Data", data);
      xhr.setRequestHeader("Authorization", `tma ${data}`);
    }
    const started = Date.now();
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const ratio = event.loaded / event.total;
      const seconds = Math.max((Date.now() - started) / 1000, 0.001);
      const speed = event.loaded / seconds;
      const left = speed > 0 ? (event.total - event.loaded) / speed : 0;
      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent: Math.round(ratio * 100),
        speed,
        left,
      });
    };
    xhr.onload = () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText || "{}"); } catch (_error) { payload = {}; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
      else reject(new Error(typeof payload.detail === "string" ? payload.detail : "Yuklashda xatolik"));
    };
    xhr.onerror = () => reject(new Error("Tarmoq xatoligi"));
    xhr.onabort = () => reject(new Error("Bekor qilindi"));
    xhr.send(form);
    onProgress.cancel = () => xhr.abort();
  });
}

export { formatSize };
