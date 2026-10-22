# Changelog

## [0.1.1] - 2026-10-21

### Fixed
- An answer with status 200 that is not JSON (an HTML error page) is retried, never cached, and a batch that keeps failing is split into single names; names that still fail are listed in `skipped` and printed.
- A bad answer cached by 0.1.0 is discarded and asked again.

### Documented
- `ranking(decade=1990)` returns people born in [1980, 1990[: the API's decade is the year it ends.
- Decades without a published count are missing from `by_decade` (zero or too few people).

## [0.1.0] - 2026-10-21

### Added
- `IbgeNomes` client for the four endpoints of IBGE's names API: `basic` (v1 basica), `by_decade` (v2, several names per call, by sex and locality), `by_state` (v2 groupBy=UF) and `ranking` (v2).
- Retries, wait between calls, batch split when the server refuses a batch, optional disk cache of the raw answers.
- `summarize` turns three `by_decade` answers into flat columns (female, male, share_female, peak decade, people born per decade).
- Command line `ibge-nomes` with `basica`, `decadas`, `estados`, `ranking`, `enrich` (resumable CSV enrichment) and `probe`.
