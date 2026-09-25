"use client"

import { useEffect, useState } from "react"
import { Check, Globe, Loader2, Lock, ExternalLink } from "lucide-react"
import { toast } from "sonner"

import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

const PLAYIT_AGENT_WIZARD =
  "https://playit.gg/account/setup/wizard/new-account/docker/docker-name"
const REGIONS = [
  "Germany", "United Kingdom", "Sweden", "Poland", "Spain", "Seattle",
  "Los Angeles", "Denver", "Dallas", "Chicago", "New York", "Miami",
  "Singapore", "Japan", "Australia", "Sao Paulo", "Chile", "India",
]

type Step = "mode" | "playit" | "agent" | "cloudflare"
const STEPS: Step[] = ["mode", "playit", "agent", "cloudflare"]
const STEP_TITLES: Record<Step, string> = {
  mode: "Access",
  playit: "Playit account",
  agent: "Playit agent",
  cloudflare: "Custom domain",
}

interface SettingsResponse {
  values: Record<string, string>
  secrets_set: Record<string, boolean>
  env_writable: boolean
  agent: { managed: boolean; running: boolean; source: string | null }
  setup: { completed: boolean; step: Step; mode: "public" | "local" | null }
}

interface Props {
  /** true right after account creation; false when reopened from the top bar */
  firstRun: boolean
  onDone: () => void
}

