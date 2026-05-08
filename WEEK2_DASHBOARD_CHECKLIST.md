# Week 2 Patient Dashboard — Checklist

**Branch:** `Week-2-Patient-Dashboard` (off `main` @ `be7b16b`)
**Target finish:** Thu 2026-05-07, 09:00 (3-hour buffer before noon deadline)
**Framework:** React + Vite + TypeScript, separate `dashboard/` directory

---

## Time shape

| Block | Window | Output |
|---|---|---|
| 1. Backend + scaffold | T+0 → T+3h | OpenEMR (or fallback) up · `dashboard/` scaffolded · FHIR types written |
| 2. Auth + header | T+3h → T+6h | OAuth2 PKCE end-to-end · AuthGuard · PatientHeader rendering |
| 3. Three cards | T+6h → T+9h | Allergies + Problems + Meds live |
| 4. Break / sleep | T+9h → T+15h | — |
| 5. Two cards + labs | T+15h → T+18h | Prescriptions + CareTeam + LabsSection live |
| 6. Defense + CI + deploy | T+18h → T+20h | `PATIENT_DASHBOARD_MIGRATION.md` · CI job · public URL |
| 7. Demo + PR | T+20h → T+22h | Video · smoke-test · PR open · merge |

---

## Scope cuts (taken upfront for the 22-hour window)

- Lab trend chart — table-only satisfies parity
- Refresh-token rotation — re-auth on expiry is fine for demo
- Patient picker as full search — render fixed list of OpenEMR demo patients
- Vitest + MSW + Playwright tests — replaced with build/typecheck/lint CI + manual smoke-test
- Loading-state polish — basic spinners only, no skeletons

## Risk policy

**90-minute hard cap on OpenEMR Docker.** If it isn't serving FHIR + OAuth by 90 min, pivot to a FHIR-compatible substitute (HAPI test server + stub OAuth provider) and document the pivot honestly in the defense doc.

---

## Checklist

### Block 1 — Backend + scaffold
- [ ] Stand up OpenEMR locally via Docker (90-min hard budget; pivot to HAPI+stub-OAuth if blocked)
- [ ] Register OAuth2 client in OpenEMR + capture client_id, secret, redirect URI
- [ ] Scaffold `dashboard/` app (Vite + React + TS + react-router + `.env.example`)
- [ ] Build typed FHIR client (resource interfaces + bearer fetcher + Bundle pagination)

### Block 2 — Auth + header
- [ ] Implement OAuth2 Authorization Code + PKCE flow (login → callback → token storage; no refresh)
- [ ] Build AuthGuard wrapping protected routes
- [ ] Build PatientPicker (fixed list of OpenEMR demo patients, no full search)
- [ ] Build PatientHeader (name, DOB, sex, MRN, active status)

### Block 3 — Three cards
- [ ] Build AllergiesCard (AllergyIntolerance)
- [ ] Build ProblemListCard (Condition, active + problem-list-item)
- [ ] Build MedicationsCard (MedicationStatement)

### Block 5 — Two cards + labs
- [ ] Build PrescriptionsCard (MedicationRequest)
- [ ] Build CareTeamCard (CareTeam + Practitioner refs; fallback to PractitionerRole)
- [ ] Build LabsSection (Observation laboratory, sortable table only — no chart)
- [ ] Add minimal loading/error/empty states across all cards

### Block 6 — Defense + CI + deploy
- [ ] Write `PATIENT_DASHBOARD_MIGRATION.md` (framework defense, tradeoffs, FHIR coverage matrix)
- [ ] Wire `dashboard-build` CI job (typecheck + lint, no test runner)
- [ ] Update README with dashboard link + setup instructions
- [ ] Deploy dashboard publicly (FastAPI static mount = simplest path)

### Block 7 — Demo + PR
- [ ] Smoke-test deployed dashboard against live OpenEMR
- [ ] Record 2–3 min demo video (login → patient → 5 cards + labs)
- [ ] Open PR `Week-2-Patient-Dashboard` → `main` + merge after CI green

---

## Framework defense thesis (one-liner reminders for the doc)

- **Type safety against FHIR shapes** — TypeScript interfaces mirror `Patient`, `AllergyIntolerance`, etc., so integration bugs surface at compile time, not in clinic.
- **Component composition** — each clinical card is a self-contained unit (fetch + error boundary + render) instead of HTML/PHP/SQL braided together.
- **Proven stack** — same as the Co-Pilot UI we already ship; CI, deploy, bundling are solved.
- **Tradeoff** — SPA loses SSR's SEO + initial paint. For a behind-OAuth clinical surface, that's a free trade. CORS on direct-from-SPA OAuth is the real cost — addressed with a 30-line FastAPI BFF if needed.
