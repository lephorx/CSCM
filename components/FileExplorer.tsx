"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import {
  Folder,
  File,
  ChevronRight,
  Upload,
  Trash2,
  Download,
  MoreHorizontal,
  Loader2,
  Home,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import type { FileEntry } from "@/lib/types"
import { api } from "@/lib/api"

interface Props {
  serverId: number
}

function formatSize(bytes: number | null) {
  if (bytes === null) return ""
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileExplorer({ serverId }: Props) {
  const [path, setPath] = useState("/")
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [activeMenu, setActiveMenu] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)

  const loadDir = useCallback(
    async (targetPath: string) => {
      setLoading(true)
      try {
        const res = await api.files.list(serverId, targetPath)
        setEntries(res?.entries ?? [])
        setPath(res?.path ?? targetPath)
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Failed to load directory"
        )
      } finally {
        setLoading(false)
      }
    },
    [serverId]
  )

  useEffect(() => {
    loadDir(path)
  }, []) // only on mount; navigate via loadDir calls

  // Breadcrumb segments
  const segments = path === "/" ? [] : path.replace(/^\//, "").split("/")

  function navigateTo(index: number) {
    if (index < 0) {
      loadDir("/")
    } else {
      loadDir("/" + segments.slice(0, index + 1).join("/"))
    }
    setActiveMenu(null)
  }

  function handleEntryClick(entry: FileEntry) {
    if (entry.type === "directory") {
      const next = path === "/" ? `/${entry.name}` : `${path}/${entry.name}`
      loadDir(next)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.files.delete(serverId, deleteTarget)
      toast.success("Deleted successfully")
      setDeleteTarget(null)
      loadDir(path)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed")
    } finally {
      setDeleting(false)
    }
  }

  function handleDownload(name: string) {
    const filePath = path === "/" ? `/${name}` : `${path}/${name}`
    const url = api.files.downloadUrl(serverId, filePath)
    window.open(url, "_blank", "noopener")
    setActiveMenu(null)
  }

  async function uploadFiles(files: FileList | File[]) {
    const fileArr = Array.from(files)
    if (fileArr.length === 0) return
    setUploading(true)
    setUploadProgress(0)

    let done = 0
    for (const file of fileArr) {
      try {
        await api.files.upload(serverId, file, path)
        done++
        setUploadProgress(Math.round((done / fileArr.length) * 100))
      } catch (err) {
        toast.error(
          `Failed to upload ${file.name}: ${err instanceof Error ? err.message : "Unknown error"}`
        )
      }
    }

    setUploading(false)
    setUploadProgress(null)
    toast.success(`Uploaded ${done}/${fileArr.length} file(s)`)
    loadDir(path)
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) uploadFiles(e.target.files)
    e.target.value = ""
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (e.dataTransfer.files) uploadFiles(e.dataTransfer.files)
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        {/* Breadcrumb */}
        <nav
          aria-label="File path"
          className="flex min-w-0 items-center gap-1 text-xs"
        >
          <button
            onClick={() => navigateTo(-1)}
            className="flex items-center gap-0.5 text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Go to root"
          >
            <Home className="size-3" />
          </button>
          {segments.map((seg, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
              <button
                onClick={() => navigateTo(i)}
                className="max-w-24 truncate text-muted-foreground transition-colors hover:text-foreground"
              >
                {seg}
              </button>
            </span>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {uploading && uploadProgress !== null && (
            <span className="text-xs text-muted-foreground">
              {uploadProgress}%
            </span>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            aria-label="Upload file"
          >
            {uploading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Upload className="size-3.5" />
            )}
            Upload
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileInput}
          />
        </div>
      </div>

      {/* File list drop zone */}
      <div
        ref={dropZoneRef}
        className="flex-1 overflow-y-auto"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : entries.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            Empty directory
          </div>
        ) : (
          <ul>
            {entries
              .sort((a, b) => {
                if (a.type !== b.type) return a.type === "directory" ? -1 : 1
                return a.name.localeCompare(b.name)
              })
              .map((entry) => {
                const entryPath =
                  path === "/" ? `/${entry.name}` : `${path}/${entry.name}`
                const isMenuOpen = activeMenu === entry.name

                return (
                  <li
                    key={entry.name}
                    className="group flex items-center gap-3 px-4 py-2 transition-colors hover:bg-muted/60"
                  >
                    {/* Icon + name */}
                    <button
                      className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                      onDoubleClick={() => handleEntryClick(entry)}
                      onClick={() => {
                        if (entry.type === "directory") handleEntryClick(entry)
                      }}
                      aria-label={`${entry.type === "directory" ? "Open folder" : "File"}: ${entry.name}`}
                    >
                      {entry.type === "directory" ? (
                        <Folder className="size-4 shrink-0 text-primary" />
                      ) : (
                        <File className="size-4 shrink-0 text-muted-foreground" />
                      )}
                      <span className="truncate text-sm">{entry.name}</span>
                    </button>

                    {/* Size */}
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatSize(entry.size)}
                    </span>

                    {/* Actions menu */}
                    <div className="relative">
                      <button
                        className="flex size-6 items-center justify-center opacity-0 transition-all group-hover:opacity-100 hover:bg-muted"
                        onClick={(e) => {
                          e.stopPropagation()
                          setActiveMenu(isMenuOpen ? null : entry.name)
                        }}
                        aria-label={`Actions for ${entry.name}`}
                        aria-haspopup="true"
                        aria-expanded={isMenuOpen}
                      >
                        <MoreHorizontal className="size-3.5" />
                      </button>

                      {isMenuOpen && (
                        <div
                          className="absolute right-0 bottom-7 z-50 min-w-32 border border-border bg-popover py-1 shadow-md"
                          role="menu"
                        >
                          {entry.type === "file" && (
                            <button
                              role="menuitem"
                              className="flex w-full items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted"
                              onClick={() => handleDownload(entry.name)}
                            >
                              <Download className="size-3.5" />
                              Download
                            </button>
                          )}
                          <button
                            role="menuitem"
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                            onClick={() => {
                              setDeleteTarget(entryPath)
                              setActiveMenu(null)
                            }}
                          >
                            <Trash2 className="size-3.5" />
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </li>
                )
              })}
          </ul>
        )}
      </div>

      {/* Delete confirm */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete File</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete{" "}
            <span className="font-mono text-foreground">{deleteTarget}</span>?
            This cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={handleDelete}
            >
              {deleting && <Loader2 className="size-3.5 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
