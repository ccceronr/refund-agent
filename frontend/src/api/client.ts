// Fetch wrapper for /api (design §4): same-origin cookie session, the anti-CSRF header
// on every change (design §4.0), and plain-language errors (ui.md §3).

export const NETWORK_ERROR =
  "We couldn't reach the server. Check your connection and try again."
const GENERIC_ERROR = 'Something went wrong. Please try again.'
export const REQUESTED_WITH = { 'X-Requested-With': 'refund-app' }

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export function isSignedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const json: Record<string, string> =
    body === undefined ? {} : { 'Content-Type': 'application/json' }
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { ...REQUESTED_WITH, ...json, ...headers },
  })
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      credentials: 'same-origin',
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError(0, 'network', NETWORK_ERROR)
  }
  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw toApiError(response.status, body)
  // The backend validates every response with Pydantic models (design §4).
  return body as T
}

export async function readApiError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null)
  return toApiError(response.status, body)
}

function toApiError(status: number, body: unknown): ApiError {
  const error =
    typeof body === 'object' && body !== null && 'error' in body
      ? (body as { error: { code?: string; message?: string } }).error
      : {}
  return new ApiError(
    status,
    error.code ?? 'error',
    error.message ?? GENERIC_ERROR,
  )
}
