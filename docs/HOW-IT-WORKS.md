# How the system works

This document explains, in plain and complete sentences, what the system is, what it does step by step, which parts are AI agents, which strategies it uses, how we measure whether it works, and what every term means. You do not need to know programming to read it. The last section lists the code files for developers.

It describes the system as it is on 2026-10-15. Every statement was checked against the code on that day. Where this document and an older document disagree, this document is the one that was checked against the code.

Related documents: `README.md` (setup), `docs/RUNBOOK.md` (how to run and look after it), `docs/ARCHITECTURE.md` (the design and the reasons), `docs/MILESTONES.md` (what is built), `docs/ACCURACY-REPORT-2026-10-15.md` (how good the forecasts are), `docs/agent/GRAPHS.md` (the research steps in more technical detail).

---

## 1. What the system is for

Kalshi is an exchange where people buy and sell contracts about future events. For sports, a contract might say "Arsenal wins this match". If Arsenal wins, the contract pays one dollar. If Arsenal does not win, it pays nothing. The price of the contract, between zero and one dollar, is therefore also the crowd's estimate of the probability. A price of 60 cents means the crowd thinks Arsenal has about a 60 percent chance.

This system is an AI research assistant for those markets. For a game you choose, it searches the web for facts about the game, checks those facts against the web pages they came from, asks several AI forecasters to estimate the probability of each outcome, and compares those estimates with the Kalshi prices. When the estimates differ from the price by enough, it marks the market as "worth a look".

Three rules shape the whole design:

1. **A person decides.** The system never places a bet on its own. A person has to approve every order.
2. **Nothing real is ordered.** The system only reads from Kalshi. The approval screen exists, but the orders on it are simulated. There is no code in the system that sends an order to Kalshi. A test makes sure of this.
3. **The question is whether it finds real opportunities,** not only whether it writes good research. Because of that, every forecast is saved before the game starts and scored after the game ends.

---

## 2. The path from a game to a flag, in order

When a person presses Research on a game, these steps happen:

1. **Read the game from Kalshi.** The system downloads the game, its outcomes, its rules and its start time. For some sports it also loads the related markets of the same game, such as the total number of goals, both teams to score, or the winning margin.
2. **Plan the research.** An AI planner decides which angles are worth looking into, for example injuries and lineups, recent form, head-to-head history, venue and rest days, and betting odds.
3. **Research in parallel.** One AI researcher per angle searches the web. Each one returns short factual lines with links to the pages they came from.
4. **Download the cited pages.** The system opens each page the researchers cited, safely, and saves its text.
5. **Check every claim.** An AI checker reads the saved page text and decides, for each claim, whether the page really says it. A verdict only counts if the checker also quotes the page and the quote really is in the saved text.
6. **Forecast.** Three independent AI forecasters each estimate the probability of every outcome, using only the claims that were confirmed. They never see the Kalshi price. At the same time, one plain AI call makes the same estimate with no research at all, for comparison.
7. **Combine.** The system takes the median of the forecasters' numbers for each outcome and keeps the lowest and highest numbers to show how much they disagreed.
8. **Compare with the market.** The system reads fresh Kalshi prices, calculates the fee, and works out the gap between our probability and the price a bet could really be placed at.
9. **Flag.** A market is marked "worth a look" only if it passes several tests (section 5.5).
10. **Save a record.** The forecast, the plain-AI estimate and the market price at that moment are saved together as a frozen record, before the game starts. After the game ends, the result is added, so we can score the forecast.

A run takes about one to one and a half minutes. In the real runs it cost between about 0.32 and 0.63 US dollars per game (the more markets a game has, the more it costs), and up to about 0.55 dollars for a basketball game with 48 markets.

---

## 3. The parts of the system

| Part | What it is | Where it runs |
|---|---|---|
| Database (PostgreSQL) | The only place where data is kept: runs, saved page texts, claim checks, forecasts, the frozen records, alerts, simulated orders and accounts. | In Docker, on your computer or server |
| Backend (FastAPI, Python) | Serves the web app, runs the research in the background, reads Kalshi, runs the watcher and sends alerts. | In Docker, port 8000 |
| Web app (Next.js) | The pages a person uses: Dashboard (how the forecasts compare with Kalshi), Games, Opportunities, Prediction (the research results), Approval and Results. | In Docker, port 3000 |
| Watcher | A background loop inside the backend. Every 10 minutes it re-reads prices for the games that were researched and raises alerts. | Inside the backend, switched on with a setting |
| Telegram alerts | Short messages sent to a Telegram chat when the watcher finds something. | Switched on with settings and a bot token |
| OpenAI | The AI models for planning, research, checking and forecasting. Paid per use. | OpenAI's servers |
| Kalshi | The source of games, prices, rules and fees. The system only reads from it. | Kalshi's servers, public read-only interface |
| LangSmith | An optional tracing service that records what every AI step did and what it cost. | LangSmith's servers |

