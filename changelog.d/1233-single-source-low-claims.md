### Fixed (Ein stützender Beleg bleibt als Low-Claim sichtbar — 2026-08-11)

- **Der generische Zweier-Floor entfernte gültige ADR-0002-Claims:** Die Bindungsphase fand nach #1217 passende Belege, routete atomisierte Aussagen mit genau einer stützenden Quelle danach aber weiterhin zur Hypothese. Das Gate verlangt jetzt mindestens einen stützenden Beleg; eine einzelne Quelle wird auf `low` begrenzt, während Aussagen ohne stützende Evidence unverändert Hypothese und Data-Gap werden. Der Replay des betroffenen DeepSeek-Artefakts hebt damit drei belegte Claims von 0 auf 3. (#1233)
