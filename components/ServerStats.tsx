"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { Loader2 } from "lucide-react"

import { Progress } from "@/components/ui/progress"
import type { ServerStats as Stats } from "@/lib/types"
import { api } from "@/lib/api"

interface Props {
  serverId: number
}

const POLL_INTERVAL = 5000

function formatUptime(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":")
}

function tpsColor(tps: number) {
  if (tps >= 19) return "text-emerald-500"
  if (tps >= 15) return "text-amber-500"
  return "text-red-500"
}

function StatRow({
  label,
  value,
  bar,
  barColor,
}: {
  label: string
  value: string
  bar?: number
  barColor?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-medium tabular-nums">{value}</span>
      </div>
      {bar !== undefined && (
        <Progress value={bar} className={`h-1.5 ${barColor ?? ""}`} />
      )}
    </div>
  )
}

export function ServerStats({ serverId }: Props) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.servers.stats(serverId)
      if (res?.data) setStats(res.data)
      else if (res?.running !== undefined) setStats(res)
    } catch {
      // silently fail on poll errors
    } finally {
      setLoading(false)
    }
  }, [serverId])

  useEffect(() => {
    fetchStats()
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchStats])

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        Unable to load stats.
      </div>
    )
  }

  const rawMem = stats.mem ?? 0
  const cpuPct = Math.min(100, Math.round(stats.cpu ?? 0))

  // API may return mem in bytes or MB — normalise to MB for display
  // Values > 10,000 are almost certainly bytes; divide down to MB
  const memMB = rawMem > 10_000 ? rawMem / (1024 * 1024) : rawMem
  const memDisplay =
    memMB >= 1024
      ? `${(memMB / 1024).toFixed(2)} GB`
      : `${Math.round(memMB)} MB`

  // Use a fixed 100% bar scaled to memMB (no disk_total dependency)
  const memPct = Math.min(100, Math.round((memMB / 4096) * 100))

  const diskUsed = stats.disk_used ?? null
  const diskTotal = stats.disk_total ?? null
  const diskPct =
    diskUsed !== null && diskTotal
      ? Math.min(100, Math.round((diskUsed / diskTotal) * 100))
      : null

  const tps = stats.tps ?? null
  const uptimeSec = stats.uptime ?? null

  return (
    <div className="grid gap-6 p-6 sm:grid-cols-2 lg:grid-cols-3">
      {/* Status */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Status</span>
        <div className="flex items-center gap-2">
          <span
            className={`size-2 rounded-full ${stats.running ? "bg-emerald-500" : "bg-zinc-400"}`}
          />
          <span className="text-sm font-medium">
            {stats.running ? "Running" : "Stopped"}
          </span>
        </div>
      </div>

      {/* Players */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Players Online</span>
        <span className="text-sm font-medium tabular-nums">
          {stats.online ?? 0} / {stats.max ?? "—"}
        </span>
        {Array.isArray(stats.players) && stats.players.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {stats.players.join(", ")}
          </p>
        )}
      </div>

      {/* TPS */}
      {tps !== null && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">TPS</span>
          <span
            className={`text-sm font-semibold tabular-nums ${tpsColor(tps)}`}
          >
            {tps.toFixed(1)}
          </span>
        </div>
      )}

      {/* Uptime */}
      {uptimeSec !== null && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Uptime</span>
          <span className="text-sm font-medium tabular-nums">
            {formatUptime(uptimeSec)}
          </span>
        </div>
      )}

      {/* Last backup */}
      {stats.last_backup !== undefined && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Last Backup</span>
          <span className="text-sm font-medium">
            {stats.last_backup ?? "Never"}
          </span>
        </div>
      )}

      {/* CPU — full row */}
      <div className="col-span-full">
        <StatRow label="CPU Usage" value={`${cpuPct}%`} bar={cpuPct} />
      </div>

      {/* Memory */}
      <div className="col-span-full">
        <StatRow label="Memory Usage" value={memDisplay} bar={memPct} />
      </div>

      {/* Disk */}
      {diskPct !== null && diskUsed !== null && diskTotal !== null && (
        <div className="col-span-full">
          <StatRow
            label="Disk Usage"
            value={`${diskUsed.toFixed(1)} / ${diskTotal.toFixed(1)} GB`}
            bar={diskPct}
          />
        </div>
      )}
    </div>
  )
}
