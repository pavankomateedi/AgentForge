# Social post drafts

Pick one. LinkedIn version is longer (the post format rewards that). X version is condensed for the 280-char window. Both end with the @GauntletAI tag the case-study doc requires for Final submission.

---

## LinkedIn version (recommended — fits the platform)

> 🩺 Just finished week 1 of @GauntletAI's Austin admission track — building an AI agent that helps primary-care physicians get a verified, source-grounded patient briefing in the 90 seconds between rooms.
>
> The hard part wasn't the agent. It was making it defensible.
>
> A few decisions I'd put in front of a hospital CTO:
>
> 🔍 **Verification is deterministic Python, not an LLM.** Two-pass check on every response: source-id matching + numeric value-tolerance. So "real record, wrong number" gets caught — not just made-up citations. Fails route to a structured fallback panel; the doctor never sees an unverified answer.
>
> 🛡️ **Patient locking is in the dispatcher, not the prompt.** A clever injection that talks the LLM into looking up the wrong patient still gets blocked at the tool layer. 12 injection variants tested; all refused before any data is touched.
>
> 📊 **LangGraph for the orchestration.** Plan → Retrieve → Rules → Reason → Verify as named nodes with explicit edges. The graph diagram in ARCHITECTURE.md is auto-rendered from the compiled graph, so the spec and the implementation can never drift.
>
> 📈 **Langfuse for observability.** Every request gets a trace with token cost, per-node latency, verifier scores. Operators can click from a /chat response straight to its trace.
>
> 🧪 **156 deterministic tests + 4 replay cassettes**, all running in CI on every PR. Free + fast — paid live-API tests are opt-in.
>
> Stack: Python 3.12 · FastAPI · Anthropic Claude Opus 4.7 · LangGraph · Langfuse · React · Railway.
>
> Code: github.com/pavankomateedi/AgentForge
> Live demo: web-production-6259a.up.railway.app
>
> Thanks @GauntletAI for the case study — building to defendable-in-front-of-a-hospital-CTO is a much better bar than "demo-impressive."
>
> #AI #Healthcare #LLM #Agents #LangGraph #Langfuse #BuildInPublic

---

## X / Twitter version (condensed)

> Built a clinical AI co-pilot for @GauntletAI's week 1.
>
> Verifier is deterministic Python (not an LLM). Two checks: real source ID + value-tolerance. "Real record, wrong number" gets caught.
>
> Patient lock is in the tool dispatcher, not the prompt — 12 injection variants all refused.
>
> LangGraph orchestration. Langfuse traces. 156 tests. CI gated.
>
> github.com/pavankomateedi/AgentForge
>
> Demo: web-production-6259a.up.railway.app

---

## Optional: short BlueSky / Mastodon version

> Week 1 of GauntletAI: a clinical co-pilot agent that fits in the 90 seconds between exam rooms.
>
> Verification is deterministic Python (no LLM grading itself). Two-pass: source-id match + numeric value-tolerance. Patient locking enforced in the dispatcher so injection can't redirect it.
>
> Code + Langfuse traces in the repo: github.com/pavankomateedi/AgentForge

---

## Pre-post checklist

1. **Drop the Loom URL** at the bottom of the post if you have a Final-submission re-record. (Tonight's Early-Submission video covers most of the same ground; not a blocker.)
2. **Add a screenshot** if posting to LinkedIn — the chat UI with the verifier badge + a Langfuse trace pane side-by-side is the highest-impact image.
3. **Tag @GauntletAI** — the case study explicitly requires this. Spelling: capital G + capital A.
4. **Don't post until after Final submission lands** — the deployed link should match the code reviewers see.
5. **Pin / boost on LinkedIn** if you want the post to reach beyond your immediate network. (Optional.)

---

## Why these particular hooks

The reviewer feedback on the MVP video was: tighten the architecture explanation, show how verification works step by step, walk through edge cases. Each of the bullets above is a concrete answer to one of those:

- "Verification is deterministic" → tightens architecture
- "Two-pass check" → step-by-step verification
- "Patient locking is in the dispatcher" → edge case (prompt injection) handled structurally
- "LangGraph + Langfuse + 156 tests" → defensible at depth

Any reviewer scanning the post sees the same hooks they'd score the demo against.
