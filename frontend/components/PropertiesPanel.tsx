"use client"

import { useState, useEffect, useCallback } from "react"
import { Loader2, Save, Search, RotateCcw } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ServerProperties } from "@/lib/types"
import { api } from "@/lib/api"

interface Props {
  serverId: number
}

export function PropertiesPanel({ serverId }: Props) {
  const [original, setOriginal] = useState<ServerProperties>({})
  const [values, setValues] = useState<ServerProperties>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.properties.get(serverId)
      const props: ServerProperties = res?.properties ?? {}
      setOriginal(props)
      setValues(props)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load properties"
      )
    } finally {
      setLoading(false)
    }
  }, [serverId])

  useEffect(() => {
    load()
  }, [load])

  const dirtyKeys = Object.keys(values).filter((k) => values[k] !== original[k])

  async function handleSave() {
    if (dirtyKeys.length === 0) return
    setSaving(true)
    try {
      const changed = Object.fromEntries(dirtyKeys.map((k) => [k, values[k]]))
      const res = await api.properties.update(serverId, changed)
      if (Array.isArray(res?.rejected) && res.rejected.length > 0) {
        toast.warning(
          `Some properties are managed by the server and were ignored: ${res.rejected.join(", ")}`
        )
      }
      setOriginal((prev) => ({ ...prev, ...changed }))
      if (res?.restart_required) {
        toast.success("Properties saved — restart the server to apply changes")
      } else {
        toast.success("Properties saved")
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  function handleReset() {
    setValues(original)
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const keys = Object.keys(values)
    .sort()
    .filter((k) => !search || k.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter properties…"
            className="w-full min-w-0 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {dirtyKeys.length > 0 && (
            <>
              <span className="text-xs text-muted-foreground">
                {dirtyKeys.length} changed
              </span>
              <Button size="sm" variant="outline" onClick={handleReset}>
                <RotateCcw className="size-3.5" />
                Reset
              </Button>
            </>
          )}
          <Button size="sm" disabled={dirtyKeys.length === 0 || saving} onClick={handleSave}>
            {saving ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Save className="size-3.5" />
            )}
            Save
          </Button>
        </div>
      </div>

      {/* Property list */}
      <div className="flex-1 overflow-y-auto" style={{ minHeight: "400px" }}>
        {keys.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            No properties found
          </div>
        ) : (
          <div className="divide-y divide-border">
            {keys.map((key) => {
              const isDirty = values[key] !== original[key]
              return (
                <div
                  key={key}
                  className="flex items-center gap-4 px-4 py-2.5"
                >
                  <span className="w-56 shrink-0 truncate font-mono text-xs text-muted-foreground">
                    {key}
                  </span>
                  <Input
                    className={`h-8 flex-1 font-mono text-xs ${isDirty ? "border-primary" : ""}`}
                    value={values[key]}
                    onChange={(e) =>
                      setValues((v) => ({ ...v, [key]: e.target.value }))
                    }
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
