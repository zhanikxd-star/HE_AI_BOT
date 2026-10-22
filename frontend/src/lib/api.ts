const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = window.localStorage.getItem("hr_token");
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${base}${path}`, { ...init, headers });
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    window.localStorage.removeItem("hr_token");
    window.location.href = "/login";
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : "Ошибка запроса");
  }
  return data as T;
}
