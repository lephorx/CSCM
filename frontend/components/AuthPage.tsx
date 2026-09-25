"use client"

import { useState } from "react"
import {
  Loader2,
  Server,
  ShieldCheck,
  KeyRound,
  Copy,
  Check,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { authApi } from "@/lib/api"
import type { AuthUser } from "@/hooks/useAuth"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type View = "setup-form" | "setup-qr" | "login-form"

interface Props {
  initialView: "setup-form" | "login-form"
  onLoginSuccess: (token: string, user: AuthUser) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ErrorMessage({ message }: { message: string }) {
  return (
    <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </p>
  )
}

export function AuthStatusError({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-card p-6 text-center">
        <h1 className="font-semibold">CSCM is unavailable</h1>
        <ErrorMessage message={message} />
        <Button onClick={onRetry}>Retry</Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Setup form (first-time account creation)
// ---------------------------------------------------------------------------

interface SetupFormProps {
  onSuccess: (data: {
    setup_token: string
    totp_secret: string
    totp_uri: string
    qr_code_data_uri: string
  }) => void
}

function SetupForm({ onSuccess }: SetupFormProps) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")

    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }

    setSubmitting(true)
    try {
      const { ok, data } = await authApi.setup(username, password)
      if (!ok) {
        setError(data.error ?? "Setup failed.")
        return
      }
      onSuccess({
        setup_token: data.setup_token,
        totp_secret: data.totp_secret,
        totp_uri: data.totp_uri,
        qr_code_data_uri: data.qr_code_data_uri,
      })
    } catch {
      setError("An unexpected error occurred.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="setup-username">Username</Label>
        <Input
          id="setup-username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="admin"
          required
          minLength={3}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="setup-password">Password</Label>
        <Input
          id="setup-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 12 characters"
          required
          minLength={12}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="setup-confirm">Confirm password</Label>
        <Input
          id="setup-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Repeat password"
          required
        />
      </div>

      {error && <ErrorMessage message={error} />}

      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            Preparing authenticator…
          </>
        ) : (
          "Continue to authenticator"
        )}
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// QR code / TOTP display
// ---------------------------------------------------------------------------

interface QrViewProps {
  qrCodeDataUri: string
  totpSecret: string
  setupToken: string
  onVerified: (token: string, user: AuthUser) => void
  onStartOver: () => void
}

function QrView({
  qrCodeDataUri,
  totpSecret,
  setupToken,
  onVerified,
  onStartOver,
}: QrViewProps) {
  const [copied, setCopied] = useState(false)
  const [otp, setOtp] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  function copySecret() {
    navigator.clipboard.writeText(totpSecret).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    try {
      const { ok, data } = await authApi.verifySetup(setupToken, otp)
      if (!ok) {
        setError(data.error ?? "Could not verify the code.")
        return
      }
      toast.success("Administrator account created")
      onVerified(data.token, data.user)
    } catch {
      setError("An unexpected error occurred.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Scan the QR code with your authenticator app (Google Authenticator,
        Authy, 1Password, etc.) or enter the secret manually.
      </p>

      <div className="flex justify-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={qrCodeDataUri}
          alt="TOTP QR code"
          className="size-48 rounded-lg border border-border bg-white p-2"
        />
      </div>

      <div className="space-y-1.5">
        <Label>Manual secret</Label>
        <div className="flex gap-2">
          <Input
            value={totpSecret}
            readOnly
            className="font-mono text-xs tracking-widest"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={copySecret}
            aria-label="Copy secret"
          >
            {copied ? (
              <Check className="size-4 text-green-500" />
            ) : (
              <Copy className="size-4" />
            )}
          </Button>
        </div>
      </div>

      <form onSubmit={handleVerify} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="setup-otp">One-time code</Label>
          <Input
            id="setup-otp"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
            placeholder="6-digit code"
            minLength={6}
            maxLength={6}
            pattern="[0-9]{6}"
            required
          />
        </div>
        {error && <ErrorMessage message={error} />}
        <Button className="w-full" type="submit" disabled={submitting}>
          {submitting ? (
            <Loader2 className="mr-2 size-4 animate-spin" />
          ) : (
            <KeyRound className="mr-2 size-4" />
          )}
          Verify and create account
        </Button>
      </form>
      <Button type="button" variant="outline" className="w-full" onClick={onStartOver}>
        Start over
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Login form
// ---------------------------------------------------------------------------

interface LoginFormProps {
  onLoginSuccess: (token: string, user: AuthUser) => void
}

function LoginForm({ onLoginSuccess }: LoginFormProps) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [otp, setOtp] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)

    try {
      const { ok, data } = await authApi.login(username, password, otp)
      if (!ok) {
        setError(data.error ?? "Login failed.")
        return
      }
      toast.success(`Welcome, ${data.user.username}!`)
      onLoginSuccess(data.token, data.user)
    } catch {
      setError("An unexpected error occurred.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="login-username">Username</Label>
        <Input
          id="login-username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="admin"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="login-password">Password</Label>
        <Input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="login-otp">One-time code</Label>
        <Input
          id="login-otp"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
          placeholder="6-digit code"
          maxLength={6}
          required
        />
      </div>

      {error && <ErrorMessage message={error} />}

      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            Signing in…
          </>
        ) : (
          <>
            <ShieldCheck className="mr-2 size-4" />
            Sign in
          </>
        )}
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Main AuthPage
// ---------------------------------------------------------------------------

export function AuthPage({
  initialView,
  onLoginSuccess,
}: Props) {
  const [view, setView] = useState<View>(initialView)
  const [totpData, setTotpData] = useState<{
    setup_token: string
    totp_secret: string
    qr_code_data_uri: string
  } | null>(null)

  function handleSetupSuccess(data: {
    setup_token: string
    totp_secret: string
    totp_uri: string
    qr_code_data_uri: string
  }) {
    setTotpData({
      setup_token: data.setup_token,
      totp_secret: data.totp_secret,
      qr_code_data_uri: data.qr_code_data_uri,
    })
    setView("setup-qr")
  }

  const titles: Record<View, { heading: string; sub: string }> = {
    "setup-form": {
      heading: "Create administrator account",
      sub: "First-time setup — this can only be done once.",
    },
    "setup-qr": {
      heading: "Set up authenticator",
      sub: "Scan the QR code, then enter one code to finish registration.",
    },
    "login-form": {
      heading: "Sign in",
      sub: "Enter your credentials and one-time code.",
    },
  }

  const { heading, sub } = titles[view]

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Brand */}
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
            <Server className="size-5 text-primary" />
          </div>
          <span className="text-lg font-semibold tracking-tight">CSCM</span>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <div className="mb-5 space-y-0.5">
            <h1 className="text-base font-semibold">{heading}</h1>
            <p className="text-sm text-muted-foreground">{sub}</p>
          </div>

          <Separator className="mb-5" />

          {view === "setup-form" && (
            <SetupForm onSuccess={handleSetupSuccess} />
          )}

          {view === "setup-qr" && totpData && (
            <QrView
              qrCodeDataUri={totpData.qr_code_data_uri}
              totpSecret={totpData.totp_secret}
              setupToken={totpData.setup_token}
              onVerified={onLoginSuccess}
              onStartOver={() => {
                setTotpData(null)
                setView("setup-form")
              }}
            />
          )}

          {view === "login-form" && (
            <LoginForm onLoginSuccess={onLoginSuccess} />
          )}
        </div>
      </div>
    </div>
  )
}
