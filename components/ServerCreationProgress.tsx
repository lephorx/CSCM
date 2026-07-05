"use client"

import { X, CheckCircle2, Loader2, AlertCircle, ExternalLink } from "lucide-react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import type { CreationTask } from "@/hooks/useServerCreation"

interface Props {
  task: CreationTask
  onDismiss: () => void
}

// Pure display component — the actual polling and progress state live in
// useServerCreation, shared with ServerCreateModal, so minimizing/reopening
// the create modal never restarts or loses progress.
export function ServerCreationProgress({ task, onDismiss }: Props) {
  const { stage, progress, step, name, serverId } = task

  return (
    <div className="fixed right-4 bottom-4 z-50 w-72 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
      {/* Header */}
      <div className="flex items-start justify-between px-3 pt-3 pb-1.5">
        <div className="min-w-0 pr-2">
          <p className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
            New Server
          </p>
          <p className="truncate text-sm font-medium">{name}</p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="size-6 shrink-0 p-0 text-muted-foreground hover:text-foreground"
          onClick={onDismiss}
        >
          <X className="size-3" />
        </Button>
      </div>

      {/* Status line */}
      <div className="flex items-center gap-2 px-3 py-1.5">
        {stage === "ready" ? (
          <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
        ) : stage === "error" ? (
          <AlertCircle className="size-3.5 shrink-0 text-destructive" />
        ) : (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
        )}
        <span
          className={`text-xs ${
            stage === "ready"
              ? "text-emerald-600 dark:text-emerald-400"
              : stage === "error"
                ? "text-destructive"
                : "text-muted-foreground"
          }`}
        >
          {stage === "submitting"
            ? "Provisioning server…"
            : stage === "starting"
              ? step || "Server is starting up…"
              : stage === "ready"
                ? "Server is ready!"
                : "Server encountered an error"}
        </span>
      </div>

      {/* Progress bar */}
      <div className="px-3 pb-3">
        <Progress
          value={progress}
          className={`h-1.5 transition-all duration-700 ${
            stage === "ready"
              ? "[&>div]:bg-emerald-500"
              : stage === "error"
                ? "[&>div]:bg-destructive"
                : ""
          }`}
        />
      </div>

      {/* "View server" link — only when ready */}
      {stage === "ready" && (
        <div className="border-t border-border px-3 py-2">
          <Link
            href={`/servers/${serverId}`}
            className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
            onClick={onDismiss}
          >
            View server
            <ExternalLink className="size-3" />
          </Link>
        </div>
      )}
    </div>
  )
}
