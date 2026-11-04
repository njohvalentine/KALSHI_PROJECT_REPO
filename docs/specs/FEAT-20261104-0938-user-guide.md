# Spec: user guide for the client (FEAT-20261104-0938)

Branch `feature/security-hardening` (base `master`). Format chosen by the user (4 Nov): Markdown file plus a PDF.

## What is wanted, and the reasons behind it

The client wrote (4 Nov): "I don't know how it works or how to access and operate it", asked for a demo, and asked to close the contract. The user replied that a guide would be sent. The user's answer on access: the client has given no server and will most likely run it on his own computer.

Two reasons stack up. (1) He needs to **get it running**: nothing is hosted for him (the old server link shows the old design and I do not recommend sending it). (2) He needs to **use and read it**: the pages, the numbers and the limits, in plain language, including the honest finding that the forecasts have not beaten the Kalshi price. A guide with only the second would not let him start; with only the first he would not know what he is looking at.

## What I verified (read 4 Nov)

- `README.md` has the set-up steps (Docker, `.env` from `.env.example`, five required values, `docker compose up -d --build`, health check, `create-user`, sign in at 127.0.0.1:3000). No Kalshi key is needed to run (Kalshi is only read). A VPN is needed only if Kalshi is not reachable from his country; I have not verified Texas and the guide says so as a check, not a fact.
- His repository is `njohvalentine/KALSHI_PROJECT_REPO`. **`master` is the old state; the current work is on `feature/security-hardening`** (not merged, by your decision), so the guide must tell him to use that branch. The last 3 local commits (this spec, least privilege, screenshots) are **not pushed**: pushing needs your go-ahead.
- Costs measured on real runs: a full research run about 0.43 USD (95 earlier runs average 0.43), a lineup update about 0.20, limits 5 games and 5 updates per 24 hours by default.
- The README title still says "research assistant"; the client's name for it is "Our Agent". The guide says "Our Agent". Whether to rename the README is a separate small item for you.

## Design

`docs/USER-GUIDE.md` (with images in `docs/user-guide/`) and `docs/USER-GUIDE.pdf`, written in plain English, "Our Agent", no contractions:
1. What Our Agent is and is not: researches a game, gives a probability for each outcome, compares with the Kalshi price; a person approves; **paper trading only, nothing is ever ordered**; the honest status with the real numbers from `score-records` on the day of writing.
2. What you need: Docker, an OpenAI key with credit (cost per run), optional Odds API key and Telegram, a VPN only if Kalshi is not reachable.
3. Get the code: clone, switch to `feature/security-hardening`.
4. Set up in six steps (from the README, tested): `.env` (what to put, what never to share), start, check, make the account, sign in, stop.
5. A first walk (about 30 minutes, about 1 USD): Games, Research one game, the result page, Ranking, Update with lineups, Opportunities and the alerts, Approval (a simulated order), Results; each with a screenshot taken today from a fresh set-up.
6. How to read the numbers: Brier score, the gap after fees, "Worth a look" is not a recommendation, the confidence label (and that it barely separates accuracy so far), source labels, "too few games".
7. Costs and limits, what the daily limits are for, what is off by default (automatic research, automatic updates, Telegram).
8. Problems: health check fails, backend will not start (which log line), no Kalshi, no OpenAI credit; where to read more (`docs/RUNBOOK.md`, `docs/HOW-IT-WORKS.md`).
9. Honest limits: no edge shown so far, small samples, news is not seen, only simulated orders.

The PDF is made from the Markdown with Chrome's print to PDF (installed on this computer); the Markdown is the source. No new dependency: the small Markdown-to-HTML step is a throwaway script outside the repo.

## How the set-up steps are tested

I clone the branch into a new empty folder, make a `.env` with throwaway values (not the real one: never read or copied), start it under a different Compose project name with its own volume, follow the guide's steps word for word, and take the screenshots from that copy. This needs the ports 3000 and 8000, so the running stack is stopped (not deleted) while I do it and started again afterwards. The OpenAI key is the one in the real `.env`, passed through the shell for the one real research run of the walk; it is never printed or written. **This run costs about 0.5 USD** (I will ask before starting it).

## Not done

No hosted deployment, no change to the app, no README rename (offered above), no push (your decision), no video.

## Checks to state at close

Lateral spread: the README and RUNBOOK set-up text is compared with the guide, and any difference is fixed in the older file or stated. Causal depth: the client's two reasons (get it running, understand it) are both covered; whether he can reach Kalshi from his location is **not** verified and is written as a check for him.
