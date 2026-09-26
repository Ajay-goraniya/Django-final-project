# Zurich tape export for the early-fire study (09-24 UTC)

`zurich_tape_13_0_0.sqlite3.gz` — 10.6 MB gzipped, 31.9 MB raw, `integrity_check ok` after a
round-trip. Read-only extract from the Zurich shadow journal
`polymarket_v12_zurich_live4.sqlite3`. **Nothing on the box was restarted or changed to produce it.**

| table | rows | filter |
|---|---|---|
| `tape1s` | 145,907 | **all rows**, ts 1790105407 -> 1790252231 (09-23 00:50:07 -> 09-24 17:37:11) |
| `signals` | 516 | all rows |
| `calls` | 256 | all rows |
| `diagnostics_ef` | 5,796 | EF decide rows since the 13.0.0 restart (ts >= 1790125530) |

**One thing to know before you query `diagnostics_ef`.** The brief asked for "diagnostics rows with
kind EF". **No diagnostics row carries `kind == "EF"`** — that key holds values like `AMBIENT_AGE` and
`MAIN`. EF decide rows are identifiable instead by `mode == "pnl"` together with a `breakeven` key.
I applied both rules as an OR, so the literal-`kind` match is included and currently contributes zero
rows. If a later build starts stamping `kind: "EF"`, the same query keeps working.

`tape1s` deliberately starts *before* the 13.0.0 restart, because the brief said all rows and the
recorder was already running under 12.24.8. Only `diagnostics_ef` is cut at 13.0.0.

An `export_meta` table inside the file repeats all of this, so the provenance travels with the data.

Context at export: build 13.0.0, pid 153702, lane SHADOW, master OFF, `ef_profile` raw_v10_live25.
