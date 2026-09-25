export interface Tunnel {
  address: string
  local_port: number
  external_port: number
}

export type RuntimeStatus =
  | "not_created"
  | "stopped"
  | "starting"
  | "healthy"
  | "unhealthy"
  | "running"

export interface Server {
  id: number
  name: string
  slug: string
  type: string
  version: string
  loader_version?: string | null
  port: number
  mem_min?: number
  mem_max?: number
  status: string
  runtime_status: RuntimeStatus
  created_at: string
  tunnels: Tunnel[]
  local_only?: boolean
}

export interface ServerStats {
  running: boolean
  status: string
  health: string
  cpu_percent: number
  memory_usage_bytes: number
  memory_limit_bytes: number
  // Java: raw RCON `list` output, e.g. "There are 2 of a max of 20 players online: Steve, Alex"
  players_raw?: string | null
  // Bedrock: no RCON, so this is reconstructed from container log connect/disconnect lines instead
  players_online?: string[] | null
  player_count?: number | null
}

export interface ParsedPlayers {
  online: number
  max: number | null
  names: string[]
}

export interface FileEntry {
  name: string
  type: "file" | "directory"
  size: number | null
}

export interface UploadProgressInfo {
  loaded: number
  total: number
  status: "uploading" | "done" | "error"
  error?: string
}

export interface FileListResponse {
  success: boolean
  path: string
  entries: FileEntry[]
}

export interface CreateServerPayload {
  name: string
  type?: string
  version?: string
  loader_version?: string | null
  port?: number
  mem_min?: number
  mem_max?: number
  subscription?: string
  agent?: string
  properties?: Record<string, string>
  local_only?: boolean
}

// ---------------------------------------------------------------------------
// server.properties
// ---------------------------------------------------------------------------

export type ServerProperties = Record<string, string>

// ---------------------------------------------------------------------------
// Players
// ---------------------------------------------------------------------------

export interface NamedEntry {
  name?: string
  username?: string
  uuid?: string
}

export type PlayerRef = string | NamedEntry

export interface BannedPlayer extends NamedEntry {
  reason?: string
  created?: string
  expires?: string
  source?: string
}

export interface PlayersData {
  online: PlayerRef[]
  whitelist: PlayerRef[]
  ops: PlayerRef[]
  banned: BannedPlayer[]
}

export interface PlayerHistoryEntry {
  name: string
  uuid: string
  last_seen: string
}

export interface InventoryItem {
  slot: number
  id: string
  count: number
}

export interface PlayerData {
  uuid: string
  username: string
  health: number
  food_level: number
  food_saturation: number
  xp_level: number
  game_mode: number
  inventory: InventoryItem[]
  enderchest: InventoryItem[]
  warning?: string
}

// ---------------------------------------------------------------------------
// Backups
// ---------------------------------------------------------------------------

export interface Backup {
  id: number
  filename: string
  size_bytes?: number | null
  created_at: string
  backup_type?: "zip" | "zfs"
}

export interface BackupSchedule {
  cron: string
  retention: number
  enabled: boolean
  backup_type?: "zip" | "zfs"
}

// ---------------------------------------------------------------------------
// Player extended data
// ---------------------------------------------------------------------------

export interface PlayerPosition {
  x: number
  y: number
  z: number
}

export interface PlayerStatistics {
  playtime_ticks: number
  playtime_seconds: number
  playtime_hours: number
  deaths: number
  player_kills: number
  kd: number
  distance_traveled_blocks: number
  blocks_removed: number
  blocks_added: number
  items_used: number
  entities_killed: number
}
