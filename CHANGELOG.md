# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-06-21

### Added

- Continuous-integration workflow running the test suite with pytest on every
  push and pull request (`.github/workflows/test.yaml`).
- `requirements_test.txt` declaring the test dependencies, including the
  Home Assistant Bluetooth/USB stack pulled in when importing the integration.
- `pytest.ini` with the test path and asyncio configuration.
- `.gitignore` covering Python, pytest, ruff, virtualenv and editor artifacts.
- `loggers` manifest key (`bleak`, `bleak_retry_connector`) so enabling debug
  logging for the integration also covers its Bluetooth dependencies.
- Hardware guide (FR and EN) on recycling the obsolete Flipr WiFi gateway into
  an ESPHome Bluetooth proxy, linked from the README Hardware Rescue section.
- English version of the calibration guide. The guides now live under `docs/`
  with a uniform `<topic>.<lang>.md` naming, and the calibration guide (which
  was previously unlinked) is referenced from both READMEs.
- `.markdownlint.jsonc` config encoding the repository's Markdown style, and a
  pass fixing the structural lint issues (blank lines around headings, lists
  and tables, trailing spaces, empty and non-descriptive links) so all Markdown
  files lint cleanly.
- Unit tests for the previously untested pure logic: calibration validation
  (`validate_calibration`, `_flatten_sections`), BLE frame parsing
  (`_parse_raw_frame`), pH calibration math (`_compute_ph_calibrated`) and
  model detection (`get_flipr_model`).

### Changed

- Exposed a public `is_shutdown` coordinator property; entities no longer read
  the private attribute.
- Translated the remaining French code comments to English and added the
  offending value to the `get_mv_from_input` error for clearer logs.
- Set `manifest.json` version to `1.2.0` (it had been left at `1.0.0`, never
  bumped for the 1.1.0 release).
- Replaced the linear battery percentage with a Li-SOCl2 (Saft LS26500)
  discharge curve in `battery.py`. The previous linear 2500-3600 mV mapping did
  not fit this chemistry's flat plateau and gave almost no end-of-life warning;
  the new piecewise curve stays near full across the plateau and drops through
  the knee where the voltage is actually informative.
- Internal cleanup with no behaviour change: cleared the extended ruff lints
  (`itertools.pairwise`, `ClassVar`, `raise ... from None`, `contextlib.suppress`),
  hoisted the per-call sensor icon dictionaries to module constants, and lowered
  the chemistry "could not compute" logs from error to debug to cut log noise.
- Refactored `config_flow.py` with no behaviour change: drive every number field
  from a shared bounds table so the config and options flows can no longer drift
  apart (the calibration and threshold sections were fully duplicated), and split
  `validate_calibration` into focused helpers. New tests lock the schema builders.
- Refactored the entity platforms with no behaviour change: a shared
  `resolve_entry_context` helper and `CONF_MODEL` constant remove the repeated
  setup boilerplate, and the dispatcher signal is centralised in
  `options_updated_signal` (one sender, four receivers) with a small entity mixin
  for the subscription wiring.

### Fixed

- Repaired the chemistry test suite, which referenced functions removed during
  an earlier refactor (`compute_active_chlorine`, `compute_flipr_active_chlorine`,
  `compute_flipr_theoretical_orp`) and failed to import. Tests now cover the
  current API (`estimate_free_chlorine`, `compute_active_chlorine_from_fc`,
  `compute_isl`, `compute_ph_equilibrium`, `get_mv_from_input`).
- Dutch and Brazilian Portuguese options dialog: a duplicate `sections` key
  silently dropped the General and Probe-calibration sections at parse time;
  merged into one block so both locales are complete again.
- Options-flow error messages: added the missing pH calibration error keys to
  every locale (they previously appeared as raw, untranslated keys).
- Locale wording: Czech RSSI name order, Polish sentence case, Russian "raw"
  term, Dutch and Danish compound nouns, Chinese stabilizer term.
- Config flow: preserve the calibration already entered when choosing manual
  MAC entry; set a `unique_id` for manual entries to prevent the same device
  being configured twice; attribute a pH parse error to the field that failed.
- BLE coordinator: compare the pending command value (not just its type) so a
  sync-mode change made during a poll is not lost; stop `_do_save` from leaking
  a scheduled save-timer handle and guard the debounce callback on shutdown;
  cancel an armed retry timer when going out of range.
- Entities: apply a new scan interval immediately by rescheduling the poll
  timer; tag a naive `last_received` as UTC instead of local time; keep the
  RSSI sensor available while advertisements arrive during paused measurements.

## [1.1.0] - 2026-05-12

### Added

- Bluetooth discovery matchers for additional Flipr local names
  (`F2B*` and `F30*`–`F3F*`), broadening automatic device detection.

### Changed

- Refactored inline comments and improved code clarity.
- Documentation updates (`README.md`, `README.fr.md`).

## [1.0.0] - 2026-04-19

### Added

- Initial release: local (BLE) integration for Flipr pool analysers, with
  temperature, pH, ORP, estimated free chlorine, active chlorine (HOCl),
  Langelier saturation index, battery and Bluetooth diagnostics.
- Configurable pH/ORP calibration, temperature offset, water parameters
  (TAC, TH, TDS, CyA) and alert thresholds via the options flow.
- Chlorine/bromine model selection, sync-mode control and gateway mode.

[1.2.0]: https://github.com/Adrien40/ha-flipr-local/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Adrien40/ha-flipr-local/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Adrien40/ha-flipr-local/releases/tag/v1.0.0
