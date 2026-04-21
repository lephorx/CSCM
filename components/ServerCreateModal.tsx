"use client"

import { useState, useEffect, useRef } from "react"
import { Loader2, Plus, CheckCircle2, XCircle } from "lucide-react"
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

const RAM_OPTIONS = [
  { label: "No limit", value: "none" },
  { label: "512 MB", value: "512M" },
  { label: "1 GB", value: "1G" },
  { label: "2 GB", value: "2G" },
  { label: "4 GB", value: "4G" },
  { label: "8 GB", value: "8G" },
  { label: "16 GB", value: "16G" },
  { label: "32 GB", value: "32G" },
]

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
    version: "1.20.1",
    port: "25565",
    mem_min: "1G",
    mem_max: "2G",
  })

  const [errors, setErrors] = useState<Partial<typeof form>>({})
  const portDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load server types and existing ports when modal opens
  useEffect(() => {
    if (!open) return
    api
      .serverTypes()
      .then((res) => {
        if (Array.isArray(res?.data)) setServerTypes(res.data)
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
      const payload: Parameters<typeof api.servers.create>[0] = {
        name: form.name.trim(),
        type: form.type,
        version: form.version.trim(),
        port: parseInt(form.port, 10),
        ...(form.mem_min && form.mem_min !== "none"
          ? { mem_min: form.mem_min }
          : {}),
        ...(form.mem_max && form.mem_max !== "none"
          ? { mem_max: form.mem_max }
          : {}),
      }

      await api.servers.create(payload)
      toast.success("Server created successfully")
      onOpenChange(false)
      onCreated()
      setForm({
        name: "",
        type: "paper",
        version: "1.20.1",
        port: "25565",
        mem_min: "1G",
        mem_max: "2G",
      })
      setErrors({})
      setPortStatus("idle")
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
      <DialogContent className="sm:max-w-md">
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
              <Label htmlFor="srv-memmin">Min RAM</Label>
              <Select
                value={form.mem_min}
                onValueChange={(v) => handleChange("mem_min", v)}
                disabled={loading}
              >
                <SelectTrigger id="srv-memmin" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RAM_OPTIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="srv-memmax">Max RAM</Label>
              <Select
                value={form.mem_max}
                onValueChange={(v) => handleChange("mem_max", v)}
                disabled={loading}
              >
                <SelectTrigger id="srv-memmax" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RAM_OPTIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
