import { ref, type Ref } from "vue";
import { GraphDiffSchema, type GraphDiff } from "../contracts/graphDiffContract";

export function useGraphDiff() {
  const diff: Ref<GraphDiff | null> = ref(null);
  const loading = ref(false);
  const error: Ref<string | null> = ref(null);

  async function fetchDiff(
    graphId: string,
    snapshotA: string,
    snapshotB: string
  ): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const url = `/api/graph/${encodeURIComponent(graphId)}/diff?snapshot_a=${encodeURIComponent(snapshotA)}&snapshot_b=${encodeURIComponent(snapshotB)}`;
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 404) {
          error.value =
            (body?.error?.message as string | undefined) ??
            "Snapshot nicht gefunden";
        } else if (res.status === 422) {
          error.value =
            (body?.error?.message as string | undefined) ??
            "Snapshot unvollständig";
        } else {
          error.value =
            (body?.error?.message as string | undefined) ??
            `Fehler ${res.status}`;
        }
        diff.value = null;
        return;
      }
      const json = (await res.json()) as unknown;
      // tolerantes Envelope-Unwrap; Layer-0-Boundary via strict .parse()
      const payload =
        (json as Record<string, unknown>)?.data !== undefined
          ? ((json as Record<string, unknown>).data as Record<string, unknown>)
              ?.diff
          : (json as Record<string, unknown>)?.diff !== undefined
            ? (json as Record<string, unknown>).diff
            : json;
      diff.value = GraphDiffSchema.parse(payload);
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      diff.value = null;
    } finally {
      loading.value = false;
    }
  }

  function reset(): void {
    diff.value = null;
    error.value = null;
    loading.value = false;
  }

  return { diff, loading, error, fetchDiff, reset };
}
