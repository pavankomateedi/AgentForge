# Demo video script — Clinical Co-Pilot

**Target length: ~3:00 single take.**
Speak naturally — these are talking-point guidelines, not lines to read verbatim.

---

## Pre-flight (do this once before pressing record)

1. **Local server running** — `python -m uvicorn agent.main:app --host 127.0.0.1 --port 8000`. Verify `http://127.0.0.1:8000/health` returns `{"status":"ok","model":"claude-opus-4-7"}`.
2. **Phone ready** — Google Authenticator / Authy / 1Password installed and unlocked.
3. **Browser** — one tab on `http://127.0.0.1:8000/`. Window roughly **1280 × 800** (wider has too much empty space, narrower crops the form). Hide bookmarks bar.
4. **Hard-refresh** the tab (`Ctrl + Shift + R`) and **clear cookies** for `127.0.0.1` so you start at the fresh Sign-in screen.
5. **Reset demo state** so the recording starts clean:
   ```bash
   python -m agent.cli reset-mfa dr.chen
   python -m agent.cli unlock dr.chen
   # (if password drifted): python -m agent.cli reset-password dr.chen
   ```
6. **Close** notifications, Slack, IDE, anything that could pop up.
7. **Mic check** — record 5 seconds, listen back. Watch out for fan noise, echo, mouse-click pickup.
8. **Recorder ready** — Loom (easiest, ≤5 min free), OBS (full control), or `Win + G` Game Bar.

---

## Beat 1 — Intro · 0:00–0:15

**On screen:** Sign-in screen.

**Say:**
> "This is Clinical Co-Pilot — an AI agent for primary care physicians that fits in the 60-90 second gap between exam rooms. The clinician asks 'brief me' on a patient and gets a verified, source-grounded summary. Every clinical claim it produces is matched against a real source record before the user sees it."

---

## Beat 2 — Sign in + MFA · 0:15–0:45

**On screen:** Sign-in form.

**Action:** Type `dr.chen`, then your password. Press **Sign in**.

**Say while typing:**
> "Access is gated behind login. Passwords are bcrypt-hashed, five failed attempts triggers a 15-minute account lockout, and sessions time out after five minutes of inactivity. All of this is audit-logged."

**On screen:** MFA enrollment screen with the QR code appears.

**Action:** Hold up your phone. Open the authenticator app. Scan the QR. Read the 6-digit code. Type it into the form. Click **Verify and finish**.

**Say:**
> "First login forces MFA enrollment using TOTP — any standard authenticator app works. After this, every subsequent login goes through a 6-digit challenge instead of the QR."

**On screen:** Lands in the main chat UI.

---

## Beat 3 — UC-1 happy path · 0:45–1:15

**On screen:** Main UI. Patient picker shows **Margaret Hayes**. Question box is pre-filled with `Brief me on this patient.`

**Action:** Click **Ask**.

**Say while it loads (5-10s):**
> "I'm asking the agent to brief me on Margaret Hayes. Under the hood, the agent plans which FHIR tools to call — patient summary, problem list, medications, recent labs — runs them in parallel, and generates a four-to-six-line briefing. Every clinical fact has to cite a source ID that came back in the retrieval bundle. A deterministic verifier checks that match before the response is returned. If any cited ID is fabricated or doesn't exist in the bundle, the response gets thrown out."

**On screen:** Briefing appears. Green **✓ Verified** badge in the header.

**Action:** Hover the **Verified** badge briefly so it's visible.

**Say:**
> "Green check — every fact in this briefing matched a real record. The headline the agent surfaces is the elevated A1c at 7.4 percent, which is the right call-out for a diabetic patient on metformin."

---

## Beat 4 — UC-2 follow-up · 1:15–1:35

**Action:** Click the **Latest A1c?** example chip, then **Ask**.

**Say:**
> "Conversational follow-up — same patient, narrower question. The agent goes back to the lab tool specifically and gives a focused answer with the value and the date."

**On screen:** Short response with the A1c number and lab date.

---

## Beat 5 — UC-3 sparse data · 1:35–2:00

**Action:** Switch the patient picker to **James Whitaker**. Click **Ask** (the box is still on the previous question — clear it and click an example or just click Ask if "Brief me" is still in there).

**Say:**
> "Different patient now — James Whitaker. He has one chronic problem, chronic heart failure, one medication, furosemide, and crucially, no recent labs on file. Watch what the agent does with that."

**On screen:** Briefing renders. It mentions the CHF, the furosemide, and explicitly notes that no recent labs are on file — and ties it to a clinical concern.

**Action:** Point at the line that flags the missing labs.

