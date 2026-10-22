# Changelog

## [0.1.0] - 2026-10-21

### Added
- `IbgeNomes` client for the four endpoints of IBGE's names API: `basic` (v1 basica), `by_decade` (v2, several names per call, by sex and locality), `by_state` (v2 groupBy=UF) and `ranking` (v2).
- Retries, wait between calls, batch split when the server refuses a batch, optional disk cache of the raw answers.
- `summarize` turns three `by_decade` answers into flat columns (female, male, share_female, peak decade, people born per decade).
- Command line `ibge-nomes` with `basica`, `decadas`, `estados`, `ranking`, `enrich` (resumable CSV enrichment) and `probe`.
