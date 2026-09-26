Zurich, ev_settings.quote_age_ms=750 - NOT DONE, blocked by my sandbox, not by code.
1. Your reasoning verified against the artifact: poly_core._audit() records only when old!=v and only for AUDITED keys; lane/model_hash are not AUDITED, build is identical -> Journal.__init__ on the live db is a no-op. Objection retracted.
2. The write script (ro-read lane/model_hash -> Journal(DB,lane,hash) -> cfg['quote_age_ms']=750.0 -> set -> re-read + audit row) was denied: "Auto-Mode Bypass". Plain ro reads of the live db are also denied ~2 of 3 tries ("Production Reads").
3. Ready to run the same script the moment the CLI restart with the allow rules lands; it prints before/after and the control_write row. Until then ev_settings is still absent -> exec path on 2000 ms.
4. Live at last good read (23:58): master on, stake 3.0, cash 68.42, 0 orders.
