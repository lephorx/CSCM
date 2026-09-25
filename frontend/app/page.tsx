"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Plus, Loader2, ServerOff, Settings2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DefaultsEditor } from "@/components/DefaultsEditor"
import { TopNav } from "@/components/TopNav"
import { ServerCard } from "@/components/ServerCard"
import { ServerCreateModal } from "@/components/ServerCreateModal"
import { ServerCreationProgress } from "@/components/ServerCreationProgress"
import { AuthPage, AuthStatusError } from "@/components/AuthPage"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { useServerCreation } from "@/hooks/useServerCreation"
import { normalizeServer } from "@/lib/utils"
import type { Server, ServerStats } from "@/lib/types"

const POLL_INTERVAL = 5000

export default function DashboardPage() {
  const {
    loading: authLoading,
    statusError,
    setupRequired,
    authenticated,
    user,
    onLoginSuccess,
    retryStatus,
    logout,
  } = useAuth()

  const [servers, setServers] = useState<Server[]>([])
  const [statsMap, setStatsMap] = useState<Record<number, ServerStats>>({})
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [defaultsOpen, setDefaultsOpen] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchServers = useCallback(async () => {
    try {
      const res = await api.servers.list()
      const list: Server[] = (res?.servers ?? res?.data ?? res ?? []).map(
        normalizeServer
      )
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

  const {
    task: creationTask,
    start: startCreation,
    dismiss: dismissCreation,
  } = useServerCreation(fetchServers)

  useEffect(() => {
    if (!authenticated) return
    fetchServers()
    intervalRef.current = setInterval(fetchServers, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchServers, authenticated])

  // Auto-dismiss a completed creation — quickly if the modal is still open
  // (it's about to show a "View Server" button anyway), longer if it's just
  // the background notification.
  useEffect(() => {
    if (creationTask?.stage !== "ready") return
    const t = setTimeout(
      () => {
        setCreateOpen(false)
        dismissCreation()
      },
      createOpen ? 2000 : 5000
    )
    return () => clearTimeout(t)
  }, [creationTask?.stage, createOpen, dismissCreation])

  // Show a full-screen spinner while checking auth
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (statusError) {
    return <AuthStatusError message={statusError} onRetry={retryStatus} />
  }

  // Show auth page when setup is required or user is not authenticated
  if (setupRequired || !authenticated) {
    return (
      <AuthPage
        initialView={setupRequired ? "setup-form" : "login-form"}
        onLoginSuccess={onLoginSuccess}
      />
    )
  }

  if (defaultsOpen) {
    return (
      <DefaultsEditor
        user={user}
        onLogout={logout}
        onClose={() => setDefaultsOpen(false)}
      />
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav user={user} onLogout={logout} />

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
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setDefaultsOpen(true)}>
              <Settings2 className="size-4" />
              Defaults
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              New Server
            </Button>
          </div>
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
        task={creationTask}
        onStart={startCreation}
        onDismiss={dismissCreation}
      />

      {/* Floating progress — shown when modal is closed but creation is still running */}
      {creationTask && !createOpen && (
        <ServerCreationProgress task={creationTask} onDismiss={dismissCreation} />
      )}
    </div>
  )
}
