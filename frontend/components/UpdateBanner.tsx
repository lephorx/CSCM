"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowUpCircle, Loader2, TriangleAlert } from "lucide-react"
import { toast } from "sonner"

import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

const HELP_URL = "https://lephor.com/wiki/cscm/help"
const HELP_FAILED = `${HELP_URL}#update-failed`
const HELP_MANUAL = `${HELP_URL}#manual-update`
const RECHECK_MS = 30 * 60 * 1000
const POLL_MS = 3000

interface VersionInfo {
  current: string
  latest: string | null
  update_available: boolean
  can_update: boolean
  reason: string | null
}

interface UpdateStatus {
  state: "idle" | "running" | "done" | "failed"
  log: string[]
  version: string
}

type Phase = "idle" | "confirm" | "running" | "restarting" | "failed"

// Permanent banner shown while a newer CSCM version exists. "Update" starts
// the backend's update helper, then follows its progress through the restart
// and reloads the dashboard once the new version answers.
export function UpdateBanner() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [phase, setPhase] = useState<Phase>("idle")
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState("")
  const fromVersion = useRef("")
  const logEnd = useRef<HTMLDivElement>(null)

  const check = useCallback(async () => {
    try {
      setInfo(await api.system.version())
    } catch {
      // not critical; try again on the next interval
    }
  }, [])

  // Initial check, a periodic re-check, and resuming an update that was
  // already running when the page was (re)loaded.
  useEffect(() => {
    check()
    const id = setInterval(check, RECHECK_MS)
    api.system
      .updateStatus()
      .then((s: UpdateStatus) => {
        if (s?.state === "running") {
          fromVersion.current = s.version
          setLog(s.log)
          setPhase("running")
        }
      })
      .catch(() => {})
    return () => clearInterval(id)
  }, [check])

  // Follow the update while it runs.
  useEffect(() => {
    if (phase !== "running" && phase !== "restarting") return
    const id = setInterval(async () => {
      try {
        const s: UpdateStatus = await api.system.updateStatus()
        setLog(s.log)
        if (s.state === "failed") {
          setError(s.log[s.log.length - 1] ?? "The update failed.")
          setPhase("failed")
        } else if (s.state === "done" && s.version !== fromVersion.current) {
          toast.success(`CSCM updated to ${s.version}`)
          window.location.reload()
        } else {
          setPhase("running")
        }
      } catch {
        // the API is being rebuilt and restarted right now
        setPhase("restarting")
      }
    }, POLL_MS)
    return () => clearInterval(id)
  }, [phase])

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "end" })
  }, [log])

  async function startUpdate() {
    setError("")
    fromVersion.current = info?.current ?? ""
    try {
      await api.system.update()
      setLog([])
      setPhase("running")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the update")
      setPhase("failed")
    }
  }

  const busy = phase === "running" || phase === "restarting"
  if (!info?.update_available && !busy && phase !== "failed") return null

  return (
    <>
      {info?.update_available && (
        <div className="border-b border-primary/30 bg-primary/10">
          <div className="mx-auto flex max-w-screen-xl flex-wrap items-center justify-between gap-3 px-6 py-2.5">
            <p className="flex items-center gap-2 text-sm">
              <ArrowUpCircle className="size-4 shrink-0 text-primary" />
              <span>
                <span className="font-medium">CSCM {info.latest}</span> is
                available. You&apos;re on {info.current}.
              </span>
            </p>
            {info.can_update ? (
              <Button
                size="sm"
                disabled={busy}
                onClick={() => setPhase("confirm")}
              >
                {busy && <Loader2 className="size-3.5 animate-spin" />}
                {busy ? "Updating…" : "Update"}
              </Button>
            ) : (
              <a
                href={HELP_MANUAL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground underline underline-offset-4"
              >
                {info.reason} How to update manually
              </a>
            )}
          </div>
        </div>
      )}

      <Dialog
        open={phase !== "idle"}
        onOpenChange={(open) => {
          // can't be closed while the update runs
          if (!open && !busy) setPhase("idle")
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {phase === "confirm" && `Update to CSCM ${info?.latest}`}
              {phase === "running" && "Updating CSCM…"}
              {phase === "restarting" && "Restarting CSCM…"}
              {phase === "failed" && "Update failed"}
            </DialogTitle>
          </DialogHeader>

          {phase === "confirm" && (
            <p className="text-sm text-muted-foreground">
              CSCM downloads the new version from GitHub and rebuilds itself.
              The dashboard is offline for a few minutes and reloads on its own
              when it&apos;s back. Your Minecraft servers keep running, and your
              settings, worlds and backups are kept.
            </p>
          )}

          {(busy || phase === "failed") && (
            <>
              {busy && (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {phase === "restarting"
                    ? "Waiting for CSCM to come back online…"
                    : "This takes a few minutes. Keep this page open."}
                </p>
              )}
              {phase === "failed" && (
                <p className="flex items-start gap-2 text-sm text-destructive">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                  <span>
                    {error}{" "}
                    <a
                      href={HELP_FAILED}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline underline-offset-4"
                    >
                      Help page
                    </a>
                  </span>
                </p>
              )}
              {log.length > 0 && (
                <div className="max-h-56 overflow-y-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                  {log.map((line, i) => (
                    <div key={i} className="break-words whitespace-pre-wrap">
                      {line}
                    </div>
                  ))}
                  <div ref={logEnd} />
                </div>
              )}
            </>
          )}

          {(phase === "confirm" || phase === "failed") && (
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setPhase("idle")}>
                {phase === "failed" ? "Close" : "Cancel"}
              </Button>
              <Button onClick={startUpdate}>
                {phase === "failed" ? "Try again" : "Update now"}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
