### Changed

- **ADR-0016: Multi-User vor 1.0** — Workspaces, Supabase Auth mit JWT, Row Level Security, Supabase-Auth-Client im Frontend und Realtime für Listen-Projektionen werden vorgezogen (Epic #1610). Das ADR löst ADR-0001 (Single-User für v1.0) und ROADMAP-Regel 4 ab und legt fest: Auth-Default `hybrid`, JWT nur bei vollständigem PostgreSQL-Backend, offene Registrierung mit §37-Härtung, Realtime nur als Invalidierungssignal, SSE bleibt. Noch ohne Codeänderung. (#1611)
