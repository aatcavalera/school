export async function apiFetch(path: string, options: RequestInit = {}) {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (!(options.body instanceof FormData) && options.method && options.method !== "GET") {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (res.status === 401) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Sesi berakhir, silakan login kembali");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Terjadi kesalahan");
  }
  return res.json();
}

export async function login(username: string, password: string) {
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    credentials: "same-origin",
    body: form.toString(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Login gagal");
  }
  return res.json();
}
