"use client"

import { X, CheckCircle2, Loader2, AlertCircle } from "lucide-react"

import { Progress } from "@/components/ui/progress"

export interface FileUploadItem {
  id: string
  name: string
  loaded: number
  total: number
  status: "uploading" | "done" | "error"
  error?: string
}

interface Props {
  uploads: FileUploadItem[]
  onDismiss: () => void
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileUploadProgress({ uploads, onDismiss }: Props) {
  if (uploads.length === 0) return null

  const doneCount = uploads.filter((u) => u.status === "done").length
  const errorCount = uploads.filter((u) => u.status === "error").length
  const allSettled = uploads.every((u) => u.status !== "uploading")

  return (
    <div className="fixed right-4 bottom-4 z-50 w-80 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <p className="text-xs font-medium">
          {allSettled
            ? errorCount > 0
              ? `${doneCount}/${uploads.length} uploaded — ${errorCount} failed`
              : `Uploaded ${uploads.length} file${uploads.length !== 1 ? "s" : ""}`
            : `Uploading ${uploads.length} file${uploads.length !== 1 ? "s" : ""}…`}
        </p>
        <button
          className="flex size-5 shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          <X className="size-3.5" />
        </button>
      </div>

      {/* Per-file list */}
      <div className="max-h-64 overflow-y-auto">
        {uploads.map((u) => {
          const pct = u.total > 0 ? Math.round((u.loaded / u.total) * 100) : 0
          return (
            <div
              key={u.id}
              className="flex flex-col gap-1 border-b border-border px-3 py-2 last:border-b-0"
            >
              <div className="flex items-center gap-2">
                {u.status === "done" ? (
                  <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
                ) : u.status === "error" ? (
                  <AlertCircle className="size-3.5 shrink-0 text-destructive" />
                ) : (
                  <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
                )}
                <span className="min-w-0 flex-1 truncate text-xs">
                  {u.name}
                </span>
                <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">
                  {u.status === "uploading" ? `${pct}%` : formatSize(u.total)}
                </span>
              </div>
              {u.status === "error" ? (
                <p className="truncate text-[10px] text-destructive">
                  {u.error}
                </p>
              ) : (
                <Progress
                  value={u.status === "done" ? 100 : pct}
                  className={`h-1 ${u.status === "done" ? "[&>div]:bg-emerald-500" : ""}`}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
