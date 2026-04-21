"use client"

import Link from "next/link"
import { Server } from "lucide-react"

export function TopNav() {
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
        <span className="text-xs text-muted-foreground">
          Minecraft Server Manager
        </span>
      </div>
    </header>
  )
}
