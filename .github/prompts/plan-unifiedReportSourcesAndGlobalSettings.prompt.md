## Plan: Unified Report Sources and Global Settings

**Implementation status:** Complete. Automated validation passes; the connected-ETABS scenarios
in Phase 6 remain a release-time manual checklist because they require a running ETABS instance.

**Phase commits**

- `19a5e0b` — Add global report preferences
- `3c1ea72` — Add application settings dialog
- `ace9c7e` — Unify report section source controls
- `e96c7fb` — Add report source fallback policy
- `3f4c641` — Apply custom report section titles

**Automated validation**

- Full test suite: `81 passed`
- Focused report suite: `16 passed`
- All changed Python files except two legacy modules pass Ruff. The existing
   `report/docx_report.py` and `gui/main_window.py` modules retain unrelated findings
   outside this feature's changes (63 and 18 respectively).
- `git diff --check` passes for the implementation commits.

Replace the duplicate report controls with one reorderable section table that owns inclusion, source choice, and saved-JSON selection. Persist report names/order/inclusion/ETABS choices globally in the existing application `Settings` backend, while a separate `ModelReportSources` type owns browsed JSON paths for each ETABS model. Add a polished General + Report Settings dialog under Help. Source behavior will be explicit: checked rows read ETABS; unchecked rows use a validated civilTools JSON; missing JSON falls back to ETABS when the global fallback is enabled, otherwise the section is skipped with a visible warning. Existing `app_log` levels and the report progress log remain the user-facing diagnostic channel. Each phase ends in a focused validated commit.

**Phase 1 — Global report preference model (Commit 1: complete)**
1. Extend `G:\civiltools\src\civiltools\config.py` with `settings_schema_version` and a versioned global report-settings schema represented as an ordered list of section records: stable `key`, editable `title_en`, editable `title_fa`, `included`, and `read_from_etabs`; add `report_fallback_to_etabs_if_missing=True`, report workers, TOC, language, and appearance defaults for the General tab.
2. Deep-copy and normalize nested defaults on load so existing `settings.json` files migrate safely and idempotently: run migrations only when `settings_schema_version` is older, preserve known user values, append newly introduced `DEFAULT_SECTION_ORDER` keys, discard no user title/order data, and avoid shared mutable defaults. Add a batch/update API so accepting Settings writes once rather than once per field; do not add a separate boolean migration flag.
3. Keep global preferences in `%APPDATA%/civilTools/civilTools/settings.json`; do not put these fields in ETABS Project Settings or model report config.
4. Define report image-render workers as `1..16`, with the current conservative default `min(4, os.cpu_count() or 4)`. Document that ETABS COM extraction remains serial and workers apply only to process-safe image rendering.
5. Add `G:\civiltools\tests\test_settings.py` for first-run defaults, versioned/idempotent legacy migration, ordered section persistence, bilingual title round-trip, fallback default, and worker bounds.
6. Run focused settings tests and Ruff; commit as `Add global report preferences`.

**Phase 2 — Modern application Settings UI (Commit 2: complete, depends on Phase 1)**
7. Create `G:\civiltools\src\civiltools\gui\dialogs\app_settings_dialog.py` as a polished resizable `QDialog` using existing Qt styling/icons and English-only control labels. Use two tabs:
   - General: light/dark appearance and application language.
   - Report: an editable reorderable table with Include, English title, Persian title, and Read from ETABS columns; global fallback checkbox; workers and TOC defaults; Restore Defaults action.
8. Use stable section keys as hidden item data, validate non-empty English/Persian titles, preserve row order through drag/drop, and save only on Apply/OK. Cancel must leave the stored settings unchanged. Keep the application settings UI English and LTR; automatically set only Persian title editors to RTL. Do not add a global RTL checkbox.
9. Add `Help > Settings...` with the standard `Ctrl+,` shortcut in `G:\civiltools\src\civiltools\gui\main_window.py`, per the user's preferred menu location. Pass the existing `self._settings`; apply appearance changes immediately after acceptance. Leave the existing model-specific Project Settings command untouched.
10. Add GUI tests for loading, editing, reorder persistence, Apply/Cancel behavior, worker bounds, RTL Persian title editors, and menu action presence. Run focused tests and Ruff; commit as `Add application settings dialog`.

