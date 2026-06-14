# Golden datasets (#27)

Ground-truth I/O for offline regression. Each `<layer>.jsonl` holds one case per line:

```json
{"id": "ground_football", "layer": "grounding", "input": "best football transfers",
 "context": {"catalog_id": null}, "expected": {"grounded": false},
 "category": "off_catalog", "severity": "high"}
```

- `input` — the user text fed to the layer.
- `context` *(optional)* — extra args: `history` / `pending` (router, gate), `catalog_id` (grounding).
- `expected` — the ground-truth contract the layer must satisfy:
  - **gate**: `{"blocked": true|false}`
  - **router**: `{"route": "greeting|recommend|foundry_iq|study_plan|work_iq|upcoming|general"}`
  - **grounding**: `{"grounded": true|false, "course"?: "<id-prefix>", "not_course"?: "<id-prefix>"}`

## Run

```bash
unset OFFLINE_LLM
python -m agent_audit.golden                  # all layers
python -m agent_audit.golden --layer grounding   # deterministic, free
python -m agent_audit.golden --layer gate        # live model path
```

Exit code is non-zero on any mismatch, so it doubles as a CI gate. `grounding` needs no
model call; `gate`/`router` hit the live providers.

## Maintain

Run on **every prompt or model change** (new deployment, temperature change, prompt edit).
When the campaign hardens a new behavior, add the canonical case here so a future change
that regresses it fails loudly. Keep cases that encode *fixed* regressions tagged with a
`*_regression` category (e.g. `ground_ml_curiosity`, `router_general_offtopic_in_costume`).

This is read-only: it never imports from a writable path or mutates `app/` or the database.
