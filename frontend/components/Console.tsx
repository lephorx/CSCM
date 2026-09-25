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
const MAX_LINES = 2000

export function Console({ serverId, isRunning }: Props) {
  const [logs, setLogs] = useState<string[]>([])
  const [command, setCommand] = useState("")
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [live, setLive] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const historyRef = useRef<string[]>([])
  const historyIndexRef = useRef<number>(-1)
  // Pending lines are accumulated here and flushed on a timer to avoid
  // a state update (and full re-render) for every single SSE message.
  const pendingLinesRef = useRef<string[]>([])
  // Track whether the user is scrolled to the bottom so we don't snap
  // them back while they're reading older output.
  const atBottomRef = useRef(true)

  const flushPending = useCallback(() => {
    if (pendingLinesRef.current.length === 0) return
    const toAdd = pendingLinesRef.current.splice(0)
    setLogs((prev) => {
      const next = prev.concat(toAdd)
      return next.length > MAX_LINES
        ? next.slice(next.length - MAX_LINES)
        : next
    })
  }, [])

  const appendLine = useCallback((line: string) => {
    pendingLinesRef.current.push(line)
  }, [])

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

  const startPolling = useCallback(() => {
    if (intervalRef.current) return
    fetchLogs()
    intervalRef.current = setInterval(fetchLogs, POLL_INTERVAL)
  }, [fetchLogs])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  // Load history once, then switch to the live SSE stream. Fall back to
  // polling if the stream can't be opened or drops.
  useEffect(() => {
    let cancelled = false

    // Flush accumulated SSE lines at most 5× per second
    const flushTimer = setInterval(flushPending, 200)

    fetchLogs().then(() => {
      if (cancelled) return

      const es = new EventSource(api.console.streamUrl(serverId))
      eventSourceRef.current = es

      es.addEventListener("log", (e: MessageEvent) => {
        setLive(true)
        stopPolling()
        appendLine(e.data)
      })

      es.onerror = () => {
        setLive(false)
        es.close()
        eventSourceRef.current = null
        startPolling()
      }
    })

    return () => {
      cancelled = true
      clearInterval(flushTimer)
      flushPending() // drain any remaining lines on unmount
      eventSourceRef.current?.close()
      eventSourceRef.current = null
      stopPolling()
    }
  }, [serverId, fetchLogs, appendLine, flushPending, startPolling, stopPolling])

  // Auto-scroll only when the user is already at (or very near) the bottom
  useEffect(() => {
    if (!atBottomRef.current) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  }

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
      historyRef.current = [cmd, ...historyRef.current].slice(0, 100)
      historyIndexRef.current = -1
      setCommand("")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send command")
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    const history = historyRef.current
    if (e.key === "ArrowUp") {
      e.preventDefault()
      const next = Math.min(historyIndexRef.current + 1, history.length - 1)
      historyIndexRef.current = next
      if (history[next] !== undefined) setCommand(history[next])
    } else if (e.key === "ArrowDown") {
      e.preventDefault()
      const next = historyIndexRef.current - 1
      historyIndexRef.current = next
      setCommand(next < 0 ? "" : (history[next] ?? ""))
    }
  }

  return (
    <div className="flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Console
          </span>
          <span
            className={`flex items-center gap-1 text-[10px] ${live ? "text-emerald-500" : "text-muted-foreground"}`}
          >
            <span
              className={`size-1.5 rounded-full ${live ? "animate-pulse bg-emerald-500" : "bg-zinc-400"}`}
            />
            {live ? "Live" : "Polling"}
          </span>
        </div>
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
        onScroll={handleScroll}
        className="h-[420px] overflow-y-auto bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-200"
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
        className="flex items-center gap-2 border-t border-border bg-zinc-950 px-4 py-2"
      >
        <span className="shrink-0 font-mono text-xs text-muted-foreground select-none">
          &gt;
        </span>
        <Input
          className="flex-1 border-none bg-transparent font-mono text-xs text-zinc-200 shadow-none placeholder:text-zinc-600 focus-visible:ring-0"
          placeholder={isRunning ? "Enter command…" : "Server is not running"}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!isRunning || sending}
          autoComplete="off"
          spellCheck={false}
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
