"use client"

import { useState, useEffect } from "react"
import { ArrowLeft, Loader2, RotateCcw, Save } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { TopNav } from "@/components/TopNav"
import { api } from "@/lib/api"

// ── Minecraft Java Edition server.properties defaults ─────────────────────────
// Excludes blacklisted keys: server-port, enable-rcon, rcon.port, rcon.password

const MC_DEFAULTS: Record<string, string> = {
  "accept-transfers": "false",
  "allow-flight": "false",
  "allow-nether": "true",
  "broadcast-console-to-ops": "true",
  "broadcast-rcon-to-ops": "true",
  difficulty: "easy",
  "enable-command-block": "false",
  "enable-query": "false",
  "enable-status": "true",
  "enforce-secure-profile": "true",
  "enforce-whitelist": "false",
  "entity-broadcast-range-percentage": "100",
  "force-gamemode": "false",
  "function-permission-level": "2",
  gamemode: "survival",
  "generate-structures": "true",
  "generator-settings": "{}",
  hardcore: "false",
  "hide-online-players": "false",
  "initial-disabled-packs": "",
  "initial-enabled-packs": "vanilla",
  "level-name": "world",
  "level-seed": "",
  "level-type": "minecraft\\:normal",
  "log-ips": "true",
  "max-chained-neighbor-updates": "1000000",
  "max-players": "20",
  "max-tick-time": "60000",
  "max-world-size": "29999984",
  motd: "A Minecraft Server",
  "network-compression-threshold": "256",
  "online-mode": "true",
  "op-permission-level": "4",
  "pause-when-empty-seconds": "60",
  "player-idle-timeout": "0",
  "prevent-proxy-connections": "false",
  pvp: "true",
  "query.port": "25565",
  "rate-limit": "0",
  "region-file-compression": "deflate",
  "require-resource-pack": "false",
  "resource-pack": "",
  "resource-pack-id": "",
  "resource-pack-prompt": "",
  "resource-pack-sha1": "",
  "server-ip": "",
  "simulation-distance": "10",
  "spawn-animals": "true",
  "spawn-monsters": "true",
  "spawn-npcs": "true",
  "spawn-protection": "16",
  "sync-chunk-writes": "true",
  "text-filtering-config": "",
  "text-filtering-version": "0",
  "use-native-transport": "true",
  "view-distance": "10",
  "white-list": "false",
}

type PropType = "text" | "number" | "boolean" | "select"

interface PropDef {
  key: string
  label: string
  type: PropType
  options?: string[]
  hint?: string
}

