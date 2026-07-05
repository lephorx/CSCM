// Shared server.properties definitions for both editions — used by
// DefaultsEditor (the global defaults screen) and ServerCreateModal (to
// filter the "Initial Properties" list down to whichever edition is being
// created, instead of showing every key from both mixed together).

export type PropType = "text" | "number" | "boolean" | "select"

export interface PropDef {
  key: string
  label: string
  type: PropType
  options?: string[]
  hint?: string
}

export type PropCategory = { title: string; props: PropDef[] }

// ── Minecraft Java Edition server.properties defaults ─────────────────────────
// Excludes blacklisted keys: server-port, enable-rcon, rcon.port, rcon.password

export const MC_DEFAULTS: Record<string, string> = {
  "accept-transfers": "false",
  "allow-flight": "false",
  "allow-nether": "true",
  "broadcast-console-to-ops": "true",
  "broadcast-rcon-to-ops": "true",
  difficulty: "easy",
  "enable-command-block": "false",
  "enable-query": "false",
  "enable-status": "true",
  "enforce-secure-profile": "true",
  "enforce-whitelist": "false",
  "entity-broadcast-range-percentage": "100",
  "force-gamemode": "false",
  "function-permission-level": "2",
  gamemode: "survival",
  "generate-structures": "true",
  "generator-settings": "{}",
  hardcore: "false",
  "hide-online-players": "false",
  "initial-disabled-packs": "",
  "initial-enabled-packs": "vanilla",
  "level-name": "world",
  "level-seed": "",
  "level-type": "minecraft\\:normal",
  "log-ips": "true",
  "max-chained-neighbor-updates": "1000000",
  "max-players": "20",
  "max-tick-time": "60000",
  "max-world-size": "29999984",
  motd: "A Minecraft Server",
  "network-compression-threshold": "256",
  "online-mode": "true",
  "op-permission-level": "4",
  "pause-when-empty-seconds": "60",
  "player-idle-timeout": "0",
  "prevent-proxy-connections": "false",
  pvp: "true",
  "query.port": "25565",
  "rate-limit": "0",
  "region-file-compression": "deflate",
  "require-resource-pack": "false",
  "resource-pack": "",
  "resource-pack-id": "",
  "resource-pack-prompt": "",
  "resource-pack-sha1": "",
  "server-ip": "",
  "simulation-distance": "10",
  "spawn-animals": "true",
  "spawn-monsters": "true",
  "spawn-npcs": "true",
  "spawn-protection": "16",
  "sync-chunk-writes": "true",
  "text-filtering-config": "",
  "text-filtering-version": "0",
  "use-native-transport": "true",
  "view-distance": "10",
  "white-list": "false",
}

