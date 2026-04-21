"use client"

import { useState, useEffect, useRef } from "react"
import { Search, ChevronDown, Check, Loader2 } from "lucide-react"
import { api } from "@/lib/api"

interface VersionEntry {
  id: string
  type: "release" | "snapshot" | "old_beta" | "old_alpha"
}

interface Props {
  value: string
  onChange: (version: string) => void
  disabled?: boolean
}

export function VersionPicker({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<VersionEntry[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [search, setSearch] = useState("")
  const [showAll, setShowAll] = useState(false)

  const wrapperRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // Fetch version manifest once on mount
  useEffect(() => {
    setLoadingVersions(true)
    api.versions
      .manifest()
      .then((data) => setVersions(data ?? []))
      .catch(() => setVersions([]))
      .finally(() => setLoadingVersions(false))
  }, [])

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
      setTimeout(() => searchRef.current?.focus({ preventScroll: true }), 0)
    } else {
      setSearch("")
    }
  }, [open])

  const filtered = versions.filter((v) => {
    if (!showAll && v.type !== "release") return false
    if (search && !v.id.toLowerCase().includes(search.toLowerCase()))
      return false
    return true
  })

  function handleSelect(id: string) {
    onChange(id)
    setOpen(false)
  }

  const displayValue = value || "Select a version"

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
        {loadingVersions ? (
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
              placeholder="Search game versions..."
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>

          {/* Version list */}
          <ul className="max-h-56 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-muted-foreground">
                {loadingVersions ? (
                  <Loader2 className="mx-auto size-4 animate-spin" />
                ) : (
                  "No versions found"
                )}
              </li>
            ) : (
              filtered.map((v) => {
                const selected = v.id === value
                return (
                  <li
                    key={v.id}
                    role="option"
                    aria-selected={selected}
                    onClick={() => handleSelect(v.id)}
                    className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors hover:bg-muted ${
                      selected
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    <span>{v.id}</span>
                    {selected && <Check className="size-3.5 text-primary" />}
                  </li>
                )
              })
            )}
          </ul>

          {/* Show all versions toggle */}
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
              Show all versions
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
