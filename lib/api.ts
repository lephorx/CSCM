import type { CreateServerPayload } from "./types"

// All requests go to the local Next.js proxy route (/app/api/[...path]/route.ts)
// which forwards the caller's JWT (from localStorage) on to the CSCM backend.
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
    get: (id: number) => apiCall(`/servers/${id}`),
    create: (data: CreateServerPayload) =>
      apiCall("/servers", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: number) => apiCall(`/servers/${id}`, { method: "DELETE" }),
    stats: (id: number) => apiCall(`/servers/${id}/stats`),
    progress: (id: number) => apiCall(`/servers/${id}/progress`),
    logs: (id: number, tail = 200) =>
      apiCall(`/servers/${id}/logs?tail=${tail}`),
  },
  properties: {
    get: (id: number) => apiCall(`/servers/${id}/properties`),
    update: (id: number, properties: Record<string, string>) =>
      apiCall(`/servers/${id}/properties`, {
        method: "PATCH",
        body: JSON.stringify({ properties }),
      }),
  },
  players: {
    list: (id: number) => apiCall(`/servers/${id}/players`),
    whitelistAdd: (id: number, username: string) =>
      apiCall(`/servers/${id}/whitelist`, {
        method: "POST",
        body: JSON.stringify({ username }),
      }),
    whitelistRemove: (id: number, username: string) =>
      apiCall(`/servers/${id}/whitelist`, {
        method: "DELETE",
        body: JSON.stringify({ username }),
      }),
    opAdd: (id: number, username: string) =>
      apiCall(`/servers/${id}/ops`, {
        method: "POST",
        body: JSON.stringify({ username }),
      }),
    opRemove: (id: number, username: string) =>
      apiCall(`/servers/${id}/ops`, {
        method: "DELETE",
        body: JSON.stringify({ username }),
      }),
    bans: (id: number) => apiCall(`/servers/${id}/bans`),
    banAdd: (id: number, username: string, reason?: string) =>
      apiCall(`/servers/${id}/bans`, {
        method: "POST",
        body: JSON.stringify({ username, reason }),
      }),
    banRemove: (id: number, username: string) =>
      apiCall(`/servers/${id}/bans/${encodeURIComponent(username)}`, {
        method: "DELETE",
      }),
    kick: (id: number, username: string, reason?: string) =>
      apiCall(`/servers/${id}/kick`, {
        method: "POST",
        body: JSON.stringify({ username, reason }),
      }),
    history: (id: number) => apiCall(`/servers/${id}/players/history`),
    getData: (id: number, username: string, refresh = false) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/data${
          refresh ? "?refresh=true" : ""
        }`
      ),
    clearInventory: (id: number, username: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/inventory`,
        {
          method: "DELETE",
        }
      ),
    clearInventorySlot: (id: number, username: string, slot: number) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/inventory/${slot}`,
        {
          method: "DELETE",
        }
      ),
    addInventoryItem: (
      id: number,
      username: string,
      body: { item_id: string; count?: number; slot?: number }
    ) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/inventory`,
        {
          method: "POST",
          body: JSON.stringify(body),
        }
      ),
    clearEnderchest: (id: number, username: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/enderchest`,
        {
          method: "DELETE",
        }
      ),
    clearEnderchestSlot: (id: number, username: string, slot: number) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/enderchest/${slot}`,
        {
          method: "DELETE",
        }
      ),
    addEnderchestItem: (
      id: number,
      username: string,
      body: { item_id: string; count?: number; slot?: number }
    ) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/enderchest`,
        {
          method: "POST",
          body: JSON.stringify(body),
        }
      ),
    // ── Per-player action endpoints ────────────────────────────────────────
    setGameMode: (id: number, username: string, game_mode: number) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/gamemode`,
        { method: "POST", body: JSON.stringify({ game_mode }) }
      ),
    killPlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/kill`, {
        method: "POST",
      }),
    healPlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/heal`, {
        method: "POST",
      }),
    starvePlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/starve`, {
        method: "POST",
      }),
    feedPlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/feed`, {
        method: "POST",
      }),
    getPosition: (id: number, username: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/position`
      ),
    teleport: (id: number, username: string, x: number, y: number, z: number) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/teleport`,
        { method: "POST", body: JSON.stringify({ x, y, z }) }
      ),
    whitelistPlayer: (id: number, username: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/whitelist`,
        { method: "POST" }
      ),
    banPlayer: (id: number, username: string, reason?: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/ban`, {
        method: "POST",
        body: JSON.stringify(reason ? { reason } : {}),
      }),
    unbanPlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/ban`, {
        method: "DELETE",
      }),
    opPlayer: (id: number, username: string) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/op`, {
        method: "POST",
      }),
    getStatistics: (id: number, username: string, refresh = false) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/statistics${
          refresh ? "?refresh=true" : ""
        }`
      ),
    resetData: (id: number, username: string, targets: string[]) =>
      apiCall(`/servers/${id}/players/${encodeURIComponent(username)}/data`, {
        method: "DELETE",
        body: JSON.stringify({ targets }),
      }),
    addEffect: (
      id: number,
      username: string,
      body: {
        effect: string
        seconds?: number
        amplifier?: number
        hide_particles?: boolean
      }
    ) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/effects`,
        { method: "POST", body: JSON.stringify(body) }
      ),
    clearAllEffects: (id: number, username: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/effects`,
        { method: "DELETE" }
      ),
    clearEffect: (id: number, username: string, effect: string) =>
      apiCall(
        `/servers/${id}/players/${encodeURIComponent(username)}/effects/${encodeURIComponent(effect)}`,
        { method: "DELETE" }
      ),
  },
  backups: {
    list: (id: number) => apiCall(`/servers/${id}/backups`),
    create: (id: number, type: "zip" | "zfs" = "zip") =>
      apiCall(`/servers/${id}/backups`, {
        method: "POST",
        body: JSON.stringify({ type }),
      }),
    delete: (id: number, backupId: number) =>
      apiCall(`/servers/${id}/backups/${backupId}`, { method: "DELETE" }),
    restore: (id: number, backupId: number) =>
      apiCall(`/servers/${id}/backups/${backupId}/restore`, {
        method: "POST",
      }),
    downloadUrl: (id: number, backupId: number) =>
      `/api/servers/${id}/backups/${backupId}/download`,
    download: async (id: number, backupId: number): Promise<Blob> => {
      const token = getStoredToken()
      const res = await fetch(
        `/api/servers/${id}/backups/${backupId}/download`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          cache: "no-store",
        }
      )
      if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem(JWT_KEY)
        window.location.reload()
        throw new Error("Unauthorized")
      }
      if (!res.ok) {
        let message = `Download failed: ${res.status}`
        try {
          const body = await res.json()
          message = body.message ?? body.error ?? message
        } catch {
          /* ignore */
        }
        throw new Error(message)
      }
      return res.blob()
    },
    getSchedule: (id: number) => apiCall(`/servers/${id}/backups/schedule`),
    setSchedule: (
      id: number,
      schedule: {
        cron: string
        retention: number
        enabled: boolean
        backup_type?: string
      }
    ) =>
      apiCall(`/servers/${id}/backups/schedule`, {
        method: "PUT",
        body: JSON.stringify(schedule),
      }),
    deleteSchedule: (id: number) =>
      apiCall(`/servers/${id}/backups/schedule`, { method: "DELETE" }),
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
    changeVersion: (
      id: number,
      version?: string,
      loader_version?: string | null
    ) =>
      apiCall(`/servers/${id}/version`, {
        method: "PATCH",
        body: JSON.stringify({
          ...(version ? { version } : {}),
          ...(loader_version !== undefined ? { loader_version } : {}),
        }),
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
    upload: async (
      id: number,
      files: File[],
      path = "/",
      filename?: string
    ) => {
      const formData = new FormData()
      for (const file of files) {
        formData.append("files", file)
      }
      let url = `/api/servers/${id}/files/upload?path=${encodePath(path)}`
      if (filename) url += `&filename=${encodeURIComponent(filename)}`
      const token = getStoredToken()
      return fetch(url, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then((r) => r.json())
    },
    delete: (id: number, path: string) =>
      apiCall(`/servers/${id}/files/delete?path=${encodePath(path)}`, {
        method: "DELETE",
      }),
  },
  serverTypes: () => apiCall("/server-types"),
  console: {
    streamUrl: (id: number) => {
      const token = getStoredToken() ?? ""
      return `/api/servers/${id}/console/stream?token=${encodeURIComponent(token)}`
    },
  },
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
    fabricLoaders: async () => {
      const res = await fetch("/api/loader-versions?loader=fabric")
      if (!res.ok) throw new Error("Failed to fetch Fabric loader versions")
      return res.json() as Promise<{ id: string; stable: boolean }[]>
    },
    forgeVersions: async (mcVersion: string) => {
      const res = await fetch(
        `/api/loader-versions?loader=forge&mcVersion=${encodeURIComponent(mcVersion)}`
      )
      if (!res.ok) throw new Error("Failed to fetch Forge versions")
      return res.json() as Promise<{
        versions: string[]
        latest: string | null
      }>
    },
  },
  health: () => fetch("/health").then((r) => r.json()),
  defaults: {
    getProperties: () => apiCall("/defaults/properties"),
    putProperties: (properties: Record<string, string>) =>
      apiCall("/defaults/properties", {
        method: "PUT",
        body: JSON.stringify({ properties }),
      }),
    patchProperties: (properties: Record<string, string>) =>
      apiCall("/defaults/properties", {
        method: "PATCH",
        body: JSON.stringify({ properties }),
      }),
    deleteProperties: (keys?: string[]) =>
      apiCall("/defaults/properties", {
        method: "DELETE",
        body: keys?.length ? JSON.stringify({ keys }) : undefined,
      }),
  },
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
