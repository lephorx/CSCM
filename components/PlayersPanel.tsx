"use client"

import { useState, useEffect, useCallback, memo } from "react"
import {
  Loader2,
  UserPlus,
  UserX,
  ShieldOff,
  ShieldCheck,
  LogOut,
  Ban,
  Trash2,
  Plus,
  Clock,
  ChevronRight,
  Heart,
  Skull,
  Utensils,
  Minus,
  MapPin,
  Navigation,
  BarChart2,
  Database,
  RefreshCw,
  Gamepad2,
  UserCheck,
  Zap,
  ArrowLeft,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type {
  PlayersData,
  PlayerRef,
  BannedPlayer,
  PlayerHistoryEntry,
  InventoryItem,
  PlayerData,
  PlayerStatistics,
} from "@/lib/types"
import { api } from "@/lib/api"
import { playerName } from "@/lib/utils"

// ── Constants ────────────────────────────────────────────────────────────────

const GAME_MODES: Record<number, string> = {
  0: "Survival",
  1: "Creative",
  2: "Adventure",
  3: "Spectator",
}

const ARMOR_SLOTS = [103, 102, 101, 100] // head → feet

// ── Helpers ──────────────────────────────────────────────────────────────────

function itemTextureUrl(id: string) {
  // Convert "minecraft:diamond_sword" → "Diamond_Sword" for the wiki invicon
  const name = id
    .replace(/^minecraft:/, "")
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("_")
  return `https://minecraft.wiki/w/Special:Redirect/file/Invicon_${name}.png`
}

function playerHeadUrl(username: string) {
  return `https://mc-heads.net/avatar/${encodeURIComponent(username)}/32`
}

function buildMainGrid(items: InventoryItem[]): (InventoryItem | null)[] {
  const bySlot = new Map(items.map((it) => [it.slot, it]))
  return [
    ...Array.from({ length: 27 }, (_, i) => bySlot.get(i + 9) ?? null),
    ...Array.from({ length: 9 }, (_, i) => bySlot.get(i) ?? null),
  ]
}

function buildEnderGrid(items: InventoryItem[]): (InventoryItem | null)[] {
  const bySlot = new Map(items.map((it) => [it.slot, it]))
  return Array.from({ length: 27 }, (_, i) => bySlot.get(i) ?? null)
}

function visualIndexToSlot(index: number): number {
  return index < 27 ? index + 9 : index - 27
}

function fmtNum(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(Math.round(n))
}

// ── Shared layout ─────────────────────────────────────────────────────────────

function AddRow({
  placeholder,
  disabled,
  onAdd,
}: {
  placeholder: string
  disabled: boolean
  onAdd: (username: string) => Promise<void>
}) {
  const [value, setValue] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const username = value.trim()
    if (!username) return
    setSubmitting(true)
    try {
      await onAdd(username)
      setValue("")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <Input
        className="h-8 flex-1 text-xs"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled || submitting}
      />
      <Button
        type="submit"
        size="sm"
        variant="outline"
        disabled={disabled || submitting || !value.trim()}
      >
        {submitting ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <UserPlus className="size-3.5" />
        )}
        Add
      </Button>
    </form>
  )
}

function Section({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 border border-border p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {title}
        </h3>
        <span className="text-xs text-muted-foreground">{count}</span>
      </div>
      {children}
    </div>
  )
}

function EmptyRow({ label }: { label: string }) {
  return <p className="py-1 text-xs text-muted-foreground">{label}</p>
}

// ── Minecraft pixel-art icons ───────────────────────────────────────────────
// Pre-computed once at module level — no per-render work.
// Heart shape expressed as 6 grouped rects instead of 26 individual 1×1 rects.

const SVG_PROPS = {
  width: 9,
  height: 9,
  style: { imageRendering: "pixelated" as const, display: "block" as const },
} as const

