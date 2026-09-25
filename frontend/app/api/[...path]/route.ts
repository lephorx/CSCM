import { type NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.CSCM_API_URL ?? "http://localhost:5000"

async function proxy(req: NextRequest, segments: string[]) {
  const isAuthRoute = segments[0] === "auth"
  // EventSource cannot set an Authorization header, so the console stream
  // authenticates via a `?token=` query param instead.
  const isConsoleStream = segments[segments.length - 1] === "stream"

  const authHeader = req.headers.get("authorization")
  const queryToken = req.nextUrl.searchParams.get("token")
  // The JWT from login is the one and only credential CSCM understands —
  // forward it as-is. The stream endpoint gets it via `?token=` instead of
  // a header, since EventSource can't set custom headers.
  const bearer = authHeader?.startsWith("Bearer ")
    ? authHeader
    : isConsoleStream && queryToken
      ? `Bearer ${queryToken}`
      : null

  // Non-auth routes require the caller to have a JWT (real verification is on the backend)
  if (!isAuthRoute && !bearer) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const path = segments.join("/")
  // Decode %2F back to / so the backend receives path=/ not path=%2F
  const search = req.nextUrl.search.replace(/%2F/gi, "/")
  const url = `${BACKEND}/api/${path}${search}`

  const isFormData = req.headers
    .get("content-type")
    ?.includes("multipart/form-data")

  const headers = new Headers()
  if (bearer) headers.set("Authorization", bearer)

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

  let upstream: Response
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body: body as BodyInit | undefined,
      // @ts-expect-error — Node fetch duplex requirement
      duplex: "half",
    })
  } catch {
    return NextResponse.json(
      { error: "CSCM API is unavailable" },
      { status: 503 }
    )
  }

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