export const MC_CATEGORIES: PropCategory[] = [
  {
    title: "World",
    props: [
      { key: "level-name", label: "Level Name", type: "text" },
      {
        key: "level-seed",
        label: "Level Seed",
        type: "text",
        hint: "Leave empty for random",
      },
      {
        key: "level-type",
        label: "Level Type",
        type: "select",
        options: [
          "minecraft\\:normal",
          "minecraft\\:flat",
          "minecraft\\:large_biomes",
          "minecraft\\:amplified",
          "minecraft\\:single_biome_surface",
          "minecraft\\:debug",
        ],
      },
      {
        key: "generate-structures",
        label: "Generate Structures",
        type: "boolean",
      },
      {
        key: "generator-settings",
        label: "Generator Settings",
        type: "text",
        hint: "JSON for flat/single-biome",
      },
      {
        key: "max-world-size",
        label: "Max World Size (blocks)",
        type: "number",
      },
    ],
  },
  {
    title: "Gameplay",
    props: [
      {
        key: "gamemode",
        label: "Default Game Mode",
        type: "select",
        options: ["survival", "creative", "adventure", "spectator"],
      },
      {
        key: "difficulty",
        label: "Difficulty",
        type: "select",
        options: ["peaceful", "easy", "normal", "hard"],
      },
      { key: "hardcore", label: "Hardcore Mode", type: "boolean" },
      { key: "pvp", label: "PvP", type: "boolean" },
      { key: "force-gamemode", label: "Force Gamemode", type: "boolean" },
      { key: "allow-nether", label: "Allow Nether", type: "boolean" },
      { key: "spawn-animals", label: "Spawn Animals", type: "boolean" },
      { key: "spawn-monsters", label: "Spawn Monsters", type: "boolean" },
      { key: "spawn-npcs", label: "Spawn NPCs / Villagers", type: "boolean" },
      {
        key: "spawn-protection",
        label: "Spawn Protection Radius",
        type: "number",
        hint: "0 = disabled",
      },
      { key: "allow-flight", label: "Allow Flight", type: "boolean" },
      {
        key: "enable-command-block",
        label: "Enable Command Blocks",
        type: "boolean",
      },
      {
        key: "function-permission-level",
        label: "Function Permission Level",
        type: "number",
      },
    ],
  },
  {
    title: "Players",
    props: [
      { key: "max-players", label: "Max Players", type: "number" },
      { key: "online-mode", label: "Online Mode (auth)", type: "boolean" },
      { key: "white-list", label: "Whitelist Enabled", type: "boolean" },
      { key: "enforce-whitelist", label: "Enforce Whitelist", type: "boolean" },
      {
        key: "player-idle-timeout",
        label: "Idle Timeout (min)",
        type: "number",
        hint: "0 = never",
      },
      {
        key: "op-permission-level",
        label: "Op Permission Level",
        type: "number",
      },
      {
        key: "enforce-secure-profile",
        label: "Enforce Secure Chat Profile",
        type: "boolean",
      },
      {
        key: "hide-online-players",
        label: "Hide Online Players",
        type: "boolean",
      },
    ],
  },
  {
    title: "Server",
    props: [
      { key: "motd", label: "MOTD", type: "text" },
      {
        key: "server-ip",
        label: "Bind IP",
        type: "text",
        hint: "Empty = all interfaces",
      },
      { key: "view-distance", label: "View Distance (chunks)", type: "number" },
      {
        key: "simulation-distance",
        label: "Simulation Distance (chunks)",
        type: "number",
      },
      {
        key: "entity-broadcast-range-percentage",
        label: "Entity Broadcast Range %",
        type: "number",
      },
      {
        key: "broadcast-console-to-ops",
        label: "Broadcast Console to Ops",
        type: "boolean",
      },
      {
        key: "broadcast-rcon-to-ops",
        label: "Broadcast RCON to Ops",
        type: "boolean",
      },
      {
        key: "enable-status",
        label: "Enable Server Status (ping)",
        type: "boolean",
      },
      { key: "enable-query", label: "Enable GameSpy4 Query", type: "boolean" },
      { key: "query.port", label: "Query Port", type: "number" },
      {
        key: "prevent-proxy-connections",
        label: "Prevent Proxy Connections",
        type: "boolean",
      },
      { key: "log-ips", label: "Log Player IPs", type: "boolean" },
    ],
  },
  {
    title: "Resource Pack",
    props: [
      { key: "resource-pack", label: "Resource Pack URL", type: "text" },
      { key: "resource-pack-id", label: "Resource Pack UUID", type: "text" },
      { key: "resource-pack-sha1", label: "Resource Pack SHA-1", type: "text" },
      {
        key: "resource-pack-prompt",
        label: "Resource Pack Prompt",
        type: "text",
      },
      {
        key: "require-resource-pack",
        label: "Require Resource Pack",
        type: "boolean",
      },
    ],
  },
  {
    title: "Performance",
    props: [
      {
        key: "max-tick-time",
        label: "Max Tick Time (ms)",
        type: "number",
        hint: "-1 = disabled",
      },
      {
        key: "network-compression-threshold",
        label: "Network Compression Threshold",
        type: "number",
      },
      {
        key: "max-chained-neighbor-updates",
        label: "Max Chained Neighbor Updates",
        type: "number",
      },
      { key: "sync-chunk-writes", label: "Sync Chunk Writes", type: "boolean" },
      {
        key: "use-native-transport",
        label: "Use Native Transport (Netty)",
        type: "boolean",
      },
      {
        key: "rate-limit",
        label: "Packet Rate Limit (per player)",
        type: "number",
        hint: "0 = no limit",
      },
      {
        key: "region-file-compression",
        label: "Region File Compression",
        type: "select",
        options: ["deflate", "lz4", "zstd", "none"],
      },
    ],
  },
  {
    title: "Misc",
    props: [
      {
        key: "pause-when-empty-seconds",
        label: "Pause When Empty (seconds)",
        type: "number",
      },
      {
        key: "accept-transfers",
        label: "Accept Server Transfers",
        type: "boolean",
      },
      {
        key: "initial-enabled-packs",
        label: "Initial Enabled Data Packs",
        type: "text",
      },
      {
        key: "initial-disabled-packs",
        label: "Initial Disabled Data Packs",
        type: "text",
      },
      {
        key: "text-filtering-config",
        label: "Text Filtering Config",
        type: "text",
      },
      {
        key: "text-filtering-version",
        label: "Text Filtering Version",
        type: "number",
      },
    ],
  },
]

