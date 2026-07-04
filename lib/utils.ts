import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

import type { ParsedPlayers, PlayerRef, Server } from "@/lib/types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Player list entries come back either as bare username strings or as
// objects (uuid/name pairs from whitelist.json, ops.json, etc).
export function playerName(ref: PlayerRef): string {
  if (typeof ref === "string") return ref
  return ref.name ?? ref.username ?? ref.uuid ?? "unknown"
}

// Parses the `players_raw` string returned by /stats, e.g.
// "There are 2 of a max of 20 players online: Steve, Alex"
export function parsePlayersRaw(raw: string | null | undefined): ParsedPlayers {
  if (!raw) return { online: 0, max: null, names: [] }

  const match = raw.match(/There are (\d+) of a max of (\d+) players online/i)
  const online = match ? parseInt(match[1], 10) : 0
  const max = match ? parseInt(match[2], 10) : null

  const namesMatch = raw.match(/online:\s*(.+)$/i)
  const names = namesMatch
    ? namesMatch[1]
        .split(",")
        .map((n) => n.trim())
        .filter(Boolean)
    : []

  return { online, max, names }
}

// Some endpoints (notably GET /servers/<id>) may omit tunnels/dns_records
// when a server has none, rather than returning an empty array.
export function normalizeServer(raw: Server): Server {
  return {
    ...raw,
    tunnels: raw.tunnels ?? [],
    dns_records: raw.dns_records ?? [],
  }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
