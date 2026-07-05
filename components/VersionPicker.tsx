"use client"

import { useState, useEffect, useRef } from "react"
import { Search, ChevronDown, Check, Loader2 } from "lucide-react"
import { api } from "@/lib/api"

interface VersionEntry {
  id: string
  type: "release" | "snapshot" | "old_beta" | "old_alpha"
}

interface LoaderItem {
  id: string
  label: string
  stable?: boolean
}

interface Props {
  value: string
  onChange: (version: string) => void
  disabled?: boolean
  mode?: "game" | "loader"
  loaderType?: "forge" | "fabric"
  // Selected Minecraft version — required to look up matching Forge builds.
  gameVersion?: string
}

export function VersionPicker({
  value,
  onChange,
  disabled,
  mode = "game",
  loaderType,
  gameVersion,
}: Props) {
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<VersionEntry[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [loaderItems, setLoaderItems] = useState<LoaderItem[]>([])
  const [loadingLoaderItems, setLoadingLoaderItems] = useState(false)
  const [search, setSearch] = useState("")
  const [showAll, setShowAll] = useState(false)

  const wrapperRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // Fetch the vanilla version manifest once on mount
  useEffect(() => {
    if (mode !== "game") return
    let active = true
    const load = async () => {
      setLoadingVersions(true)
      try {
        const data = await api.versions.manifest()
        if (active) setVersions(data ?? [])
      } catch {
        if (active) setVersions([])
      } finally {
        if (active) setLoadingVersions(false)
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [mode])

  // Fetch loader versions dynamically — Fabric loaders are version-agnostic,
  // Forge builds are tied to the selected Minecraft version.
  useEffect(() => {
    if (mode !== "loader" || !loaderType) return

    let active = true
    const load = async () => {
      if (loaderType === "forge" && !gameVersion) {
        setLoaderItems([])
        return
      }
      setLoadingLoaderItems(true)
      try {
        if (loaderType === "fabric") {
          const data = await api.versions.fabricLoaders()
          if (active) {
            setLoaderItems(
              data.map((d) => ({ id: d.id, label: d.id, stable: d.stable }))
            )
          }
        } else {
          const data = await api.versions.forgeVersions(gameVersion!)
          if (active) {
            const items: LoaderItem[] = []
            if (data.latest) items.push({ id: "LATEST", label: "LATEST" })
            for (const v of data.versions) items.push({ id: v, label: v })
            setLoaderItems(items)
          }
        }
      } catch {
        if (active) setLoaderItems([])
      } finally {
        if (active) setLoadingLoaderItems(false)
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [mode, loaderType, gameVersion])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handleOutside(e: MouseEvent) {
      if (!wrapperRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleOutside)
    return () => document.removeEventListener("mousedown", handleOutside)
  }, [open])

  // Auto-focus search when opened
  useEffect(() => {
    if (open) {
      const t = window.setTimeout(
        () => searchRef.current?.focus({ preventScroll: true }),
        0
      )
      return () => window.clearTimeout(t)
    }
    const t = window.setTimeout(() => setSearch(""), 0)
    return () => window.clearTimeout(t)
  }, [open])

  const isLoaderMode = mode === "loader"
  const isFabric = isLoaderMode && loaderType === "fabric"
  const loading = isLoaderMode ? loadingLoaderItems : loadingVersions

  const displayItems: { id: string; label: string }[] = isLoaderMode
    ? [
        { id: "", label: "Latest" },
        ...loaderItems
          .filter((item) => !isFabric || showAll || item.stable)
          .map((item) => ({ id: item.id, label: item.label })),
      ].filter((item) => {
        if (!item.id) return true
        if (search && !item.label.toLowerCase().includes(search.toLowerCase()))
          return false
        return true
      })
    : versions
        .filter((v) => {
          if (!showAll && v.type !== "release") return false
          if (search && !v.id.toLowerCase().includes(search.toLowerCase()))
            return false
          return true
        })
        .map((v) => ({ id: v.id, label: v.id }))

  function handleSelect(id: string) {
    onChange(id)
    setOpen(false)
  }

  const displayValue =
    mode === "loader" ? value || "Latest" : value || "Select a version"

  const noItemsReason =
    isLoaderMode && loaderType === "forge" && !gameVersion
      ? "Select a Minecraft version first"
      : "No versions found"

  return (
    <div ref={wrapperRef} className="relative">
      {/* Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={value ? "text-foreground" : "text-muted-foreground"}>
          {displayValue}
        </span>
        {loading ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {/* Dropdown — inline, no portal */}
      {open && (
        <div
          role="listbox"
          aria-label="Select game version"
          onMouseDown={(e) => e.stopPropagation()}
          className="absolute top-full left-0 z-[200] mt-1.5 w-full overflow-hidden rounded-xl border border-border bg-popover shadow-xl"
        >
          {/* Search */}
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={
                mode === "loader"
                  ? "Search loader versions..."
                  : "Search game versions..."
              }
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>

          {/* Version list */}
          <ul className="max-h-56 overflow-y-auto py-1">
            {displayItems.length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-muted-foreground">
                {loading ? (
                  <Loader2 className="mx-auto size-4 animate-spin" />
                ) : (
                  noItemsReason
                )}
              </li>
            ) : (
              displayItems.map((item) => {
                const selected = item.id === value
                return (
                  <li
                    key={item.id}
                    role="option"
                    aria-selected={selected}
                    onClick={() => handleSelect(item.id)}
                    className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors hover:bg-muted ${
                      selected
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    <span>{item.label}</span>
                    {selected && <Check className="size-3.5 text-primary" />}
                  </li>
                )
              })
            )}
          </ul>

          {/* Show all versions toggle */}
          {(mode !== "loader" || isFabric) && (
            <div className="flex items-center gap-2.5 border-t border-border px-3 py-2.5">
              <button
                type="button"
                role="checkbox"
                aria-checked={showAll}
                onClick={() => setShowAll((s) => !s)}
                className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
                  showAll
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background"
                }`}
              >
                {showAll && (
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
              <span
                className="cursor-pointer text-sm text-foreground select-none"
                onClick={() => setShowAll((s) => !s)}
              >
                {isFabric ? "Show unstable builds" : "Show all versions"}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