// Heart rects: [x, y, w, h]
const HEART_FULL_RECTS = [
  [1, 0, 2, 1],
  [5, 0, 2, 1],
  [0, 1, 8, 3],
  [1, 4, 6, 1],
  [2, 5, 4, 1],
  [3, 6, 2, 1],
]
// Half-heart: left side (x<4) red, right side grey — split at the midpoint
const HEART_HALF_RED = [
  [1, 0, 2, 1],
  [0, 1, 4, 3],
  [1, 4, 3, 1],
  [2, 5, 2, 1],
  [3, 6, 1, 1],
]
const HEART_HALF_GREY = [
  [5, 0, 2, 1],
  [4, 1, 4, 3],
  [4, 4, 3, 1],
  [4, 5, 2, 1],
  [4, 6, 1, 1],
]
// Food drumstick rects (diagonal chicken-leg shape)
const FOOD_RECTS = [
  [4, 0, 2, 1],
  [3, 1, 4, 1],
  [2, 2, 4, 1],
  [1, 3, 3, 1],
  [0, 4, 3, 1],
  [0, 5, 2, 1],
  [1, 6, 1, 1],
]

function heartRects(rects: number[][], fill: string) {
  return rects.map(([x, y, w, h], i) => (
    <rect key={i} x={x} y={y} width={w} height={h} fill={fill} />
  ))
}

// All 6 icon variants are static — created once, reused for every render
const MC_HEART: Record<"full" | "half" | "empty", React.ReactElement> = {
  full: (
    <svg {...SVG_PROPS} viewBox="0 0 8 7">
      {heartRects(HEART_FULL_RECTS, "#FF3030")}
    </svg>
  ),
  half: (
    <svg {...SVG_PROPS} viewBox="0 0 8 7">
      {heartRects(HEART_HALF_RED, "#FF3030")}
      {heartRects(HEART_HALF_GREY, "#4C4C4C")}
    </svg>
  ),
  empty: (
    <svg {...SVG_PROPS} viewBox="0 0 8 7">
      {heartRects(HEART_FULL_RECTS, "#4C4C4C")}
    </svg>
  ),
}

const MC_FOOD: Record<"full" | "half" | "empty", React.ReactElement> = {
  full: (
    <svg {...SVG_PROPS} viewBox="0 0 8 8">
      {heartRects(FOOD_RECTS, "#CC8822")}
    </svg>
  ),
  half: (
    <svg
      {...SVG_PROPS}
      viewBox="0 0 8 8"
      style={{ imageRendering: "pixelated", display: "block", opacity: 0.55 }}
    >
      {heartRects(FOOD_RECTS, "#CC8822")}
    </svg>
  ),
  empty: (
    <svg {...SVG_PROPS} viewBox="0 0 8 8">
      {heartRects(FOOD_RECTS, "#4C4C4C")}
    </svg>
  ),
}

function McHeartIcon({ state }: { state: "full" | "half" | "empty" }) {
  return MC_HEART[state]
}

function McFoodIcon({ state }: { state: "full" | "half" | "empty" }) {
  return MC_FOOD[state]
}

// ── Minecraft UI ──────────────────────────────────────────────────────────────

const McItem = memo(
  function McItem({
    item,
    onRemove,
  }: {
    item: InventoryItem | null
    onRemove?: () => void
  }) {
    const clickable = !!onRemove && !!item
    return (
      <div
        className={`group relative flex size-9 items-center justify-center border border-[#373737] bg-[#8b8b8b]/10 select-none ${clickable ? "cursor-pointer hover:border-zinc-400 hover:bg-zinc-800" : ""}`}
        onClick={clickable ? onRemove : undefined}
        title={item ? `${item.id} ×${item.count}` : undefined}
      >
        {item && (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={itemTextureUrl(item.id)}
              alt={item.id}
              className="size-7"
              style={{ imageRendering: "pixelated" }}
              onError={(e) => {
                ;(e.target as HTMLImageElement).style.display = "none"
              }}
            />
            <span
              className="absolute right-0.5 bottom-0 text-[9px] leading-none font-bold text-white"
              style={{ textShadow: "1px 1px 0 #222" }}
            >
              {item.count}
            </span>
            {clickable && (
              <span className="absolute inset-0 hidden items-center justify-center bg-red-900/50 group-hover:flex">
                <Trash2 className="size-3 text-red-300" />
              </span>
            )}
          </>
        )}
      </div>
    )
  },
  // Only re-render when the item itself changes or clickability flips.
  // This prevents the 68-cell cascade re-render when `pending` state
  // changes in the dialog (each onRemove is a fresh arrow, but the item
  // data and slot occupancy haven't changed).
  (prev, next) => prev.item === next.item && !!prev.onRemove === !!next.onRemove
)

