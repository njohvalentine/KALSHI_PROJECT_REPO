# Architecture (Draft for Client Review)

**Status: draft, not final.** This describes the system as it stands after Milestone 3 and the extras added at the client's request, and the plan for the rest. Items marked **Open** still need a decision or an answer from you. A step-by-step explanation of the agent graphs is in `docs/agent/GRAPHS.md`.

Last updated: 2026-10-15.

---

## 1. What we are building

An AI research assistant for Kalshi prediction markets, focused on **soccer, baseball and tennis**. You pick a game (for example, "Arsenal vs Chelsea"). It researches the game on the web, checks what it found against the sources, estimates the probability of each outcome with three independent forecasts, and compares them with Kalshi's price to show where the price may be worth a closer look. Every claim comes with a source link. A person decides whether to bet.

**The main question is whether it finds genuine opportunities, not only research.** We test that against what really happened before any real money is used (section 5).

**It does not place bets on its own.** Any bet needs a person to approve it. During testing no bets are placed at all.

## 2. What exists today, and what does not

| Part | State |
|---|---|
| Sign-in (one account, created by the operator with a script) | **Built** |
| Games list: upcoming soccer, baseball and tennis games with start times, buy and sell prices and, where researched, our estimate; filter by sport, search | **Built** (15 leagues and tours by default; a setting) |
| Research per game: a planner chooses angles, several researchers search the web in parallel, results with source links | **Built**, tested on real games |
| Reading each cited page and checking every claim against it (supported, page says something different, could not check) | **Built**; only supported claims go on to the forecasters |
| Three independent forecasts per game (they never see Kalshi's price), combined with the median; a plain AI call with no research as a comparison | **Built** |
| Markets beyond the game winner: total goals or runs, both teams to score, margin of victory | **Built** (soccer: all three; baseball: total runs and margin) |
| Comparison with the price a bet could really be placed at, after fees; "worth a look" flag with the reasons shown | **Built**; the limits behind the flag are placeholders until we have scored real forecasts |
| Result pages, an Opportunities page (researched games ranked by the gap at today's prices) | **Built** |
| Record of every forecast with the market price at that moment, and scoring against what happened | **Built**; the first real results come as games finish |
| Watcher: alerts recorded in the app, optional automatic research of upcoming games (off, capped) | **Built**; alerts go to a chat message once you tell us which application |
| Accuracy report and results dashboard | Planned (Milestone 4); needs about 30 or more finished games |
| Approval screen: prepare, check, approve or reject, and place in a simulation; settled when the game ends | **Built** (simulated: no order is sent to Kalshi) |
| Real orders on Kalshi | Planned, last, only on your approval |

**Important wording on the result page:** a claim marked "Supported" means the page itself says it. "Could not check" means the page could not be read, does not say it, or the claim was worked out rather than stated. Only supported claims are used. "Worth a look" is never a recommendation.

### Update 2026-10-15

Since the first draft: Telegram alerts are live; tickets of several games exist (simulated); the Games page can list every sport Kalshi offers, with the sports we have no scores for marked "not yet measured", and the NBA is supported; a replay tool tests ideas on saved evidence; 10 browser tests and 551 backend tests exist. The accuracy results (61 finished games) show no sign of an edge over Kalshi's price; see `docs/MILESTONES.md`, Milestone 4.

## 3. How it works

```
 Kalshi game
      |
      v
 [1] LEAD AGENT ........ reads the game, plans which angles to research                (built)
      |
      v
 [2] RESEARCHERS (several, at the same time)
      each searches the web on one angle and returns facts with links                  (built)
      |
      v
 [3] READ AND CHECK SOURCES .. reads each cited page, labels each claim               (built)
      |                        supported / page says something different / could not check
      v
 [4] FORECASTERS (three, independent) each estimates every outcome                     (built)
      |   plus one plain AI call with no research, for comparison
      v
 [5] COMBINE ........... median of the three, with how far apart they were             (built)
      |
      v
 [6] MARKET COMPARER ... compares with the price a bet could be placed at, after fees (built)
      |
      v
 [7] HUMAN APPROVAL .... a person approves or rejects a bet                           (built, simulated)
      |
      v
 [8] ORDER STEP ........ simulated today; a real order only after your approval and later  (planned)
```

| Step | What it does | Why it exists |
|---|---|---|
| Lead agent | Chooses research angles for this game (injuries and lineups, recent form, head-to-head, scoring, venue or surface, probable pitchers, betting odds) | One place decides what is worth looking into |
| Researchers | Each takes one angle, searches the web, returns one fact per line with links | Different angles give different evidence; running them together saves time |
| Read and check sources | Opens each cited page, saves its text, and checks every claim against it; a verdict stands only with an exact quote from the page | So "cited" becomes "checked"; wrong claims were caught in real runs |
| Forecasters | Three independent estimates for every outcome, from the checked facts only | Independent views are steadier than one; not seeing the price stops them just copying it |
| Plain AI call | The same question with no facts at all | Shows what the research added |
| Combine | Median, with the lowest and highest estimate kept | One clear answer, plus a measure of disagreement |
| Market comparer | Compares with the price a bet could actually be placed at, and shows the gap after Kalshi's fee | A bet only makes sense if we disagree with the market by enough |
| Flag "worth a look" | Only when the gap is large enough but not suspiciously large, the research moved our estimate away from the plain AI call toward the gap, the forecasters agree, enough claims were supported and enough contracts are on offer | The first soccer run showed that without these tests almost everything looked like an opportunity |
| Human approval | A person says yes or no on the exact order | You stay in control of your money |
| Order step | Places the approved bet | Kept separate so an approval can never cause a bet to be sent twice |

### Why this design and not the alternative

We considered two ways to organize the AI agents.

**Design 1 (chosen): one lead agent, with helper agents for each task.** The lead agent plans and hands tasks to helpers (researchers, forecasters). Helpers report back and do not create further helpers.

**Design 2 (rejected): a team of equal agents, each able to create more agents of its own.**

| | Design 1: one lead + helpers (chosen) | Design 2: many agents, each creating more |
|---|---|---|
| Who decides what happens | One place: the lead agent | Spread across several agents |
| Cost | Predictable: hard limit on helpers per run | Can grow unexpectedly |
| Testing | Easy: same steps every run | Hard: the shape of a run changes |
| Debugging | Follow one tree from the lead down | Harder to trace who started what |
| Human approval | One clear stop before any bet | Harder to guarantee |
| Evidence it forecasts better | A published research system uses this shape and reports large gains over a single agent* | None found for this task |

\*Reported as about 90% better on research tasks at about 15 times the AI cost, from secondary summaries; measured on general research, not betting forecasts. We will test it on our own system (section 5).

**What we give up:** helpers cannot restructure the work themselves. **When we would revisit:** only if testing shows the lead agent's limits are holding helpers back, with evidence.

## 4. Technology

| Part | Choice | Reason |
|---|---|---|
| AI models | OpenAI (your key). Planner and claim checker `gpt-5.4-mini`, researchers and forecasters `gpt-5.4`, all changeable in settings | You supplied the key |
| Agent framework | LangGraph (Python) for the research step; the later steps run as plain code, each saving its result | The research fans out in parallel; the later steps do not, so saved progress between them adds nothing |
| Evidence gathering | OpenAI web search tool, then our own safe download of each cited page (public addresses only, size and time limits, every redirect checked) | The search tool returns a link but no page text; we need the text to check claims |
| Market data | Kalshi public API (no key needed to read) | Games, outcomes, prices, rules, fees. Kalshi has no sports filter, so the Games page reads a configured list of series (leagues and tours) |
| Backend | FastAPI (Python) | Runs research in the background and serves the web app |
| Web app | Next.js with shadcn/ui, light theme | Pages: Games, Opportunities, Prediction (runs and results), Approval, Results |
| Database | PostgreSQL | Runs, saved sources and page text, claim checks, forecasts, a record of every forecast, alerts, accounts |
| Packaging | Docker Compose: database, backend and web app start together | One command to run everything |
| Tracing | LangSmith (free tier; consent given) | Shows what every agent did and what it cost |
| Sign-in | Email and password, one account created by the operator with a script; no registration page | Single-user tool; a public registration page would let strangers approve bets |

**Open:** which leagues and tours you trade. The Games page shows 15 by default (Premier League, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, Japan's NPB, Korea's KBO, ATP, WTA and both challenger tours).
**Open:** which chat application you want alerts in (you answered "chat message"; Telegram is the simplest).

## 5. How we will know if it works

The honest question is whether the system predicts better than the market price alone. Kalshi prices are already well calibrated, and sports prices especially, so the room to beat them is small. We test before any real money is used.

**Live paper trading.** Every forecast is recorded with Kalshi's price at that moment, **before the game starts**; when the game ends, the result is added. **No bets are placed and no money is at risk.** The records are made only from live forecasts, so nothing about the result can leak into them. This is the main test, and sports results arrive within hours or days. The command `score-records` prints the scores; below about 30 finished games it says there is too little to conclude anything.

**What we compare, on the same outcomes:** our forecast, one plain AI call with no research, and Kalshi's price (the middle of buy and sell). Scores use the Brier score (a standard accuracy measure for probabilities; lower is better), shown per kind of market (winner, total, both teams to score, margin), and what buying the chosen side at the market price would have paid.
- If our forecast does not beat the plain AI call, the research adds cost without accuracy, and we simplify.
- If it beats the plain call but not Kalshi's price, it is a useful research assistant but not a betting edge.
- If it beats both, it is worth taking further.

**What we already saw in real runs:** on the first games the forecasts were close to the plain AI call and far from the market on some markets; the market is usually the better informed side, so a large gap is more often the model's mistake than an opportunity. The flag "worth a look" was therefore tightened (the research must move the estimate away from the plain AI call, and a suspiciously large gap is not flagged). The scores will show whether any of this is real.

The rule for when real betting could be considered is **deferred**; we will agree it after seeing real results.

## 6. Costs

- A run (research, page reading, claim checking, three forecasts and the comparison) takes about one to one and a half minutes and cost **about 0.32 to 0.63 USD per game** in the real runs (the more markets a game has, the more it costs). The result page shows the cost of each step.
- Built-in limits: at most 4 researchers per run, at most 3 searches each, a cap on output length per call, at most 2 runs at the same time, and one active run per game. A run that costs more than a set warning level is flagged.
- Every press of Research spends credit, and the button says so. Automatic research of upcoming games exists but is **off**; if you switch it on you set how many games it may research per day.

## 7. Risks you should know about

1. **No guaranteed edge.** The system may be a good research assistant but not a way to beat the market. The testing in section 5 finds this out cheaply.
2. **Sports contracts are legally contested.** Several US states and federal appeals courts have ruled against Kalshi's sports contracts (as of late September 2026). What you can trade depends on your state. **Open:** your state.
3. **Fees.** Kalshi charges trading fees that reduce small edges. We read each series' fee type and multiplier from Kalshi and use the published formula, which we have so far only seen described by third parties; it will be confirmed against Kalshi's own schedule.
4. **Research quality.** Web evidence can be wrong or outdated. Checking against the pages caught real mistakes, but in the real runs only about a quarter to a half of the cited claims could be confirmed, because many pages (bookmaker sites, pages built by scripts, PDFs) cannot be read by an automatic reader.
5. **Keys.** The Kalshi key was shared in a chat. For real trading, create a new one and share it more safely. Keys are kept only in local settings files, never in the code.

## 8. Questions for you

1. Which US state are you in?
2. Which leagues and tours do you trade?
3. Which chat application do you want alerts in? We suggest Telegram.
4. What should "help" cover: finding and researching bets, or also suggesting how much to bet?
5. What is the most you want to risk on one bet, and in one day? (The approval screen enforces these limits; for now it uses placeholders.)
6. Will you create a new Kalshi key (limited permissions if Kalshi offers them) before any real trading?

## 9. What happens next

1. The first real scores as games finish; keep researching games so the record grows.
2. Milestone 4: a short accuracy report once there are enough finished games.
3. Chat alerts, once you tell us the application.
4. Your betting limits (the most per bet and per day), then, only if the results justify it, real orders.