// ── Bedrock Edition server.properties defaults ────────────────────────────────
// Key list and allowed values sourced from itzg/docker-minecraft-bedrock-server's
// property-definitions.json (matches the backend's validated Bedrock property
// list exactly, minus server-port/server-portv6 which CSCM manages itself).
// Default values verified against a live itzg/minecraft-bedrock-server
// container's shipped server.properties where available; a handful of keys
// that container's version has since dropped (superseded by newer ones) use
// their long-documented historical defaults instead.

export const BEDROCK_DEFAULTS: Record<string, string> = {
  "server-name": "Dedicated Server",
  gamemode: "survival",
  "force-gamemode": "false",
  difficulty: "easy",
  "allow-cheats": "false",
  "max-players": "10",
  "online-mode": "true",
  "white-list": "false",
  "allow-list": "false",
  "enable-lan-visibility": "true",
  "view-distance": "32",
  "tick-distance": "4",
  "player-idle-timeout": "30",
  "max-threads": "8",
  "level-name": "Bedrock level",
  "level-seed": "",
  "level-type": "DEFAULT",
  "default-player-permission-level": "member",
  "texturepack-required": "false",
  "content-log-file-enabled": "false",
  "content-log-level": "info",
  "content-log-console-output-enabled": "false",
  "compression-threshold": "1",
  "compression-algorithm": "zlib",
  "server-authoritative-movement": "server-auth",
  "player-position-acceptance-threshold": "0.5",
  "player-movement-score-threshold": "20",
  "player-movement-action-direction-threshold": "0.85",
  "player-movement-distance-threshold": "0.3",
  "player-movement-duration-threshold-in-ms": "500",
  "correct-player-movement": "false",
  "server-authoritative-block-breaking": "false",
  "server-authoritative-block-breaking-pick-range-scalar": "1.5",
  "chat-restriction": "None",
  "disable-player-interaction": "false",
  "client-side-chunk-generation-enabled": "true",
  "block-network-ids-are-hashes": "true",
  "disable-persona": "false",
  "disable-custom-skins": "false",
  "server-build-radius-ratio": "Disabled",
  "allow-outbound-script-debugging": "false",
  "allow-inbound-script-debugging": "false",
  "force-inbound-debug-port": "19144",
  "script-debugger-auto-attach": "disabled",
  "script-debugger-auto-attach-connect-address": "localhost:19144",
  "script-watchdog-enable": "true",
  "script-watchdog-enable-exception-handling": "true",
  "script-watchdog-enable-shutdown": "true",
  "script-watchdog-hang-exception": "true",
  "script-watchdog-hang-threshold": "10000",
  "script-watchdog-spike-threshold": "100",
  "script-watchdog-slow-threshold": "10",
  "script-watchdog-memory-warning": "100",
  "script-watchdog-memory-limit": "250",
  "op-permission-level": "4",
  "emit-server-telemetry": "true",
  "msa-gamertags-only": "false",
  "item-transaction-logging-enabled": "false",
}