**Phase 3 — Unified report section/source table (Commit 3: complete, depends on Phases 1–2)**
11. Refactor `G:\civiltools\src\civiltools\gui\dialogs\report_dialog.py`: remove the entire separate `Refresh Results from ETABS` group and replace the lower `QListWidget` with one reorderable multi-column section view.
12. Table columns will be: Include checkbox, Section name, Read from ETABS checkbox, Source status/filename, and Browse action. Every section row exposes the ETABS checkbox. Source status must explicitly show `ETABS`, `Saved JSON`, `ETABS fallback`, or `Unavailable`; do not imply that every section has a compatible saved-table schema. The displayed section name uses the global English/Persian title appropriate to the selected report language.
13. Place Select All and Clear All above this unified table; they affect only the Include column, never the ETABS-source column. Add one global `Read from ETABS if saved result is missing` checkbox, defaulting to enabled and synchronized with global settings.
14. For unchecked ETABS rows, show the selected JSON basename when configured and valid; Browse accepts JSON only and validates the civilTools schema and expected `section_key`. New civilTools result metadata records `schema_version`, `section_key`, and a normalized model fingerprint derived from the ETABS model path. If model metadata identifies another model, warn and require explicit confirmation; legacy civilTools JSON without provenance metadata remains usable after a warning. Invalid or incompatible schemas are rejected and not saved.
15. Add a dedicated model-local `ModelReportSources` dataclass/repository in `G:\civiltools\src\civiltools\report\report_config.py`. It exclusively reads and writes `<model_stem>_report_sources.json`, containing `schema_version` and `section_json_paths`; `ReportConfig` consumes a resolved snapshot but does not own persistence. Stop writing global section names/order/include/ETABS choices to `<model_stem>_report_config.json`.
16. Handle legacy model report config through a versioned, idempotent migration: import compatible JSON paths only when the model-source schema is older, write the new schema version after successful migration, and never repeat or overwrite newer user choices.
17. Pass the existing application `Settings` from `MainWindow._generate_report()` into `ReportDialog`. On Generate, persist current names/order/include/ETABS/fallback/options globally and ask `ModelReportSources` to persist only JSON paths for the current model.
18. Rewrite `G:\civiltools\tests\test_report_dialog.py` around the unified table: upper group absent, all sections present once, Select/Clear controls inclusion only, source checks remain unchanged, fallback is global, source status and JSON basename appear, cross-model/legacy Browse behavior is explicit, and model paths do not leak into global settings. Run focused GUI/config tests and Ruff; commit as `Unify report section source controls`.

**Phase 4 — Source policy and missing-result fallback (Commit 4: complete, depends on Phase 3)**
19. Extend `ReportConfig` with runtime-only/generated fields for `section_sources`, `section_json_paths`, `fallback_to_etabs_if_missing`, and custom section titles. These are assembled from global preferences plus a `ModelReportSources` snapshot for the current generation, not treated as model-owned preferences.
20. Update `G:\civiltools\src\civiltools\report\refresh.py` so included rows checked for ETABS refresh command-backed checks (`drift`, `torsion`, `pmm_columns`, `joint_shear`, `columns_100_30`) before extraction. Rows not included are never refreshed.
21. Update `G:\civiltools\src\civiltools\report\data_extractor.py` and `report_generator.py` to resolve each included section through one explicit policy:
   - ETABS checked: read/compute live and update its normal civilTools cache where supported.
   - ETABS unchecked + valid configured JSON: load that exact file instead of auto-selecting another file.
   - ETABS unchecked + no valid JSON + fallback enabled: read/compute live and report that fallback in progress output.
   - ETABS unchecked + no valid JSON + fallback disabled: mark the section skipped, remove it from effective active sections, and log a warning; generation continues.
22. In this first implementation, saved-file loading is restricted to existing civilTools JSON schemas. Result-backed sections use current colored table JSON loaders. Sections without a compatible civilTools JSON schema can still be checked for live ETABS; if unchecked they follow fallback-or-skip. Do not pretend arbitrary JSON can populate formulas, plans, or structured sections.
23. Before each live source operation, verify that the ETABS connection is available. If ETABS closes or disconnects, do not retry COM operations automatically: use a valid configured/cached JSON when available, otherwise skip the affected section and emit a clear `WARNING` in `app_log` and the report generation log. Continue generating unaffected sections.
24. Ensure refresh failures preserve a usable configured/cached file when available and emit section key, selected source, fallback decision, and outcome through existing `INFO`, `WARNING`, and `ERROR` logging levels. Persistent rotating file logs are intentionally a separate feature, not part of this report-control change.
25. Add tests for explicit-file precedence, live selection, fallback enabled, fallback disabled/skip, excluded sections, disconnected ETABS, cross-model metadata, legacy metadata warnings, and command-backed 100%-30% refresh. Run focused report tests and Ruff; commit as `Add report source fallback policy`.

