"""Supabase-Mirror-Paket: App-Metadaten-Index im self-hosted Supabase.

Phase 0/1 des Plans (docs/plans/supabase.md): optionaler, best-effort
Spiegel der Run-/Report-/Dokument-Metadaten nach Postgres (schema
``agora``). Kein Graph-, Embedding- oder Business-Logik-Ersatz.
"""
from .client import SupabaseMirrorError, SupabaseRestClient
from .mirror import SupabaseMirror, get_supabase_mirror

__all__ = [
    "SupabaseMirror",
    "SupabaseMirrorError",
    "SupabaseRestClient",
    "get_supabase_mirror",
]
