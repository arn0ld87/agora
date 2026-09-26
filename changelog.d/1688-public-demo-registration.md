### Added

- Separate public demo deployment with Supabase email confirmation, workspace-scoped encrypted provider keys, and browser login without the Agora master token.

### Security

- JWT runs use only their workspace's provider key across model, embedding, and background-job paths; missing keys and redirected provider endpoints fail closed.