export const BEDROCK_CATEGORIES: PropCategory[] = [
  {
    title: "Gameplay",
    props: [
      { key: "server-name", label: "Server Name", type: "text" },
      { key: "allow-cheats", label: "Allow Cheats", type: "boolean" },
      { key: "allow-list", label: "Allow List Enabled", type: "boolean" },
      {
        key: "enable-lan-visibility",
        label: "Visible on LAN",
        type: "boolean",
      },
      {
        key: "default-player-permission-level",
        label: "Default Permission Level",
        type: "select",
        options: ["visitor", "member", "operator"],
      },
      {
        key: "texturepack-required",
        label: "Require Texture Pack",
        type: "boolean",
      },
      { key: "tick-distance", label: "Tick Distance (chunks)", type: "number" },
      {
        key: "max-threads",
        label: "Max Threads",
        type: "number",
        hint: "0 = unlimited",
      },
    ],
  },
  {
    title: "Anti-Cheat & Movement",
    props: [
      {
        key: "server-authoritative-movement",
        label: "Server-Authoritative Movement",
        type: "select",
        options: ["server-auth", "client-auth", "server-auth-with-rewind"],
      },
      {
        key: "correct-player-movement",
        label: "Correct Player Movement",
        type: "boolean",
      },
      {
        key: "server-authoritative-block-breaking",
        label: "Server-Authoritative Block Breaking",
        type: "boolean",
      },
      {
        key: "server-authoritative-block-breaking-pick-range-scalar",
        label: "Block Breaking Pick Range Scalar",
        type: "text",
      },
      {
        key: "player-position-acceptance-threshold",
        label: "Position Acceptance Threshold",
        type: "text",
      },
      {
        key: "player-movement-score-threshold",
        label: "Movement Score Threshold",
        type: "number",
      },
      {
        key: "player-movement-action-direction-threshold",
        label: "Movement Action Direction Threshold",
        type: "text",
      },
      {
        key: "player-movement-distance-threshold",
        label: "Movement Distance Threshold",
        type: "text",
      },
      {
        key: "player-movement-duration-threshold-in-ms",
        label: "Movement Duration Threshold (ms)",
        type: "number",
      },
      {
        key: "disable-player-interaction",
        label: "Disable Player Interaction",
        type: "boolean",
      },
      {
        key: "client-side-chunk-generation-enabled",
        label: "Client-Side Chunk Generation",
        type: "boolean",
      },
      {
        key: "server-build-radius-ratio",
        label: "Server Build Radius Ratio",
        type: "text",
        hint: '"Disabled" or 0.0–1.0',
      },
    ],
  },
  {
    title: "Chat & Social",
    props: [
      {
        key: "chat-restriction",
        label: "Chat Restriction",
        type: "select",
        options: ["None", "Dropped", "Disabled"],
      },
      { key: "disable-persona", label: "Disable Persona", type: "boolean" },
      {
        key: "disable-custom-skins",
        label: "Disable Custom Skins",
        type: "boolean",
      },
      {
        key: "msa-gamertags-only",
        label: "MSA Gamertags Only",
        type: "boolean",
      },
      {
        key: "block-network-ids-are-hashes",
        label: "Block Network IDs Are Hashes",
        type: "boolean",
      },
    ],
  },
  {
    title: "Networking",
    props: [
      {
        key: "compression-threshold",
        label: "Compression Threshold",
        type: "number",
      },
      {
        key: "compression-algorithm",
        label: "Compression Algorithm",
        type: "select",
        options: ["zlib", "snappy"],
      },
    ],
  },
  {
    title: "Logging & Telemetry",
    props: [
      {
        key: "content-log-file-enabled",
        label: "Content Log to File",
        type: "boolean",
      },
      {
        key: "content-log-level",
        label: "Content Log Level",
        type: "select",
        options: ["verbose", "info", "warning", "error"],
      },
      {
        key: "content-log-console-output-enabled",
        label: "Content Log to Console",
        type: "boolean",
      },
      {
        key: "emit-server-telemetry",
        label: "Emit Server Telemetry",
        type: "boolean",
      },
      {
        key: "item-transaction-logging-enabled",
        label: "Item Transaction Logging",
        type: "boolean",
      },
    ],
  },
  {
    title: "Script Debugging",
    props: [
      {
        key: "allow-outbound-script-debugging",
        label: "Allow Outbound Script Debugging",
        type: "boolean",
      },
      {
        key: "allow-inbound-script-debugging",
        label: "Allow Inbound Script Debugging",
        type: "boolean",
      },
      {
        key: "script-debugger-auto-attach",
        label: "Script Debugger Auto-Attach",
        type: "select",
        options: ["disabled", "connect", "listen"],
      },
      {
        key: "script-debugger-auto-attach-connect-address",
        label: "Debugger Connect Address",
        type: "text",
      },
      {
        key: "force-inbound-debug-port",
        label: "Inbound Debug Port",
        type: "number",
      },
    ],
  },
  {
    title: "Script Watchdog",
    props: [
      {
        key: "script-watchdog-enable",
        label: "Enable Watchdog",
        type: "boolean",
      },
      {
        key: "script-watchdog-enable-exception-handling",
        label: "Watchdog Exception Handling",
        type: "boolean",
      },
      {
        key: "script-watchdog-enable-shutdown",
        label: "Watchdog Shutdown on Hang",
        type: "boolean",
      },
      {
        key: "script-watchdog-hang-exception",
        label: "Watchdog Hang Exception",
        type: "boolean",
      },
      {
        key: "script-watchdog-hang-threshold",
        label: "Hang Threshold (ms)",
        type: "number",
      },
      {
        key: "script-watchdog-spike-threshold",
        label: "Spike Threshold (ms)",
        type: "number",
      },
      {
        key: "script-watchdog-slow-threshold",
        label: "Slow Threshold (ms)",
        type: "number",
      },
      {
        key: "script-watchdog-memory-warning",
        label: "Memory Warning (MB)",
        type: "number",
      },
      {
        key: "script-watchdog-memory-limit",
        label: "Memory Limit (MB)",
        type: "number",
      },
    ],
  },
]

