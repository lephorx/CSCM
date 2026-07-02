import { type NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000"
const BEARER_TOKEN = process.env.BEARER_TOKEN ?? ""

async function proxy(req: NextRequest, segments: string[]) {
  const isAuthRoute = segments[0] === "auth"

  // Non-auth routes require the user to have a JWT (real verification is on the backend)
  if (!isAuthRoute) {
    const authHeader = req.headers.get("authorization")
    if (!authHeader?.startsWith("Bearer ")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    }
  }

  const path = segments.join("/")
  // Decode %2F back to / so the backend receives path=/ not path=%2F
  const search = req.nextUrl.search.replace(/%2F/gi, "/")
  const url = `${BACKEND}/api/${path}${search}`

  const isFormData = req.headers
    .get("content-type")
    ?.includes("multipart/form-data")

  const headers = new Headers()

  // Auth routes forward the user's JWT so the backend can verify it.
  // All other routes use the static API key so the backend accepts them.
  if (isAuthRoute) {
    const authHeader = req.headers.get("authorization")
    if (authHeader) headers.set("Authorization", authHeader)
  } else {
    headers.set("Authorization", `Bearer ${BEARER_TOKEN}`)
  }

  if (!isFormData) {
    const ct = req.headers.get("content-type")
    if (ct) headers.set("content-type", ct)
  }

  const body =
    req.method === "GET" || req.method === "HEAD"
      ? undefined
      : isFormData
        ? await req.formData()
        : await req.arrayBuffer()

  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: body as BodyInit | undefined,
    // @ts-expect-error — Node fetch duplex requirement
    duplex: "half",
  })

  const resHeaders = new Headers()
  const ct = upstream.headers.get("content-type")
  if (ct) resHeaders.set("content-type", ct)
  const cd = upstream.headers.get("content-disposition")
  if (cd) resHeaders.set("content-disposition", cd)

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  })
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(req, path)
}
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(req, path)
}
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(req, path)
}
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(req, path)
}
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(req, path)
}