// Connection setup after account creation. Every step is saved to the
// installation's .env as soon as the user continues, and the current step is
// stored on the server, so the wizard resumes where it was left.
export function SetupWizard({ firstRun, onDone }: Props) {
  const [loaded, setLoaded] = useState<SettingsResponse | null>(null)
  const [step, setStep] = useState<Step>("mode")
  const [saving, setSaving] = useState(false)

  // form state (secrets stay empty unless the user types a new one)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [subscription, setSubscription] = useState("free")
  const [region, setRegion] = useState("Germany")
  const [agentMode, setAgentMode] = useState<"managed" | "existing">("managed")
  const [agentName, setAgentName] = useState("")
  const [secretKey, setSecretKey] = useState("")
  const [cfEnabled, setCfEnabled] = useState(false)
  const [cfToken, setCfToken] = useState("")
  const [cfZone, setCfZone] = useState("")
  const [cfDomain, setCfDomain] = useState("")

  useEffect(() => {
    api.settings
      .get()
      .then((res: SettingsResponse) => {
        const v = res.values
        setLoaded(res)
        setStep(firstRun ? res.setup.step : "mode")
        setEmail(v.PLAYIT_EMAIL ?? "")
        setSubscription(v.PLAYIT_SUBSCRIPTION || "free")
        setRegion(v.PLAYIT_REGION || "Germany")
        setAgentName(v.PLAYIT_AGENT ?? "")
        setAgentMode(
          res.secrets_set.PLAYIT_SECRET_KEY || res.agent.managed || !v.PLAYIT_AGENT
            ? "managed"
            : "existing"
        )
        setCfEnabled(
          (v.CLOUDFLARE_ENABLED || "false") !== "false" && !!v.CLOUDFLARE_ZONE_ID
        )
        setCfZone(v.CLOUDFLARE_ZONE_ID ?? "")
        setCfDomain(v.CLOUDFLARE_BASE_DOMAIN ?? "")
      })
      .catch((err) =>
        toast.error(err instanceof Error ? err.message : "Could not load settings")
      )
  }, [firstRun])

  async function run(action: () => Promise<void>) {
    setSaving(true)
    try {
      await action()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save")
    } finally {
      setSaving(false)
    }
  }

  const goTo = (next: Step) => {
    setStep(next)
    api.setup.update({ step: next }).catch(() => {})
  }

  const finish = (mode: "public" | "local") =>
    run(async () => {
      await api.setup.update({ mode, completed: true, step: "mode" })
      toast.success(
        mode === "public"
          ? "Setup complete. New servers get a public address."
          : "Setup complete. Servers are reachable in your network."
      )
      onDone()
    })

  const saveAccount = () =>
    run(async () => {
      if (!email.trim()) throw new Error("Enter your Playit email.")
      if (!password && !loaded?.secrets_set.PLAYIT_PASSWORD)
        throw new Error("Enter your Playit password.")
      await api.settings.save({
        PLAYIT_EMAIL: email.trim(),
        PLAYIT_PASSWORD: password || null,
        PLAYIT_SUBSCRIPTION: subscription,
        PLAYIT_REGION: region,
      })
      await api.setup.update({ mode: "public" })
      goTo("agent")
    })

  const saveAgent = () =>
    run(async () => {
      if (agentMode === "managed") {
        if (!secretKey && !loaded?.secrets_set.PLAYIT_SECRET_KEY)
          throw new Error("Paste the agent's SECRET_KEY.")
        await api.settings.save({
          PLAYIT_SECRET_KEY: secretKey || null,
          PLAYIT_AGENT: agentName.trim(),
        })
        await api.settings.startAgent()
      } else {
        await api.settings.save({ PLAYIT_AGENT: agentName.trim() })
        if (loaded?.agent.source === "cscm") await api.settings.stopAgent()
      }
      goTo("cloudflare")
    })

  const saveCloudflare = () =>
    run(async () => {
      if (cfEnabled) {
        if (!cfZone.trim() || !cfDomain.trim())
          throw new Error("Enter the zone ID and base domain.")
        if (!cfToken && !loaded?.secrets_set.CLOUDFLARE_API_TOKEN)
          throw new Error("Enter a Cloudflare API token.")
      }
      await api.settings.save({
        CLOUDFLARE_ENABLED: cfEnabled ? "auto" : "false",
        CLOUDFLARE_API_TOKEN: cfEnabled ? cfToken || null : null,
        CLOUDFLARE_ZONE_ID: cfEnabled ? cfZone.trim() : null,
        CLOUDFLARE_BASE_DOMAIN: cfEnabled ? cfDomain.trim() : null,
      })
      await finish("public")
    })

  if (!loaded) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const stepIndex = STEPS.indexOf(step)
  const savedHint = (set: boolean) => (set ? "Saved. Leave empty to keep it." : "")

  return (
    <div className="mx-auto w-full max-w-xl px-6 py-10">
      <p className="text-xs tracking-widest text-muted-foreground uppercase">
        {firstRun ? "Welcome to CSCM" : "Settings"}
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        {firstRun ? "Finish setting up" : "Connection settings"}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Settings are saved to your installation&apos;s <code>.env</code> as you
        go. You can change them later in the top bar, or edit <code>.env</code>{" "}
        directly.
      </p>

      {!loaded.env_writable && (
        <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          CSCM can&apos;t write to <code>.env</code> in this installation. Update
          CSCM, or add the values to <code>.env</code> by hand and run{" "}
          <code>docker compose restart api</code>.
        </p>
      )}

      {/* progress */}
      <ol className="mt-8 flex gap-2">
        {STEPS.map((s, i) => (
          <li
            key={s}
            className={cn(
              "h-1 flex-1 rounded-full bg-border",
              i <= stepIndex && "bg-primary"
            )}
            title={STEP_TITLES[s]}
          />
        ))}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">
        Step {stepIndex + 1} of {STEPS.length}: {STEP_TITLES[step]}
      </p>

      <div className="mt-6 rounded-lg border border-border p-6">
        {step === "mode" && (
          <div className="space-y-3">
            <p className="text-sm font-medium">
              Who should be able to join your Minecraft servers?
            </p>
            <button
              type="button"
              onClick={() => goTo("playit")}
              className="flex w-full items-start gap-3 rounded-md border border-border p-4 text-left transition-colors hover:border-primary"
            >
              <Globe className="mt-0.5 size-4 text-primary" />
              <span>
                <span className="block text-sm font-medium">
                  Anyone, over the internet
                </span>
                <span className="block text-xs text-muted-foreground">
                  Uses a free Playit.gg account, no router setup needed.
                </span>
              </span>
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => finish("local")}
              className="flex w-full items-start gap-3 rounded-md border border-border p-4 text-left transition-colors hover:border-primary"
            >
              <Lock className="mt-0.5 size-4 text-muted-foreground" />
              <span>
                <span className="block text-sm font-medium">
                  Only my local network
                </span>
                <span className="block text-xs text-muted-foreground">
                  Nothing else to set up. You can switch later.
                </span>
              </span>
            </button>
          </div>
        )}

        {step === "playit" && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              CSCM creates the tunnels for your servers with your{" "}
              <a
                href="https://playit.gg"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-4"
              >
                Playit.gg
              </a>{" "}
              account.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="playit-email">Playit email</Label>
              <Input
                id="playit-email"
                type="email"
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="playit-password">Playit password</Label>
              <Input
                id="playit-password"
                type="password"
                autoComplete="new-password"
                placeholder={loaded.secrets_set.PLAYIT_PASSWORD ? "••••••••" : ""}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {savedHint(loaded.secrets_set.PLAYIT_PASSWORD)}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Subscription</Label>
              <div className="flex gap-2">
                {["free", "premium"].map((s) => (
                  <Button
                    key={s}
                    type="button"
                    size="sm"
                    variant={subscription === s ? "default" : "outline"}
                    onClick={() => setSubscription(s)}
                  >
                    {s === "free" ? "Free" : "Premium"}
                  </Button>
                ))}
              </div>
            </div>
            {subscription === "premium" && (
              <div className="space-y-1.5">
                <Label htmlFor="playit-region">Region</Label>
                <select
                  id="playit-region"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                >
                  {REGIONS.map((r) => (
                    <option key={r} value={r} className="bg-background">
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {step === "agent" && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              A Playit agent on this device carries the traffic to your
              servers.
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={agentMode === "managed" ? "default" : "outline"}
                onClick={() => setAgentMode("managed")}
              >
                Let CSCM run it
              </Button>
              <Button
                type="button"
                size="sm"
                variant={agentMode === "existing" ? "default" : "outline"}
                onClick={() => setAgentMode("existing")}
              >
                I already run one
              </Button>
            </div>

            {agentMode === "managed" ? (
              <>
                <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                  <li>
                    Create or claim an agent in the{" "}
                    <a
                      href={PLAYIT_AGENT_WIZARD}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 underline underline-offset-4"
                    >
                      Playit Docker setup <ExternalLink className="size-3" />
                    </a>
                    .
                  </li>
                  <li>Copy its SECRET_KEY and paste it below.</li>
                </ol>
                <div className="space-y-1.5">
                  <Label htmlFor="playit-secret">Agent SECRET_KEY</Label>
                  <Input
                    id="playit-secret"
                    type="password"
                    autoComplete="off"
                    placeholder={loaded.secrets_set.PLAYIT_SECRET_KEY ? "••••••••" : ""}
                    value={secretKey}
                    onChange={(e) => setSecretKey(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {savedHint(loaded.secrets_set.PLAYIT_SECRET_KEY)}
                  </p>
                </div>
                <p className="text-xs text-muted-foreground">
                  On macOS and Windows, first enable{" "}
                  <strong>
                    Settings → Resources → Network → Enable host networking
                  </strong>{" "}
                  in Docker Desktop (4.34 or newer).
                </p>
              </>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="playit-agent">Agent name (optional)</Label>
                <Input
                  id="playit-agent"
                  placeholder="First available agent"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Keep that agent running on this device.
                </p>
              </div>
            )}
          </div>
        )}

        {step === "cloudflare" && (
          <div className="space-y-4">
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>
                <span className="block font-medium">
                  Use my own domain (optional)
                </span>
                <span className="block text-xs text-muted-foreground">
                  Give servers addresses like survival.example.com through
                  Cloudflare. Otherwise players use the Playit address.
                </span>
              </span>
              <Switch checked={cfEnabled} onCheckedChange={setCfEnabled} />
            </label>
            {cfEnabled && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="cf-token">Cloudflare API token</Label>
                  <Input
                    id="cf-token"
                    type="password"
                    autoComplete="off"
                    placeholder={
                      loaded.secrets_set.CLOUDFLARE_API_TOKEN ? "••••••••" : ""
                    }
                    value={cfToken}
                    onChange={(e) => setCfToken(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {savedHint(loaded.secrets_set.CLOUDFLARE_API_TOKEN) ||
                      "Needs permission to edit DNS for your zone."}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cf-zone">Zone ID</Label>
                  <Input
                    id="cf-zone"
                    value={cfZone}
                    onChange={(e) => setCfZone(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cf-domain">Base domain</Label>
                  <Input
                    id="cf-domain"
                    placeholder="example.com"
                    value={cfDomain}
                    onChange={(e) => setCfDomain(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <div>
          {stepIndex > 0 && (
            <Button
              variant="ghost"
              disabled={saving}
              onClick={() => goTo(STEPS[stepIndex - 1])}
            >
              Back
            </Button>
          )}
          {!firstRun && stepIndex === 0 && (
            <Button variant="ghost" onClick={onDone}>
              Close
            </Button>
          )}
        </div>
        {step !== "mode" && (
          <Button
            disabled={saving}
            onClick={
              step === "playit"
                ? saveAccount
                : step === "agent"
                  ? saveAgent
                  : saveCloudflare
            }
          >
            {saving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              step === "cloudflare" && <Check className="size-4" />
            )}
            {step === "cloudflare" ? "Finish" : "Continue"}
          </Button>
        )}
      </div>
    </div>
  )
}