The three local parts (database, backend, web app) are started together with Docker Compose. All ports are bound to the local computer, so nothing is reachable from outside unless the operator publishes it.

---

## 4. The agents

An agent here means a step that is carried out by an AI model with its own instructions. The system uses one lead agent and several helper agents. The helpers do not create more helpers. This keeps the cost predictable and the behaviour easy to test and trace. A design in which agents create further agents was considered and rejected; the reasons are in `docs/ARCHITECTURE.md`.

### 4.1 The planner (lead agent)

- **Job:** read the game and decide which research angles to look into, between two and four.
- **Model:** a smaller model (gpt-5.4-mini).
- **Rules it follows:** each angle covers one topic only. Betting odds are always their own angle, marked as a market-odds angle, and never mixed with other topics. It must not predict anything or state a probability. It picks angles that fit the sport (for example probable starting pitchers for baseball, the playing surface for tennis, back-to-back games for basketball). If it knows nothing specific about a sport, it uses general angles such as the latest news and the rules that decide the outcome.
- **Why it exists:** one place decides what is worth researching, instead of every researcher choosing for itself.

### 4.2 The researchers

- **Job:** each researcher takes one angle, searches the web, and writes up to ten findings. Each finding is one fact on its own line.
- **Model:** the larger model (gpt-5.4) with low reasoning effort, using OpenAI's web search tool. Up to three searches each, and up to four researchers per game, all at the same time.
- **Rules it follows:** one fact per line, so that a line can be checked against a page. Only dates that the page itself shows. Prefer official club, league and news pages. No calculations or inferences unless the page states the number. Odds only with the date the page shows, and not older than three days. Never a probability, a prediction or a recommendation.
- **Where the links come from:** only from the links that the search tool itself attached to the text, never from web addresses that the model typed in its answer. A line without a link is kept but marked as having no source.

### 4.3 The page reader (not an AI)

- **Job:** download each cited page and save its text, so the text can be used for checking and kept as a frozen copy.
- **Safety rules:** only http and https, only public addresses (never this computer, the database or a cloud address), every redirect checked again, limits on time and size, only text pages. Every outcome is recorded with a short reason, such as "blocked" or "too large". Nothing is skipped silently.
- **Limits we know:** many pages cannot be read by an automatic reader. About 204 claims in the measured runs were lost because pages refused the download (HTTP 403), and a smaller number because the page is a PDF or its content is built by scripts.

### 4.4 The checker

- **Job:** for each page, decide for every claim that was cited to it whether it is supported, not supported, or could not be checked.
- **Model:** the smaller model (gpt-5.4-mini) with medium reasoning effort. One call per page.
- **The safe default:** the default verdict is "could not check". A claim becomes "supported" or "not supported" only when the checker quotes the page and that quote is found in the saved page text. If the checker says "supported" without a real quote, the verdict is thrown away.
- **Strict rules:** every number, name and date in the claim must be on the page. A claim that was calculated rather than stated cannot be supported. Claims about odds, lineups, injuries or form need a date on the page that matches. A page that is only menus or a message that says "you are a robot" supports nothing. A claim the page does not mention is "could not check", never "not supported".
- **Protection against tricks:** the page text is treated as untrusted data. The checker has no tools. If a page contains a sentence that tells the checker what to answer, it achieves nothing, because only quoted text counts.

### 4.5 The forecasters