function HeartBar({ health }: { health: number }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-px">
        {Array.from({ length: 10 }, (_, i) => {
          const hp = health - i * 2
          const state = hp >= 2 ? "full" : hp >= 1 ? "half" : "empty"
          return <McHeartIcon key={i} state={state} />
        })}
      </div>
      <span className="text-xs text-muted-foreground">{health}/20</span>
    </div>
  )
}

function FoodBar({ food, saturation }: { food: number; saturation: number }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-px">
        {Array.from({ length: 10 }, (_, i) => {
          const f = food - i * 2
          const state = f >= 2 ? "full" : f >= 1 ? "half" : "empty"
          return <McFoodIcon key={i} state={state} />
        })}
      </div>
      <span className="text-xs text-muted-foreground">
        {food}/20 · sat {saturation.toFixed(1)}
      </span>
    </div>
  )
}

function AddItemForm({
  onAdd,
  disabled,
}: {
  onAdd: (itemId: string, count: number) => Promise<void>
  disabled: boolean
}) {
  const [itemId, setItemId] = useState("")
  const [count, setCount] = useState("1")
  const [adding, setAdding] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const raw = itemId.trim()
    if (!raw) return
    const id = raw.includes(":") ? raw : `minecraft:${raw}`
    const n = Math.min(64, Math.max(1, parseInt(count, 10) || 1))
    setAdding(true)
    try {
      await onAdd(id, n)
      setItemId("")
      setCount("1")
    } finally {
      setAdding(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-2 flex items-center gap-1.5">
      <Input
        className="h-7 flex-1 font-mono text-xs"
        placeholder="diamond  or  mod:item_id"
        value={itemId}
        onChange={(e) => setItemId(e.target.value)}
        disabled={disabled || adding}
      />
      <Input
        className="h-7 w-14 text-xs"
        type="number"
        min={1}
        max={64}
        value={count}
        onChange={(e) => setCount(e.target.value)}
        disabled={disabled || adding}
      />
      <Button
        type="submit"
        size="sm"
        variant="outline"
        className="h-7 px-2 text-xs"
        disabled={disabled || adding || !itemId.trim()}
      >
        {adding ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <Plus className="size-3" />
        )}
        Give
      </Button>
    </form>
  )
}

// ── Player detail dialog ──────────────────────────────────────────────────────

