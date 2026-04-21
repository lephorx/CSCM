"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, notFound } from "next/navigation"
import Link from "next/link"
import { ArrowLeft, Loader2, Globe, Pencil } from "lucide-react"
import { toast } from "sonner"

import { TopNav } from "@/components/TopNav"
import { Console } from "@/components/Console"
import { FileExplorer } from "@/components/FileExplorer"
import { ServerStats } from "@/components/ServerStats"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import type { Server, ServerStats as Stats } from "@/lib/types"

const POLL_INTERVAL = 5000

export default function ServerDetailPage() {
  const params = useParams()
  const serverId = Number(params?.serverId)

  const [server, setServer] = useState<Server | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [loadingServer, setLoadingServer] = useState(true)
  const [loadingAction, setLoadingAction] = useState<
    "start" | "stop" | "restart" | "kill" | null
  >(null)
  const [confirmAction, setConfirmAction] = useState<"stop" | "kill" | null>(
    null
  )
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [tunneling, setTunneling] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [renameValue, setRenameValue] = useState("")
  const [renaming, setRenaming] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.servers.stats(serverId)
      setStats(res?.data ?? res)
    } catch {
      // ignore poll errors
    }
  }, [serverId])

  useEffect(() => {
    if (isNaN(serverId)) return

    // Load server list to get this server's metadata
    api.servers
      .list()
      .then((res) => {
        const list: Server[] = res?.servers ?? res?.data ?? res ?? []
        const found = list.find((s) => s.id === serverId)
        if (!found) return notFound()
        setServer(found)
      })
      .catch(() => toast.error("Failed to load server"))
      .finally(() => setLoadingServer(false))

    fetchStats()
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [serverId, fetchStats])

  const isRunning = stats?.running ?? false

  async function execAction(action: "start" | "stop" | "restart" | "kill") {
    setLoadingAction(action)
    try {
      if (action === "start") await api.control.start(serverId)
      else if (action === "stop") await api.control.stop(serverId)
      else if (action === "restart") await api.control.restart(serverId)
      else await api.control.kill(serverId)

      toast.success(
        action === "start"
          ? "Server started"
          : action === "stop"
            ? "Server stopped"
            : action === "restart"
              ? "Server restarting"
              : "Server killed"
      )
      fetchStats()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : `Failed to ${action} server`
      )
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleDelete() {
    setDeleteOpen(false)
    try {
      await api.servers.delete(serverId)
      toast.success("Server deleted")
      window.location.href = "/"
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete server"
      )
    }
  }

  async function refreshServerMeta() {
    const res = await api.servers.list()
    const list: Server[] = res?.servers ?? res?.data ?? res ?? []
    const found = list.find((s) => s.id === serverId)
    if (found) setServer(found)
  }

  async function handleSetupTunnel() {
    setTunneling(true)
    try {
      await api.control.tunnel(serverId)
      toast.success("Tunnel set up — DNS records created")
      await refreshServerMeta()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to set up tunnel"
      )
    } finally {
      setTunneling(false)
    }
  }

  async function handleRenameSubdomain(e: React.FormEvent) {
    e.preventDefault()
    const subdomain = renameValue.trim()
    if (!subdomain) return
    setRenaming(true)
    try {
      await api.control.subdomain(serverId, subdomain)
      toast.success("Subdomain updated — DNS propagates within ~1 minute")
      setRenameOpen(false)
      await refreshServerMeta()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to rename subdomain"
      )
    } finally {
      setRenaming(false)
    }
  }

  if (loadingServer) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!server) return null

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />

      <main className="mx-auto w-full max-w-screen-xl flex-1 px-6 py-8">
        {/* Breadcrumb + header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              All Servers
            </Link>
            <h1 className="text-xl font-semibold">{server.name}</h1>
            <p className="text-xs text-muted-foreground capitalize">
              {server.type} · {server.version} · :{server.port}
            </p>
          </div>

          {/* Control buttons */}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="bg-emerald-600 text-white hover:bg-emerald-700"
              disabled={isRunning || loadingAction !== null}
              onClick={() => execAction("start")}
            >
              {loadingAction === "start" && (
                <Loader2 className="size-3.5 animate-spin" />
              )}
              Start
            </Button>
            <Button
              size="sm"
              className="bg-amber-500 text-white hover:bg-amber-600"
              disabled={!isRunning || loadingAction !== null}
              onClick={() => setConfirmAction("stop")}
            >
              {loadingAction === "stop" && (
                <Loader2 className="size-3.5 animate-spin" />
              )}
              Stop
            </Button>
            <Button
              size="sm"
              className="bg-blue-600 text-white hover:bg-blue-700"
              disabled={!isRunning || loadingAction !== null}
              onClick={() => execAction("restart")}
            >
              {loadingAction === "restart" && (
                <Loader2 className="size-3.5 animate-spin" />
              )}
              Restart
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={loadingAction !== null}
              onClick={() => setConfirmAction("kill")}
            >
              {loadingAction === "kill" && (
                <Loader2 className="size-3.5 animate-spin" />
              )}
              Kill
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-destructive text-destructive hover:bg-destructive/10"
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </div>
        </div>

        {/* DNS / tunnel info */}
        {server.dns_records.length > 0 ? (
          <div className="mb-6 flex items-center justify-between border border-border bg-muted/40 px-4 py-3">
            <div className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Connect: </span>
              {server.dns_records[0].name}
              {server.tunnels.length > 0 && (
                <span className="ml-4">
                  Tunnel: {server.tunnels[0].address}:
                  {server.tunnels[0].external_port}
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const current = server.dns_records[0].name.split(".")[0]
                setRenameValue(current)
                setRenameOpen(true)
              }}
            >
              <Pencil className="size-3.5" />
              Rename
            </Button>
          </div>
        ) : (
          <div className="mb-6 flex items-center justify-between border border-border bg-muted/40 px-4 py-3">
            <div>
              <p className="text-sm font-medium">No tunnel configured</p>
              <p className="text-xs text-muted-foreground">
                Players cannot connect externally yet. Set up a tunnel to create
                public DNS records.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={tunneling}
              onClick={handleSetupTunnel}
            >
              {tunneling ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Globe className="size-3.5" />
              )}
              {tunneling ? "Setting up…" : "Setup Tunnel"}
            </Button>
          </div>
        )}

        {/* Tabs */}
        <Tabs defaultValue="console" className="flex flex-col gap-0">
          <TabsList
            variant="line"
            className="mb-0 w-full justify-start border-b border-border pb-0"
          >
            <TabsTrigger value="console">Console</TabsTrigger>
            <TabsTrigger value="files">Files</TabsTrigger>
            <TabsTrigger value="stats">Stats</TabsTrigger>
          </TabsList>

          <TabsContent
            value="console"
            className="mt-0 border border-t-0 border-border"
            style={{ minHeight: "480px" }}
          >
            <Console serverId={serverId} isRunning={isRunning} />
          </TabsContent>

          <TabsContent
            value="files"
            className="mt-0 border border-t-0 border-border"
            style={{ minHeight: "480px" }}
          >
            <FileExplorer serverId={serverId} />
          </TabsContent>

          <TabsContent
            value="stats"
            className="mt-0 border border-t-0 border-border"
          >
            <ServerStats serverId={serverId} />
          </TabsContent>
        </Tabs>
      </main>

      {/* Stop / Kill confirm */}
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
              onClick={() => {
                const action = confirmAction!
                setConfirmAction(null)
                execAction(action)
              }}
            >
              {confirmAction === "kill" ? "Kill" : "Stop"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete server confirm */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Server</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently delete{" "}
            <span className="font-medium text-foreground">{server.name}</span>{" "}
            and all associated resources. This cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete Server
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename subdomain */}
      <Dialog
        open={renameOpen}
        onOpenChange={(open) => {
          if (!open) setRenameOpen(false)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Rename Subdomain</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Enter a new subdomain name. DNS records will be updated and players
            can connect via the new address within ~1 minute.
          </p>
          <form onSubmit={handleRenameSubdomain} className="space-y-4 pt-1">
            <Input
              placeholder="my-server"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              disabled={renaming}
              autoFocus
            />
            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setRenameOpen(false)}
                disabled={renaming}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={renaming || !renameValue.trim()}>
                {renaming && <Loader2 className="size-3.5 animate-spin" />}
                {renaming ? "Renaming…" : "Rename"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
