"use client"

import { useState, useEffect } from "react"
import { Loader2, Plus } from "lucide-react"
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
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"

const RAM_OPTIONS = ["512M", "1G", "2G", "4G", "8G", "16G", "32G"]

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

export function ServerCreateModal({ open, onOpenChange, onCreated }: Props) {
  const [serverTypes, setServerTypes] = useState<string[]>([
    "paper",
    "forge",
    "fabric",
    "vanilla",
    "purpur",
  ])
  const [loading, setLoading] = useState(false)
  const [modsEnabled, setModsEnabled] = useState(false)

  const [form, setForm] = useState({
    name: "",
    type: "paper",
    version: "1.20.1",
    port: "25565",
    mem_min: "1G",
    mem_max: "2G",
  })

  const [errors, setErrors] = useState<Partial<typeof form>>({})

  useEffect(() => {
    api
      .serverTypes()
      .then((res) => {
        if (Array.isArray(res?.data)) setServerTypes(res.data)
        else if (Array.isArray(res)) setServerTypes(res)
      })
      .catch(() => {
        /* use defaults */
      })
  }, [])

  function handleChange(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  function validate() {
    const next: Partial<typeof form> = {}
    if (!form.name.trim()) next.name = "Server name is required"
    if (!form.version.trim()) next.version = "Version is required"
    const port = parseInt(form.port, 10)
    if (isNaN(port) || port < 1024 || port > 65535)
      next.port = "Port must be between 1024 and 65535"
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
      await api.servers.create({
        name: form.name.trim(),
        type: form.type,
        version: form.version.trim(),
        port: parseInt(form.port, 10),
        mem_min: form.mem_min,
        mem_max: form.mem_max,
      })
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
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create server"
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Server</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
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
              aria-describedby={errors.name ? "srv-name-err" : undefined}
            />
            {errors.name && (
              <p id="srv-name-err" className="text-xs text-destructive">
                {errors.name}
              </p>
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
            <Input
              id="srv-version"
              placeholder="1.20.1"
              value={form.version}
              onChange={(e) => handleChange("version", e.target.value)}
              disabled={loading}
              aria-invalid={!!errors.version}
            />
            {errors.version && (
              <p className="text-xs text-destructive">{errors.version}</p>
            )}
          </div>

          {/* Port */}
          <div className="space-y-1.5">
            <Label htmlFor="srv-port">Port</Label>
            <Input
              id="srv-port"
              type="number"
              min={1024}
              max={65535}
              value={form.port}
              onChange={(e) => handleChange("port", e.target.value)}
              disabled={loading}
              aria-invalid={!!errors.port}
              aria-describedby={errors.port ? "srv-port-err" : undefined}
            />
            {errors.port && (
              <p id="srv-port-err" className="text-xs text-destructive">
                {errors.port}
              </p>
            )}
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
                    <SelectItem key={r} value={r}>
                      {r}
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
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Mods/Plugins toggle */}
          <div className="flex items-center justify-between py-1">
            <Label htmlFor="srv-mods" className="cursor-pointer">
              Enable mods / plugins
            </Label>
            <Switch
              id="srv-mods"
              checked={modsEnabled}
              onCheckedChange={setModsEnabled}
              disabled={loading}
            />
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
            <Button type="submit" disabled={loading} className="flex-1">
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
