import type { CreateServerPayload } from "./types"

// In the browser, always use the relative proxy path (/api/*) so requests
// go through Next.js and never hit the backend directly (avoids CORS).
// On the server (SSR/SSG) we call the backend directly with the bearer token.
const IS_SERVER = typeof window === "undefined"

const API_BASE = IS_SERVER
  ? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000"}/api`
  : "/api"

const BEARER_TOKEN = process.env.BEARER_TOKEN ?? ""

async function apiCall(endpoint: string, options: RequestInit = {}) {
  const isFormData = options.body instanceof FormData

  const headers: Record<string, string> = {
    Authorization: `Bearer ${BEARER_TOKEN}`,
    ...(options.headers as Record<string, string>),
  }

  if (!isFormData) {
    headers["Content-Type"] = "application/json"
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    cache: "no-store",
  })

  if (!res.ok) {
    let message = `API error: ${res.status}`
    try {
      const body = await res.json()
      message = body.message ?? body.error ?? message
    } catch {
      // ignore parse error
    }
    throw new Error(message)
  }

  return res.json()
}

export const api = {
  servers: {
    list: () => apiCall("/servers"),
    create: (data: CreateServerPayload) =>
      apiCall("/servers", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: number) => apiCall(`/servers/${id}`, { method: "DELETE" }),
    stats: (id: number) => apiCall(`/servers/${id}/stats`),
    logs: (id: number) => apiCall(`/servers/${id}/logs`),
  },
  control: {
    start: (id: number) => apiCall(`/servers/${id}/start`, { method: "POST" }),
    stop: (id: number) => apiCall(`/servers/${id}/stop`, { method: "POST" }),
    restart: (id: number) =>
      apiCall(`/servers/${id}/restart`, { method: "POST" }),
    kill: (id: number) => apiCall(`/servers/${id}/kill`, { method: "POST" }),
    command: (id: number, command: string) =>
      apiCall(`/servers/${id}/command`, {
        method: "POST",
        body: JSON.stringify({ command }),
      }),
  },
  files: {
    list: (id: number, path = "/") =>
      apiCall(`/servers/${id}/files?path=${encodeURIComponent(path)}`),
    downloadUrl: (id: number, path: string) =>
      `${
        IS_SERVER
          ? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000"}/api`
          : "/api"
      }/servers/${id}/files/download?path=${encodeURIComponent(path)}`,
    upload: async (id: number, file: File, path = "/") => {
      const formData = new FormData()
      formData.append("file", file)
      const uploadBase = IS_SERVER
        ? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000"}/api`
        : "/api"
      const headers: Record<string, string> = {}
      if (IS_SERVER) headers["Authorization"] = `Bearer ${BEARER_TOKEN}`
      return fetch(
        `${uploadBase}/servers/${id}/files/upload?path=${encodeURIComponent(path)}`,
        {
          method: "POST",
          headers,
          body: formData,
        }
      ).then((r) => r.json())
    },
    delete: (id: number, path: string) =>
      apiCall(`/servers/${id}/files/delete?path=${encodeURIComponent(path)}`, {
        method: "DELETE",
      }),
  },
  serverTypes: () => apiCall("/server-types"),
  health: () => fetch("/health").then((r) => r.json()),
}