- **Job:** estimate the probability of every outcome of the game.
- **Model:** the larger model (gpt-5.4) with medium reasoning effort. Three forecasters by default, running at the same time.
- **What they see:** the game, its outcomes, the rules, and the confirmed claims only (up to 60 claims, each up to 500 characters, inside a marked block that is labelled as data, not instructions). **They never see the Kalshi price.** Betting odds that appear in a claim are to be ignored.
- **Three working styles:** the forecasters are copies of one model, so to make them think differently each gets a different way of working. The first weighs each fact on its own and then settles on probabilities. The second starts from the usual win rate of such a side and adjusts only as far as the facts justify. The third forms a first view, argues the strongest case for the outcome it rates least likely, and then gives final numbers. If more than three forecasters are configured, the styles repeat.
- **If the evidence is thin,** they are told to say so and stay closer to the usual base rate.
- **The answer is checked in code, not trusted:** every outcome exactly once; no probability of exactly 0 or 1; where exactly one outcome can happen, the probabilities must add up to about 100 percent (within 3 points) and are then scaled to exactly 100 percent. Related markets must agree: a higher line is never more likely than a lower one, winning by a large margin is never more likely than winning, and both teams to score is never more likely than more than 1.5 goals. A small disagreement is repaired by lowering the number that is too high, and the repair is written down. A large disagreement makes that forecast invalid. A forecast that fails is dropped, logged and counted.
- **Minimum:** at least two valid forecasts are needed. With fewer, there is no prediction, and the result page says why.

### 4.6 The plain-AI baseline

- **Job:** the same forecasting question, answered by one forecaster with no facts at all.
- **Why it exists:** it shows what the research adds. If our forecast is no better than this, the research did not help. The baseline is also used inside the flag rule (section 5.5).

### 4.7 The combiner (not an AI)

For each outcome, the system takes the median of the valid forecasts. The median is used because one odd forecaster cannot pull it far. The lowest and highest estimates are kept, and the spread (highest minus lowest) shows how much the forecasters agreed.

---

## 5. The strategies

### 5.1 Every claim needs a source, and the source is checked

A forecaster only sees a claim if a real web page was found for it and that page was confirmed to say it. The reasons: language models sometimes write facts that sound right but are not, and a link alone does not prove the page says it. In real runs, between a quarter and a half of the cited claims could be confirmed. That is a low share, but it is the share that can be trusted.

### 5.2 Forecasters are kept independent and blind to the price

The forecasters never see the market price. If they did, they would tend to copy it, and a comparison between our forecast and the market would mean nothing. Using three different working styles and taking the median makes the result steadier than one forecast.

### 5.3 Compare against the price a bet could really be placed at

Kalshi shows two prices for each side. To buy "yes" you pay the "yes" ask. To buy "no" you pay the "no" ask, which equals one dollar minus the best "yes" bid. The system compares our probability with the ask price of each side, and chooses the side with the larger gap. A side with no ask has no price and is never compared.

### 5.4 Fees

Kalshi charges a fee when you buy. For the usual fee type, the fee for one contract is 0.07 times a series multiplier times the price times (one minus the price). It is largest near a price of 50 cents. The system reads the fee type and multiplier from Kalshi for each series. If it cannot read them, it uses an assumed value and marks the result as assumed, so this is never hidden. This formula was confirmed only from secondary sources and still has to be checked against Kalshi's own fee schedule. Kalshi rounds fees up per order, which the system does not copy, so real fees can be a little higher.

The "gap after fees" is: our probability for the side, minus the price, minus the fee.

### 5.5 When a market is marked "worth a look"

A market is flagged only if every one of these is true. The limits are placeholders. They have not been tuned on results, and the accuracy report (section 7) explains why we have not changed them.

1. The gap after fees is at least 5 cents (`EDGE_MIN`).
2. The gap is not more than 15 cents (`EDGE_PLAUSIBLE_MAX`). A very large gap is more often the model's mistake than an opportunity, because the market is usually better informed.
3. The research moved our probability at least 5 points toward the gap, away from what the plain AI says with no facts (`MIN_RESEARCH_SHIFT`). If the research changed nothing, there is no reason to think it found something.
4. Even the least favourable forecaster still shows a gap on this side. If one of the three forecasters sees no edge, the flag is not given.
5. At least 5 claims were confirmed (`MIN_SUPPORTED_CLAIMS`), and there was some confirmed evidence at all.
6. At least 10 contracts are offered at the best price (`MIN_ASK_SIZE`), so the price is real.

If a market is not flagged, the result page lists the reasons. "Worth a look" is never a recommendation to bet. It only means a person might want to look more closely.

Every game also gets one plain answer, the same on the Opportunities page, the result page and in the alerts: **NO BET** when no market passed the tests, when the forecast is more than 12 hours old, or when there is no forecast or price. When a market did pass, the answer is "Worth a look", with the caution "NO BET is the default" for as long as the finished games do not show that our forecasts beat the Kalshi price, or while the sport has no scored results. Only a flag in a measured sport, while we are ahead of Kalshi by at least 0.005 on 30 or more games, is shown without the caution. The word BET is never used on its own.

### 5.5b The bookmakers are compared with the Kalshi price (shown, not used to flag)

