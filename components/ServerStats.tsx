"use client"

import { Loader2 } from "lucide-react"

import { Progress } from "@/components/ui/progress"
import type { ServerStats as Stats } from "@/lib/types"
import { formatBytes, parsePlayersRaw } from "@/lib/utils"

interface Props {
  stats: Stats | null
  loading?: boolean
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

const healthColor: Record<string, string> = {
  healthy: "bg-emerald-500",
  unhealthy: "bg-red-500",
  starting: "bg-amber-500",
}

export function ServerStats({ stats, loading = false }: Props) {
  if (loading || !stats) {
    return (
      <div className="flex h-48 items-center justify-center">
        {loading ? (
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <span className="text-sm text-muted-foreground">
            Unable to load stats.
          </span>
        )}
      </div>
    )
  }

  const cpuPct = Math.min(100, Math.round(stats.cpu_percent ?? 0))

  const memUsed = stats.memory_usage_bytes ?? 0
  const memLimit = stats.memory_limit_bytes ?? 0
  const memPct =
    memLimit > 0 ? Math.min(100, Math.round((memUsed / memLimit) * 100)) : 0

  const { online, max, names } = parsePlayersRaw(stats.players_raw)
  const dotColor = stats.running
    ? (healthColor[stats.health] ?? "bg-emerald-500")
    : "bg-zinc-400"

  return (
    <div className="grid gap-6 p-6 sm:grid-cols-2 lg:grid-cols-3">
      {/* Status */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Status</span>
        <div className="flex items-center gap-2">
          <span className={`size-2 rounded-full ${dotColor}`} />
          <span className="text-sm font-medium capitalize">
            {stats.running ? (stats.health ?? "Running") : "Stopped"}
          </span>
        </div>
      </div>

      {/* Players */}
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Players Online</span>
        <span className="text-sm font-medium tabular-nums">
          {stats.running ? `${online} / ${max ?? "—"}` : "—"}
        </span>
        {names.length > 0 && (
          <p className="text-xs text-muted-foreground">{names.join(", ")}</p>
        )}
      </div>

      {/* CPU — full row */}
      <div className="col-span-full">
        <StatRow label="CPU Usage" value={`${cpuPct}%`} bar={cpuPct} />
      </div>

      {/* Memory */}
      <div className="col-span-full">
        <StatRow
          label="Memory Usage"
          value={
            memLimit > 0
              ? `${formatBytes(memUsed)} / ${formatBytes(memLimit)}`
              : formatBytes(memUsed)
          }
          bar={memPct}
        />
      </div>
    </div>
  )
}
