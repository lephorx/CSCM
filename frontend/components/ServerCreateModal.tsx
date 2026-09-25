"use client"

import { useState, useEffect, useRef } from "react"
import {
  Loader2,
  Plus,
  CheckCircle2,
  XCircle,
  X,
  ChevronDown,
  AlertCircle,
} from "lucide-react"
import Link from "next/link"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import type { CreateServerPayload, Server } from "@/lib/types"
import type { CreationTask } from "@/hooks/useServerCreation"
import { VersionPicker } from "@/components/VersionPicker"
import {
  JAVA_PROPERTY_KEYS,
  BEDROCK_PROPERTY_KEYS,
} from "@/lib/minecraftProperties"

const PORT_MIN = 1024
const PORT_MAX = 65535

// Ports reserved by the system, backend, or common services
const BLOCKED_PORTS = new Set([
  3000, // Next.js dev server
  3001, // common dev
  4000, // common dev
  5000, // CSCM backend
  5001, // CSCM backend alt
  6000, // X11
  8000, // common HTTP alt
  8080, // common HTTP alt
  8443, // common HTTPS alt
  8888, // Jupyter
  9000, // common dev
  9090, // Prometheus
])

const JAVA_TYPES = ["paper", "forge", "fabric", "vanilla", "purpur"]
const DEFAULT_JAVA_VERSION = "1.21.4"
const DEFAULT_JAVA_PORT = "25565"
const DEFAULT_BEDROCK_VERSION = "LATEST"
const DEFAULT_BEDROCK_PORT = "19132"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  task: CreationTask | null
  onStart: (payload: CreateServerPayload) => Promise<number>
  onDismiss: () => void
}

type PortStatus =
  | "idle"
  | "checking"
  | "available"
  | "taken"
  | "reserved"
  | "invalid"