**Phase 5 — Custom bilingual titles in UI and DOCX (Commit 5: complete, depends on Phases 2–4)**
26. Make `ReportConfig.get_section_name()` prefer custom global titles with built-in `SECTION_NAMES` as fallback. Use those titles in both Settings and ReportDialog.
27. Apply custom section titles only to each report section's top-level `H1`. Preserve all built-in `H2`/`H3` subsection headings, table captions, engineering wording, and clause text. Update `G:\civiltools\src\civiltools\report\docx_report.py` dispatch so every top-level renderer uses the configured H1 rather than embedding its own unrelated heading. English reports use `title_en`; Persian reports use `title_fa` and automatically retain existing RTL handling.
28. Add DOCX tests that customize representative English and Persian H1 titles (including 100%-30%), generate the document, and assert custom top-level headings appear while subsection headings and built-in defaults remain unchanged. Run focused tests and Ruff; commit as `Apply custom report section titles`.

**Phase 6 — Integrated validation (automated complete; live ETABS checklist pending)**
29. Run `conda run -n civiltools python -m pytest` and Ruff on every touched Python module. Run `git diff --check` after each commit and at the end.
30. Manually verify with a connected ETABS model: reorder rows; include/exclude via Select/Clear; leave source choices unchanged; browse valid same-model and legacy result JSON files; reject invalid schemas; confirm cross-model warnings; test missing JSON with fallback on and off; generate DOCX; restart the app and verify global names/order/include/ETABS choices persist while the browsed path appears only for that model.
31. During manual generation, close or disconnect ETABS after opening the dialog and verify affected sections fall back or skip with visible warnings without crashing or retrying indefinitely.
32. If validation requires a code correction, make the smallest correction and commit it separately as a validation fix; otherwise do not create a cosmetic final commit.

**Relevant files**
- `G:\civiltools\src\civiltools\config.py` — application-wide settings schema, migration, and atomic updates.
- `G:\civiltools\src\civiltools\gui\dialogs\app_settings_dialog.py` — new General + Report settings surface.
- `G:\civiltools\src\civiltools\gui\main_window.py` — Help menu action, settings launch, appearance application, and Settings injection into ReportDialog.
- `G:\civiltools\src\civiltools\gui\dialogs\report_dialog.py` — unified include/source/file table and global fallback control.
- `G:\civiltools\src\civiltools\report\report_config.py` — runtime source policy/custom titles plus the dedicated `ModelReportSources` model-local repository.
- `G:\civiltools\src\civiltools\report\refresh.py` — selected live command refresh only for included sections.
- `G:\civiltools\src\civiltools\report\data_extractor.py` — explicit JSON/live/fallback/skip resolution.
- `G:\civiltools\src\civiltools\report\report_generator.py` — source-policy orchestration and progress reporting.
- `G:\civiltools\src\civiltools\report\docx_report.py` — custom bilingual top-level headings.
- `G:\civiltools\tests\test_settings.py`, `test_report_dialog.py`, `test_report_refresh.py`, `test_report.py` — focused regression coverage.

**Decisions**
- Project Settings remains model-specific and unchanged.
- The user-facing application Settings command is under Help, with General and Report tabs.
- All section names, ordering, inclusion, ETABS choices, fallback, and report defaults are application-global.
- Browsed JSON paths are model-specific because result files belong to a particular ETABS model.
- Select All/Clear All changes only report inclusion.
- Every row displays an ETABS checkbox; unchecked means configured civilTools JSON, then optional global ETABS fallback, then skip-with-warning.
- Source status is always explicit: `ETABS`, `Saved JSON`, `ETABS fallback`, or `Unavailable`.
- Missing data never blocks the whole report.
- Browse accepts only validated civilTools JSON in the first version.
- New JSON metadata identifies schema, section, and model; legacy files remain usable with a warning, and cross-model files require confirmation.
- ETABS disconnects are not automatically retried; valid cache fallback or skip-with-warning keeps the remaining report generation alive.
- Existing in-app structured logging is used; persistent file logging remains a separate feature.
- Custom English and Persian names affect UI labels and DOCX H1 headings only; subsections and engineering text retain built-in titles.
- The Settings UI remains English/LTR, Persian title editors use RTL, and Persian DOCX output uses automatic RTL.
- Each independently verifiable phase receives its own commit, as explicitly requested.
