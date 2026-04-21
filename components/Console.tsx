"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Send, Trash2, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

interface Props {
  serverId: number
  isRunning: boolean
}

const POLL_INTERVAL = 3000

export function Console({ serverId, isRunning }: Props) {
  const [logs, setLogs] = useState<string[]>([])
  const [command, setCommand] = useState("")
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchLogs = useCallback(async () => {
    try {
      const res = await api.servers.logs(serverId)
      if (Array.isArray(res?.data)) {
        setLogs(res.data)
      }
    } catch {
      // silently fail on polling errors
    } finally {
      setLoading(false)
    }
  }, [serverId])

  useEffect(() => {
    fetchLogs()
    intervalRef.current = setInterval(fetchLogs, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchLogs])

  // Auto-scroll when logs change
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  async function sendCommand(e: React.FormEvent) {
    e.preventDefault()
    const cmd = command.trim()
    if (!cmd) return

    // Basic validation: no shell metacharacters
    if (/[;&|`$]/.test(cmd)) {
      toast.error("Command contains invalid characters")
      return
    }

    setSending(true)
    try {
      await api.control.command(serverId, cmd)
      setCommand("")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send command")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex h-full flex-col gap-0">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Console
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLogs([])}
          aria-label="Clear console"
        >
          <Trash2 className="size-3.5" />
          Clear
        </Button>
      </div>

      {/* Log output */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-200"
        style={{ minHeight: "320px" }}
        aria-live="polite"
        aria-label="Server console output"
      >
        {loading ? (
          <span className="text-zinc-500">Loading logs…</span>
        ) : logs.length === 0 ? (
          <span className="text-zinc-500">No output yet.</span>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="break-all whitespace-pre-wrap">
              {line}
            </div>
          ))
        )}
      </div>

      {/* Command input */}
      <form
        onSubmit={sendCommand}
        className="flex items-center gap-2 border-t border-border p-3"
      >
        <span className="shrink-0 font-mono text-xs text-muted-foreground select-none">
          &gt;
        </span>
        <Input
          className="flex-1 font-mono text-xs"
          placeholder={isRunning ? "Enter command…" : "Server is not running"}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          disabled={!isRunning || sending}
          autoComplete="off"
          aria-label="Console command input"
        />
        <Button
          type="submit"
          size="sm"
          disabled={!isRunning || sending || !command.trim()}
          aria-label="Send command"
        >
          {sending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Send className="size-3.5" />
          )}
        </Button>
      </form>
    </div>
  )
}
