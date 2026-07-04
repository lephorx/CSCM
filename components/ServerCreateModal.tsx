"use client"

import { useState, useEffect, useRef } from "react"
import {
  Loader2,
  Plus,
  CheckCircle2,
  XCircle,
  X,
  ChevronDown,
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
import type { Server } from "@/lib/types"
import { VersionPicker } from "@/components/VersionPicker"

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
  19132, // Bedrock default
])

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

type PortStatus =
  | "idle"
  | "checking"
  | "available"
  | "taken"
  | "reserved"
  | "invalid"

export function ServerCreateModal({ open, onOpenChange, onCreated }: Props) {
  const [serverTypes, setServerTypes] = useState<string[]>([
    "paper",
    "forge",
    "fabric",
    "vanilla",
    "purpur",
  ])
  const [loading, setLoading] = useState(false)
  const [usedPorts, setUsedPorts] = useState<Set<number>>(new Set())
  const [portStatus, setPortStatus] = useState<PortStatus>("idle")

  const [form, setForm] = useState({
    name: "",
    type: "paper",
    version: "1.21.4",
    port: "25565",
    mem_min: "2",
    mem_max: "4",
  })

  const [errors, setErrors] = useState<Partial<typeof form>>({})
  const [props, setProps] = useState<{ key: string; value: string }[]>([])
  const [showProps, setShowProps] = useState(false)
  const portDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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

    api.defaults
      .getProperties()
      .then((res) => {
        const p: Record<string, string> = res?.properties ?? {}
        setProps(
          Object.entries(p).map(([key, value]) => ({
            key,
            value: String(value),
          }))
        )
      })
      .catch(() => {})
  }, [open])

  // Debounced port availability check
  useEffect(() => {
    if (portDebounceRef.current) clearTimeout(portDebounceRef.current)
    const port = parseInt(form.port, 10)

    if (!form.port || isNaN(port)) {
      setPortStatus("idle")
      return
    }
    if (port < PORT_MIN || port > PORT_MAX) {
      setPortStatus("invalid")
      return
    }

    setPortStatus("checking")
    portDebounceRef.current = setTimeout(() => {
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

    const memMin = parseInt(form.mem_min, 10)
    const memMax = parseInt(form.mem_max, 10)
    if (isNaN(memMin) || memMin < 1) next.mem_min = "Must be at least 1 GB"
    if (isNaN(memMax) || memMax < memMin)
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

    setLoading(true)
    try {
      const propsObj: Record<string, string> = {}
      for (const p of props) {
        const k = p.key.trim()
        if (k) propsObj[k] = p.value
      }
      const payload: Parameters<typeof api.servers.create>[0] = {
        name: form.name.trim(),
        type: form.type,
        version: form.version.trim(),
        port: parseInt(form.port, 10),
        mem_min: parseInt(form.mem_min, 10),
        mem_max: parseInt(form.mem_max, 10),
        ...(Object.keys(propsObj).length > 0 ? { properties: propsObj } : {}),
      }

      await api.servers.create(payload)
      toast.success("Server created successfully")
      onOpenChange(false)
      onCreated()
      setForm({
        name: "",
        type: "paper",
        version: "1.21.4",
        port: "25565",
        mem_min: "2",
        mem_max: "4",
      })
      setErrors({})
      setPortStatus("idle")
      setProps([])
      setShowProps(false)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create server"
      )
    } finally {
      setLoading(false)
    }
  }

  const portNum = parseInt(form.port, 10)
  const portOutOfRange =
    !isNaN(portNum) && (portNum < PORT_MIN || portNum > PORT_MAX)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Server</DialogTitle>
        </DialogHeader>

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
              disabled={loading}
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
              onValueChange={(v) => handleChange("type", v)}
              disabled={loading}
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

          {/* Version */}
          <div className="space-y-1.5">
            <Label htmlFor="srv-version">Version</Label>
            <VersionPicker
              value={form.version}
              onChange={(v) => handleChange("version", v)}
              disabled={loading}
            />
            {errors.version && (
              <p className="text-xs text-destructive">{errors.version}</p>
            )}
          </div>

          {/* Port */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="srv-port">Port</Label>
              <span className="text-xs text-muted-foreground">
                {PORT_MIN}–{PORT_MAX}
              </span>
            </div>
            <Input
              id="srv-port"
              type="number"
              min={PORT_MIN}
              max={PORT_MAX}
              value={form.port}
              onChange={(e) => handleChange("port", e.target.value)}
              disabled={loading}
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

          {/* RAM */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="srv-memmin">Min RAM (GB)</Label>
              <Input
                id="srv-memmin"
                type="number"
                min={1}
                value={form.mem_min}
                onChange={(e) => handleChange("mem_min", e.target.value)}
                disabled={loading}
                aria-invalid={!!errors.mem_min}
              />
              {errors.mem_min && (
                <p className="text-xs text-destructive">{errors.mem_min}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="srv-memmax">Max RAM (GB)</Label>
              <Input
                id="srv-memmax"
                type="number"
                min={1}
                value={form.mem_max}
                onChange={(e) => handleChange("mem_max", e.target.value)}
                disabled={loading}
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
                      disabled={loading}
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
                      disabled={loading}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        setProps((prev) => prev.filter((_, idx) => idx !== i))
                      }
                      disabled={loading}
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
                  disabled={loading}
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
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                loading ||
                portStatus === "taken" ||
                portStatus === "reserved" ||
                portStatus === "invalid"
              }
              className="flex-1"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {loading ? "Creating…" : "Create Server"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