function PlayerDetailDialog({
  serverId,
  username,
  isRunning,
  onClose,
}: {
  serverId: number
  username: string
  isRunning: boolean
  onClose: () => void
}) {
  const [data, setData] = useState<PlayerData | null>(null)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState<string | null>(null)
  const [position, setPosition] = useState<{
    x: number
    y: number
    z: number
  } | null>(null)
  const [positionLoading, setPositionLoading] = useState(false)
  const [statsData, setStatsData] = useState<PlayerStatistics | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [tpX, setTpX] = useState("")
  const [tpY, setTpY] = useState("")
  const [tpZ, setTpZ] = useState("")
  const [effectId, setEffectId] = useState("")
  const [effectSeconds, setEffectSeconds] = useState("30")
  const [effectAmplifier, setEffectAmplifier] = useState("0")

  const load = useCallback(
    async (silent = false, refresh = false) => {
      if (!silent) setLoading(true)
      try {
        const res = await api.players.getData(serverId, username, refresh)
        setData(res)
      } catch (err) {
        if (!silent)
          toast.error(
            err instanceof Error ? err.message : "Failed to load player data"
          )
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [serverId, username]
  )

  useEffect(() => {
    load()
  }, [load])

  async function act(key: string, fn: () => Promise<unknown>) {
    setPending(key)
    try {
      await fn()
      await load(true) // silent — preserves scroll position
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Action failed")
    } finally {
      setPending(null)
    }
  }

  async function loadPosition() {
    setPositionLoading(true)
    try {
      const res = await api.players.getPosition(serverId, username)
      setPosition(res?.position ?? res)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to get position")
    } finally {
      setPositionLoading(false)
    }
  }

  async function loadStats(refresh = false) {
    setStatsLoading(true)
    try {
      const res = await api.players.getStatistics(serverId, username, refresh)
      setStatsData(res?.statistics ?? res)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load statistics"
      )
    } finally {
      setStatsLoading(false)
    }
  }

  async function handleTeleport(e: React.FormEvent) {
    e.preventDefault()
    const x = parseFloat(tpX)
    const y = parseFloat(tpY)
    const z = parseFloat(tpZ)
    if (isNaN(x) || isNaN(y) || isNaN(z)) {
      toast.error("Invalid coordinates")
      return
    }
    await act("teleport", () =>
      api.players.teleport(serverId, username, x, y, z)
    )
  }

  async function handleDataReset(targets: string[]) {
    await act(`reset-${targets.join(",")}`, () =>
      api.players.resetData(serverId, username, targets)
    )
  }

  async function handleAddEffect(e: React.FormEvent) {
    e.preventDefault()
    const raw = effectId.trim()
    if (!raw) return
    const effect = raw.includes(":") ? raw : `minecraft:${raw}`
    const seconds = Math.max(1, parseInt(effectSeconds, 10) || 30)
    const amplifier = Math.max(0, parseInt(effectAmplifier, 10) || 0)
    await act("effect-add", () =>
      api.players.addEffect(serverId, username, { effect, seconds, amplifier })
    )
    setEffectId("")
  }

  // Game-mode change is handled separately: on a live server the RCON
  // command takes effect immediately but the NBT file (read by getData)
  // only refreshes on disconnect. Calling load() would revert the
  // highlight to the stale value, so we update local state directly.
  async function handleGameMode(modeNum: number) {
    const key = `gm-${modeNum}`
    setPending(key)
    try {
      await api.players.setGameMode(serverId, username, modeNum)
      setData((prev) => (prev ? { ...prev, game_mode: modeNum } : prev))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Action failed")
    } finally {
      setPending(null)
    }
  }

  const inventory = data?.inventory ?? []
  const enderchest = data?.enderchest ?? []
  const mainGrid = buildMainGrid(inventory)
  const enderGrid = buildEnderGrid(enderchest)
  const armorItems = ARMOR_SLOTS.map(
    (s) => inventory.find((it) => it.slot === s) ?? null
  )
  const offhandItem = inventory.find((it) => it.slot === -106) ?? null

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Button size="sm" variant="ghost" className="gap-1.5" onClick={onClose}>
          <ArrowLeft className="size-4" />
          Back
        </Button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={playerHeadUrl(username)}
          alt={username}
          className="size-8 rounded"
          style={{ imageRendering: "pixelated" }}
        />
        <span className="text-base font-semibold">{username}</span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto gap-1.5 text-xs"
          disabled={loading}
          title="Flush player data to disk then reload (live state)"
          onClick={() => {
            load(false, true)
            if (statsData) loadStats(true)
          }}
        >
          {loading ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <RefreshCw className="size-3" />
          )}
          Live
        </Button>
      </div>

      <div className="overflow-y-auto p-4">
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : !data ? (
          <p className="text-sm text-muted-foreground">No player data found.</p>
        ) : (
          <div className="flex flex-col gap-5">
            {data.warning && (
              <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
                ⚠ {data.warning}
              </div>
            )}

            {/* Stats */}
            <div className="flex flex-col gap-3 rounded border border-border p-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
                    Health
                  </span>
                  <HeartBar health={data.health} />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
                    Hunger
                  </span>
                  <FoodBar
                    food={data.food_level}
                    saturation={data.food_saturation}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="secondary">XP {data.xp_level}</Badge>
                <Badge variant="secondary">
                  {GAME_MODES[data.game_mode] ?? `Mode ${data.game_mode}`}
                </Badge>
                <Badge variant="outline" className="font-mono text-[9px]">
                  {data.uuid}
                </Badge>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex flex-col gap-2 rounded border border-border p-3">
              <span className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
                Actions
              </span>

              {/* Health / food / kill */}
              <div className="flex flex-wrap gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!!pending}
                  onClick={() =>
                    act("heal", () =>
                      api.players.healPlayer(serverId, username)
                    )
                  }
                >
                  {pending === "heal" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Heart className="size-3 text-red-400" />
                  )}
                  Heal
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!!pending}
                  onClick={() =>
                    act("feed", () =>
                      api.players.feedPlayer(serverId, username)
                    )
                  }
                >
                  {pending === "feed" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Utensils className="size-3 text-amber-400" />
                  )}
                  Feed
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!!pending}
                  onClick={() =>
                    act("starve", () =>
                      api.players.starvePlayer(serverId, username)
                    )
                  }
                >
                  {pending === "starve" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Minus className="size-3" />
                  )}
                  Starve
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10"
                  disabled={!isRunning || !!pending}
                  onClick={() =>
                    act("kill", () =>
                      api.players.killPlayer(serverId, username)
                    )
                  }
                >
                  {pending === "kill" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Skull className="size-3" />
                  )}
                  Kill
                </Button>
              </div>

              {/* Game mode */}
              <div className="flex flex-wrap items-center gap-1">
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Gamepad2 className="size-3" />
                  Mode:
                </span>
                {Object.entries(GAME_MODES).map(([mode, label]) => {
                  const modeNum = Number(mode)
                  return (
                    <Button
                      key={mode}
                      size="sm"
                      variant={
                        data.game_mode === modeNum ? "default" : "outline"
                      }
                      className="h-7 px-2 text-xs"
                      disabled={data.game_mode === modeNum || !!pending}
                      onClick={() => handleGameMode(modeNum)}
                    >
                      {pending === `gm-${modeNum}` && (
                        <Loader2 className="mr-1 size-3 animate-spin" />
                      )}
                      {label}
                    </Button>
                  )
                })}
              </div>

              {/* Effects */}
              <form
                onSubmit={handleAddEffect}
                className="flex items-center gap-1.5"
              >
                <span className="flex shrink-0 items-center gap-1 text-[10px] text-muted-foreground">
                  <Zap className="size-3" />
                  Effect:
                </span>
                <Input
                  className="h-7 min-w-0 flex-1 font-mono text-xs"
                  placeholder="speed"
                  value={effectId}
                  onChange={(e) => setEffectId(e.target.value)}
                  disabled={!isRunning || !!pending}
                />
                <Input
                  className="h-7 w-14 text-xs"
                  type="number"
                  min={1}
                  max={3600}
                  placeholder="30s"
                  value={effectSeconds}
                  onChange={(e) => setEffectSeconds(e.target.value)}
                  disabled={!isRunning || !!pending}
                />
                <Input
                  className="h-7 w-12 text-xs"
                  type="number"
                  min={0}
                  max={255}
                  placeholder="lvl"
                  value={effectAmplifier}
                  onChange={(e) => setEffectAmplifier(e.target.value)}
                  disabled={!isRunning || !!pending}
                />
                <Button
                  type="submit"
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!isRunning || !!pending || !effectId.trim()}
                >
                  {pending === "effect-add" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Plus className="size-3" />
                  )}
                  Apply
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                  disabled={!isRunning || !!pending}
                  onClick={() =>
                    act("effect-clear", () =>
                      api.players.clearAllEffects(serverId, username)
                    )
                  }
                >
                  {pending === "effect-clear" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : null}
                  Clear
                </Button>
              </form>

              {/* Whitelist / Op / Ban */}
              <div className="flex flex-wrap gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!isRunning || !!pending}
                  onClick={() =>
                    act("whitelist", () =>
                      api.players.whitelistPlayer(serverId, username)
                    )
                  }
                >
                  {pending === "whitelist" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <UserCheck className="size-3" />
                  )}
                  Whitelist
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!isRunning || !!pending}
                  onClick={() =>
                    act("op", () => api.players.opPlayer(serverId, username))
                  }
                >
                  {pending === "op" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <ShieldCheck className="size-3" />
                  )}
                  Op
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10"
                  disabled={!isRunning || !!pending}
                  onClick={() =>
                    act("ban", () => api.players.banPlayer(serverId, username))
                  }
                >
                  {pending === "ban" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Ban className="size-3" />
                  )}
                  Ban
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-xs"
                  disabled={!!pending}
                  onClick={() =>
                    act("unban", () =>
                      api.players.unbanPlayer(serverId, username)
                    )
                  }
                >
                  {pending === "unban" && (
                    <Loader2 className="mr-1 size-3 animate-spin" />
                  )}
                  Unban
                </Button>
              </div>
            </div>

            {/* Position & Teleport */}
            <div className="flex flex-col gap-2 rounded border border-border p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
                  <MapPin className="size-3" />
                  Position
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-xs"
                  disabled={positionLoading}
                  onClick={loadPosition}
                >
                  {positionLoading ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3" />
                  )}
                </Button>
              </div>
              {position && (
                <p className="font-mono text-xs text-muted-foreground">
                  X&nbsp;{position.x.toFixed(1)}&emsp;Y&nbsp;
                  {position.y.toFixed(1)}&emsp;Z&nbsp;{position.z.toFixed(1)}
                </p>
              )}
              <form
                onSubmit={handleTeleport}
                className="flex items-center gap-1.5"
              >
                <Input
                  className="h-7 w-[4.5rem] font-mono text-xs"
                  placeholder="X"
                  value={tpX}
                  onChange={(e) => setTpX(e.target.value)}
                />
                <Input
                  className="h-7 w-[4.5rem] font-mono text-xs"
                  placeholder="Y"
                  value={tpY}
                  onChange={(e) => setTpY(e.target.value)}
                />
                <Input
                  className="h-7 w-[4.5rem] font-mono text-xs"
                  placeholder="Z"
                  value={tpZ}
                  onChange={(e) => setTpZ(e.target.value)}
                />
                <Button
                  type="submit"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!!pending || !tpX || !tpY || !tpZ}
                >
                  {pending === "teleport" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Navigation className="size-3" />
                  )}
                  Teleport
                </Button>
              </form>
            </div>

            {/* Statistics */}
            <div className="flex flex-col gap-2 rounded border border-border p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
                  <BarChart2 className="size-3" />
                  Statistics
                </span>
                {!statsData && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-xs"
                    disabled={statsLoading}
                    onClick={() => loadStats()}
                  >
                    {statsLoading ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      "Load"
                    )}
                  </Button>
                )}
              </div>
              {statsData && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {(
                    [
                      ["Playtime", `${statsData.playtime_hours.toFixed(1)} h`],
                      ["Deaths", fmtNum(statsData.deaths)],
                      ["Player Kills", fmtNum(statsData.player_kills)],
                      ["K/D Ratio", statsData.kd.toFixed(2)],
                      [
                        "Distance",
                        `${fmtNum(statsData.distance_traveled_blocks)} blk`,
                      ],
                      ["Blocks Mined", fmtNum(statsData.blocks_removed)],
                      ["Blocks Placed", fmtNum(statsData.blocks_added)],
                      ["Items Used", fmtNum(statsData.items_used)],
                      ["Entities Killed", fmtNum(statsData.entities_killed)],
                    ] as [string, string][]
                  ).map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-2">
                      <span className="text-xs text-muted-foreground">
                        {label}
                      </span>
                      <span className="font-mono text-xs font-medium tabular-nums">
                        {value}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Inventory */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                  Inventory
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10"
                  disabled={pending === "inv-clear"}
                  onClick={() =>
                    act("inv-clear", () =>
                      api.players.clearInventory(serverId, username)
                    )
                  }
                >
                  {pending === "inv-clear" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Trash2 className="size-3" />
                  )}
                  Clear all
                </Button>
              </div>

              <div className="flex gap-1.5">
                {/* Armor + offhand column */}
                <div className="flex flex-col gap-0.5">
                  {armorItems.map((item, idx) => {
                    const slot = ARMOR_SLOTS[idx]
                    return (
                      <McItem
                        key={slot}
                        item={item}
                        onRemove={
                          item
                            ? () =>
                                act(`inv-${slot}`, () =>
                                  api.players.clearInventorySlot(
                                    serverId,
                                    username,
                                    slot
                                  )
                                )
                            : undefined
                        }
                      />
                    )
                  })}
                  <McItem
                    item={offhandItem}
                    onRemove={
                      offhandItem
                        ? () =>
                            act("inv--106", () =>
                              api.players.clearInventorySlot(
                                serverId,
                                username,
                                -106
                              )
                            )
                        : undefined
                    }
                  />
                </div>

                {/* 4×9 grid (3 main rows + hotbar) */}
                <div className="flex flex-col gap-0.5">
                  {[0, 1, 2, 3].map((row) => (
                    <div key={row} className="flex gap-0.5">
                      {Array.from({ length: 9 }, (_, col) => {
                        const gridIndex = row * 9 + col
                        const item = mainGrid[gridIndex]
                        const slot = visualIndexToSlot(gridIndex)
                        return (
                          <McItem
                            key={col}
                            item={item}
                            onRemove={
                              item
                                ? () =>
                                    act(`inv-${slot}`, () =>
                                      api.players.clearInventorySlot(
                                        serverId,
                                        username,
                                        slot
                                      )
                                    )
                                : undefined
                            }
                          />
                        )
                      })}
                    </div>
                  ))}
                </div>
              </div>

              <AddItemForm
                disabled={false}
                onAdd={(itemId, count) =>
                  act("inv-add", () =>
                    api.players.addInventoryItem(serverId, username, {
                      item_id: itemId,
                      count,
                    })
                  )
                }
              />
            </div>

            <Separator />

            {/* Ender Chest */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                  Ender Chest
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10"
                  disabled={pending === "ec-clear"}
                  onClick={() =>
                    act("ec-clear", () =>
                      api.players.clearEnderchest(serverId, username)
                    )
                  }
                >
                  {pending === "ec-clear" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Trash2 className="size-3" />
                  )}
                  Clear all
                </Button>
              </div>

              <div className="flex flex-col gap-0.5">
                {[0, 1, 2].map((row) => (
                  <div key={row} className="flex gap-0.5">
                    {Array.from({ length: 9 }, (_, col) => {
                      const slot = row * 9 + col
                      const item = enderGrid[slot]
                      return (
                        <McItem
                          key={col}
                          item={item}
                          onRemove={
                            item
                              ? () =>
                                  act(`ec-${slot}`, () =>
                                    api.players.clearEnderchestSlot(
                                      serverId,
                                      username,
                                      slot
                                    )
                                  )
                              : undefined
                          }
                        />
                      )
                    })}
                  </div>
                ))}
              </div>

              <AddItemForm
                disabled={false}
                onAdd={(itemId, count) =>
                  act("ec-add", () =>
                    api.players.addEnderchestItem(serverId, username, {
                      item_id: itemId,
                      count,
                    })
                  )
                }
              />
            </div>

            <Separator />

            {/* Data Management */}
            <div className="flex flex-col gap-2 rounded border border-destructive/30 p-3">
              <span className="flex items-center gap-1 text-[10px] font-semibold tracking-wider text-destructive/70 uppercase">
                <Database className="size-3" />
                Data Management
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    ["Reset XP", ["xp"]],
                    ["Reset Statistics", ["statistics"]],
                    ["Reset Advancements", ["advancements"]],
                    ["Clear Inventory", ["inventory"]],
                    ["Clear Ender Chest", ["enderchest"]],
                    ["Reset Everything", ["everything"]],
                  ] as [string, string[]][]
                ).map(([label, targets]) => (
                  <Button
                    key={label}
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                    disabled={!!pending}
                    onClick={() => handleDataReset(targets)}
                  >
                    {pending === `reset-${targets.join(",")}` ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : null}
                    {label}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  serverId: number
  isRunning: boolean
}

export function PlayersPanel({ serverId, isRunning }: Props) {
  const [data, setData] = useState<PlayersData | null>(null)
  const [history, setHistory] = useState<PlayerHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState<string | null>(null)
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [playersRes, historyRes] = await Promise.all([
        api.players.list(serverId),
        api.players.history(serverId).catch(() => ({ players: [] })),
      ])
      setData(playersRes?.data ?? playersRes)
      setHistory(historyRes?.players ?? [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load players")
    } finally {
      setLoading(false)
    }
  }, [serverId])

  useEffect(() => {
    load()
  }, [load])

  const requireRunning = () => {
    if (!isRunning) {
      toast.error("Server must be running to perform this action")
      return false
    }
    return true
  }

  async function withPending(key: string, fn: () => Promise<void>) {
    setPending(key)
    try {
      await fn()
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Action failed")
    } finally {
      setPending(null)
    }
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        Unable to load player data.
      </div>
    )
  }

  const online = data.online ?? []
  const whitelist = data.whitelist ?? []
  const ops = data.ops ?? []
  const banned = data.banned ?? []

  if (selectedPlayer) {
    return (
      <PlayerDetailDialog
        serverId={serverId}
        username={selectedPlayer}
        isRunning={isRunning}
        onClose={() => setSelectedPlayer(null)}
      />
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Online */}
        <Section title="Online" count={online.length}>
          {online.length === 0 ? (
            <EmptyRow
              label={isRunning ? "No players online" : "Server is not running"}
            />
          ) : (
            <ul className="flex flex-col gap-1.5">
              {online.map((p: PlayerRef) => {
                const name = playerName(p)
                return (
                  <li
                    key={name}
                    className="flex items-center justify-between gap-2"
                  >
                    <button
                      className="flex items-center gap-1.5 text-sm hover:underline"
                      onClick={() => setSelectedPlayer(name)}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={playerHeadUrl(name)}
                        alt={name}
                        className="size-5 rounded-sm"
                        style={{ imageRendering: "pixelated" }}
                      />
                      {name}
                    </button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                      disabled={pending === `kick-${name}`}
                      onClick={() => {
                        if (!requireRunning()) return
                        withPending(`kick-${name}`, () =>
                          api.players.kick(serverId, name)
                        )
                      }}
                    >
                      {pending === `kick-${name}` ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <LogOut className="size-3" />
                      )}
                      Kick
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>

        {/* Whitelist */}
        <Section title="Whitelist" count={whitelist.length}>
          <div className="flex flex-col gap-1.5">
            {whitelist.length === 0 ? (
              <EmptyRow label="No whitelisted players" />
            ) : (
              <ul className="flex flex-col gap-1.5">
                {whitelist.map((p: PlayerRef) => {
                  const name = playerName(p)
                  return (
                    <li
                      key={name}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="text-sm">{name}</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                        disabled={pending === `wl-rm-${name}`}
                        onClick={() => {
                          if (!requireRunning()) return
                          withPending(`wl-rm-${name}`, () =>
                            api.players.whitelistRemove(serverId, name)
                          )
                        }}
                      >
                        {pending === `wl-rm-${name}` ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          <UserX className="size-3" />
                        )}
                      </Button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <AddRow
            placeholder="Username"
            disabled={!isRunning}
            onAdd={(username) =>
              withPending("wl-add", () =>
                api.players.whitelistAdd(serverId, username)
              )
            }
          />
        </Section>

        {/* Operators */}
        <Section title="Operators" count={ops.length}>
          <div className="flex flex-col gap-1.5">
            {ops.length === 0 ? (
              <EmptyRow label="No operators" />
            ) : (
              <ul className="flex flex-col gap-1.5">
                {ops.map((p: PlayerRef) => {
                  const name = playerName(p)
                  return (
                    <li
                      key={name}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="flex items-center gap-1.5 text-sm">
                        <ShieldCheck className="size-3 text-primary" />
                        {name}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                        disabled={pending === `op-rm-${name}`}
                        onClick={() => {
                          if (!requireRunning()) return
                          withPending(`op-rm-${name}`, () =>
                            api.players.opRemove(serverId, name)
                          )
                        }}
                      >
                        {pending === `op-rm-${name}` ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          <ShieldOff className="size-3" />
                        )}
                      </Button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <AddRow
            placeholder="Username"
            disabled={!isRunning}
            onAdd={(username) =>
              withPending("op-add", () => api.players.opAdd(serverId, username))
            }
          />
        </Section>

        {/* Banned */}
        <Section title="Banned" count={banned.length}>
          <div className="flex flex-col gap-1.5">
            {banned.length === 0 ? (
              <EmptyRow label="No banned players" />
            ) : (
              <ul className="flex flex-col gap-1.5">
                {banned.map((p: BannedPlayer) => {
                  const name = playerName(p)
                  return (
                    <li
                      key={name}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-sm">
                          <Ban className="size-3 text-destructive" />
                          {name}
                        </span>
                        {p.reason && (
                          <span className="block truncate text-xs text-muted-foreground">
                            {p.reason}
                          </span>
                        )}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 shrink-0 px-2 text-xs"
                        disabled={pending === `ban-rm-${name}`}
                        onClick={() => {
                          withPending(`ban-rm-${name}`, () =>
                            api.players.banRemove(serverId, name)
                          )
                        }}
                      >
                        {pending === `ban-rm-${name}` ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          "Unban"
                        )}
                      </Button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <AddRow
            placeholder="Username to ban"
            disabled={!isRunning}
            onAdd={(username) =>
              withPending("ban-add", () =>
                api.players.banAdd(serverId, username)
              )
            }
          />
        </Section>
      </div>

      {/* Player History */}
      <div className="border border-border p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            <Clock className="size-3" />
            Player History
          </h3>
          <span className="text-xs text-muted-foreground">
            {history.length}
          </span>
        </div>

        {history.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No players have joined yet.
          </p>
        ) : (
          <div className="grid gap-0.5 sm:grid-cols-2 lg:grid-cols-3">
            {history.map((p) => (
              <button
                key={p.uuid}
                className="flex items-center gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-muted/60"
                onClick={() => setSelectedPlayer(p.name)}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={playerHeadUrl(p.name)}
                  alt={p.name}
                  className="size-6 rounded-sm"
                  style={{ imageRendering: "pixelated" }}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{p.name}</p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {new Date(p.last_seen).toLocaleDateString()}
                  </p>
                </div>
                <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
