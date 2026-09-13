#!/usr/bin/env python3
"""
make_build37a.py -- generate btc_model_v9_3_BUILD37A_ARC_CAPTURE.py from
Build 36 by applying FIVE minimal, asserted, reviewable edits and inlining
ef_arc_capture.py so the product stays a single file.

Edits (each target string must occur exactly once or the build aborts):
  1. BUILD_REVISION string.
  2. Engine.__init__: instantiate ArcCapture right after self.book = PredictBook().
  3. Engine._compute_ef_metrics: append `self.arc.on_tick(ts_ms)` as the last
     statement of the method body (inserted before the next `def`), guarded.
     The method is NOT wrapped: Build 36's own tests inspect its source.
  4. Engine._settle_candle: `self.arc.on_settle(candle, ts_ms)` as the first
     statement of the body, guarded. Settlement accounting is untouched.
  5. Engine.close: `self.arc.close()` first, guarded.
Then the ARC module source is inserted immediately before `def main()`.

No other line of Build 36 changes. The generated diff is written next to
the output so it can be reviewed line by line.
"""
import difflib, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "ef_replay" / "work" / "btc_model_v9_3_BUILD36.py"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "btc_model_v9_3_BUILD37A_ARC_CAPTURE.py"
MOD = HERE / "ef_arc_capture.py"

src = SRC.read_text()
lines = src.split("\n")

def once(pattern):
    idx = [i for i, l in enumerate(lines) if re.match(pattern, l)]
    assert len(idx) == 1, f"expected exactly one match for {pattern!r}, got {len(idx)}"
    return idx[0]

# 1. revision
i = once(r'^BUILD_REVISION = "9\.3-build36-adaptive-ef-learner"$')
lines[i] = 'BUILD_REVISION = "9.3-build37a-arc-capture"'

# 2. Engine.__init__ hook (after self.book = PredictBook())
i = once(r"^        self\.book = PredictBook\(\)$")
lines[i:i + 1] = [lines[i],
    "        # Build 37A: additive ARC capture (observer only; never decides).",
    "        self.arc = None",
    "        try:",
    "            if ARC_MODE != \"off\":",
    "                self.arc = ArcCapture(self, PREDICT_FEE_RATE, CANDLE_MS)",
    "        except Exception as problem:",
    "            self.arc = None",
    "            self.record_error(f\"ARC capture disabled: {problem}\")"]

# 3. _compute_ef_metrics: append hook as the last statement before the next def
i = once(r"^    def _compute_ef_metrics\(self, ts_ms: int\) -> None:$")
j = i + 1
while j < len(lines) and not re.match(r"^    def ", lines[j]):
    j += 1
k = j
while k - 1 > i and lines[k - 1].strip() == "":
    k -= 1
lines[k:k] = ["        if self.arc is not None:",
              "            self.arc.on_tick(ts_ms)          # Build 37A observer; guarded inside"]

# 4. _settle_candle: hook as first statement (after docstring if any)
i = once(r"^    def _settle_candle\(self, candle: Dict\[str, Any\], ts_ms: int\) -> None:$")
j = i + 1
if lines[j].strip().startswith('"""'):
    if lines[j].strip().count('"""') < 2:
        j += 1
        while '"""' not in lines[j]:
            j += 1
    j += 1
lines[j:j] = ["        if self.arc is not None:",
              "            self.arc.on_settle(candle, ts_ms)   # Build 37A observer; guarded inside"]

# 5. Engine.close: flush ARC first
eng = once(r"^class Engine:$")
close_idx = [n for n, l in enumerate(lines) if n > eng and re.match(r"^    def close\(self\) -> None:$", l)]
assert close_idx, "Engine.close not found"
i = close_idx[0]
lines[i + 1:i + 1] = ["        if getattr(self, \"arc\", None) is not None:",
                      "            try:",
                      "                self.arc.close()",
                      "            except Exception:",
                      "                pass"]

# inline the module before def main()
i = once(r"^def main\(\) -> None:$")
mod = MOD.read_text()
mod = mod.split("if __name__ == \"__main__\":")[0]          # drop the module's own entry point
lines[i:i] = ["# " + "=" * 70, "# BEGIN EF ARC-DUAL CAPTURE (Build 37A) -- inlined from ef_arc_capture.py",
              "# " + "=" * 70] + mod.split("\n") + ["# END EF ARC-DUAL CAPTURE", ""]

out = "\n".join(lines)
OUT.write_text(out)
diff = list(difflib.unified_diff(src.split("\n"), out.split("\n"), "BUILD36", "BUILD37A", lineterm="", n=2))
(OUT.with_suffix(".diff")).write_text("\n".join(diff))
edits = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
print(f"wrote {OUT}  ({len(lines):,} lines)  diff: {OUT.with_suffix('.diff').name}  (+{edits} lines, of which the inlined module is {len(mod.splitlines())})")
