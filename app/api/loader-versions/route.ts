import { type NextRequest, NextResponse } from "next/server"

// Server-side fetches so the browser never hits Fabric/Forge directly —
// Forge's maven/promotions hosts don't send CORS headers, so a client fetch
// would be blocked outright.

async function getFabricLoaders() {
  const res = await fetch("https://meta.fabricmc.net/v2/versions/loader", {
    next: { revalidate: 3600 },
  })
  if (!res.ok) throw new Error("Failed to fetch Fabric loader versions")
  const data: { version: string; stable: boolean }[] = await res.json()
  return data.map((d) => ({ id: d.version, stable: d.stable }))
}

async function getForgeVersions(mcVersion: string) {
  const [metaRes, promoRes] = await Promise.all([
    fetch(
      "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
      { next: { revalidate: 3600 } }
    ),
    fetch(
      "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
      { next: { revalidate: 3600 } }
    ),
  ])
  if (!metaRes.ok) throw new Error("Failed to fetch Forge versions")

  const xml = await metaRes.text()
  const prefix = `${mcVersion}-`
  const versions = Array.from(xml.matchAll(/<version>([^<]+)<\/version>/g))
    .map((m) => m[1])
    .filter((v) => v.startsWith(prefix))
    .map((v) => v.slice(prefix.length))
    .reverse()

  let latest: string | null = null
  if (promoRes.ok) {
    const promo: { promos?: Record<string, string> } = await promoRes.json()
    const promos = promo.promos ?? {}
    const lat = promos[`${mcVersion}-latest`]
    // Modern promos are bare build numbers ("47.4.10"); some legacy MC
    // versions prefix the build with the MC version again ("1.7.10-...-1.7.10").
    latest = lat ? (lat.startsWith(prefix) ? lat.slice(prefix.length) : lat) : null
  }

  return { versions, latest }
}

export async function GET(req: NextRequest) {
  const loader = req.nextUrl.searchParams.get("loader")
  const mcVersion = req.nextUrl.searchParams.get("mcVersion") ?? ""

  try {
    if (loader === "fabric") {
      return NextResponse.json(await getFabricLoaders())
    }
    if (loader === "forge") {
      if (!mcVersion) return NextResponse.json({ error: "mcVersion is required" }, { status: 400 })
      return NextResponse.json(await getForgeVersions(mcVersion))
    }
    return NextResponse.json({ error: "Unknown loader" }, { status: 400 })
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch versions" },
      { status: 502 }
    )
  }
}