// ── Properties common to both editions ────────────────────────────────────────
// Same key name in both Java's and Bedrock's server.properties. A few (notably
// level-type, level-name, max-players, view-distance, player-idle-timeout)
// have different factory defaults or value formats per edition — the hint
// text calls that out since this is one shared value applied to whichever
// edition a new server ends up being.

export const SHARED_DEFAULTS: Record<string, string> = {
  gamemode: "survival",
  "force-gamemode": "false",
  difficulty: "easy",
  "online-mode": "true",
  "white-list": "false",
  "level-type": "minecraft\\:normal",
  "level-name": "world",
  "level-seed": "",
  "max-players": "20",
  "view-distance": "10",
  "player-idle-timeout": "0",
  "op-permission-level": "4",
}

export const SHARED_KEYS = new Set(Object.keys(SHARED_DEFAULTS))

export const SHARED_CATEGORIES: PropCategory[] = [
  {
    title: "Core Settings",
    props: [
      {
        key: "gamemode",
        label: "Default Game Mode",
        type: "select",
        options: ["survival", "creative", "adventure"],
        hint: "Java also allows spectator",
      },
      { key: "force-gamemode", label: "Force Gamemode", type: "boolean" },
      {
        key: "difficulty",
        label: "Difficulty",
        type: "select",
        options: ["peaceful", "easy", "normal", "hard"],
      },
      { key: "online-mode", label: "Online Mode (auth)", type: "boolean" },
      { key: "white-list", label: "Whitelist Enabled", type: "boolean" },
      {
        key: "level-type",
        label: "Level Type",
        type: "text",
        hint: 'Java: e.g. "minecraft\\:normal" · Bedrock: "DEFAULT"/"FLAT"/"LEGACY"',
      },
      {
        key: "level-name",
        label: "Level Name",
        type: "text",
        hint: 'Java default "world" · Bedrock default "Bedrock level"',
      },
      {
        key: "level-seed",
        label: "Level Seed",
        type: "text",
        hint: "Leave empty for random",
      },
      {
        key: "max-players",
        label: "Max Players",
        type: "number",
        hint: "Java default 20 · Bedrock default 10",
      },
      {
        key: "view-distance",
        label: "View Distance (chunks)",
        type: "number",
        hint: "Java default 10 · Bedrock default 32",
      },
      {
        key: "player-idle-timeout",
        label: "Idle Timeout (min)",
        type: "number",
        hint: "0 = never · Java default 0 · Bedrock default 30",
      },
      {
        key: "op-permission-level",
        label: "Op Permission Level",
        type: "number",
      },
    ],
  },
]

// Filter out shared keys from each edition's own category list so nothing
// renders twice, and drop any category left with no props as a result.
function withoutSharedKeys(categories: PropCategory[]): PropCategory[] {
  return categories
    .map((cat) => ({
      ...cat,
      props: cat.props.filter((p) => !SHARED_KEYS.has(p.key)),
    }))
    .filter((cat) => cat.props.length > 0)
}

export const JAVA_ONLY_CATEGORIES = withoutSharedKeys(MC_CATEGORIES)
export const BEDROCK_ONLY_CATEGORIES = withoutSharedKeys(BEDROCK_CATEGORIES)

// Single flat baseline covering every key across both editions — this is
// what's actually loaded/saved via /api/defaults/properties (one shared,
// edition-agnostic bag), just organized into three groups for display.
export const ALL_DEFAULTS: Record<string, string> = {
  ...MC_DEFAULTS,
  ...BEDROCK_DEFAULTS,
  ...SHARED_DEFAULTS,
}

// Every key valid for a given edition (shared + edition-specific) — used to
// filter the "Initial Properties" list shown when creating a server, so a
// Bedrock server doesn't show Java-only defaults (or vice versa).
export const JAVA_PROPERTY_KEYS = new Set(Object.keys(MC_DEFAULTS))
export const BEDROCK_PROPERTY_KEYS = new Set(Object.keys(BEDROCK_DEFAULTS))
