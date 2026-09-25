"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import {
  useParams,
  useRouter,
  useSearchParams,
  notFound,
} from "next/navigation"
import Link from "next/link"
import {
  ArrowLeft,
  Loader2,
  Globe,
  Pencil,
  Settings2,
  RefreshCw,
} from "lucide-react"
import { toast } from "sonner"

import { TopNav } from "@/components/TopNav"
import { Console } from "@/components/Console"
import { FileExplorer } from "@/components/FileExplorer"
import { ServerStats } from "@/components/ServerStats"
import { PropertiesPanel } from "@/components/PropertiesPanel"
import { PlayersPanel } from "@/components/PlayersPanel"
import { BackupsPanel } from "@/components/BackupsPanel"
import { AuthPage, AuthStatusError } from "@/components/AuthPage"
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
import { Label } from "@/components/ui/label"
import { VersionPicker } from "@/components/VersionPicker"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { normalizeServer } from "@/lib/utils"
import type { Server, ServerStats as Stats } from "@/lib/types"

const POLL_INTERVAL = 5000

export default function ServerDetailPage() {
  const params = useParams()
  const serverId = Number(params?.serverId)

  const {
    loading: authLoading,
    setupRequired,
    authenticated,
    user,
    onLoginSuccess,
    retryStatus,
    statusError,
    logout,
  } = useAuth()

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

  // Settings edit state
  type EditField = "name" | "port" | "ram" | "version" | null
  const [editField, setEditField] = useState<EditField>(null)
  const [editValues, setEditValues] = useState({
    name: "",
    port: "",
    mem_min: "",
    mem_max: "",
    version: "",
    loader_version: "",
  })
  const [editSaving, setEditSaving] = useState(false)
  const [portError, setPortError] = useState("")

  // Bedrock-only: allow-cheats toggle
  const [cheatsEnabled, setCheatsEnabled] = useState<boolean | null>(null)
  const [cheatsConfirmOpen, setCheatsConfirmOpen] = useState(false)
  const [cheatsSaving, setCheatsSaving] = useState(false)

  // Recreate container (rebuild from current DB config, no settings change)
  const [recreateConfirmOpen, setRecreateConfirmOpen] = useState(false)
  const [recreating, setRecreating] = useState(false)
  const [recreateStep, setRecreateStep] = useState("")

  const router = useRouter()
  const searchParams = useSearchParams()
  const VALID_TABS = [
    "console",
    "files",
    "stats",
    "players",
    "properties",
    "backups",
    "settings",
  ] as const
  type Tab = (typeof VALID_TABS)[number]
  const rawTab = searchParams.get("tab") ?? ""
  const activeTab: Tab = (VALID_TABS as readonly string[]).includes(rawTab)
    ? (rawTab as Tab)
    : "console"

  function setTab(tab: Tab) {
    const params = new URLSearchParams(searchParams.toString())
    params.set("tab", tab)
    router.replace(`?${params.toString()}`, { scroll: false })
  }

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
    if (isNaN(serverId) || !authenticated) return

    // Load this server's metadata
    api.servers
      .get(serverId)
      .then((res) => {
        const found: Server | undefined = res?.server ?? res?.data ?? res
        if (!found) return notFound()
        const normalized = normalizeServer(found)
        setServer(normalized)
        if (normalized.type === "bedrock") {
          api.bedrock
            .getProperties(serverId)
            .then((r) =>
              setCheatsEnabled(r?.properties?.["allow-cheats"] === "true")
            )
            .catch(() => {})
        }
      })
      .catch(() => toast.error("Failed to load server"))
      .finally(() => setLoadingServer(false))

    fetchStats()
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [serverId, authenticated, fetchStats])

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
    const res = await api.servers.get(serverId)
    const found: Server | undefined = res?.server ?? res?.data ?? res
    if (found) setServer(normalizeServer(found))
  }

  async function handleRecreate() {
    setRecreateConfirmOpen(false)
    setRecreating(true)
    try {
      setRecreateStep("Backing up server…")
      await api.backups.create(serverId, "zip")

      setRecreateStep("Rebuilding container…")
      await api.control.recreate(serverId)

      toast.success("Server recreated — container rebuilt from current config")
      await refreshServerMeta()
      fetchStats()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to recreate server"
      )
    } finally {
      setRecreating(false)
      setRecreateStep("")
    }
  }

  async function handleToggleCheats() {
    const next = !cheatsEnabled
    setCheatsConfirmOpen(false)
    setCheatsSaving(true)
    try {
      await api.bedrock.setCheats(serverId, next)
      setCheatsEnabled(next)
      toast.success(`Cheats ${next ? "enabled" : "disabled"} — server restarted`)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to change cheats setting"
      )
    } finally {
      setCheatsSaving(false)
    }
  }

  async function handleSetupTunnel() {
    setTunneling(true)
    try {
      await api.control.tunnel(serverId)
      toast.success("Playit tunnel ready")
      await refreshServerMeta()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to set up tunnel"
      )
    } finally {
      setTunneling(false)
    }
  }

  function openEdit(field: "name" | "port" | "ram" | "version") {
    if (!server) return
    setPortError("")
    if (field === "name") setEditValues((v) => ({ ...v, name: server.name }))
    if (field === "port")
      setEditValues((v) => ({ ...v, port: String(server.port ?? "") }))
    if (field === "ram")
      setEditValues((v) => ({
        ...v,
        mem_min: String(server.mem_min ?? 2),
        mem_max: String(server.mem_max ?? 4),
      }))
    if (field === "version")
      setEditValues((v) => ({
        ...v,
        version: server.version,
        loader_version: server.loader_version ?? "",
      }))
    setEditField(field)
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault()
    if (!editField || !server) return
    setEditSaving(true)
    try {
      if (editField === "name") {
        const name = editValues.name.trim()
        if (!name) {
          toast.error("Name cannot be empty")
          return
        }
        await api.control.rename(serverId, name)
        toast.success("Server renamed")
      } else if (editField === "port") {
        const port = parseInt(editValues.port, 10)
        if (isNaN(port) || port < 1024 || port > 65535) {
          setPortError("Port must be between 1024 and 65535")
          return
        }
        await api.control.changePort(serverId, port)
        toast.success("Port updated")
      } else if (editField === "ram") {
        const isBedrock = server.type === "bedrock"
        const min = parseInt(editValues.mem_min, 10)
        const max = parseInt(editValues.mem_max, 10)
        if (
          (!isBedrock && (isNaN(min) || min < 1)) ||
          isNaN(max) ||
          max < (isBedrock ? 1 : min)
        ) {
          toast.error("Invalid RAM values")
          return
        }
        await api.control.changeRam(serverId, isBedrock ? max : min, max)
        toast.success("RAM updated")
      } else if (editField === "version") {
        const version = editValues.version.trim()
        if (!version) {
          toast.error("Version cannot be empty")
          return
        }
        const loader_version = editValues.loader_version.trim() || null
        await api.control.changeVersion(serverId, version, loader_version)
        toast.success("Version updated — server is being recreated")
      }
      setEditField(null)
      await refreshServerMeta()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setEditSaving(false)
    }
  }

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

  if (setupRequired || !authenticated) {
    return (
      <AuthPage
        initialView={setupRequired ? "setup-form" : "login-form"}
        onLoginSuccess={onLoginSuccess}
      />
    )
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
      <TopNav user={user} onLogout={logout} />

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
              {server.type} · {server.version}
              {server.loader_version ? ` / ${server.loader_version}` : ""} · :
              {server.port}
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

        {/* Playit address */}
        {server.local_only ? (
          <div className="mb-6 flex items-center justify-between gap-4 border border-border bg-muted/40 px-4 py-3">
            <div className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Local address: </span>
              {typeof window !== "undefined" ? window.location.hostname : "—"}:{server.port}
              <p className="mt-1 text-[11px]">Reachable from your local network. Set up a Playit tunnel for public access.</p>
            </div>
            <Button size="sm" variant="outline" onClick={handleSetupTunnel} disabled={tunneling}>
              {tunneling && <Loader2 className="size-3.5 animate-spin" />}
              Set up Playit tunnel
            </Button>
          </div>
        ) : server.tunnels.length > 0 ? (
          <div className="mb-6 border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">
              {server.type === "bedrock" ? "Address: " : "Connect: "}
            </span>
            {server.tunnels[0].address}
            {server.type === "bedrock" && (
              <>
                <span className="ml-4 font-medium text-foreground">Port: </span>
                {server.tunnels[0].external_port ?? "See Playit dashboard"}
                <p className="mt-1 text-[11px]">Enter the address and port separately in Bedrock.</p>
              </>
            )}
          </div>
        ) : (
          <div className="mb-6 border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            No Playit tunnel address is available for this server.
          </div>
        )}

        {/* Tabs */}
        <Tabs
          value={activeTab}
          onValueChange={(v) => setTab(v as Tab)}
          className="flex flex-col gap-0"
        >
          <TabsList
            variant="line"
            className="mb-0 w-full justify-start border-b border-border pb-0"
          >
            <TabsTrigger value="console">Console</TabsTrigger>
            <TabsTrigger value="files">Files</TabsTrigger>
            <TabsTrigger value="stats">Stats</TabsTrigger>
            <TabsTrigger value="players">Players</TabsTrigger>
            <TabsTrigger value="properties">Properties</TabsTrigger>
            <TabsTrigger value="backups">Backups</TabsTrigger>
            <TabsTrigger value="settings">
              <Settings2 className="size-3.5" />
              Settings
            </TabsTrigger>
          </TabsList>

          <TabsContent
            value="console"
            className="mt-0 border border-t-0 border-border"
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
            <ServerStats stats={stats} loading={loadingServer} />
          </TabsContent>

          <TabsContent
            value="players"
            className="mt-0 border border-t-0 border-border"
          >
            <PlayersPanel
              serverId={serverId}
              isRunning={isRunning}
              serverType={server.type}
            />
          </TabsContent>

          <TabsContent
            value="properties"
            className="mt-0 border border-t-0 border-border"
            style={{ minHeight: "480px" }}
          >
            <PropertiesPanel serverId={serverId} />
          </TabsContent>

          <TabsContent
            value="backups"
            className="mt-0 border border-t-0 border-border"
          >
            <BackupsPanel serverId={serverId} />
          </TabsContent>

          <TabsContent
            value="settings"
            className="mt-0 border border-t-0 border-border"
          >
            <div className="divide-y divide-border">
              {[
                {
                  label: "Server Name",
                  value: server.name,
                  field: "name" as const,
                },
                {
                  label: "Version",
                  value:
                    server.type === "bedrock"
                      ? "Always latest"
                      : server.version +
                        (server.loader_version
                          ? ` / ${server.loader_version}`
                          : ""),
                  field: "version" as const,
                },
                {
                  label: "Port",
                  value: server.port != null ? String(server.port) : "—",
                  field: "port" as const,
                },
                {
                  label: "RAM",
                  value:
                    server.mem_min != null && server.mem_max != null
                      ? `${server.mem_min} GB / ${server.mem_max} GB`
                      : "Edit min/max heap",
                  field: "ram" as const,
                },
              ].map(({ label, value, field }) => (
                <div
                  key={field}
                  className="flex items-center justify-between px-6 py-4"
                >
                  <div>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="text-sm font-medium">{value}</p>
                  </div>
                  {/* Bedrock always runs the latest release — nothing to edit */}
                  {!(field === "version" && server.type === "bedrock") && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openEdit(field)}
                    >
                      <Pencil className="size-3.5" />
                      Edit
                    </Button>
                  )}
                </div>
              ))}

              {/* Cheats — Bedrock only. allow-cheats is only read at server
                  startup, so toggling it always restarts the container. */}
              {server.type === "bedrock" && (
                <div className="flex items-center justify-between px-6 py-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Cheats</p>
                    <p className="text-sm font-medium">
                      {cheatsEnabled === null
                        ? "Loading…"
                        : cheatsEnabled
                          ? "Enabled"
                          : "Disabled"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={cheatsEnabled === null || cheatsSaving}
                    onClick={() => setCheatsConfirmOpen(true)}
                  >
                    {cheatsSaving ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Pencil className="size-3.5" />
                    )}
                    {cheatsEnabled ? "Disable" : "Enable"}
                  </Button>
                </div>
              )}

              {/* Recreate — rebuilds the container from current DB config,
                  no settings change. Useful when backend/image updates
                  require a fresh container (new labels, env vars, etc.)
                  that an existing container won't pick up on its own.
                  World data lives on the bind-mounted volume, not in the
                  container, so it survives — a backup is still taken first
                  as a safety net. */}
              <div className="flex items-center justify-between px-6 py-4">
                <div>
                  <p className="text-xs text-muted-foreground">
                    Recreate Container
                  </p>
                  <p className="text-sm font-medium">
                    {recreating
                      ? recreateStep || "Working…"
                      : "Rebuild from current config"}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={recreating}
                  onClick={() => setRecreateConfirmOpen(true)}
                >
                  {recreating ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3.5" />
                  )}
                  Recreate
                </Button>
              </div>
            </div>
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

      {/* Bedrock cheats toggle confirm */}
      <Dialog
        open={cheatsConfirmOpen}
        onOpenChange={(open) => {
          if (!open) setCheatsConfirmOpen(false)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {cheatsEnabled ? "Disable Cheats" : "Enable Cheats"}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {`allow-cheats is only read when the server starts up, so this will
            restart the server to apply the change. Players will be
            disconnected briefly.`}
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setCheatsConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={handleToggleCheats}>
              {cheatsEnabled ? "Disable & Restart" : "Enable & Restart"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Recreate container confirm */}
      <Dialog
        open={recreateConfirmOpen}
        onOpenChange={(open) => {
          if (!open) setRecreateConfirmOpen(false)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Recreate Container</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This stops, removes, and rebuilds the container from the
            server&apos;s current settings — no settings will change, and
            world data isn&apos;t touched since it lives outside the
            container. This is mainly useful after a backend update that an
            existing container needs to pick up. A backup will be created
            automatically first as a safety net.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setRecreateConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={handleRecreate}>Back Up &amp; Recreate</Button>
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

      {/* Settings edit dialog */}
      <Dialog
        open={editField !== null}
        onOpenChange={(open) => {
          if (!open) setEditField(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {editField === "name"
                ? "Rename Server"
                : editField === "port"
                  ? "Change Port"
                  : editField === "version"
                    ? "Change Version"
                    : "Change RAM"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditSave} className="space-y-4 pt-1">
            {editField === "version" && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Minecraft Version</Label>
                  <VersionPicker
                    value={editValues.version}
                    onChange={(v) =>
                      setEditValues((prev) => ({ ...prev, version: v }))
                    }
                    disabled={editSaving}
                  />
                </div>
                {["forge", "fabric"].includes(server.type) && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="edit-loader-ver">Loader Version</Label>
                      <span className="text-[10px] text-muted-foreground">
                        empty = latest
                      </span>
                    </div>
                    <VersionPicker
                      value={editValues.loader_version}
                      onChange={(v) =>
                        setEditValues((prev) => ({
                          ...prev,
                          loader_version: v,
                        }))
                      }
                      disabled={editSaving}
                      mode="loader"
                      loaderType={server.type as "forge" | "fabric"}
                      gameVersion={editValues.version.trim()}
                    />
                  </div>
                )}
              </div>
            )}
            {editField === "name" && (
              <div className="space-y-1.5">
                <Label htmlFor="edit-name">Server Name</Label>
                <Input
                  id="edit-name"
                  value={editValues.name}
                  onChange={(e) =>
                    setEditValues((v) => ({ ...v, name: e.target.value }))
                  }
                  disabled={editSaving}
                  autoFocus
                />
              </div>
            )}
            {editField === "port" && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="edit-port">Port</Label>
                  <span className="text-xs text-muted-foreground">
                    1024–65535
                    {server.type === "bedrock" ? " (UDP)" : ""}
                  </span>
                </div>
                <Input
                  id="edit-port"
                  type="number"
                  min={1024}
                  max={65535}
                  value={editValues.port}
                  onChange={(e) => {
                    setEditValues((v) => ({ ...v, port: e.target.value }))
                    setPortError("")
                  }}
                  disabled={editSaving}
                  autoFocus
                />
                {portError && (
                  <p className="text-xs text-destructive">{portError}</p>
                )}
              </div>
            )}
            {editField === "ram" && (
              <div
                className={
                  server.type === "bedrock"
                    ? "grid grid-cols-1 gap-3"
                    : "grid grid-cols-2 gap-3"
                }
              >
                {server.type !== "bedrock" && (
                  <div className="space-y-1.5">
                    <Label htmlFor="edit-memmin">Min (GB)</Label>
                    <Input
                      id="edit-memmin"
                      type="number"
                      min={1}
                      value={editValues.mem_min}
                      onChange={(e) =>
                        setEditValues((v) => ({
                          ...v,
                          mem_min: e.target.value,
                        }))
                      }
                      disabled={editSaving}
                      autoFocus
                    />
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label htmlFor="edit-memmax">
                    {server.type === "bedrock" ? "Memory Limit (GB)" : "Max (GB)"}
                  </Label>
                  <Input
                    id="edit-memmax"
                    type="number"
                    min={1}
                    value={editValues.mem_max}
                    onChange={(e) =>
                      setEditValues((v) => ({ ...v, mem_max: e.target.value }))
                    }
                    disabled={editSaving}
                    autoFocus={server.type === "bedrock"}
                  />
                </div>
              </div>
            )}
            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditField(null)}
                disabled={editSaving}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={editSaving}>
                {editSaving && <Loader2 className="size-3.5 animate-spin" />}
                {editSaving ? "Saving…" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
