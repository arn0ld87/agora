/**
 * Frontend OpenTelemetry Web-Tracer (Slice 1e).
 *
 * Gated via VITE_OTEL_ENABLED=true. Without that flag this module is a
 * no-op — no dependencies are initialised and no network connections are made.
 *
 * Exports:
 *  initFrontendTracing()  — call once before createApp (idempotent).
 *  getTracer(name?)       — returns the active OTel Tracer.
 *  traceIdToSigNozUrl()   — builds a SigNoz deep-link from a hex trace_id.
 */
import { context, trace } from '@opentelemetry/api'
import { ZoneContextManager } from '@opentelemetry/context-zone'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { Resource } from '@opentelemetry/resources'
import { BatchSpanProcessor, WebTracerProvider } from '@opentelemetry/sdk-trace-web'
import { SEMRESATTRS_SERVICE_NAME } from '@opentelemetry/semantic-conventions'

let initialized = false

export function initFrontendTracing(): void {
  if (initialized) return
  if (import.meta.env.VITE_OTEL_ENABLED !== 'true') return

  const provider = new WebTracerProvider({
    resource: new Resource({
      [SEMRESATTRS_SERVICE_NAME]: 'agora-frontend',
    }),
    spanProcessors: [
      new BatchSpanProcessor(
        new OTLPTraceExporter({
          url:
            (import.meta.env.VITE_OTEL_ENDPOINT as string | undefined) ??
            'http://localhost:4318/v1/traces',
        }),
      ),
    ],
  })

  provider.register({ contextManager: new ZoneContextManager() })
  registerInstrumentations({ instrumentations: [new FetchInstrumentation()] })

  initialized = true
}

export function getTracer(name = 'agora-frontend') {
  return trace.getTracer(name)
}

export function traceIdToSigNozUrl(traceId: string): string {
  const base =
    (import.meta.env.VITE_SIGNOZ_UI as string | undefined) ?? 'http://localhost:3301'
  return `${base}/trace/${traceId}`
}

/** Re-export OTel context + trace for use by composables without double-import. */
export { context, trace }
