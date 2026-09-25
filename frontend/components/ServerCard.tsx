"use client"

import { useState, useCallback } from "react"
import Link from "next/link"
import {
  Loader2,
  Play,
  Square,
  Skull,
  Settings,
  Users,
  Network,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import type { Server, ServerStats } from "@/lib/types"
import { api } from "@/lib/api"
import { parsePlayers } from "@/lib/utils"

interface Props {
  server: Server
  stats: ServerStats | null
  onRefresh: () => void
}

type Action = "stop" | "kill" | null

export function ServerCard({ server, stats, onRefresh }: Props) {
  const [loadingAction, setLoadingAction] = useState<
    "start" | "stop" | "kill" | null
  >(null)
  const [confirmAction, setConfirmAction] = useState<Action>(null)

  const isRunning = stats?.running ?? false

  const statusDot = isRunning ? "bg-emerald-500" : "bg-zinc-400"

  const statusText = isRunning ? "Running" : "Stopped"

  async function execAction(action: "start" | "stop" | "kill") {
    setLoadingAction(action)
    try {
      if (action === "start") await api.control.start(server.id)
      else if (action === "stop") await api.control.stop(server.id)
      else await api.control.kill(server.id)
      toast.success(
        `Server ${action === "start" ? "started" : action === "stop" ? "stopped" : "killed"}`
      )
      onRefresh()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : `Failed to ${action} server`
      )
    } finally {
      setLoadingAction(null)
    }
  }

  const handleConfirm = useCallback(async () => {
    if (!confirmAction) return
    const action = confirmAction
    setConfirmAction(null)
    await execAction(action)
  }, [confirmAction])

  return (
    <>
      <div className="flex flex-col gap-4 border border-border bg-card p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="truncate text-base leading-tight font-semibold">
              {server.name}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground capitalize">
              {server.type} · {server.version}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <span className={`size-2 rounded-full ${statusDot}`} />
            <span className="text-xs font-medium text-muted-foreground">
              {statusText}
            </span>
          </div>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Users className="size-3" />
            {isRunning && stats
              ? (() => {
                  const { online, max } = parsePlayers(stats)
                  return `${online}/${max ?? "—"}`
                })()
              : "—"}{" "}
            players
          </span>
          <span className="flex items-center gap-1">
            <Network className="size-3" />:{server.port}
          </span>
        </div>

        {/* DNS / tunnel */}
        {server.dns_records.length > 0 && (
          <div className="text-xs text-muted-foreground">
            <p className="truncate">{server.dns_records[0].name}</p>
            {server.type === "bedrock" && server.tunnels.length > 0 && (
              <p className="truncate font-medium text-foreground">
                Port {server.tunnels[0].external_port}
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            className="flex-1 bg-emerald-600 text-white hover:bg-emerald-700"
            disabled={isRunning || loadingAction !== null}
            onClick={() => execAction("start")}
            aria-label="Start server"
          >
            {loadingAction === "start" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Play className="size-3.5" />
            )}
            Start
          </Button>
          <Button
            size="sm"
            className="flex-1 bg-amber-500 text-white hover:bg-amber-600"
            disabled={!isRunning || loadingAction !== null}
            onClick={() => setConfirmAction("stop")}
            aria-label="Stop server"
          >
            {loadingAction === "stop" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Square className="size-3.5" />
            )}
            Stop
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="flex-1"
            disabled={loadingAction !== null}
            onClick={() => setConfirmAction("kill")}
            aria-label="Kill server"
          >
            {loadingAction === "kill" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Skull className="size-3.5" />
            )}
            Kill
          </Button>
        </div>

        <Link href={`/servers/${server.id}`} className="block w-full">
          <Button variant="outline" size="sm" className="w-full">
            <Settings className="size-3.5" />
            Manage
          </Button>
        </Link>
      </div>

      {/* Confirm dialog */}
      <Dialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmAction(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {confirmAction === "kill" ? "Force Kill Server" : "Stop Server"}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {confirmAction === "kill"
              ? "This will immediately terminate the server process. Any unsaved data will be lost."
              : "This will gracefully stop the server, saving world data."}
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              Cancel
            </Button>
            <Button
              variant={confirmAction === "kill" ? "destructive" : "default"}
              className={
                confirmAction === "stop"
                  ? "bg-amber-500 text-white hover:bg-amber-600"
                  : ""
              }
              onClick={handleConfirm}
            >
              {confirmAction === "kill" ? "Kill" : "Stop"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
