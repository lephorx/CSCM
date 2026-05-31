import type { CreateServerPayload } from "./types"

// All requests go to the local Next.js proxy route (/app/api/[...path]/route.ts)
// which runs server-side and injects the BEARER_TOKEN before forwarding to the backend.
const API_BASE = "/api"
const JWT_KEY = "cscm_jwt"

// Encode each path segment but keep slashes so the backend receives e.g. path=/world/region
// not path=%2Fworld%2Fregion
const encodePath = (p: string) =>
  p
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/")

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(JWT_KEY)
}

async function apiCall(endpoint: string, options: RequestInit = {}) {
  const isFormData = options.body instanceof FormData

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }

  if (!isFormData) {
    headers["Content-Type"] = "application/json"
  }

  const token = getStoredToken()
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    cache: "no-store",
  })

  // If the server signals an invalid/expired token, clear it and reload
  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem(JWT_KEY)
    window.location.reload()
    return
  }

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
    tunnel: (id: number) =>
      apiCall(`/servers/${id}/tunnel`, { method: "POST" }),
    subdomain: (id: number, subdomain: string) =>
      apiCall(`/servers/${id}/subdomain`, {
        method: "PATCH",
        body: JSON.stringify({ subdomain }),
      }),
    rename: (id: number, name: string) =>
      apiCall(`/servers/${id}/name`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    changePort: (id: number, port: number) =>
      apiCall(`/servers/${id}/port`, {
        method: "PATCH",
        body: JSON.stringify({ port }),
      }),
    changeRam: (id: number, mem_min: number, mem_max: number) =>
      apiCall(`/servers/${id}/ram`, {
        method: "PATCH",
        body: JSON.stringify({ mem_min, mem_max }),
      }),
    command: (id: number, command: string) =>
      apiCall(`/servers/${id}/command`, {
        method: "POST",
        body: JSON.stringify({ command }),
      }),
  },
  files: {
    list: (id: number, path = "/") =>
      apiCall(`/servers/${id}/files?path=${encodePath(path)}`),
    downloadUrl: (id: number, path: string) =>
      `/api/servers/${id}/files/download?path=${encodePath(path)}`,
    downloadFolderUrl: (id: number, path: string) =>
      `/api/servers/${id}/files/download-folder?path=${encodePath(path)}`,
    upload: async (id: number, files: File[], path = "/") => {
      const formData = new FormData()
      for (const file of files) {
        formData.append("files", file)
      }
      return fetch(`/api/servers/${id}/files/upload?path=${encodePath(path)}`, {
        method: "POST",
        body: formData,
      }).then((r) => r.json())
    },
    delete: (id: number, path: string) =>
      apiCall(`/servers/${id}/files/delete?path=${encodePath(path)}`, {
        method: "DELETE",
      }),
  },
  serverTypes: () => apiCall("/server-types"),
  versions: {
    manifest: async () => {
      const res = await fetch(
        "https://launchermeta.mojang.com/mc/game/version_manifest.json",
        { cache: "force-cache" }
      )
      if (!res.ok) throw new Error("Failed to fetch version manifest")
      const data = await res.json()
      return data.versions as {
        id: string
        type: "release" | "snapshot" | "old_beta" | "old_alpha"
      }[]
    },
  },
  health: () => fetch("/health").then((r) => r.json()),
}

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------

export function saveToken(token: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(JWT_KEY, token)
  }
}

export function clearToken() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(JWT_KEY)
  }
}

// ---------------------------------------------------------------------------
// Auth API (these routes are handled locally by Next.js, not proxied)
// ---------------------------------------------------------------------------

async function authFetch(endpoint: string, options: RequestInit = {}) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }
  const token = getStoredToken()
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(endpoint, { ...options, headers, cache: "no-store" })
  return { ok: res.ok, status: res.status, data: await res.json() }
}

export const authApi = {
  status: () => authFetch("/api/auth/status"),
  setup: (username: string, password: string) =>
    authFetch("/api/auth/setup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string, otp: string) =>
    authFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, otp }),
    }),
  me: () => authFetch("/api/auth/me"),
}