For winner markets, when the odds feed covers the league, the system also reads the bookmakers' prices. Each bookmaker's margin is removed by scaling its prices to 100 percent, exchanges are left out, and the median over the bookmakers is the consensus. For each side the system works out the gap against the Kalshi price the same way as for our own forecast: the bookmakers' probability minus the ask price minus the fee. It also checks that enough contracts are offered, and whether the bookmakers favour the same side as we do. This is shown on the result page and on the Opportunities page and is scored on the Dashboard as games finish. It does not change when a market is flagged. Total, margin and both-teams-to-score markets have no bookmaker price, because the feed is read for head-to-head prices only.

### 5.5c The free check before research

Research costs money, so the Games page can check games against the bookmakers first, for free in OpenAI terms. A game is "worth researching" when, for a winner outcome and a side, the bookmakers' consensus probability minus the Kalshi ask price minus the fee is at least 5 cents, at least 10 contracts are offered at that price, and the game starts within 36 hours. Games whose league has no bookmaker source, or that the feed does not list, are shown as "cannot be screened" and are never treated as promising or not promising. The check runs only when a person presses a button, because every league read uses one of the 500 free odds credits of the month, and it refuses to read when fewer than 100 are left. It does not stop anyone from researching. The first real check, on 2026-10-17, looked at 53 soccer games in six leagues with about 21 bookmakers each: the best gap anywhere was +0.9 cents and the average was -1.2 cents after fees, so none was worth researching under this rule. That is one day of data. Whether the rule picks better games is to be tested on results before it is used as a filter.

### 5.6 Old forecasts are not flagged

The Opportunities page re-reads today's prices for games that were already researched, and applies the same rules again. A forecast older than 12 hours is shown greyed out and is never flagged, because the facts it rests on may be out of date. No AI call is made on that page.

### 5.7 Tickets (simulated)

A ticket is a bundle of bets, called legs, that pays only if every leg wins. A ticket can have up to 20 legs and can mix sports. There is at most one leg per Kalshi market group, but several markets of the same game are allowed, and those are marked as "rough" because they move together. The combined price is the product of the leg prices. That is a simulation. A real Kalshi combined quote can differ, and ours is more optimistic than the real one would be.

### 5.8 The approval flow (simulated)

An order is prepared, then waits for a person. A person approves or rejects it, and an approved order is placed in a simulation by a separate press, which records a simulated fill at the price of that moment. The system checks before approval and placement:

- the order has not expired (10 minutes by default)
- it is within the limits (placeholders: 10 contracts, 5 dollars per order, 20 dollars per day)
- each leg's game has not started
- each leg's forecast is recent (12 hours or less)
- the price has not moved against us by more than 2 cents
- enough contracts are offered
- no stop rule has triggered: after the simulated results of the last 24 hours, or since a review date, lose more than a set limit, no new order is allowed (off until the client approves a value; see `docs/RISK-FRAMEWORK.md`)
- the leg is still worth a look (this one only warns)

Each change of state is a single, atomic database update, so a double click or a retry cannot place an order twice. Every change is written to an append-only history. When the game has ended, the system settles the simulated orders and shows what they would have paid.

### 5.9 The watcher and the alerts

Every 10 minutes the watcher re-reads prices for researched games that have not started and raises alerts of four kinds:

- **Worth a look:** a researched game has flagged markets at today's prices.
- **Market moved:** a market moved 8 cents or more since the forecast. The alert says the market may know something we do not and suggests researching again. It does not say to bet.
- **No longer worth a look:** markets we flagged no longer show a gap.
- **Starting soon:** a flagged game starts within 60 minutes, and the forecast may be out of date.

Each alert is raised once per game run and kind. There is a cooldown of 60 minutes for the same kind and game, and a limit of 6 alerts per hour. Alerts held back by these limits are recorded as "held back", with the reason. Alerts are recorded in the app and also sent to Telegram when it is switched on.

Automatic research (the watcher starting runs by itself) exists, but it is off. It would need a daily cap, because every run costs money.

### 5.10 Finding all sports

The system does not use a fixed list of leagues any more. Once a day it reads Kalshi's list of sports series and picks the series that are single games, meaning that the title ends in Game, Match or Fight. It leaves out tournaments and futures. A sport appears on the Games page as a measured sport only after it has at least 20 scored games (`MEASURED_MIN_GAMES`). Until then, the app says "not yet measured", because the flag has never been tested there. Alerts, automatic research and the daily batch use only measured sports.

