# Cross-platform Brainer remediation plan

## WHAT / WHY

Make Brainer's supported behavior honest and operational in Codex first, then
add the simplest viable Claude Desktop integration without pretending that an
MCP tool is a lifecycle hook.

User-visible outcome:

- Fresh Codex projects receive the same default-on capture/archive substrate
  that Brainer intends for Codex.
- The Markdown session capture is produced without a dashboard process or a
  second state store.
- Claude Desktop Code gets a schema-valid native plugin plus a precise live
  test; the UI does not expose a required end-session step.

Non-goals: native graphical dashboards, React/Electron, databases, transcript
scraping, OS Accessibility automation, automatic semantic completion, sibling
repo propagation, commits, or pushes.

Assumptions and dependencies:

- “Both platforms” means Codex Desktop and the Code section of the consumer
  Claude Desktop app. Chat and Cowork are not acceptance targets.
- Claude Desktop testing may require the user's access to the app.
- Existing uncommitted Markdown-capture and audit fixes are preserved.

## Testable requirements

1. `install.sh --project <fresh> --host codex --no-graphify` creates resolving
   `.codex/skills/*` links and wires only the intended default-on Codex hooks in
   the consumer project, without editing Brainer's own host config.
2. A Codex-specific fresh-project lifecycle test proves hook files, commands,
   paths, and synthetic hook execution; Claude Code's existing E3 test remains
   green.
3. New Markdown captures label mechanically captured requests as non-semantic
   capture, never as proof that work remains unfinished.
4. Every host-specific skill feature is classified as portable, adapted,
   manual fallback, or unsupported for Codex Desktop and Claude Desktop.
5. Claude Desktop Code support is chosen from verified public capabilities and
   a schema-valid plugin. If a lifecycle event is not observed in the app, the
   plan must not use transcript scraping; it records the event as unsupported
   or unverified and supplies a manual fallback where useful.

## Decisions most likely to change on review

- Codex hook installation should reuse the host-specific commands declared by
  each skill installer, retargeted to `.codex/skills`, rather than introduce a
  daemon. Configured events and live-observed events are reported separately.
- Claude Desktop Code should use Claude Code's native plugin carrier for skills,
  hooks, and sub-agents. MCPB/Desktop Extensions remain out of scope unless a
  separate local tool surface is later required. Hook support is reported per
  event because closing the Desktop UI is not evidence that its underlying
  Claude Code session ended.
- One Markdown file remains the display. Existing canary JSON/intent state stays
  authoritative; no new dashboard state is added.

## Execution phases

1. Codex: repair fresh-project hook installation and add a Codex lifecycle
   acceptance test.
2. Codex: cold-verify install isolation, hook liveness, Markdown output, and
   regression suites.
3. Claude Desktop Code: repair the obsolete native plugin manifest, validate
   it, then run the smallest user-assisted Code probe that checks skill loading
   and automatic hook behavior.
4. Reconcile the 31-skill compatibility matrix and document intentional
   degradations and follow-up work.

## Parallel lanes

- Codex builder owns `install.sh`, `scripts/e3_gauntlet.py`, its tests, and
  Codex fresh-project fixtures.
- Claude Desktop researcher is read-only and returns official capability
  evidence plus a minimal live-test recipe.
- Catalog auditor is read-only and classifies every skill/function by host and
  identifies the smallest remediation per gap.
- Claude plugin builder owns only the native plugin package and focused schema
  checks; a separate verifier cold-checks it before the live app probe.
- The lead owns this plan, Kimi K3 consultation, integration decisions, and
  final synthesis. A fresh verifier cold-checks every builder edit.

## Verification pipeline

Generator: dedicated Codex builder.

Verifier: separate cold agent plus deterministic core/E3/host-install tests.

Gate: all affected tests exit zero; a fresh Codex consumer has the expected
hooks and no Brainer-root config drift; Claude Desktop claims match an observed
probe or remain explicitly unsupported.

Stop: complete, or blocked on a named Claude Desktop user action/API absence.

Budget: maximum two builder correction rounds and one user-assisted Claude
Desktop probe round before surfacing the blocker.

## done means:

1. Fresh Codex consumer install automatically produces a valid, executable
   default hook configuration without mutating the canonical checkout.
2. Markdown capture behavior and wording pass dedicated regression tests.
3. Core and both Claude-Code/Codex lifecycle gates pass, with no unexplained
   skips affecting changed behavior.
4. All 31 skills have an evidence-backed Codex/Claude Desktop disposition and
   the simplest remediation or intentional fallback.
5. Claude Desktop is either live-proven at its claimed support level or left as
   an explicit user-action blocker with a precise test packet.

## Claude Desktop Code live probe

One-time user-scope install from this checkout:

```bash
claude plugin marketplace add /Users/za/Documents/Brainer --scope user
claude plugin install brainer@brainer --scope user
```

Then open a fresh Code session rooted at `/Users/za/Documents/Brainer`:

1. Confirm the Brainer plugin is enabled and invoke the displayed/namespaced
   `think` skill.
2. Send the unique plain prompt `BR-DESKTOP-UI-0719` without invoking a skill.
3. Run `/compact`.

Observed on 2026-07-19: the plugin skill appeared as `/think`; the marker wrote
exactly one project-local intent row and one visible ledger row; and `/compact`
created the matching project-local `.brainer/sessions/*.md` checkpoint. The UI
does not need an explicit end-session action for this workflow. Command-W did
not update the source transcript, so it is treated only as closing the UI, not
as a `SessionEnd` acceptance test. A raw end-of-session archive is therefore not
promised for that action.

Live carrier evidence obtained outside the UI remains useful but narrower: the
installed user plugin produced exactly one intent row and one visible capture
when the same hook was also configured project-locally, and the underlying
Claude Code engine delivered `SessionEnd` and wrote the raw archive. The
structural precedence router is covered by deterministic tests and an
independent cold live reproduction. That engine evidence must not be presented
as evidence that closing the Desktop UI ends the session.

The native plugin is packaged from the bounded `plugin/` root, not the whole
repository. A fresh 1.14.1 install measured 22 MB (down from 474 MB) and
contained only `.claude-plugin/`, `hooks/`, and `skills/`. A cache-only Claude
run with user settings disabled loaded all 31 skills, delivered exactly one
`UserPromptSubmit`, and wrote the matching intent, ledger, and `SessionEnd` raw
archive from the installed artifact.
