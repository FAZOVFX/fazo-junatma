import { initData } from "./telegram.js";

function formatSize(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${bytes} B`;
}

function errorFrom(xhr) {
  let payload = {};
  try { payload = JSON.parse(xhr.responseText || "{}"); } catch (_error) { payload = {}; }
  if (xhr.status === 502 || xhr.status === 503 || !xhr.responseText || xhr.responseText.trim().startsWith("<")) {
    return new Error("Server javob bermadi. Bir necha soniyadan keyin qayta urinib ko‘ring.");
  }
  return new Error(typeof payload.detail === "string" ? payload.detail : "Yuklashda xatolik");
}

async function startUpload(file) {
  const data = initData();
  const headers = { "Content-Type": "application/json" };
  if (data) {
    headers["X-Telegram-Init-Data"] = data;
    headers.Authorization = `tma ${data}`;
  }
  let response;
  try {
    response = await fetch("/api/files/upload/start", {
      method: "POST",
      headers,
      body: JSON.stringify({
        file_name: file.name,
        file_size: file.size,
        content_type: file.type || null,
        init_data: data || "",
      }),
    });
  } catch (_error) {
    throw new Error("Tarmoq xatoligi");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Yuklashda xatolik");
  }
  return payload.upload_url;
}

// The file body is sent as-is (no multipart) so the server can stream it straight to GoFile.
export async function uploadFile(file, onProgress, onCancelReady) {
  const uploadUrl = await startUpload(file);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
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
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText || "{}")); } catch (_error) { reject(errorFrom(xhr)); }
      } else reject(errorFrom(xhr));
    };
    xhr.onerror = () => reject(new Error("Tarmoq xatoligi"));
    xhr.onabort = () => reject(new Error("Bekor qilindi"));
    onCancelReady?.(() => xhr.abort());
    xhr.send(file);
  });
}

export { formatSize };
