# Spec: compare the bookmaker odds with the Kalshi price (client priority C, and the bookmaker part of D)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "Compare bookmaker odds with Kalshi prices after accounting for margins, fees and market liquidity" and "demonstrate whether our forecasts can outperform Kalshi and bookmaker probabilities". The user switched the feed on on 2026-10-17 (checked: key valid, 87 active sports, 493 credits left of 500, 19 bookmakers on a test game). Approved on 2026-10-17 as the fourth item.

## What is there now (read in `odds.py`, `research/records.py`, `pipeline.py`)

- `book_for_game` (never fails a run) finds the game in the feed by team names and start time and returns, per winner market, the consensus probability (the median over bookmakers, each bookmaker's margin removed by scaling its prices to 100%, exchanges left out), Pinnacle's own, and the number of bookmakers (at least `MIN_BOOKS`); otherwise a note saying why not. It is called **after** the Kalshi comparison and used only for the record (`outcome_records.book_*`) and for the `bookmakers` block of `score-records`.
- Nothing on a page shows it, no gap is computed, and the Dashboard does not score it.

## Design

- **Per winner market, a bookmaker gap after fees** (`research/compare.py`): from the bookmaker probability `b` and the live Kalshi asks: buying "yes" is worth `b - yes_ask - fee`, buying "no" is worth `(1 - b) - no_ask - fee`, the same fee formula and series fee as our own gap; the larger one is the bookmaker side. Liquidity is the contracts on offer at that ask against `MIN_ASK_SIZE`. The result per market: `book` = `{probability, pinnacle, count, read_at, side, edge, enough_contracts, passes (edge at least EDGE_MIN and enough contracts), agrees_with_us (the same side as ours, or no side)}`. Only winner markets have it (the feed gives head-to-head prices), as today.
- **Order in the pipeline:** the bookmaker read moves **before** the Kalshi comparison so the comparison can include it; it still never fails a run, and the record is built from the same read (one read, not two).
- **The flag rule does not change.** Bookmaker prices are shown and recorded but not used to flag (the six tests stay as they are; screening before research is item B).
- **Run page:** a "Bookmakers" fold, open when there is data: Outcome, our probability, Kalshi buy price, bookmaker consensus (with the number of bookmakers), Pinnacle, the gap against the bookmakers after fees (side, price), contracts on offer, and a word: agree, disagree, or no gap. If there is no bookmaker price the page says why in one line (the stored note, for example "no bookmaker source for this league"). `GET /api/runs/{id}` adds the note.
- **Opportunities:** the row's "Our / market" cell adds "bookmakers 62% (19 books, read 3 h ago)" for the best market when it is a winner market. It uses the bookmaker price stored with the forecast and the live Kalshi price, and shows the age of the bookmaker read (a live refresh would cost credits; item B reads live before research).
- **Dashboard:** when at least one finished game has a bookmaker price, a "Games with bookmaker prices" block with bars for ours, Kalshi and the bookmaker consensus (and Pinnacle) on the same outcomes, with the number of games and "too few to read" under 30 games, from the existing `score_records` numbers.
- Documented in the run guide (odds section), HOW-IT-WORKS (a short strategy paragraph and the glossary) and `.env.example` (no new setting).

## Not done

No bookmaker prices for total, spread or both-teams-to-score markets (the feed call asks for head-to-head only; more markets cost more credits). No use of bookmaker prices in the flag. No refresh of the bookmaker read after the run. No change to the credit use (one read per league, cached 10 minutes). Challenger tennis stays uncovered (the feed has none).

## Tests

Backend: the gap for the yes side and the no side, with the fee; margin already removed in the input; the liquidity rule (contracts below `MIN_ASK_SIZE` do not pass); agrees-with-us; a market without a bookmaker price; the pipeline reads the bookmaker price before the comparison and passes the same read to the record; a failed bookmaker read does not fail the run; the run detail carries the note; the Opportunities row carries the stored bookmaker price and its age; the Dashboard block appears only with data and marks under 30 games. Frontend: lint, build, the browser tests and screenshots.
With the user's yes, one real check after the code is done: research one upcoming game in a league the feed covers (about 0.43 US dollars of OpenAI credit, counted in today's limit and about 1 odds credit) to see the real output on a page.

## Checks to state at close

Lateral spread: the feed is read in one place (`book_for_game`), and every page takes the number from the stored comparison or the stored record, not from a second read; I search for any other place that reads the feed. Causal depth: the request has three parts (margin, fees, liquidity): the margin is removed in the feed step, the fee and liquidity in the gap step; and "outperform the bookmakers" needs the scored comparison, which the Dashboard block gives as games finish.
