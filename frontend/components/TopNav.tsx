"use client"

import Link from "next/link"
import { Server, LogOut } from "lucide-react"

import { Button } from "@/components/ui/button"

interface Props {
  user?: { id: number; username: string } | null
  onLogout?: () => void
}

export function TopNav({ user, onLogout }: Props) {
  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto flex h-14 max-w-screen-xl items-center justify-between px-6">
        <Link
          href="/"
          className="flex items-center gap-2.5 text-sm font-semibold tracking-tight transition-opacity hover:opacity-80"
        >
          <Server className="size-4 text-primary" />
          <span>CSCM</span>
        </Link>

        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs text-muted-foreground">
              {user.username}
            </span>
          )}
          {onLogout && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onLogout}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="size-4" />
            </Button>
          )}
          {!user && !onLogout && (
            <span className="text-xs text-muted-foreground">
              Minecraft Server Manager
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
