import { ref, type Ref } from "vue";
import {
  BranchComparisonSchema,
  type BranchComparison,
} from "../contracts/branchComparisonContract";

export function useBranchComparison() {
  const comparison: Ref<BranchComparison | null> = ref(null);
  const loading = ref(false);
  const error: Ref<string | null> = ref(null);

  async function fetchComparison(
    simulationId: string,
    branchA: string,
    branchB: string,
    windowSizeRounds?: number
  ): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const params = new URLSearchParams({
        branch_a: branchA,
        branch_b: branchB,
      });
      if (typeof windowSizeRounds === "number") {
        params.set("window_size_rounds", String(windowSizeRounds));
      }
      const url = `/api/simulation/${encodeURIComponent(simulationId)}/compare?${params.toString()}`;
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as Record<
          string,
          unknown
        >;
        const msg =
          (body?.error as Record<string, unknown>)?.message as
            | string
            | undefined;
        if (res.status === 404) {
          error.value = msg ?? "Branch nicht gefunden";
        } else if (res.status === 422) {
          error.value = msg ?? "Branch-Simulation unvollständig";
        } else if (res.status === 400) {
          error.value = msg ?? "Ungültige Branch-IDs";
        } else {
          error.value = msg ?? `Fehler ${res.status}`;
        }
        comparison.value = null;
        return;
      }
      const json = (await res.json()) as unknown;
      // Tolerantes Envelope-Unwrap; Layer-0-Boundary via strict .parse()
      const payload =
        (json as Record<string, unknown>)?.data !== undefined
          ? (
              (json as Record<string, unknown>).data as Record<string, unknown>
            )?.comparison
          : (json as Record<string, unknown>)?.comparison !== undefined
            ? (json as Record<string, unknown>).comparison
            : json;
      // Strict-Parse — Layer-0-Boundary
      comparison.value = BranchComparisonSchema.parse(payload);
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      comparison.value = null;
    } finally {
      loading.value = false;
    }
  }

  function reset(): void {
    comparison.value = null;
    error.value = null;
    loading.value = false;
  }

  return { comparison, loading, error, fetchComparison, reset };
}
