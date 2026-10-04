// SSE over POST (design §4.4) with @microsoft/fetch-event-source. One attempt: a run is
// never started twice by a silent retry.
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { ApiError, NETWORK_ERROR, readApiError, REQUESTED_WITH } from './client'

const EVENT_STREAM = 'text/event-stream'

export async function postStream(
  path: string,
  onEvent: (name: string, data: unknown) => void,
  signal: AbortSignal,
): Promise<void> {
  await fetchEventSource(`/api${path}`, {
    method: 'POST',
    headers: { Accept: EVENT_STREAM, ...REQUESTED_WITH },
    credentials: 'same-origin',
    signal,
    openWhenHidden: true,
    async onopen(response) {
      const streaming = response.headers
        .get('content-type')
        ?.startsWith(EVENT_STREAM)
      if (response.ok && streaming) return
      throw await readApiError(response)
    },
    onmessage(message) {
      if (message.event) onEvent(message.event, JSON.parse(message.data))
    },
    onerror(error) {
      // Rethrowing stops the library's automatic retries.
      throw error instanceof ApiError
        ? error
        : new ApiError(0, 'network', NETWORK_ERROR)
    },
  })
}
