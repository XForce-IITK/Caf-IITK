# Requirements traceability matrix — Deliverable 2

Update of the SRS v2.0 §6.3 full matrix at the end of Sprint 2. The columns are the SRS's own. The SRS left **Jira issue**, **PR** and **Result** as "TBD", "—" and "Not run"; they are filled in here from the repository and Jira. Rows, priorities, verification methods, use cases, user stories, test cases and test levels are unchanged from the SRS.

**How each column was filled**

- **Jira issue:** the requirement's own task (with its status), then the user stories that implement it.
- **PR:** the merged pull requests that carry those stories' keys. Log-only and release PRs are left out.
- **Result:**
  - **Pass:** every acceptance criterion listed under *Test case(s)* has a test named for it (`test_tc_usNN_acN` in `backend/tests`, or `TC-USNN-ACN` in `app/test`), and the whole suite passes in CI on `develop` (commit `f473518`, run 38634162462).
  - **Pass (direct verification):** the requirement is verified by inspection of CI or configuration, as the SRS allows (method I); the evidence is in the *Test case(s)* cell.
  - **Partial:** only part of the requirement is tested yet.
  - **Not run:** not built or not yet tested. Most of these are planned for Sprints 3 and 4.

**Summary**

| | Pass | Partial | Not run | Total |
|---|---|---|---|---|
| Functional (FR) | 47 | 0 | 17 | 64 |
| Non-functional (NFR) | 20 | 1 | 24 | 45 |

Of the 10 critical (★) requirements, 9 pass: FR-7, FR-24, FR-30, FR-32, FR-35, FR-39, FR-58, FR-60 and NFR-1. The tenth, FR-34 (the sweeper that releases expired holds), is planned for Sprint 3 (US-24).

## Full matrix

