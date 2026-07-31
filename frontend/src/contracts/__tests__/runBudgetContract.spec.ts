/**
 * Zod-Spiegel-Drift-Test gegen den Backend-Vertrag (Issue #764).
 *
 * Vergleicht die Property-Keys des Zod-Spiegels 1:1 mit den generierten
 * JSON-Schemas. Wenn backend/app/contracts/run_budget_contract.py wandert
 * (Schema-Dump), muss dieser Test brechen, bis der Spiegel nachgezogen ist.
 */
import { describe, it, expect } from 'vitest';
import {
  RunBudgetConfigSchema,
  RunUsageSchema,
  UsageMetricsSchema,
  RunBudgetStatusSchema,
  BudgetWarningSchema,
  PreflightEstimateSchema,
  PreflightModelRefSchema,
} from '../runBudgetContract';
import budgetConfigJson from '../../../../schemas/run-budget-config.schema.json';
import runUsageJson from '../../../../schemas/run-usage.schema.json';
import budgetStatusJson from '../../../../schemas/run-budget-status.schema.json';
import preflightJson from '../../../../schemas/run-preflight-estimate.schema.json';

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort();
}

describe('runBudgetContract — Schema-Drift', () => {
  it('RunBudgetConfig matcht run-budget-config.schema.json', () => {
    expect(shapeKeys(RunBudgetConfigSchema)).toEqual(
      propertyKeys(budgetConfigJson),
    );
  });

  it('RunUsage matcht run-usage.schema.json', () => {
    expect(shapeKeys(RunUsageSchema)).toEqual(propertyKeys(runUsageJson));
  });

  it('UsageMetrics matcht die $defs des Usage-Schemas', () => {
    const defs = (runUsageJson as { $defs?: Record<string, { properties?: Record<string, unknown> }> }).$defs ?? {};
    expect(defs.UsageMetrics).toBeDefined();
    expect(shapeKeys(UsageMetricsSchema)).toEqual(
      propertyKeys(defs.UsageMetrics),
    );
  });

  it('RunBudgetStatus matcht run-budget-status.schema.json', () => {
    expect(shapeKeys(RunBudgetStatusSchema)).toEqual(
      propertyKeys(budgetStatusJson),
    );
  });

  it('BudgetWarning matcht die $defs des Status-Schemas', () => {
    const defs = (budgetStatusJson as { $defs?: Record<string, { properties?: Record<string, unknown> }> }).$defs ?? {};
    expect(defs.BudgetWarning).toBeDefined();
    expect(shapeKeys(BudgetWarningSchema)).toEqual(
      propertyKeys(defs.BudgetWarning),
    );
  });

  it('PreflightEstimate matcht run-preflight-estimate.schema.json', () => {
    expect(shapeKeys(PreflightEstimateSchema)).toEqual(
      propertyKeys(preflightJson),
    );
  });

  it('PreflightModelRef matcht die $defs des Preflight-Schemas', () => {
    const defs = (preflightJson as { $defs?: Record<string, { properties?: Record<string, unknown> }> }).$defs ?? {};
    expect(defs.PreflightModelRef).toBeDefined();
    expect(shapeKeys(PreflightModelRefSchema)).toEqual(
      propertyKeys(defs.PreflightModelRef),
    );
  });
});

describe('runBudgetContract — Verhalten', () => {
  it('parst eine minimale Budget-Config mit Defaults', () => {
    const parsed = RunBudgetConfigSchema.parse({ max_tokens: 5000 });
    expect(parsed.schema_version).toBe(1);
    expect(parsed.enforcement).toBe('soft');
    expect(parsed.currency).toBe('USD');
    expect(parsed.max_tokens).toBe(5000);
  });

  it('lehnt zusätzliche Felder ab (extra=forbid gespiegelt)', () => {
    expect(() =>
      RunBudgetConfigSchema.parse({ max_tokens: 5, api_key: 'sk-x' }),
    ).toThrow();
  });

  it('hält unbekannte Kosten ehrlich nullable statt 0', () => {
    const usage = RunUsageSchema.parse({
      totals: { cost_status: 'unknown', tokens_status: 'unknown' },
    });
    expect(usage.totals.cost_micros ?? null).toBeNull();
    expect(usage.totals.cost_status).toBe('unknown');
    expect(usage.measurement_status).toBe('unknown');
  });

  it('parst eine vollständige PreflightEstimate', () => {
    const estimate = PreflightEstimateSchema.parse({
      is_estimate: true,
      estimated_tokens_low: 1000,
      estimated_tokens_high: 5000,
      estimated_cost_micros_low: 0,
      estimated_cost_micros_high: 0,
      cost_status: 'free',
      models: [
        {
          stage: 'simulation_rounds',
          provider_id: 'ollama',
          model_id: 'llama3.1',
          cost_status: 'free',
        },
      ],
      pricing_version: '2026-07',
      pricing_source: 'static',
      data_quality: 'low',
      warnings: [],
    });
    expect(estimate.models[0]?.cost_status).toBe('free');
    expect(estimate.is_estimate).toBe(true);
  });
});
