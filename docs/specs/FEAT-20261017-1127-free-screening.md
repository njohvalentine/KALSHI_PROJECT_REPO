# Spec: a free check before the OpenAI research (client priority B)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "Implement a cost-efficient screening process so OpenAI research is performed only on games with promising opportunities". Approved by the user on 2026-10-17 as the fifth item; item C (bookmaker comparison, done) is its base.

## What is there now (read in the code)

- Every upcoming game on the Games page can be researched with one press, at about 0.43 US dollars (limited to 5 a day by FEAT-20261017-1123). Nothing tells a person which games are worth that money.
- The bookmaker feed is read only inside a run (`book_for_game`), one league read per game, cached 10 minutes. The Games list (`games.py`) has the live Kalshi bid and ask of each outcome but not the contracts on offer.
- One odds read costs 1 credit per region and returns every game of a league, so one read can screen all the games of that league. The free plan has 500 credits a month (492 left today); the feed's "sports" call is free and its answer carries the credits left.

## The rule (written before any test, so it cannot be adjusted afterwards)

A game is **worth researching** when, for at least one winner outcome and one side (yes or no), all of these hold, with live prices:
1. the bookmakers' consensus probability (margin removed, exchanges left out, at least `MIN_BOOKS` bookmakers: the same figure item C uses) minus the Kalshi ask for that side minus the Kalshi fee is at least `EDGE_MIN` (5 cents);
2. at least `MIN_ASK_SIZE` (10) contracts are offered at that ask;
3. the game has not started and starts within `SCREEN_HOURS_AHEAD` hours (default 36), so the forecast would still be fresh.
Otherwise it is **not promising**. A game whose league has no bookmaker source, or that the feed does not list, is **cannot be screened**, with the reason; it is never treated as promising or as not promising. The screen does not look at our forecast (there is none yet) and it does not stop anyone from researching.

## Design

- **Where the check lives:** a new `backend/app/screening.py`. It takes the games of the Games list, groups them by league feed (`sport_keys_for`), reads each needed league once through the existing `OddsClient` (so the 10-minute cache and the credit header apply), matches each game with `find_game` and the outcome names with the same mapping as `book_for_game` (that mapping is moved into one shared function used by both, so the two cannot drift), and applies the rule. No model call, no OpenAI credit.
- **It is an explicit action, never automatic:** the Games page gets a link "Check these games against the bookmakers", which loads the page with `screen=1`. Nothing is read on a normal page load and the watcher does not screen. The link says how many odds credits it will use at most (the number of leagues with games in the list) and the page afterwards says how many were used and how many remain.
- **A credit floor:** screening refuses to read when the credits left (known from the free sports call) are below `SCREEN_MIN_CREDITS_LEFT` (default 100), and says so, so the monthly credits are never all spent on screening and research keeps its bookmaker price. The leagues read are limited to those with at least one game in the list, at most `SCREEN_MAX_LEAGUES` per press (default 8, the most promising by volume first; the rest are listed as not checked).
- **The Games list column "Bookmakers":** after a check, each game shows "Worth researching: bookmakers 62% for Roma, Kalshi sells it at 52¢, gap +8¢ after fees", or "Not promising", or "Cannot be screened: <reason>" (for example "no bookmaker source for this league"). Games that were not checked show nothing. The Research button is unchanged.
- **Every screening is saved:** a new table `screenings` (made with Alembic autogenerate), one row per winner outcome checked: the time, the game and outcome, the Kalshi bid, ask and sizes, the bookmaker probability, the number of bookmakers, the side, the gap after fees, whether it passed, and empty result fields to be filled when the game ends. This is so the rule can be tested later on real games without any new spending (see "Not done").
- The Games list outcome gets two small fields, the contracts offered at the best ask and at the best bid (Kalshi already sends them).
- Settings: `SCREEN_HOURS_AHEAD`, `SCREEN_MIN_CREDITS_LEFT`, `SCREEN_MAX_LEAGUES`, all with defaults, documented in `.env.example` and the run guide. If the odds feed is off, the link is not shown and the page says why.

## Not done (and why)

- **No automatic filter:** the screen does not block a research and does not rank the Games list; with only one real example so far (Everton vs Chelsea: Kalshi and the bookmakers agreed, gap about -1 cent on every side) nothing says yet that the rule picks better games. A hard filter should wait for evidence.
- **Testing the rule on results is a separate follow-up item** (to be logged with this one): after at least 30 finished screened games, compare, on the stored screenings only, the paper result of buying the bookmaker-favoured side at the Kalshi ask after fees, for the games that passed and for those that did not. It needs the screening rows to be settled when the games end (the same way the forecast records are) and costs no OpenAI credit. Until then the rule is a guide, not a proven filter.
- No screening of total, spread or both-teams-to-score markets (the feed is read for head-to-head only); no Telegram alert for a promising game; no daily automatic screening.

## Tests

Backend: the rule on a table of cases (gap just below and at the minimum; too few contracts; both sides; started game; game beyond the hours ahead); the shared name mapping gives the same answer for the run and for the screen; a league without a source and a game the feed does not list are "cannot be screened" with the reason, never promising; one read per league for many games; the credit floor refuses without reading; the league limit lists the rest as not checked; the screenings table gets one row per outcome checked; nothing is read without `screen=1`; the feed off gives the clear message. Frontend: lint, build, a browser test with the answer mocked on the Games page (the three kinds of label and the link), and one real check on the Games page (a few credits) to see real labels.

## Checks to state at close

Lateral spread: the feed is still read only through `OddsClient`, and the name mapping through one shared function; I search for any other reader. Causal depth: the request is about not spending OpenAI credit on games with nothing to find; the screen makes the choice visible and free, the daily limit caps the spending, and the follow-up item will say whether the screen deserves to become a filter.