| Req | ★ | Priority | Verify | Use case(s) | User stor(ies) | Jira issue | Test case(s) | Test level | PR | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-1 |  | Must | T | UC-01 | US-01 | CAFIITK-17 (Done), CAFIITK-126 | TC-US01-AC1…AC3 | Integration | #3 | Pass |
| FR-2 |  | Must | T | UC-03 | US-03 | CAFIITK-18 (To Do), CAFIITK-128 | TC-US03-AC1…AC3 | Integration | — | Not run |
| FR-3 |  | Should | T | UC-03 | US-03 | CAFIITK-19 (To Do), CAFIITK-128 | TC-US03-AC1…AC3 | Integration | — | Not run |
| FR-4 |  | Must | T | UC-02 | US-02 | CAFIITK-20 (Done), CAFIITK-127 | TC-US02-AC1…AC4 | Integration | #5 | Pass |
| FR-5 |  | Must | T, D | UC-02 | US-02 | CAFIITK-21 (Done), CAFIITK-127 | TC-US02-AC1…AC4 | Integration, E2E | #5 | Pass |
| FR-6 |  | Must | T | all (cross-cutting) | US-04 | CAFIITK-22 (Done), CAFIITK-129 | TC-US04-AC1…AC3 | Security | #8 | Pass |
| FR-7 | ★ | Must | T | UC-11, UC-12, UC-13, UC-14 (cross-cutting) | US-05 | CAFIITK-23 (Done), CAFIITK-130 | TC-US05-AC1…AC2 | Security | #49 | Pass |
| FR-8 |  | Must | T | UC-05 | US-06 | CAFIITK-24 (Done), CAFIITK-131 | TC-US06-AC1…AC3 | Integration | #9 | Pass |
| FR-9 |  | Must | T | UC-05 | US-07 | CAFIITK-25 (To Do), CAFIITK-132 | TC-US07-AC1 | Integration | — | Not run |
| FR-10 |  | Must | T | UC-05 | US-08 | CAFIITK-26 (To Do), CAFIITK-133 | TC-US08-AC1…AC3 | Integration | — | Not run |
| FR-11 |  | Must | T | UC-06 | US-09 | CAFIITK-27 (Done), CAFIITK-134 | TC-US09-AC1…AC3 | Integration | #33 | Pass |
| FR-12 |  | Must | T | UC-04, UC-06 | US-09, US-10 | CAFIITK-28 (Done), CAFIITK-134, CAFIITK-135 | TC-US09-AC1…AC3, TC-US10-AC1…AC2 | Integration | #13, #33 | Pass |
| FR-13 |  | Must | T, D | UC-04 | US-10 | CAFIITK-29 (Done), CAFIITK-135 | TC-US10-AC1…AC2 | Integration, E2E | #13 | Pass |
| FR-14 |  | Must | T | UC-07 | US-11 | CAFIITK-30 (Done), CAFIITK-136 | TC-US11-AC1 | Integration | #10 | Pass |
| FR-15 |  | Must | T | UC-07 | US-12 | CAFIITK-31 (Done), CAFIITK-137 | TC-US12-AC1…AC2 | Integration | — | Pass, tested under other names (`test_us12_ac1_…`, `test_us12_ac2_…` in `test_inventory_set.py`) |
| FR-16 |  | Must | T | UC-07 | US-13 | CAFIITK-32 (Done), CAFIITK-138 | TC-US13-AC1…AC4 | Integration | #40 | Pass |
| FR-17 |  | Must | T | UC-08 | US-14 | CAFIITK-33 (Done), CAFIITK-139 | TC-US14-AC1…AC2 | Integration | #11 | Pass |
| FR-18 |  | Must | T | UC-08 | US-15 | CAFIITK-34 (To Do), CAFIITK-140 | TC-US15-AC1…AC2 | Integration | — | Not run |
| FR-19 |  | Must | T | UC-04 | US-16 | CAFIITK-35 (Done), CAFIITK-141 | TC-US16-AC1…AC3 | Integration | #14, #18 | Pass |
| FR-20 |  | Must | T | UC-08 | US-16 | CAFIITK-36 (Done), CAFIITK-141 | TC-US16-AC1…AC3 | Integration | #14, #18 | Pass |
| FR-21 |  | Must | T | UC-08 | US-16, US-28 | CAFIITK-37 (Done), CAFIITK-141, CAFIITK-153 | TC-US16-AC1…AC3, TC-US28-AC1…AC5 | Integration | #14, #18, #39 | Pass |
| FR-22 |  | Must | T | UC-09 | US-17 | CAFIITK-38 (To Do), CAFIITK-142 | TC-US17-AC1…AC2 | Integration | — | Not run |
| FR-23 |  | Must | T | UC-09 | US-18 | CAFIITK-39 (To Do), CAFIITK-143 | TC-US18-AC1 | Integration | — | Not run |
| FR-24 | ★ | Must | T | UC-10 | US-19 | CAFIITK-40 (Done), CAFIITK-144 | TC-US19-AC1…AC5 | Unit | #7 | Pass |
| FR-25 |  | Must | T, D | UC-10 | US-19 | CAFIITK-41 (Done), CAFIITK-144 | TC-US19-AC1…AC5 | Integration | #7 | Pass |
| FR-26 |  | Should | T | UC-11 | US-20 | CAFIITK-42 (Done), CAFIITK-145 | TC-US20-AC1 | Integration | — | Pass, tested under another name (`test_price_differing_from_the_quote_is_409_with_a_fresh_quote`) |
| FR-27 |  | Must | T | UC-14 | US-21 | CAFIITK-43 (To Do), CAFIITK-146 | TC-US21-AC1…AC2 | Integration | — | Not run |
| FR-28 |  | Must | T, D | UC-14 | US-21 | CAFIITK-44 (To Do), CAFIITK-146 | TC-US21-AC1…AC2 | Integration | — | Not run |
| FR-29 |  | Must | T | UC-11, UC-17 | US-22, US-34 | CAFIITK-45 (Done), CAFIITK-147, CAFIITK-159 | TC-US22-AC1…AC3, TC-US34-AC1…AC4 | Unit, Integration | #15, #53 | Pass |
| FR-30 | ★ | Must | T | UC-11 | US-22 | CAFIITK-46 (Done), CAFIITK-147 | TC-US22-AC1…AC3 | Integration | #15 | Pass |
| FR-31 |  | Should | T | UC-11 | US-26 | CAFIITK-47 (To Do), CAFIITK-151 | TC-US26-AC1…AC2 | Integration | — | Not run |
| FR-32 | ★ | Must | T | UC-11 | US-25 | CAFIITK-48 (Done), CAFIITK-150 | TC-US25-AC1…AC3 | Integration | #12 | Pass |
| FR-33 |  | Must | T | UC-11 | US-22, US-23 | CAFIITK-49 (Done), CAFIITK-147, CAFIITK-148 | TC-US22-AC1…AC3, TC-US23-AC1…AC3 | Integration | #6, #15, #17 | Pass |
| FR-34 | ★ | Must | T | UC-15 | US-24 | CAFIITK-50 (To Do), CAFIITK-149 | TC-US24-AC1…AC3 | Integration | — | Not run |
| FR-35 | ★ | Must | T | UC-12 | US-27 | CAFIITK-51 (Done), CAFIITK-152 | TC-US27-AC1…AC5 | Integration | #44, #54, #61 | Pass |
| FR-36 |  | Must | T | UC-12 | US-27 | CAFIITK-52 (Done), CAFIITK-152 | TC-US27-AC1…AC5 | Integration | #44, #54, #61 | Pass |
| FR-37 |  | Must | T | UC-13 | US-28 | CAFIITK-53 (Done), CAFIITK-153 | TC-US28-AC1…AC5 | Integration | #39 | Pass |
| FR-38 |  | Should | T | UC-20 | US-36 | CAFIITK-54 (To Do), CAFIITK-161 | TC-US36-AC1…AC2 | Integration | — | Not run |
| FR-39 | ★ | Must | T | UC-13, UC-20 | US-28 | CAFIITK-55 (Done), CAFIITK-153 | TC-US28-AC1…AC5 | Integration | #39 | Pass |
| FR-40 |  | Must | T, D | UC-14 | US-29 | CAFIITK-56 (Done), CAFIITK-154 | TC-US29-AC1…AC2 | Integration, E2E | #31 | Pass |
| FR-41 |  | Must | T, D | UC-11 | US-23 | CAFIITK-57 (Done), CAFIITK-148 | TC-US23-AC1…AC3 | Integration | #6, #17 | Pass |
| FR-42 |  | Must | T, D | UC-16 | US-33 | CAFIITK-58 (Done), CAFIITK-158 | TC-US33-AC1…AC2 | Integration, E2E | #35 | Pass |
| FR-43 |  | Must | T | UC-17 | US-34 | CAFIITK-59 (Done), CAFIITK-159 | TC-US34-AC1…AC4 | Integration | #53 | Pass |
| FR-44 |  | Should | T | UC-18 | US-35 | CAFIITK-60 (Done), CAFIITK-160 | TC-US35-AC1 | Integration | #57 | Pass |
| FR-45 |  | Should | T, D | UC-19 | US-37 | CAFIITK-61 (To Do), CAFIITK-162 | TC-US37-AC1…AC2 | E2E | — | Not run |
| FR-46 |  | Should | D | UC-19 | US-37 | CAFIITK-62 (To Do), CAFIITK-162 | TC-US37-AC1…AC2 | E2E | — | Not run |
| FR-47 |  | Must | T | UC-21 | US-38 | CAFIITK-63 (To Do), CAFIITK-163 | TC-US38-AC1…AC4 | Integration | — | Not run |
| FR-48 |  | Must | T, I | UC-21 | US-38 | CAFIITK-64 (To Do), CAFIITK-163 | TC-US38-AC1…AC4 | Integration | — | Not run |
| FR-49 |  | Must | T, D | UC-21 | US-38 | CAFIITK-65 (To Do), CAFIITK-163 | TC-US38-AC1…AC4 | Integration | — | Not run |
| FR-50 |  | Must | T | UC-22 | US-39 | CAFIITK-66 (Done), CAFIITK-164 | TC-US39-AC1…AC3 | Integration | #32, #38 | Pass |
| FR-51 |  | Must | T | UC-23 | US-39 | CAFIITK-67 (Done), CAFIITK-164 | TC-US39-AC1…AC3 | Integration | #32, #38 | Pass |
| FR-52 |  | Must | T, D | UC-23 | US-39 | CAFIITK-68 (Done), CAFIITK-164 | TC-US39-AC1…AC3 | Integration | #32, #38 | Pass |
| FR-53 |  | Must | T | UC-24 | US-40 | CAFIITK-69 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration | #43 | Pass |
| FR-54 |  | Must | T | UC-24 | US-40 | CAFIITK-70 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration | #43 | Pass |
| FR-55 |  | Must | T | UC-24 | US-40 | CAFIITK-71 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration | #43 | Pass |
| FR-56 |  | Must | T | UC-25, UC-26 | US-40 | CAFIITK-72 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration | #43 | Pass |
| FR-57 |  | Must | T | UC-25 | US-40 | CAFIITK-73 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration | #43 | Pass |
| FR-58 | ★ | Must | T | UC-23, UC-24 | US-42 | CAFIITK-74 (Done), CAFIITK-167 | TC-US42-AC1…AC3 | Adversarial | #45 | Pass |
| FR-59 |  | Must | T | UC-23 | US-43 | CAFIITK-75 (Done), CAFIITK-168 | TC-US43-AC1…AC3 | Adversarial | #42 | Pass |
| FR-60 | ★ | Must | T | UC-24 | US-41 | CAFIITK-76 (Done), CAFIITK-166 | TC-US41-AC1…AC3 | Adversarial | #47 | Pass |
| FR-61 |  | Must | T | UC-23 | US-41 | CAFIITK-77 (Done), CAFIITK-166 | TC-US41-AC1…AC3 | Adversarial | #47 | Pass |
| FR-62 |  | Must | T, I | UC-23 | US-39 | CAFIITK-78 (Done), CAFIITK-164 | TC-US39-AC1…AC3 | Integration | #32, #38 | Pass |
| FR-63 |  | Must | D | UC-22, UC-25 | US-40 | CAFIITK-79 (Done), CAFIITK-165 | TC-US40-AC1…AC6 | Integration, E2E | #43 | Pass |
| FR-64 |  | Should | T | UC-23 | US-43 | CAFIITK-80 (Done), CAFIITK-168 | TC-US43-AC1…AC3 | Integration | #42 | Pass |
| NFR-1 | ★ | Must | T | UC-11 – UC-13 | US-30 | CAFIITK-81 (Done), CAFIITK-155 | TC-US30-AC1…AC4 | Concurrency | #23, #51, #60 | Pass |
| NFR-2 |  | Must | T | UC-11 – UC-13 | US-30 | CAFIITK-82 (Done), CAFIITK-155 | TC-US30-AC1…AC4 | Concurrency | #23, #51, #60 | Pass |
| NFR-3 |  | Must | T | — | — | CAFIITK-83 (To Do) | TC-NFR3 | Concurrency | — | Not run |
| NFR-4 |  | Must | T | UC-11 – UC-13 | US-30 | CAFIITK-84 (Done), CAFIITK-155 | TC-US30-AC1…AC4 | Concurrency | #23, #51, #60 | Pass |
| NFR-5 |  | Must | T | UC-11 – UC-13 | US-30 | CAFIITK-85 (Done), CAFIITK-155 | TC-US30-AC1…AC4 | Concurrency | #23, #51, #60 | Pass |
| NFR-6 |  | Must | I, T | — | — | CAFIITK-86 (To Do) | TC-NFR6 | Concurrency | — | Not run |
| NFR-7 |  | Must | T | UC-11 | US-25 | CAFIITK-87 (Done), CAFIITK-150 | TC-US25-AC1…AC3 | Concurrency | #12 | Pass |
| NFR-8 |  | Must | A | UC-04, UC-11 | US-31 | CAFIITK-88 (To Do), CAFIITK-156 | TC-US31-AC1…AC2 | Performance | — | Not run |
| NFR-9 |  | Must | A | UC-04, UC-11 | US-31 | CAFIITK-89 (To Do), CAFIITK-156 | TC-US31-AC1…AC2 | Performance | — | Not run |
| NFR-10 |  | Should | A | — | — | CAFIITK-90 (To Do) | TC-NFR10 | Performance | — | Not run |
| NFR-11 |  | Should | A | — | — | CAFIITK-91 (To Do) | TC-NFR11 | Performance | — | Not run |
| NFR-12 |  | Must | A | UC-04, UC-11 | US-31 | CAFIITK-92 (To Do), CAFIITK-156 | TC-US31-AC1…AC2 | Performance | — | Not run |
| NFR-13 |  | Must | T | UC-11 – UC-13 | US-30 | CAFIITK-93 (Done), CAFIITK-155 | TC-US30-AC1…AC4 | Concurrency | #23, #51, #60 | Pass |
| NFR-14 |  | Must | T | UC-11 | US-23 | CAFIITK-94 (To Do), CAFIITK-148 | TC-US23-AC1…AC3 | Failure/Recovery | #6, #17 | Partial: payment failure and timeout pass (TC-US23); release after a crash needs the hold sweeper (US-24, Sprint 3) |
| NFR-15 |  | Must | T, D | UC-15 | US-24 | CAFIITK-95 (To Do), CAFIITK-149 | TC-US24-AC1…AC3 | Failure/Recovery | — | Not run |
| NFR-16 |  | Must | T, D | cross-cutting | US-32 | CAFIITK-96 (To Do), CAFIITK-157 | TC-US32-AC1…AC2 | Failure/Recovery | — | Not run |
| NFR-17 |  | Must | T | UC-23 | US-43 | CAFIITK-97 (Done), CAFIITK-168 | TC-US43-AC1…AC3 | Failure/Recovery | #42 | Pass |
| NFR-18 |  | Should | T | UC-11 | US-25 | CAFIITK-98 (Done), CAFIITK-150 | TC-US25-AC1…AC3 | Failure/Recovery | #12 | Pass |
| NFR-19 |  | Must | T | UC-02 | US-02 | CAFIITK-99 (Done), CAFIITK-127 | TC-US02-AC1…AC4 | Security | #5 | Pass |
| NFR-20 |  | Must | T, I | — | — | CAFIITK-100 (To Do) | TC-NFR20 | Security | — | Not run |
| NFR-21 |  | Should | T | — | — | CAFIITK-101 (To Do) | TC-NFR21 | Security | — | Not run |
| NFR-22 |  | Must | T | — | — | CAFIITK-102 (To Do) | TC-NFR22 | Security | — | Not run |
| NFR-23 |  | Must | T | — | — | CAFIITK-103 (To Do) | TC-NFR23 | Security | — | Not run |
| NFR-24 |  | Must | I, T | — | — | CAFIITK-104 (Done) | TC-NFR24 — Secret scan (gitleaks) over the full history on every PR (CAFIITK-170) | Security | — | Pass (direct verification) |
| NFR-25 |  | Must | I, T | UC-23, UC-24 | US-41 | CAFIITK-105 (Done), CAFIITK-166 | TC-US41-AC1…AC3 | Security | #47 | Pass |
| NFR-26 |  | Must | I, T | UC-21 | US-38 | CAFIITK-106 (To Do), CAFIITK-163 | TC-US38-AC1…AC4 | Security | — | Not run |
| NFR-27 |  | Should | I | — | — | CAFIITK-107 (To Do) | TC-NFR27 | Security | — | Not run |
| NFR-28 |  | Must | I | — | — | CAFIITK-108 (To Do) | TC-NFR28 | Integration, Inspection | — | Not run |
| NFR-29 |  | Must | T | — | — | CAFIITK-109 (To Do) | TC-NFR29 | Integration, Inspection | — | Not run |
| NFR-30 |  | Must | T, I | — | — | CAFIITK-110 (To Do) | TC-NFR30 | Integration, Inspection | — | Not run |
| NFR-31 |  | Should | D | — | — | CAFIITK-111 (To Do) | TC-NFR31 | Integration, Inspection | — | Not run |
| NFR-32 |  | Should | D | — | — | CAFIITK-112 (Done) | TC-NFR32 — Student-flow client tests and a manual run (CAFIITK-178) | E2E | — | Pass (direct verification) |
| NFR-33 |  | Must | D | — | — | CAFIITK-113 (Done) | TC-NFR33 — Manual walkthrough in Chrome and Firefox, 360 px and desktop (D2 walkthrough) | E2E | — | Pass (direct verification) |
| NFR-34 |  | Could | D | — | — | CAFIITK-114 (To Do) | TC-NFR34 | E2E | — | Not run |
| NFR-35 |  | Must | A | — | — | CAFIITK-115 (Done) | TC-NFR35 — CI backend job fails below 80% coverage (CAFIITK-170) | CI, Inspection | — | Pass (direct verification) |
| NFR-36 |  | Must | A | — | — | CAFIITK-116 (Done) | TC-NFR36 — CI client job fails below 80% coverage (CAFIITK-170) | CI, Inspection | — | Pass (direct verification) |
| NFR-37 |  | Must | I | — | — | CAFIITK-117 (Done) | TC-NFR37 — Concurrency tests run on PostgreSQL 16 via testcontainers (CAFIITK-169, 172) | CI, Inspection | — | Pass (direct verification) |
| NFR-38 |  | Must | T | — | — | CAFIITK-118 (Done) | TC-NFR38 — Pricing engine is a pure function with DB-free unit tests (CAFIITK-144) | CI, Inspection | — | Pass (direct verification) |
| NFR-39 |  | Must | I | — | — | CAFIITK-119 (Done) | TC-NFR39 — CI regenerates the Dart client and fails if it differs (CAFIITK-176) | CI, Inspection | — | Pass (direct verification) |
| NFR-40 |  | Must | I | — | — | CAFIITK-120 (To Do) | TC-NFR40 | CI, Inspection | — | Not run |
| NFR-41 |  | Must | I | — | — | CAFIITK-121 (Done) | TC-NFR41 — CI runs on every PR; required checks block the merge (CAFIITK-170) | CI, Inspection | — | Pass (direct verification) |
| NFR-42 |  | Must | A | — | — | CAFIITK-122 (To Do) | TC-NFR42 | Analysis | — | Not run |
| NFR-43 |  | Must | I | — | — | CAFIITK-123 (To Do) | TC-NFR43 | Analysis | — | Not run |
| NFR-44 |  | Must | I | — | — | CAFIITK-124 (To Do) | TC-NFR44 | CI, Inspection | — | Not run |
| NFR-45 |  | Must | I | — | — | CAFIITK-125 (Done) | TC-NFR45 — Branch protection: one non-author approval and green CI (CAFIITK-173) | CI, Inspection | — | Pass (direct verification) |

## Notes

- **E2E checks:** requirements verified by demonstration (D) or end to end (E2E) were also exercised by hand in the D2 walkthrough on the Docker Compose stack, in Chrome and Firefox. That covered ordering, tracking, cancel and modify, the kitchen queue and transitions, an agent run with a real LLM call, and proposal decisions.
- **Agent logging:** a few agent behaviours are under review for Sprint 3 even where the listed test cases pass. One is tool-call logging in heuristic runs, which bears on FR-62.
- **Source of truth:** this file is generated from the repository and Jira; the SRS §6.3 table itself has not been edited.
