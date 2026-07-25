const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, ...data };
}

export function subscribeNewsletter(email) {
  return request("/api/newsletter", { method: "POST", body: JSON.stringify({ email }) });
}

export function createReservation(payload) {
  return request("/api/reservations", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchMenu() {
  return request("/api/menu");
}