const MC_CATEGORIES: { title: string; props: PropDef[] }[] = [
  {
    title: "World",
    props: [
      { key: "level-name", label: "Level Name", type: "text" },
      {
        key: "level-seed",
        label: "Level Seed",
        type: "text",
        hint: "Leave empty for random",
      },
      {
        key: "level-type",
        label: "Level Type",
        type: "select",
        options: [
          "minecraft\\:normal",
          "minecraft\\:flat",
          "minecraft\\:large_biomes",
          "minecraft\\:amplified",
          "minecraft\\:single_biome_surface",
          "minecraft\\:debug",
        ],
      },
      {
        key: "generate-structures",
        label: "Generate Structures",
        type: "boolean",
      },
      {
        key: "generator-settings",
        label: "Generator Settings",
        type: "text",
        hint: "JSON for flat/single-biome",
      },
      {
        key: "max-world-size",
        label: "Max World Size (blocks)",
        type: "number",
      },
    ],
  },
  {
    title: "Gameplay",
    props: [
      {
        key: "gamemode",
        label: "Default Game Mode",
        type: "select",
        options: ["survival", "creative", "adventure", "spectator"],
      },
      {
        key: "difficulty",
        label: "Difficulty",
        type: "select",
        options: ["peaceful", "easy", "normal", "hard"],
      },
      { key: "hardcore", label: "Hardcore Mode", type: "boolean" },
      { key: "pvp", label: "PvP", type: "boolean" },
      { key: "force-gamemode", label: "Force Gamemode", type: "boolean" },
      { key: "allow-nether", label: "Allow Nether", type: "boolean" },
      { key: "spawn-animals", label: "Spawn Animals", type: "boolean" },
      { key: "spawn-monsters", label: "Spawn Monsters", type: "boolean" },
      { key: "spawn-npcs", label: "Spawn NPCs / Villagers", type: "boolean" },
      {
        key: "spawn-protection",
        label: "Spawn Protection Radius",
        type: "number",
        hint: "0 = disabled",
      },
      { key: "allow-flight", label: "Allow Flight", type: "boolean" },
      {
        key: "enable-command-block",
        label: "Enable Command Blocks",
        type: "boolean",
      },
      {
        key: "function-permission-level",
        label: "Function Permission Level",
        type: "number",
      },
    ],
  },
  {
    title: "Players",
    props: [
      { key: "max-players", label: "Max Players", type: "number" },
      { key: "online-mode", label: "Online Mode (auth)", type: "boolean" },
      { key: "white-list", label: "Whitelist Enabled", type: "boolean" },
      { key: "enforce-whitelist", label: "Enforce Whitelist", type: "boolean" },
      {
        key: "player-idle-timeout",
        label: "Idle Timeout (min)",
        type: "number",
        hint: "0 = never",
      },
      {
        key: "op-permission-level",
        label: "Op Permission Level",
        type: "number",
      },
      {
        key: "enforce-secure-profile",
        label: "Enforce Secure Chat Profile",
        type: "boolean",
      },
      {
        key: "hide-online-players",
        label: "Hide Online Players",
        type: "boolean",
      },
    ],
  },
  {
    title: "Server",
    props: [
      { key: "motd", label: "MOTD", type: "text" },
      {
        key: "server-ip",
        label: "Bind IP",
        type: "text",
        hint: "Empty = all interfaces",
      },
      { key: "view-distance", label: "View Distance (chunks)", type: "number" },
      {
        key: "simulation-distance",
        label: "Simulation Distance (chunks)",
        type: "number",
      },
      {
        key: "entity-broadcast-range-percentage",
        label: "Entity Broadcast Range %",
        type: "number",
      },
      {
        key: "broadcast-console-to-ops",
        label: "Broadcast Console to Ops",
        type: "boolean",
      },
      {
        key: "broadcast-rcon-to-ops",
        label: "Broadcast RCON to Ops",
        type: "boolean",
      },
      {
        key: "enable-status",
        label: "Enable Server Status (ping)",
        type: "boolean",
      },
      { key: "enable-query", label: "Enable GameSpy4 Query", type: "boolean" },
      { key: "query.port", label: "Query Port", type: "number" },
      {
        key: "prevent-proxy-connections",
        label: "Prevent Proxy Connections",
        type: "boolean",
      },
      { key: "log-ips", label: "Log Player IPs", type: "boolean" },
    ],
  },
  {
    title: "Resource Pack",
    props: [
      { key: "resource-pack", label: "Resource Pack URL", type: "text" },
      { key: "resource-pack-id", label: "Resource Pack UUID", type: "text" },
      { key: "resource-pack-sha1", label: "Resource Pack SHA-1", type: "text" },
      {
        key: "resource-pack-prompt",
        label: "Resource Pack Prompt",
        type: "text",
      },
      {
        key: "require-resource-pack",
        label: "Require Resource Pack",
        type: "boolean",
      },
    ],
  },
  {
    title: "Performance",
    props: [
      {
        key: "max-tick-time",
        label: "Max Tick Time (ms)",
        type: "number",
        hint: "-1 = disabled",
      },
      {
        key: "network-compression-threshold",
        label: "Network Compression Threshold",
        type: "number",
      },
      {
        key: "max-chained-neighbor-updates",
        label: "Max Chained Neighbor Updates",
        type: "number",
      },
      { key: "sync-chunk-writes", label: "Sync Chunk Writes", type: "boolean" },
      {
        key: "use-native-transport",
        label: "Use Native Transport (Netty)",
        type: "boolean",
      },
      {
        key: "rate-limit",
        label: "Packet Rate Limit (per player)",
        type: "number",
        hint: "0 = no limit",
      },
      {
        key: "region-file-compression",
        label: "Region File Compression",
        type: "select",
        options: ["deflate", "lz4", "zstd", "none"],
      },
    ],
  },
  {
    title: "Misc",
    props: [
      {
        key: "pause-when-empty-seconds",
        label: "Pause When Empty (seconds)",
        type: "number",
      },
      {
        key: "accept-transfers",
        label: "Accept Server Transfers",
        type: "boolean",
      },
      {
        key: "initial-enabled-packs",
        label: "Initial Enabled Data Packs",
        type: "text",
      },
      {
        key: "initial-disabled-packs",
        label: "Initial Disabled Data Packs",
        type: "text",
      },
      {
        key: "text-filtering-config",
        label: "Text Filtering Config",
        type: "text",
      },
      {
        key: "text-filtering-version",
        label: "Text Filtering Version",
        type: "number",
      },
    ],
  },
]

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

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  user: { id: number; username: string } | null
  onLogout: () => void
  onClose: () => void
}

export function DefaultsEditor({ user, onLogout, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({
    ...MC_DEFAULTS,
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
    return values[key] !== MC_DEFAULTS[key]
  }

  const modifiedCount = Object.keys(MC_DEFAULTS).filter(isModified).length

  async function handleSave() {
    setSaving(true)
    try {
      const toSave: Record<string, string> = {}
      for (const key of Object.keys(MC_DEFAULTS)) {
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
    setValues({ ...MC_DEFAULTS })
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
          <div className="space-y-8">
            {MC_CATEGORIES.map((cat) => (
              <section key={cat.title}>
                <h3 className="mb-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                  {cat.title}
                </h3>
                <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {cat.props.map((def) => {
                    const val = values[def.key] ?? MC_DEFAULTS[def.key] ?? ""
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
                          onChange={(v) => setValue(def.key, v)}
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
        )}
      </main>
    </div>
  )
}
