"use client"

import { useState, useEffect, useCallback } from "react"
import { authApi, saveToken, clearToken } from "@/lib/api"

export interface AuthUser {
  id: number
  username: string
}

export interface AuthState {
  loading: boolean
  setupRequired: boolean
  authenticated: boolean
  user: AuthUser | null
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    loading: true,
    setupRequired: false,
    authenticated: false,
    user: null,
  })

  const checkStatus = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }))
    try {
      const { data } = await authApi.status()
      setState({
        loading: false,
        setupRequired: data.setup_required ?? false,
        authenticated: data.authenticated ?? false,
        user: data.user ?? null,
      })
    } catch {
      setState({
        loading: false,
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
      setupRequired: false,
      authenticated: true,
      user,
    })
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setState({
      loading: false,
      setupRequired: false,
      authenticated: false,
      user: null,
    })
  }, [])

  const onSetupComplete = useCallback(() => {
    setState((s) => ({
      ...s,
      setupRequired: false,
    }))
  }, [])

  return { ...state, onLoginSuccess, onSetupComplete, logout }
}
