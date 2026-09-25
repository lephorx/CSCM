"use client"

import { useState, useEffect, useCallback } from "react"
import { authApi, saveToken, clearToken } from "@/lib/api"

export interface AuthUser {
  id: number
  username: string
}

export interface AuthState {
  loading: boolean
  statusError: string | null
  setupRequired: boolean
  authenticated: boolean
  user: AuthUser | null
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    loading: true,
    statusError: null,
    setupRequired: false,
    authenticated: false,
    user: null,
  })

  const checkStatus = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }))
    try {
      const { ok, data } = await authApi.status()
      if (!ok) throw new Error(data.error ?? "Authentication service is unavailable")
      setState({
        loading: false,
        statusError: null,
        setupRequired: data.setup_required ?? false,
        authenticated: data.authenticated ?? false,
        user: data.user ?? null,
      })
    } catch (error) {
      setState({
        loading: false,
        statusError: error instanceof Error ? error.message : "Authentication service is unavailable",
        setupRequired: false,
        authenticated: false,
        user: null,
      })
    }
  }, [])

  useEffect(() => {
    checkStatus()
  }, [checkStatus])

  const onLoginSuccess = useCallback((token: string, user: AuthUser) => {
    saveToken(token)
    setState({
      loading: false,
      statusError: null,
      setupRequired: false,
      authenticated: true,
      user,
    })
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setState({
      loading: false,
      statusError: null,
      setupRequired: false,
      authenticated: false,
      user: null,
    })
  }, [])

  return { ...state, onLoginSuccess, logout, retryStatus: checkStatus }
}
