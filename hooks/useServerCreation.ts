"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import type { CreateServerPayload } from "@/lib/types"

export type CreationStage = "submitting" | "starting" | "ready" | "error"

export interface CreationTask {
  serverId: number
  name: string
  stage: CreationStage
  progress: number
  step: string
}

const POLL_MS = 2000
const SUBMIT_TICK_MS = 400
// Progress shown while the create request is in flight, before we have a
// real server to poll — capped low so it never has to jump backwards once
// the backend reports real (and possibly lower) progress.
const SUBMIT_PROGRESS_CAP = 15

// Single source of truth for "creating a server" — lives above both the
// create modal and the floating background notification so minimizing or
// reopening the modal never loses or restarts progress tracking.
export function useServerCreation(onServerCreated?: () => void) {
  const [task, setTask] = useState<CreationTask | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopTimers = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (tickRef.current) clearInterval(tickRef.current)
    pollRef.current = null
    tickRef.current = null
  }, [])

  const pollProgress = useCallback(
    (serverId: number) => {
      const poll = async () => {
        try {
          const res = await api.servers.progress(serverId)
          const percent: number = res?.percent ?? 0
          const step: string = res?.step ?? ""
          const status: string = res?.status ?? ""
          const done = status === "done" || percent >= 100

          setTask((prev) => {
            if (!prev || prev.serverId !== serverId) return prev
            return {
              ...prev,
              // Progress only ever moves forward, even if a poll returns a
              // lower number than what's already on screen.
              progress: done ? 100 : Math.max(prev.progress, percent),
              step: step || prev.step,
              stage: done ? "ready" : status === "error" ? "error" : "starting",
            }
          })

          if (done || status === "error") {
            stopTimers()
            if (done) onServerCreated?.()
          }
        } catch {
          // transient network hiccup — keep polling
        }
      }

      void poll()
      pollRef.current = setInterval(poll, POLL_MS)
    },
    [onServerCreated, stopTimers]
  )

  const start = useCallback(
    async (payload: CreateServerPayload) => {
      stopTimers()
      setTask({
        serverId: 0,
        name: payload.name,
        stage: "submitting",
        progress: 5,
        step: "",
      })

      tickRef.current = setInterval(() => {
        setTask((prev) =>
          prev &&
          prev.stage === "submitting" &&
          prev.progress < SUBMIT_PROGRESS_CAP
            ? { ...prev, progress: prev.progress + 1 }
            : prev
        )
      }, SUBMIT_TICK_MS)

      try {
        const result = await api.servers.create(payload)
        const serverId: number =
          result?.server_id ?? result?.data?.server_id ?? 0

        if (tickRef.current) clearInterval(tickRef.current)
        setTask({
          serverId,
          name: payload.name,
          stage: "starting",
          progress: SUBMIT_PROGRESS_CAP,
          step: "",
        })
        pollProgress(serverId)
        return serverId
      } catch (err) {
        stopTimers()
        setTask(null)
        throw err
      }
    },
    [pollProgress, stopTimers]
  )

  const dismiss = useCallback(() => {
    stopTimers()
    setTask(null)
  }, [stopTimers])

  // Stop polling if whatever mounted this hook goes away mid-creation.
  useEffect(() => stopTimers, [stopTimers])

  return { task, start, dismiss }
}
