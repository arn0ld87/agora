import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTracer, initFrontendTracing, traceIdToSigNozUrl } from '@/observability/tracing'

describe('frontend tracing', () => {
  beforeEach(() => {
    // Reset the module-level `initialized` flag between tests by re-importing
    // via cache-bust is complex in Vitest — instead we rely on the gate:
    // VITE_OTEL_ENABLED=false keeps initFrontendTracing a no-op so repeated
    // calls are safe to test idempotency without actual provider init.
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('traceIdToSigNozUrl baut korrekten Deep-Link', () => {
    const url = traceIdToSigNozUrl('abc123deadbeef0000000000000000ff')
    expect(url).toMatch(/\/trace\/abc123deadbeef0000000000000000ff$/)
  })

  it('traceIdToSigNozUrl respektiert VITE_SIGNOZ_UI Override', () => {
    vi.stubEnv('VITE_SIGNOZ_UI', 'http://signoz.example.com:3301')
    const url = traceIdToSigNozUrl('abc')
    expect(url).toBe('http://signoz.example.com:3301/trace/abc')
  })

  it('initFrontendTracing ist idempotent (OTEL disabled)', () => {
    // Default: VITE_OTEL_ENABLED not set → function is a no-op
    expect(() => {
      initFrontendTracing()
      initFrontendTracing()
      initFrontendTracing()
    }).not.toThrow()
  })

  it('getTracer liefert einen Tracer', () => {
    const tracer = getTracer()
    expect(tracer).toBeDefined()
    expect(typeof tracer.startSpan).toBe('function')
  })
})
