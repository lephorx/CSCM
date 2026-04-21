"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Plus, Loader2, ServerOff } from "lucide-react"

import { Button } from "@/components/ui/button"
import { TopNav } from "@/components/TopNav"
import { ServerCard } from "@/components/ServerCard"
import { ServerCreateModal } from "@/components/ServerCreateModal"
import { api } from "@/lib/api"
import type { Server, ServerStats } from "@/lib/types"

const POLL_INTERVAL = 5000

export default function DashboardPage() {
  const [servers, setServers] = useState<Server[]>([])
  const [statsMap, setStatsMap] = useState<Record<number, ServerStats>>({})
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchServers = useCallback(async () => {
    try {
      const res = await api.servers.list()
      const list: Server[] = res?.servers ?? res?.data ?? res ?? []
      setServers(list)
      // fetch stats in parallel
      const statsEntries = await Promise.allSettled(
        list.map((s) =>
          api.servers
            .stats(s.id)
            .then((r) => [s.id, r?.data ?? r] as [number, ServerStats])
        )
      )
      const next: Record<number, ServerStats> = {}
      for (const result of statsEntries) {
        if (result.status === "fulfilled") {
          const [id, stats] = result.value
          next[id] = stats
        }
      }
      setStatsMap(next)
    } catch {
      // silently fail on poll
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchServers()
    intervalRef.current = setInterval(fetchServers, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchServers])

  return (
    <div className="min-h-screen bg-background">
      <TopNav />

      <main className="mx-auto max-w-screen-xl px-6 py-8">
        {/* Page header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Servers</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {loading
                ? "Loading…"
                : `${servers.length} server${servers.length !== 1 ? "s" : ""}`}
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            New Server
          </Button>
        </div>

        {/* Server grid */}
        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : servers.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-foreground">
            <ServerOff className="size-10 opacity-40" />
            <p className="text-sm">No servers yet.</p>
            <Button variant="outline" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              Create your first server
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {servers.map((server) => (
              <ServerCard
                key={server.id}
                server={server}
                stats={statsMap[server.id] ?? null}
                onRefresh={fetchServers}
              />
            ))}
          </div>
        )}
      </main>

      <ServerCreateModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={fetchServers}
      />
    </div>
  )
}
