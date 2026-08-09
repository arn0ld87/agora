"""
Evidence-Quality-Gate.

Lädt Reports/Evidence-Maps aus Fixtures, validiert gegen Pydantic-Contract,
berechnet Quality-Metriken und failt unter Schwelle.

Aufruf:
    cd backend && uv run python scripts/check_evidence_quality.py \
        --fixtures tests/eval/fixtures \
        --min-evidence-coverage 0.85 \
        --min-claim-support-ratio 0.75 \
        --orphan-claim-rate 0.10 \
        --require-schema-version 3

Verwendete Metriken (aus ChatGPT-Audit):
- evidence_coverage:    Claims mit evidence != [] / alle Claims              >= 0.90
- claim_support_ratio:  Claims mit >= 1 EvidenceItem mit supports_claim=True
                        und match_score >= 0.55 / alle Claims                >= 0.75
- orphan_claim_rate:    Claims ohne direkte Evidence                         <= 0.10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Pfad-Setup, damit das Script standalone läuft
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from app.contracts.report_contract import EvidenceMapModel  # noqa: E402
from app.services.evidence_migrations import normalize_persisted_evidence_map  # noqa: E402


def evaluate(evidence_map: EvidenceMapModel) -> dict[str, float]:
    sections = evidence_map.sections
    all_claims = [c for s in sections for c in s.claims]
    if not all_claims:
        return {
            "evidence_coverage": 0.0,
            "claim_support_ratio": 0.0,
            "orphan_claim_rate": 1.0,
            "dedup_rate": 0.0,
            "concentration_index": 0.0,
            "total_claims": 0.0,
        }
    n = len(all_claims)
    with_any_evidence = sum(1 for c in all_claims if c.evidence)
    with_real_support = sum(
        1 for c in all_claims
        if any((e.supports_claim is True) and ((e.match_score or 0.0) >= 0.55) for e in c.evidence)
    )
    orphans = n - with_any_evidence

    # dedup_rate: Anteil der Sections, die einen section_dedup-Marker im
    # audit_trail eines ihrer claims tragen (Sub-Slice 13).
    dedup_count = 0
    total_sections = len(sections)
    for section in sections:
        has_dedup = False
        for claim in section.claims:
            for entry in claim.audit_trail:
                if entry.get("source") == "section_dedup":
                    has_dedup = True
                    break
            if has_dedup:
                break
        if has_dedup:
            dedup_count += 1
    dedup_rate = (dedup_count / total_sections) if total_sections else 0.0

    # concentration_index: max(count_pro_source) / total_evidence im
    # globalen Evidence-Pool (kleiner Pool oder Single-Source -> hoher Index).
    sources_count: dict[str, int] = {}
    for evidence_id in evidence_map.global_evidence_refs:
        item = evidence_map.evidence_index[evidence_id]
        src = str(item.source)
        sources_count[src] = sources_count.get(src, 0) + 1
    total_global = sum(sources_count.values())
    concentration_index = (max(sources_count.values()) / total_global) if total_global else 0.0

    return {
        "evidence_coverage": with_any_evidence / n,
        "claim_support_ratio": with_real_support / n,
        "orphan_claim_rate": orphans / n,
        "dedup_rate": dedup_rate,
        "concentration_index": concentration_index,
        "total_claims": float(n),
    }


def load_one(path: Path, require_schema_version: int) -> EvidenceMapModel | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Akzeptiere sowohl ReportContract als auch nackte EvidenceMap als Fixture
    evidence_raw = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else raw
    if evidence_raw.get("schema_version") != require_schema_version:
        print(
            f"Fixture {path.name}: schema_version={evidence_raw.get('schema_version')} "
            f"!= required {require_schema_version}",
            file=sys.stderr,
        )
        return None
    try:
        normalized = normalize_persisted_evidence_map(evidence_raw)
        ev = EvidenceMapModel.model_validate(normalized)
    except ValidationError as e:
        print(f"  \u2717 {path.name}: {e}", file=sys.stderr)
        return None
    if ev is None:
        print(f"  \u2717 {path.name}: keine Evidence-Map enthalten", file=sys.stderr)
        return None
    if ev.schema_version != require_schema_version:
        print(
            f"  \u2717 {path.name}: schema_version={ev.schema_version} "
            f"!= required {require_schema_version}",
            file=sys.stderr,
        )
        return None
    return ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--min-evidence-coverage", type=float, default=0.85)
    ap.add_argument("--min-claim-support-ratio", type=float, default=0.75)
    ap.add_argument("--orphan-claim-rate", type=float, default=0.10)
    ap.add_argument("--require-schema-version", type=int, default=3)
    ap.add_argument(
        "--soft",
        action="store_true",
        help="Bricht nicht hart ab, schreibt nur Warnungen (für Layer-1-Bootstrap-Phase).",
    )
    args = ap.parse_args()

    if not args.fixtures.exists():
        print(f"::warning::Fixtures-Verzeichnis fehlt: {args.fixtures}")
        return 0  # Bootstrap: noch keine Fixtures, kein Gate

    fixtures = sorted(args.fixtures.glob("*.json"))
    if not fixtures:
        print("::warning::Keine .json-Fixtures gefunden")
        return 0

    failures: list[str] = []
    aggregates = []
    for f in fixtures:
        ev = load_one(f, args.require_schema_version)
        if ev is None:
            failures.append(f.name)
            continue
        m = evaluate(ev)
        aggregates.append(m)
        print(f"  {f.name}: coverage={m['evidence_coverage']:.2f} "
              f"support={m['claim_support_ratio']:.2f} "
              f"orphan={m['orphan_claim_rate']:.2f} "
              f"dedup={m['dedup_rate']:.2f} "
              f"concentration={m['concentration_index']:.2f} "
              f"(n={int(m['total_claims'])})")

    if failures and not args.soft:
        print(f"::error::{len(failures)} Fixtures failed Validation: {failures}", file=sys.stderr)
        return 1

    if not aggregates:
        return 0 if args.soft else 1

    avg_cov = sum(m["evidence_coverage"] for m in aggregates) / len(aggregates)
    avg_sup = sum(m["claim_support_ratio"] for m in aggregates) / len(aggregates)
    avg_orph = sum(m["orphan_claim_rate"] for m in aggregates) / len(aggregates)

    print(f"\nDurchschnitt: coverage={avg_cov:.3f} support={avg_sup:.3f} orphan={avg_orph:.3f}")

    issues = []
    if avg_cov < args.min_evidence_coverage:
        issues.append(f"evidence_coverage {avg_cov:.3f} < {args.min_evidence_coverage}")
    if avg_sup < args.min_claim_support_ratio:
        issues.append(f"claim_support_ratio {avg_sup:.3f} < {args.min_claim_support_ratio}")
    if avg_orph > args.orphan_claim_rate:
        issues.append(f"orphan_claim_rate {avg_orph:.3f} > {args.orphan_claim_rate}")

    if issues:
        msg = "; ".join(issues)
        if args.soft:
            print(f"::warning::Quality-Gate-Soft: {msg}")
            return 0
        print(f"::error::Quality-Gate-Hard: {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
