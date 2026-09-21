import { describe, expect, it } from 'vitest'

import {
  capabilitySnapshot,
  candidateCapabilities,
  confirmedStableCapabilities,
} from './agentCapabilityProfile'

describe('public capability profile', () => {
  it('publishes a generic capability boundary without internal evaluation metrics', () => {
    expect(capabilitySnapshot.version).toBe('PUBLIC-1')
    expect(capabilitySnapshot.status).toBe('功能演示')
    expect(capabilitySnapshot.note).not.toMatch(/V1\.|\d+\/\d+/)
    expect(confirmedStableCapabilities).toHaveLength(2)
    expect(candidateCapabilities).toHaveLength(2)
  })
})
