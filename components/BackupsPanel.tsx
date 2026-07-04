"use client"

import { useState, useEffect, useCallback } from "react"
import { Loader2, Plus, Trash2, RotateCcw, Save, Download } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import type { Backup, BackupSchedule } from "@/lib/types"
import { api } from "@/lib/api"
import { formatBytes } from "@/lib/utils"

interface Props {
  serverId: number
}

const CRON_PRESETS = [
  { label: "Daily at 4am", value: "0 4 * * *" },
  { label: "Every 6 hours", value: "0 */6 * * *" },
  { label: "Weekly (Sun 4am)", value: "0 4 * * 0" },
]

type BackupType = "zip" | "zfs"

export function BackupsPanel({ serverId }: Props) {
  const [backups, setBackups] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [createType, setCreateType] = useState<BackupType>("zip")
  const [deleteTarget, setDeleteTarget] = useState<Backup | null>(null)
  const [restoreTarget, setRestoreTarget] = useState<Backup | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [downloadingId, setDownloadingId] = useState<number | null>(null)

  const [schedule, setSchedule] = useState<BackupSchedule | null>(null)
  const [scheduleForm, setScheduleForm] = useState({
    cron: "0 4 * * *",
    retention: 5,
    enabled: false,
    backup_type: "zip" as BackupType,
  })
  const [savingSchedule, setSavingSchedule] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [backupsRes, scheduleRes] = await Promise.all([
        api.backups.list(serverId),
        api.backups.getSchedule(serverId),
      ])
      setBackups(backupsRes?.backups ?? backupsRes?.data ?? [])
      const sched: BackupSchedule | null = scheduleRes?.schedule ?? null
      setSchedule(sched)
      if (sched)
        setScheduleForm({
          cron: sched.cron,
          retention: sched.retention,
          enabled: sched.enabled,
          backup_type: (sched.backup_type ?? "zip") as BackupType,
        })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load backups")
    } finally {
      setLoading(false)
    }
  }, [serverId])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate() {
    setCreating(true)
    try {
      await api.backups.create(serverId, createType)
      toast.success("Backup created")
      await load()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create backup"
      )
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    const target = deleteTarget
    setDeleteTarget(null)
    setBusyId(target.id)
    try {
      await api.backups.delete(serverId, target.id)
      toast.success("Backup deleted")
      await load()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete backup"
      )
    } finally {
      setBusyId(null)
    }
  }

  async function handleDownload(b: Backup) {
    setDownloadingId(b.id)
    try {
      const blob = await api.backups.download(serverId, b.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = b.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to download backup"
      )
    } finally {
      setDownloadingId(null)
    }
  }

  async function handleRestore() {
    if (!restoreTarget) return
    const target = restoreTarget
    setRestoreTarget(null)
    setBusyId(target.id)
    try {
      await api.backups.restore(serverId, target.id)
      toast.success("Restore started — server is restarting")
      await load()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to restore backup"
      )
    } finally {
      setBusyId(null)
    }
  }

  async function handleSaveSchedule() {
    setSavingSchedule(true)
    try {
      if (!scheduleForm.enabled && schedule) {
        await api.backups.deleteSchedule(serverId)
        toast.success("Backup schedule disabled")
      } else if (scheduleForm.enabled) {
        await api.backups.setSchedule(serverId, scheduleForm)
        toast.success("Backup schedule saved")
      }
      await load()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save schedule"
      )
    } finally {
      setSavingSchedule(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Manual backups */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium">Backups</h3>
          <div className="flex items-center gap-2">
            <select
              className="h-8 rounded border border-input bg-background px-2 text-xs font-medium"
              value={createType}
              disabled={creating}
              onChange={(e) => setCreateType(e.target.value as BackupType)}
              title="Backup type"
            >
              <option value="zip">zip</option>
              <option value="zfs">zfs</option>
            </select>
            <Button size="sm" disabled={creating} onClick={handleCreate}>
              {creating ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Plus className="size-3.5" />
              )}
              Create Backup
            </Button>
          </div>
        </div>

        {backups.length === 0 ? (
          <div className="flex h-24 items-center justify-center border border-border text-sm text-muted-foreground">
            No backups yet
          </div>
        ) : (
          <ul className="divide-y divide-border border border-border">
            {backups.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between gap-4 px-4 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs">{b.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {b.backup_type && (
                      <span
                        className={`mr-1.5 inline-block rounded px-1 py-px text-[9px] font-semibold uppercase ${
                          b.backup_type === "zfs"
                            ? "bg-violet-500/15 text-violet-600 dark:text-violet-400"
                            : "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                        }`}
                      >
                        {b.backup_type}
                      </span>
                    )}
                    {b.created_at}
                    {b.size_bytes != null && ` · ${formatBytes(b.size_bytes)}`}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={
                      busyId === b.id ||
                      downloadingId === b.id ||
                      b.backup_type === "zfs"
                    }
                    title={
                      b.backup_type === "zfs"
                        ? "ZFS snapshots cannot be downloaded"
                        : "Download backup"
                    }
                    onClick={() => handleDownload(b)}
                  >
                    {downloadingId === b.id ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Download className="size-3" />
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={busyId === b.id}
                    onClick={() => setRestoreTarget(b)}
                  >
                    {busyId === b.id ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <RotateCcw className="size-3" />
                    )}
                    Restore
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-destructive hover:bg-destructive/10"
                    disabled={busyId === b.id}
                    onClick={() => setDeleteTarget(b)}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Schedule */}
      <div>
        <h3 className="mb-3 text-sm font-medium">Scheduled Backups</h3>
        <div className="flex flex-col gap-4 border border-border p-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="sched-enabled">Enabled</Label>
            <Switch
              id="sched-enabled"
              checked={scheduleForm.enabled}
              onCheckedChange={(v) =>
                setScheduleForm((f) => ({ ...f, enabled: v }))
              }
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="sched-cron">Cron schedule</Label>
            <Input
              id="sched-cron"
              className="font-mono text-xs"
              value={scheduleForm.cron}
              onChange={(e) =>
                setScheduleForm((f) => ({ ...f, cron: e.target.value }))
              }
              disabled={!scheduleForm.enabled}
              placeholder="0 4 * * *"
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {CRON_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  disabled={!scheduleForm.enabled}
                  onClick={() =>
                    setScheduleForm((f) => ({ ...f, cron: preset.value }))
                  }
                  className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="sched-retention">Retention (backups to keep)</Label>
            <Input
              id="sched-retention"
              type="number"
              min={1}
              className="w-32"
              value={scheduleForm.retention}
              onChange={(e) =>
                setScheduleForm((f) => ({
                  ...f,
                  retention: parseInt(e.target.value, 10) || 1,
                }))
              }
              disabled={!scheduleForm.enabled}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="sched-type">Backup Type</Label>
            <select
              id="sched-type"
              className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
              value={scheduleForm.backup_type}
              onChange={(e) =>
                setScheduleForm((f) => ({
                  ...f,
                  backup_type: e.target.value as BackupType,
                }))
              }
            >
              <option value="zip">zip — compressed archive (default)</option>
              <option value="zfs">zfs — snapshot (requires ZFS dataset)</option>
            </select>
          </div>

          <div>
            <Button
              size="sm"
              disabled={savingSchedule}
              onClick={handleSaveSchedule}
            >
              {savingSchedule ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Save className="size-3.5" />
              )}
              Save Schedule
            </Button>
          </div>
        </div>
      </div>

      {/* Delete confirm */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Backup</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently delete{" "}
            <span className="font-mono text-foreground">
              {deleteTarget?.filename}
            </span>
            .
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restore confirm */}
      <Dialog
        open={restoreTarget !== null}
        onOpenChange={(o) => !o && setRestoreTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Restore Backup</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will stop the server, wipe current world data, and restore{" "}
            <span className="font-mono text-foreground">
              {restoreTarget?.filename}
            </span>
            . This cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setRestoreTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleRestore}>
              Restore
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
