# Security

- Das Ausnahmeregister erfasst Code- und Container-Risiken mit Evidence, Owner, Frist und dokumentierter Maintainerfreigabe. Echte Critical-Container-Befunde können nicht akzeptiert werden.
- Der CVE Monitor scannt sämtliche versionierten Supabase-Images mit gepinntem Trivy, bewahrt rohe Scanreports auf und prüft die Findings gegen den kanonischen Register-Gate, einschließlich ungefixter Advisories.
