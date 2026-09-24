### Changed

- `useEnvForm` ist nur noch Loader für Sprache und Runtime-Metadaten: die tote Modellwahl-API (`modelOption`, `customModel`, `modelOptions`, `effectiveModel()`) ist entfernt. Die Modellwahl in Step 2 läuft ausschließlich über `AiModelRef` (#903).