---

## 6. How we measure whether it works

### 6.1 The frozen record

For every market of every researched game, the system saves a record before the game starts: our probability, the lowest and highest forecaster, the plain-AI probability, the number of confirmed claims, the Kalshi bid and ask at that moment, the fee, and what the flag rule said. After the game ends, a command called `resolve-records` adds the result. It checks games that started more than three hours ago. No bet is placed and no money is at risk. Nothing about the result can leak into a record, because the record is made before the game.

### 6.2 The score

`score-records` compares, on the same outcomes, three numbers: our probability, the plain-AI probability, and the Kalshi price (the middle of bid and ask). The score is the Brier score. For each outcome, take the probability, subtract the result (1 if it happened, 0 if not), square the difference, and average over all outcomes. A forecast that always says 50 percent scores 0.25. A perfect forecast scores 0. Lower is better.

The scores are shown per sport, league, kind of market and amount of confirmed evidence, together with the number of games. The system also reports what buying the chosen side at the ask price would have paid. It says "too few games" below about 30 games and below 5 games in a group.

### 6.3 What the possible answers mean

- If our forecast does not beat the plain AI, the research adds cost and no accuracy.
- If it beats the plain AI but not Kalshi, it is a useful research assistant, but not a betting edge.
- If it beats both, it is worth taking further.

### 6.4 The replay tool

The replay tool (`replay-forecasts`) repeats the forecasting step and the flag rule on saved evidence, so an idea can be tested without paying for new research. It does not write anything back. Because the models are not deterministic, even replaying the same settings gives slightly different numbers, so the replay first measures this noise. To avoid fooling ourselves, the rules for an experiment are written down before it runs: which candidates, which games are for tuning and which are held back, and how large a gain must be. A candidate is kept only if its gain also appears on the games that were held back.

---

## 7. Results so far

On 62 finished games (on 2026-10-15), the Brier scores on the 481 outcomes that have all three numbers were: ours 0.1945, plain AI 0.1970, Kalshi price 0.1755. In plain words:

- The Kalshi price was clearly more accurate than our forecasts.
- Our research added almost nothing over the plain AI. It helped a little in tennis and not in soccer.
- Buying the chosen side at the ask price lost about 6 cents per contract on average. The 35 flagged bets lost about 13 cents on average, but 35 bets are too few to conclude anything.
- Tests of more forecasters and of higher reasoning effort did not hold up on games they had not been tuned on, so the settings were not changed.
- There is no sign of an edge yet. Sixty-two games is too few for a final verdict.

The full report, with all numbers and caveats, is `docs/ACCURACY-REPORT-2026-10-15.md`.

---

## 8. Glossary

**Agent.** A step of the system that is carried out by an AI model with its own written instructions, such as the planner or a researcher.

**Angle.** One topic of research for a game, for example "injuries and lineups" or "betting odds". The planner chooses the angles. Each angle gets one researcher.

**Ask.** The lowest price at which someone is willing to sell a contract. This is the price you pay to buy immediately.

**Baseline (plain AI).** The estimate made by one AI call with no research. It shows what the research adds.

**Bid.** The highest price at which someone is willing to buy a contract. This is the price you get if you sell immediately.

**Bookmaker consensus.** The median, over the bookmakers, of their prices for an outcome after each bookmaker's margin is removed. It is compared with the Kalshi price and with our forecast.

**Brier score.** The average squared difference between a forecast probability and what happened (1 or 0). Lower is better. A constant 50 percent scores 0.25.

**Checked fact (supported claim).** A claim for which the cited page was downloaded and the checker quoted that page, with the quote found in the saved text.

**Claim.** One factual line written by a researcher, usually with a link to the page it came from.

**Combined price (of a ticket).** The product of the prices of its legs. It is a simulation and is more optimistic than a real combined quote from Kalshi.

**Contract.** The thing you buy on Kalshi. A "yes" contract pays one dollar if the event happens and nothing if it does not. A "no" contract pays one dollar if it does not happen.

**Edge.** A real advantage over the market, meaning that your probabilities are better than the prices over time. We have not found one yet.

**Evidence level.** How many claims were confirmed for a game: none, one to four, or five or more.

**Event (Kalshi).** A group of related markets, for example all the outcomes of one match.

**Fee.** The cost Kalshi charges when you buy. See section 5.4.

**Flagged ("worth a look").** A market that passes all the tests in section 5.5. It is not a recommendation.

**Forecaster.** An AI call that estimates probabilities from the confirmed claims, without seeing the price.

