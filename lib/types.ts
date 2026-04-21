export interface Tunnel {
  address: string
  local_port: number
  external_port: number
}

export interface DnsRecord {
  type: string
  name: string
  target: string
  port: number | null
}

export interface Server {
  id: number
  name: string
  type: string
  version: string
  port: number
  created_at: string
  tunnels: Tunnel[]
  dns_records: DnsRecord[]
}

export interface ServerStats {
  running: boolean
  online: number
  max: number
  players: string[] | null | undefined
  cpu: number
  mem: number
  tps?: number
  uptime?: number
  disk_used?: number
  disk_total?: number
  last_backup?: string
}

export interface FileEntry {
  name: string
  type: "file" | "directory"
  size: number | null
}

export interface FileListResponse {
  success: boolean
  path: string
  entries: FileEntry[]
}

export interface CreateServerPayload {
  name: string
  type: string
  version: string
  port: number
  mem_min?: string
  mem_max?: string
}
