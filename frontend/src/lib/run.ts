// Live run steps from the SSE stream (design §4.4, R-16).

export interface StepEvent {
  name: string
  label: string
  status: 'running' | 'done' | 'failed'
  duration_ms?: number
}

export interface StepProgress {
  name: string
  label: string
  status: StepEvent['status']
  duration_ms: number | null
}

export function applyStepEvent(
  steps: StepProgress[],
  event: StepEvent,
): StepProgress[] {
  const step: StepProgress = {
    name: event.name,
    label: event.label,
    status: event.status,
    duration_ms: event.duration_ms ?? null,
  }
  const index = steps.findIndex((existing) => existing.name === event.name)
  if (index === -1) return [...steps, step]
  return steps.map((existing, i) => (i === index ? step : existing))
}