**Frozen record.** The saved forecast, plain-AI estimate and market price of one outcome, made before the game and never changed except for adding the result.

**Gap (after fees).** Our probability for a side, minus its price, minus the fee.

**Kalshi.** The exchange where the contracts are traded. The system only reads from it.

**Leg.** One bet inside a ticket: one market and one side.

**Lead agent.** Another name for the planner.

**Market.** One yes or no question on Kalshi, for example "Arsenal wins" or "more than 2.5 goals".

**Market-odds angle.** The research angle about betting odds. It is kept apart from other angles.

**Measured (sport).** A sport with at least 20 scored games. Only for these is the flag considered tested.

**Median.** The middle value of a list of numbers. With three forecasts, the one in the middle.

**Paper trading.** Recording forecasts and scoring them as if they were bets, without placing any real order.

**Plain AI call.** See baseline.

**Probability.** A number between 0 and 1 (or 0 and 100 percent) for how likely something is.

**Replay.** Re-running the forecasting step on saved evidence, to test a change without paying for new research.

**Research shift.** How far the research moved our probability away from the plain-AI probability, toward the gap.

**Run.** One research job for one game, from the press of the Research button to the saved result.

**Series (Kalshi).** A family of repeating events, for example all NBA games. A series has a title, tags that name the sport, and fee settings.

**Settled.** A simulated order whose game has ended and for which the paper result was worked out.

**Screening (the free check).** Comparing the bookmakers' prices with the Kalshi price before any research, to see which games are worth researching. It uses no OpenAI credit.

**Spread (of the forecasters).** The highest forecaster probability minus the lowest, for one outcome. A large spread means the forecasters disagreed.

**Stale forecast.** A forecast older than 12 hours. It is shown greyed out and is not flagged.

**Telegram.** The chat application used for alerts.

**Ticket.** A bundle of legs that pays only if every leg wins.

**Watcher.** The background loop that re-reads prices for researched games and raises alerts.

---

## 9. Limits and what is not built

- **No edge found yet.** See section 7. The system is for now a research assistant, not a proven way to beat the market.
- **Real orders are not built.** There is no code that sends an order to Kalshi. Building it is Milestone 7, which is a no-go for now. It would also need a new Kalshi key, the limits chosen by the client, the Kalshi developer agreement read, and a real combined-order flow.
- **Evidence is thin.** Many pages cannot be read automatically, and the strict checking rules throw out claims that cannot be shown to be on the page. Reading PDFs and some table pages is not built because the measured loss was small.
- **The flag limits are placeholders.** They have not been tuned. The accuracy report explains why they were not changed.
- **Sample size.** Sixty-two finished games is a modest sample, and the markets of one game move together, so the real sample is about 62 and not 485.
- **The bookmaker comparison is built but switched off.** It records the bookmakers' consensus next to our forecast, but it has no scored results yet.
- **Legal position.** Sports contracts on Kalshi are legally contested in several US states. What can be traded depends on where the user lives. We have not yet been told the client's state.
- **Secrets.** The Telegram bot token can appear in the backend log when alerts are on. Logs must not be shared.

---

## 10. For developers: where things are in the code

| Topic | Files in `backend/app/` |
|---|---|
| Research graph (planner and researchers) | `research/graph.py`, `research/model.py`, `research/prompts.py`, `research/claims.py` |
| Page downloading | `research/fetch.py` |
| Claim checking | `research/check.py` |
| Forecasting, baseline, validation | `research/forecast.py`, `research/predict.py` |
| Price comparison, fees, the flag rule | `research/compare.py` |
| The steps after research, in order | `research/pipeline.py`, `research/runner.py` |
| Frozen records, scoring, replay | `research/records.py`, `cli.py` (`resolve-records`, `score-records`, `replay-forecasts`), `research/replay.py` |
| Starting a run and reading results | `runs.py` |
| Opportunities page | `opportunities.py` |
| Tickets and approval | `orders.py` |
| Watcher and alerts | `monitor.py`, `alerts.py`, `telegram.py` |
| Finding sports and games | `discovery.py`, `games.py`, `measured.py` |
| Kalshi reading | `kalshi.py` |
| Bookmaker benchmark (off) | `odds.py` |
| Settings and their defaults | `config.py` (documented in `.env.example`) |

The web app is in `frontend/` (pages under `frontend/app/`, shared parts under `frontend/components/`). The tests are in `backend/tests/` (about 550) and `frontend/e2e/` (browser tests).
