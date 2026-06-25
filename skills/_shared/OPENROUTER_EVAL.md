# OpenRouter integration — A/B eval procedure

Branch: `feat/openrouter-transport`. Purpose: decide whether to merge OpenRouter
as the panel transport by **measuring** ours (native CLIs) vs theirs (OpenRouter)
on the same tasks — reliability, latency, drop-rate, agreement, gains/fails.

OpenRouter is **transport, not judgment**: the verifier gate stays ours either
way (see loop-engineering SKILL.md "Transport vs judgment"). This eval compares
the *wire*, plus Fusion as an advisor option.

## Status

- **P1–P4 done, no credits:** transport + Fusion built; 14 unit tests; full
  suite 68/68; live transport proven on one free model.
- **P5 (this doc) BLOCKED on credits:** paid models + Fusion return HTTP 402
  ("account never purchased credits"); free models unreliable (1 of ~6 responds,
  rest "Provider returned error"). Top up at openrouter.ai/settings/credits
  (~$10 unlocks all paid models + Fusion), then run the commands below.

## OURS — native baseline (MEASURED 2026-06-23, $0 OpenRouter spend)

```
python3 skills/_shared/model_roster.py --panel 3 --role advisor --exclude-lane claude --run \
  --task "A retry loop self-grades with no separate verifier; 3 attempts all self-approved, output still wrong." \
  --brief "generator==verifier; need a structurally different break." --timeout 90
```
Result: **3/3 lanes responded** — gpt (codex CLI), gemini (agy/Antigravity sub),
glm (z.ai). Wall ≈ **125 s** (sequential dispatch, ~42 s/member). All three
converged on the same hypothesis ("externalize the oracle / deterministic ground
truth"), i.e. strong cross-vendor agreement. Cost to us: $0 (subscription + local).

## THEIRS — OpenRouter (RUN ONCE CREDITS LAND)

1. Confirm credits unlocked:
   ```
   KEY=$(cat ~/.config/openrouter/key)
   curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
     -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"model":"openai/gpt-5-mini","max_tokens":20,"messages":[{"role":"user","content":"ROUTER_OK"}]}'
   ```
   Expect a completion, not a 402.

2. Same panel via OpenRouter (forces the proxy for every eligible lane; local
   stays native as the survivor):
   ```
   python3 skills/_shared/model_roster.py --panel 3 --role advisor --exclude-lane claude --via openrouter --run \
     --task "<same task as ours>" --brief "<same brief>" --timeout 90
   ```

3. Verifier panel both ways (the gate is ours; this only tests the wire under it):
   ```
   # ours
   python3 skills/_shared/model_roster.py --panel 3 --role verifier --exclude-lane claude --run --task "<claim>" --brief "<evidence>"
   # theirs
   python3 skills/_shared/model_roster.py --panel 3 --role verifier --exclude-lane claude --via openrouter --run --task "<claim>" --brief "<evidence>"
   ```

4. Fusion advisor (their productized diverge step):
   ```
   python3 skills/_shared/model_roster.py --fusion --run --preset general-budget \
     --task "<same task>" --brief "<same brief>" --timeout 180
   ```
   Confirm the live response shape matches `fusion_request_body` (the plugin wire
   is provisional until this runs — adjust `fusion_request_body` if the API
   rejects the `plugins:[{id:fusion,…}]` form).

## Compare on (fill in when P5 runs)

| Metric | OURS (native) | THEIRS (OpenRouter) |
|---|---|---|
| lanes responded / dispatched | 3/3 | — |
| wall-clock | ~125 s | — |
| drop-rate / failures | 0 | — |
| finding quality (agreement, novelty) | high agreement | — |
| cost | $0 (subscription) | $ (metered) |
| reliability notes | agy/codex/z.ai all live | — |

## Decision rule

Merge OpenRouter as **backfill default** (native preferred, proxy fills gaps) if
THEIRS is at least as reliable on reachable lanes and adds availability/lanes the
host lacks. Adopt `--via openrouter` as the *consolidation* lever only if its
drop-rate ≤ native and latency is acceptable. Keep ollama as the survivor lane
unconditionally. Do **not** wire Fusion as the verifier under any result.
