import { NextResponse } from "next/server"

export async function GET() {
  try {
    const backend = process.env.CSCM_API_URL ?? "http://localhost:5000"
    const response = await fetch(`${backend}/health`, { cache: "no-store" })
    if (!response.ok) throw new Error("API health check failed")
    return NextResponse.json({ status: "ok" })
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 })
  }
}
