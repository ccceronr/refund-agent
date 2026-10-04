import { describe, expect, it } from 'vitest'
import { applyStepEvent } from './run'

describe('applyStepEvent', () => {
  it('adds a step when it starts and updates it when it ends (R-16)', () => {
    const started = applyStepEvent([], {
      name: 'screen',
      label: 'Reading the message',
      status: 'running',
    })
    const done = applyStepEvent(started, {
      name: 'screen',
      label: 'Reading the message',
      status: 'done',
      duration_ms: 312,
    })

    expect(started).toEqual([
      {
        name: 'screen',
        label: 'Reading the message',
        status: 'running',
        duration_ms: null,
      },
    ])
    expect(done).toEqual([
      {
        name: 'screen',
        label: 'Reading the message',
        status: 'done',
        duration_ms: 312,
      },
    ])
  })

  it('keeps the order the steps started in', () => {
    const steps = ['load_case', 'screen'].reduce(
      (all, name) =>
        applyStepEvent(all, { name, label: name, status: 'running' }),
      applyStepEvent([], {
        name: 'start',
        label: 'start',
        status: 'done',
        duration_ms: 1,
      }),
    )
    expect(steps.map((s) => s.name)).toEqual(['start', 'load_case', 'screen'])
  })
})
