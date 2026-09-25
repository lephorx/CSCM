"use client"

import { useState, useEffect } from "react"
import { ArrowLeft, Loader2, RotateCcw, Save } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { TopNav } from "@/components/TopNav"
import { api } from "@/lib/api"
import {
  ALL_DEFAULTS,
  JAVA_ONLY_CATEGORIES,
  BEDROCK_ONLY_CATEGORIES,
  SHARED_CATEGORIES,
  type PropDef,
} from "@/lib/minecraftProperties"

// ── Input helpers ─────────────────────────────────────────────────────────────

const INPUT_BASE =
  "h-8 w-full rounded border border-input bg-background px-2.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"

function PropInput({
  def,
  value,
  disabled,
  onChange,
}: {
  def: PropDef
  value: string
  disabled: boolean
  onChange: (v: string) => void
}) {
  if (def.type === "boolean") {
    return (
      <select
        className={INPUT_BASE}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    )
  }
  if (def.type === "select" && def.options) {
    return (
      <select
        className={INPUT_BASE}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {def.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    )
  }
  return (
    <input
      type={def.type === "number" ? "number" : "text"}
      className={INPUT_BASE}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function CategoryList({
  categories,
  values,
  saving,
  isModified,
  onChange,
}: {
  categories: { title: string; props: PropDef[] }[]
  values: Record<string, string>
  saving: boolean
  isModified: (key: string) => boolean
  onChange: (key: string, value: string) => void
}) {
  return (
    <div className="space-y-8">
      {categories.map((cat) => (
        <section key={cat.title}>
          <h3 className="mb-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
            {cat.title}
          </h3>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cat.props.map((def) => {
              const val = values[def.key] ?? ALL_DEFAULTS[def.key] ?? ""
              const modified = isModified(def.key)
              return (
                <div
                  key={def.key}
                  className={`rounded border p-2.5 transition-colors ${
                    modified
                      ? "border-primary/50 bg-primary/5"
                      : "border-border bg-card"
                  }`}
                >
                  <div className="mb-0.5 flex items-center justify-between gap-1">
                    <span className="text-xs leading-tight font-medium">
                      {def.label}
                    </span>
                    {modified && (
                      <span className="shrink-0 rounded-full bg-primary/15 px-1.5 py-px text-[9px] font-semibold text-primary">
                        override
                      </span>
                    )}
                  </div>
                  <p className="mb-1.5 font-mono text-[10px] text-muted-foreground">
                    {def.key}
                  </p>
                  <PropInput
                    def={def}
                    value={val}
                    disabled={saving}
                    onChange={(v) => onChange(def.key, v)}
                  />
                  {def.hint && (
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      {def.hint}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  user: { id: number; username: string } | null
  onLogout: () => void
  onClose: () => void
}

export function DefaultsEditor({ user, onLogout, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({
    ...ALL_DEFAULTS,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.defaults
      .getProperties()
      .then((res) => {
        const stored: Record<string, string> = res?.properties ?? {}
        setValues((prev) => ({ ...prev, ...stored }))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function setValue(key: string, val: string) {
    setValues((prev) => ({ ...prev, [key]: val }))
  }

  function isModified(key: string) {
    return values[key] !== ALL_DEFAULTS[key]
  }

  const modifiedCount = Object.keys(ALL_DEFAULTS).filter(isModified).length

  async function handleSave() {
    setSaving(true)
    try {
      const toSave: Record<string, string> = {}
      for (const key of Object.keys(ALL_DEFAULTS)) {
        if (isModified(key)) toSave[key] = values[key]
      }
      await api.defaults.putProperties(toSave)
      toast.success(
        modifiedCount === 0
          ? "Defaults cleared (all values are Minecraft defaults)"
          : `Saved ${modifiedCount} override${modifiedCount !== 1 ? "s" : ""}`
      )
      onClose()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save defaults"
      )
    } finally {
      setSaving(false)
    }
  }

  function handleResetAll() {
    setValues({ ...ALL_DEFAULTS })
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav user={user} onLogout={onLogout} />

      <main className="mx-auto max-w-screen-xl px-6 py-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              className="gap-1.5"
              onClick={onClose}
            >
              <ArrowLeft className="size-4" />
              Back
            </Button>
            <div>
              <h2 className="text-lg font-semibold">
                Default Server Properties
              </h2>
              <p className="text-sm text-muted-foreground">
                {loading
                  ? "Loading saved overrides…"
                  : modifiedCount > 0
                    ? `${modifiedCount} propert${modifiedCount !== 1 ? "ies" : "y"} differ from Minecraft defaults — only those will be saved`
                    : "All values match Minecraft defaults — nothing will be saved"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleResetAll}
              disabled={saving || modifiedCount === 0}
            >
              <RotateCcw className="size-3.5" />
              Reset all
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Save className="size-3.5" />
              )}
              {saving
                ? "Saving…"
                : `Save${modifiedCount > 0 ? ` (${modifiedCount})` : ""}`}
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-12">
            <div>
              <h2 className="mb-4 text-sm font-semibold">
                Shared — Java &amp; Bedrock
              </h2>
              <CategoryList
                categories={SHARED_CATEGORIES}
                values={values}
                saving={saving}
                isModified={isModified}
                onChange={setValue}
              />
            </div>

            <div>
              <h2 className="mb-4 text-sm font-semibold">Java Only</h2>
              <CategoryList
                categories={JAVA_ONLY_CATEGORIES}
                values={values}
                saving={saving}
                isModified={isModified}
                onChange={setValue}
              />
            </div>

            <div>
              <h2 className="mb-4 text-sm font-semibold">Bedrock Only</h2>
              <CategoryList
                categories={BEDROCK_ONLY_CATEGORIES}
                values={values}
                saving={saving}
                isModified={isModified}
                onChange={setValue}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