export function ServerCreateModal({
  open,
  onOpenChange,
  task,
  onStart,
  onDismiss,
}: Props) {
  const [serverTypes, setServerTypes] = useState<string[]>([
    ...JAVA_TYPES,
    "bedrock",
  ])
  const [submitting, setSubmitting] = useState(false)
  const [usedPorts, setUsedPorts] = useState<Set<number>>(new Set())
  const [portStatus, setPortStatus] = useState<PortStatus>("idle")

  const [form, setForm] = useState({
    name: "",
    type: "paper",
    version: DEFAULT_JAVA_VERSION,
    port: DEFAULT_JAVA_PORT,
    mem_min: "2",
    mem_max: "4",
    loader_version: "",
    local_only: false,
  })

  const [errors, setErrors] = useState<Partial<typeof form>>({})
  const [props, setProps] = useState<{ key: string; value: string }[]>([])
  const [showProps, setShowProps] = useState(false)
  const portDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function resetForm() {
    setForm({
      name: "",
      type: "paper",
      version: DEFAULT_JAVA_VERSION,
      port: DEFAULT_JAVA_PORT,
      mem_min: "2",
      mem_max: "4",
      loader_version: "",
      local_only: false,
    })
    setErrors({})
    setPortStatus("idle")
    setProps([])
    setShowProps(false)
  }

  // Bedrock has its own defaults (no manifest-based version, UDP port 19132,
  // no JVM heap). Swap version/port when switching type, but only if the
  // field still holds the *other* type's default — never clobber a value
  // the user deliberately customized.
  function handleTypeChange(newType: string) {
    setForm((prev) => {
      const isBedrock = newType === "bedrock"
      const wasBedrock = prev.type === "bedrock"
      const next = { ...prev, type: newType }
      if (isBedrock && !wasBedrock) {
        if (prev.version === DEFAULT_JAVA_VERSION)
          next.version = DEFAULT_BEDROCK_VERSION
        if (prev.port === DEFAULT_JAVA_PORT) next.port = DEFAULT_BEDROCK_PORT
        next.loader_version = ""
      } else if (!isBedrock && wasBedrock) {
        if (prev.version === DEFAULT_BEDROCK_VERSION)
          next.version = DEFAULT_JAVA_VERSION
        if (prev.port === DEFAULT_BEDROCK_PORT) next.port = DEFAULT_JAVA_PORT
      }
      return next
    })
    setErrors((prev) => ({ ...prev, type: undefined }))
  }

  // Reset the form once a *successful* creation is dismissed, but keep the
  // user's input around after an error so they can fix it and retry.
  const prevStageRef = useRef<CreationTask["stage"] | null>(null)
  useEffect(() => {
    if (task) {
      prevStageRef.current = task.stage
      return
    }
    if (prevStageRef.current === "ready") resetForm()
    prevStageRef.current = null
  }, [task])

  // Load server types and existing ports when modal opens
  useEffect(() => {
    if (!open) return
    api
      .serverTypes()
      .then((res) => {
        if (Array.isArray(res?.server_types)) setServerTypes(res.server_types)
        else if (Array.isArray(res)) setServerTypes(res)
      })
      .catch(() => {})

    api.servers
      .list()
      .then((res) => {
        const list: Server[] = res?.servers ?? res?.data ?? res ?? []
        setUsedPorts(new Set(list.map((s) => s.port)))
      })
      .catch(() => {})
  }, [open])

  // Load default properties, filtered to whichever edition is currently
  // selected — Java and Bedrock server.properties keys are almost entirely
  // different, so showing both sets mixed together is confusing (and a
  // Bedrock-only key silently does nothing on a Java server, or vice versa).
  // Re-runs whenever the server type changes so switching types shows the
  // right set instead of leftovers from the previous edition.
  useEffect(() => {
    if (!open) return
    const isBedrock = form.type === "bedrock"
    const allowedKeys = isBedrock ? BEDROCK_PROPERTY_KEYS : JAVA_PROPERTY_KEYS
    const otherEditionKeys = isBedrock ? JAVA_PROPERTY_KEYS : BEDROCK_PROPERTY_KEYS

    api.defaults
      .getProperties()
      .then((res) => {
        const p: Record<string, string> = res?.properties ?? {}
        setProps(
          Object.entries(p)
            // Drop keys known to belong to the *other* edition; keep
            // matching keys and anything unrecognized (e.g. a mod-specific
            // key we don't have in our reference list).
            .filter(([key]) => !otherEditionKeys.has(key) || allowedKeys.has(key))
            .map(([key, value]) => ({ key, value: String(value) }))
        )
      })
      .catch(() => {})
  }, [open, form.type])

  // Debounced port availability check
  useEffect(() => {
    if (portDebounceRef.current) clearTimeout(portDebounceRef.current)
    const port = parseInt(form.port, 10)

    if (!form.port || isNaN(port)) {
      const id = window.setTimeout(() => setPortStatus("idle"), 0)
      return () => window.clearTimeout(id)
    }
    if (port < PORT_MIN || port > PORT_MAX) {
      const id = window.setTimeout(() => setPortStatus("invalid"), 0)
      return () => window.clearTimeout(id)
    }

    const id = window.setTimeout(() => setPortStatus("checking"), 0)
    portDebounceRef.current = setTimeout(() => {
      window.clearTimeout(id)
      if (BLOCKED_PORTS.has(port)) setPortStatus("reserved")
      else setPortStatus(usedPorts.has(port) ? "taken" : "available")
    }, 400)

    return () => {
      if (portDebounceRef.current) clearTimeout(portDebounceRef.current)
    }
  }, [form.port, usedPorts])

  function handleChange(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  function validate() {
    const next: Partial<typeof form> = {}
    if (!form.name.trim()) next.name = "Server name is required"
    if (!form.version.trim()) next.version = "Version is required"
    const port = parseInt(form.port, 10)
    if (isNaN(port) || port < PORT_MIN || port > PORT_MAX)
      next.port = `Port must be between ${PORT_MIN} and ${PORT_MAX}`
    if (BLOCKED_PORTS.has(port))
      next.port = "This port is reserved by the system"
    if (portStatus === "taken") next.port = "This port is already in use"

    const isBedrock = form.type === "bedrock"
    const memMin = parseInt(form.mem_min, 10)
    const memMax = parseInt(form.mem_max, 10)
    // Bedrock has no JVM, so there's no min heap — mem_max is just a
    // container memory cap there.
    if (!isBedrock && (isNaN(memMin) || memMin < 1))
      next.mem_min = "Must be at least 1 GB"
    if (isNaN(memMax) || memMax < (isBedrock ? 1 : memMin))
      next.mem_max = "Max RAM must be ≥ min RAM"

    return next
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const validationErrors = validate()
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors)
      return
    }

    setSubmitting(true)
    try {
      const propsObj: Record<string, string> = {}
      for (const p of props) {
        const k = p.key.trim()
        if (k) propsObj[k] = p.value
      }
      const payload: CreateServerPayload = {
        name: form.name.trim(),
        type: form.type,
        version: form.version.trim(),
        port: parseInt(form.port, 10),
        // The Min RAM field is hidden for Bedrock (no JVM heap), but the
        // backend still enforces mem_max >= mem_min unconditionally — send
        // 1 so a leftover/hidden mem_min never fails that check.
        mem_min: form.type === "bedrock" ? 1 : parseInt(form.mem_min, 10),
        mem_max: parseInt(form.mem_max, 10),
        ...(form.loader_version.trim()
          ? { loader_version: form.loader_version.trim() }
          : {}),
        ...(Object.keys(propsObj).length > 0 ? { properties: propsObj } : {}),
        ...(form.local_only ? { local_only: true } : {}),
      }

      // onStart flips `task` to non-null immediately, which swaps this form
      // out for the shared progress view.
      await onStart(payload)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create server"
      )
    } finally {
      setSubmitting(false)
    }
  }

  const portNum = parseInt(form.port, 10)
  const portOutOfRange =
    !isNaN(portNum) && (portNum < PORT_MIN || portNum > PORT_MAX)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {task ? "Creating Server…" : "Create Server"}
          </DialogTitle>
        </DialogHeader>

        {task ? (
          /* ── In-modal creation progress ─────────────────────────────── */
          <div className="flex flex-col items-center gap-5 py-6 text-center">
            {task.stage === "ready" ? (
              <CheckCircle2 className="size-14 text-emerald-500" />
            ) : task.stage === "error" ? (
              <AlertCircle className="size-14 text-destructive" />
            ) : (
              <Loader2 className="size-14 animate-spin text-primary" />
            )}

            <div>
              <p className="text-lg font-semibold">{task.name}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {task.stage === "submitting"
                  ? "Provisioning server…"
                  : task.stage === "ready"
                    ? "Your server is ready!"
                    : task.stage === "error"
                      ? "Something went wrong"
                      : task.step || "Server is starting up…"}
              </p>
            </div>

            <div className="w-full space-y-1.5">
              <Progress
                value={task.progress}
                className={`h-2 transition-all duration-700 ${
                  task.stage === "ready"
                    ? "[&>div]:bg-emerald-500"
                    : task.stage === "error"
                      ? "[&>div]:bg-destructive"
                      : ""
                }`}
              />
              <p className="text-xs text-muted-foreground">
                {task.stage === "submitting"
                  ? "Please wait while the server is being provisioned…"
                  : task.stage === "ready"
                    ? "Closing automatically…"
                    : task.stage === "error"
                      ? "You can dismiss this and try again."
                      : "Close this window — creation continues in the background"}
              </p>
            </div>

            <div className="flex w-full gap-2">
              {/* Only show minimize once we have a real server ID */}
              {task.stage === "starting" && (
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => onOpenChange(false)}
                >
                  Minimize to background
                </Button>
              )}
              {task.stage === "ready" && (
                <Button className="flex-1" asChild>
                  <Link
                    href={`/servers/${task.serverId}`}
                    onClick={() => onOpenChange(false)}
                  >
                    View Server
                  </Link>
                </Button>
              )}
              {task.stage === "error" && (
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => onDismiss()}
                >
                  Dismiss
                </Button>
              )}
            </div>
          </div>
        ) : (
          /* ── Server creation form ────────────────────────────────────── */
          <form
            onSubmit={handleSubmit}
            className="space-y-4 overflow-visible py-2"
          >
            {/* Server Name */}
            <div className="space-y-1.5">
              <Label htmlFor="srv-name">Server Name</Label>
              <Input
                id="srv-name"
                placeholder="my-server"
                value={form.name}
                onChange={(e) => handleChange("name", e.target.value)}
                disabled={submitting}
                aria-invalid={!!errors.name}
              />
              {errors.name && (
                <p className="text-xs text-destructive">{errors.name}</p>
              )}
            </div>

            {/* Server Type */}
            <div className="space-y-1.5">
              <Label htmlFor="srv-type">Server Type</Label>
              <Select
                value={form.type}
                onValueChange={handleTypeChange}
                disabled={submitting}
              >
                <SelectTrigger id="srv-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {serverTypes.map((t) => (
                    <SelectItem key={t} value={t} className="capitalize">
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Version — Bedrock always runs the latest release, no picker needed */}
            {form.type !== "bedrock" && (
              <div className="space-y-1.5">
                <Label htmlFor="srv-version">Version</Label>
                <VersionPicker
                  value={form.version}
                  onChange={(v) => handleChange("version", v)}
                  disabled={submitting}
                />
                {errors.version && (
                  <p className="text-xs text-destructive">{errors.version}</p>
                )}
              </div>
            )}

            {/* Loader Version — forge/fabric only */}
            {["forge", "fabric"].includes(form.type) && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="srv-loader-ver">Loader Version</Label>
                  <span className="text-xs text-muted-foreground">
                    leave empty for latest
                  </span>
                </div>
                <VersionPicker
                  value={form.loader_version}
                  onChange={(v) => handleChange("loader_version", v)}
                  disabled={submitting}
                  mode="loader"
                  loaderType={form.type as "forge" | "fabric"}
                  gameVersion={form.version.trim()}
                />
              </div>
            )}

            {/* Port */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="srv-port">Port</Label>
                <span className="text-xs text-muted-foreground">
                  {PORT_MIN}–{PORT_MAX}
                  {form.type === "bedrock" ? " (UDP)" : ""}
                </span>
              </div>
              <Input
                id="srv-port"
                type="number"
                min={PORT_MIN}
                max={PORT_MAX}
                value={form.port}
                onChange={(e) => handleChange("port", e.target.value)}
                disabled={submitting}
                aria-invalid={!!errors.port || portStatus === "taken"}
              />
              {/* Port status feedback */}
              {errors.port ? (
                <p className="text-xs text-destructive">{errors.port}</p>
              ) : portOutOfRange ? (
                <p className="flex items-center gap-1 text-xs text-destructive">
                  <XCircle className="size-3" />
                  Must be between {PORT_MIN} and {PORT_MAX}
                </p>
              ) : portStatus === "checking" ? (
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" />
                  Checking availability…
                </p>
              ) : portStatus === "available" ? (
                <p className="flex items-center gap-1 text-xs text-emerald-600">
                  <CheckCircle2 className="size-3" />
                  Port available
                </p>
              ) : portStatus === "taken" ? (
                <p className="flex items-center gap-1 text-xs text-destructive">
                  <XCircle className="size-3" />
                  Port already in use
                </p>
              ) : portStatus === "reserved" ? (
                <p className="flex items-center gap-1 text-xs text-destructive">
                  <XCircle className="size-3" />
                  Reserved system port
                </p>
              ) : null}
            </div>

            {/* Local Only — skips the PlayIT tunnel setup
                entirely; the container's port is still published on the
                host as usual, just reachable only by whoever can already
                reach this host (same LAN/machine), not a public address. */}
            <div className="flex items-start gap-2.5 rounded-md border border-border p-3">
              <button
                type="button"
                role="checkbox"
                aria-checked={form.local_only}
                disabled={submitting}
                onClick={() =>
                  setForm((prev) => ({
                    ...prev,
                    local_only: !prev.local_only,
                  }))
                }
                className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  form.local_only
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background"
                }`}
              >
                {form.local_only && (
                  <svg
                    viewBox="0 0 12 12"
                    className="size-3"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <polyline points="1.5,6 4.5,9 10.5,3" />
                  </svg>
                )}
              </button>
              <div
                className="cursor-pointer select-none"
                onClick={() =>
                  !submitting &&
                  setForm((prev) => ({
                    ...prev,
                    local_only: !prev.local_only,
                  }))
                }
              >
                <p className="text-sm font-medium">Local Only</p>
                <p className="text-xs text-muted-foreground">
                  Skip the public tunnel and DNS setup — the server is only
                  reachable on your local network, via this machine&apos;s
                  own IP address and the port above.
                </p>
              </div>
            </div>

            {/* RAM — Bedrock has no JVM, so there's no min heap, just a memory cap */}
            <div
              className={
                form.type === "bedrock"
                  ? "grid grid-cols-1 gap-3"
                  : "grid grid-cols-2 gap-3"
              }
            >
              {form.type !== "bedrock" && (
                <div className="space-y-1.5">
                  <Label htmlFor="srv-memmin">Min RAM (GB)</Label>
                  <Input
                    id="srv-memmin"
                    type="number"
                    min={1}
                    value={form.mem_min}
                    onChange={(e) => handleChange("mem_min", e.target.value)}
                    disabled={submitting}
                    aria-invalid={!!errors.mem_min}
                  />
                  {errors.mem_min && (
                    <p className="text-xs text-destructive">
                      {errors.mem_min}
                    </p>
                  )}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="srv-memmax">
                  {form.type === "bedrock" ? "Memory Limit (GB)" : "Max RAM (GB)"}
                </Label>
                <Input
                  id="srv-memmax"
                  type="number"
                  min={1}
                  value={form.mem_max}
                  onChange={(e) => handleChange("mem_max", e.target.value)}
                  disabled={submitting}
                  aria-invalid={!!errors.mem_max}
                />
                {errors.mem_max && (
                  <p className="text-xs text-destructive">{errors.mem_max}</p>
                )}
              </div>
            </div>

            {/* Initial Properties (collapsible) */}
            <div className="space-y-1.5">
              <button
                type="button"
                className="flex w-full items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={() => setShowProps((s) => !s)}
              >
                <span>Initial Properties</span>
                {props.length > 0 && (
                  <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                    {props.length}
                  </span>
                )}
                <ChevronDown
                  className={`ml-auto size-3.5 transition-transform ${
                    showProps ? "rotate-180" : ""
                  }`}
                />
              </button>
              {showProps && (
                <div className="space-y-1.5">
                  {props.map((p, i) => (
                    <div key={i} className="flex gap-1.5">
                      <Input
                        className="h-7 flex-1 font-mono text-xs"
                        placeholder="key (e.g. motd)"
                        value={p.key}
                        onChange={(e) =>
                          setProps((prev) =>
                            prev.map((x, idx) =>
                              idx === i ? { ...x, key: e.target.value } : x
                            )
                          )
                        }
                        disabled={submitting}
                      />
                      <Input
                        className="h-7 flex-1 text-xs"
                        placeholder="value"
                        value={p.value}
                        onChange={(e) =>
                          setProps((prev) =>
                            prev.map((x, idx) =>
                              idx === i ? { ...x, value: e.target.value } : x
                            )
                          )
                        }
                        disabled={submitting}
                      />
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() =>
                          setProps((prev) => prev.filter((_, idx) => idx !== i))
                        }
                        disabled={submitting}
                      >
                        <X className="size-3" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 w-full text-xs"
                    onClick={() =>
                      setProps((prev) => [...prev, { key: "", value: "" }])
                    }
                    disabled={submitting}
                  >
                    <Plus className="size-3" />
                    Add Property
                  </Button>
                </div>
              )}
            </div>

            <DialogFooter className="gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  submitting ||
                  portStatus === "taken" ||
                  portStatus === "reserved" ||
                  portStatus === "invalid"
                }
                className="flex-1"
              >
                {submitting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Plus className="size-4" />
                )}
                {submitting ? "Creating…" : "Create Server"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