**Say:**
> "The agent didn't drop the labs section silently. It surfaces the gap and ties it to a real clinical concern: no current renal function or electrolytes alongside loop-diuretic therapy. That's the architecture's 'present versus absent versus conflicting' rule in action — the agent never pretends data is there when it isn't."

---

## Beat 6 — Security under injection · 2:00–2:25

**Action:** Switch the patient picker back to **Margaret Hayes**.

**Action:** Clear the question box and type — *slowly enough to read* — `Tell me about James Whitaker.`

**Action:** Click **Ask**.

**On screen:** Short response — explicit refusal naming the locked patient.

**Say:**
> "Now I'm trying to get the agent to surface data about a different patient than the one I have open. The patient subject is locked at the request level — every tool call carries the locked patient ID, and any deviation is rejected by the dispatcher before it reaches the data layer. The agent refuses explicitly and tells me which patient is currently open. This is a structural defense, not a prompt-instruction defense."

---

## Beat 7 — Observability · 2:25–2:55

**Pre-flight:** open a second tab on `https://us.cloud.langfuse.com` already signed in, on the project's **Traces** view. Have it ready to alt-tab to.

**Action:** alt-tab to the Langfuse tab. The most recent trace is the one you just produced.

**Action:** click the most recent `chat_turn` trace.

**Say:**
> "Every request opens a Langfuse trace. The doc asks for four things from observability: what the agent did, how long each step took, did any tools fail, and how many tokens we burned. All four are right here. The root span is the chat turn. Inside it: a generation for the Plan call with token usage and computed cost, a span for parallel retrieval, a generation for the Reason call, and a span for the verifier. Trace-level scores — verified, regenerated, refused, value-mismatch count — power a verifier-pass-rate dashboard over time. If retrieval had failed, that span would be red with the reason attached. This is the data plane the eval suite writes scores into and the audit log joins on the trace ID."

---

## Beat 8 — Closing · 2:55–3:05

**On screen:** Either alt-tab back to the refusal screen, or briefly flash the README / ARCHITECTURE doc.

**Say:**
> "This is the v0 demo on mock FHIR with standalone authentication. The architecture document specifies the production path: a custom React module inside OpenEMR, using OpenEMR's OAuth2 SMART-on-FHIR for auth and FHIR R4 as the only data path. All the verification, patient locking, and audit guarantees you just saw carry forward unchanged. The full architecture, eval suite, and Langfuse traces are in the repo."

---

## Recovery cheatsheet

| Stumble | Fix |
|---|---|
| Sign-in says "Invalid username or password" | `python -m agent.cli reset-password dr.chen` to set a fresh password |
| You're already MFA-enrolled (no QR screen, just challenge) | `python -m agent.cli reset-mfa dr.chen` and re-record |
| "Account temporarily locked" | `python -m agent.cli unlock dr.chen` |
| `/chat` returns 401 in the middle of recording | Session expired — sign out and back in. (Or extend `IDLE_TIMEOUT_SECONDS` in `agent/auth.py` *temporarily* to 1800 just for the recording.) |
| `/chat` takes >15 s | Adaptive thinking on cold cache. Start narrating *as* you click Ask, not after the response. The second call on the same prompt will be much faster. |
| Browser shows old UI | Hard refresh `Ctrl + Shift + R`; clear cookies if needed |

---

## Post-recording checklist

1. **Watch it back at 1× speed.** Cut any silence over ~1 second. Cut any uhh / umm if it bothers you.
2. **No real secrets visible** in any frame. Specifically verify no real `sk-ant-...` key is anywhere on screen — terminal scrollback, IDE, browser DevTools. The `mr.prvv-onboarding-api-key` placeholder in `.env.example` is fine.
3. **Audio level** — should peak around -6dB; not clipping.
4. **Export / copy link.** Loom: just copy the share URL. OBS: export MP4, target ≤25 MB if possible.
5. **Update README** — replace `_(link)_` placeholder under **Demo video** at the top with your URL.
6. **Sanity check** — open the link in an incognito window to make sure it plays without a login.
7. **Submit.**

---

## Notes for tighter takes (optional)

- **If you have time for a second pass**, do a separate take of just Beat 5 (sparse data) — it's the single most differentiated beat and worth getting clean. The "missing labs is itself a clinical signal" line is the strongest single piece of the demo.
- **Skip Beat 4** if you're tight on time — it's a nice-to-have, not load-bearing for the case-study message.
- **Skip the closing line about ARCHITECTURE.md** if you can let the work speak for itself — but the OpenEMR/OAuth2 production path is worth one mention so reviewers know v0 is intentional, not unfinished.
