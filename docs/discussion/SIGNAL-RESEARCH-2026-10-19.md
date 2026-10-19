# Signal research, 2026-10-19: why our forecasts add nothing to Kalshi's price, and where a better signal could come from

An analysis made in another working session (read-only: no change to the repository or the database, no OpenAI call), checked by this session on the same day. The three scripts it used are in `scripts/signal_analysis/`. The user's instruction afterwards was: "your call, I just want better signals."

## The short answer

Our forecasts carry no information that Kalshi's price does not already have. The cause is not a bug that can be fixed. It comes from how the system is built and from how accurate pre-game sports prices already are. Better places to look for a signal exist, but none is a quick win.

## 1. What our own data shows (62 finished games, 481 outcomes)

| Test | Result | Checked on 2026-10-19 |
|---|---|---|
| Accuracy (Brier, lower is better) | Kalshi 0.176, ours 0.195, plain AI 0.197 | Reproduces: 0.1755, 0.1945, 0.1970 |
| Does our number add to the price? (logistic regression, interval by whole games) | Weight on "our number minus the price" is -0.41, 95% range -0.88 to +0.17 | Reproduces exactly with the other session's script. A simple linear fit gives -0.56 (-1.18 to +0.07): same direction, different size by method |
| The best mix of our number with the price, chosen on held-out games | Leans away from our number (weight -0.4 to -0.5; Brier 0.1738 against 0.1755 for the price) | Reproduces |
| Did the price later move toward our number? (closing line value, 389 markets) | Average move about 0 (range -0.52 to +0.53 cents); correlation -0.004 | **Not re-checked** (it needs hundreds of Kalshi requests) |
| How far our number sits from the price | 7.5 cents on average | Reproduces |
| Kalshi against the bookmakers' fair price | 0.8 cents apart; none passed the free check | 0.76 cents; best gap after fees +0.9 cent. **The 471 rows are 53 games screened three times; the sample is 53 games (157 outcomes)** |
| When we forecast | Median 6.5 hours before the game | 6.5 hours per game (66 runs); 12.2 hours per market |
| Research effect where it moved our number by 5 cents or more | Toward the result 65 of 108 times; accuracy 0.206 -> 0.191 | Reproduces exactly |

When we are below the price, the result is on average higher than the price: where we sit 15 cents or more below it, the outcomes came in 12 cents above the price (47 outcomes). So our deviations are mostly our own error, not news.

One small positive: against a plain AI, the research helps a little (see the last row). It is still far behind the price.

## 2. Why the signal is weak

1. The design asks the model to rebuild the price from nothing and then bets on the difference. The forecasters never see the price. Since the price is more accurate than they are, most of the difference between us and it is our own error, and the flag picks out exactly those cases. (This was a deliberate choice, to keep the comparison honest; it also means the system is a forecaster, not a market-aware assistant.)
2. The model's own starting belief dominates. How far our number sits from the price and how far the plain AI's sits move together (correlation 0.85, reproduced).
3. The same leans appear with or without research: totals about 7 cents below the price, both teams to score about 11 below (reproduced: -7.3 and -11.1), winner markets closer to 50/50 than the market.
4. We look at the wrong time. A few hours before a game the price already includes the public news the researchers find.
5. Researchers collect bookmaker odds and the forecasters are told to ignore them; many true claims are lost at the checking step.

## 3. What published research says (NOT verified by us unless marked)

The analysis cites, and we have not re-read: Prophet Arena (models vs the market, market price alone 0.173 against news only 0.191), WC2026-Agents (four frontier agents forecast all 104 World Cup matches; none beat the betting market), LLM-SoccerArena (web search improved accuracy by only 0.023), ForecastBench and the "wisdom of the silicon crowd" studies (the best AI forecasters start from the crowd or market price), a calibration study of 429,000 Kalshi and Polymarket contracts (average calibration error 0.008 within 48 hours of the event), Bürgi, Deng and Whelan on Kalshi's makers and takers (**this one we did read in summary on 2026-10-17**: contracts under 10 cents lose more than 60%; makers average -9.6%, takers -31.5%), "When do prophets profit" (fixed-fraction betting is disastrous with a miscalibrated model), a 2025 study of bookmaker reaction to a star player's absence, and a tennis model review. The message they carry is the same as our own numbers; treat the exact figures as reported, not confirmed.

## 4. The ideas, and the decision taken

| # | Idea | Decision (2026-10-19) |
|---|---|---|
| 1 | Better ways to measure: whether our number adds to the price, and closing line value | The scripts are saved (`scripts/signal_analysis/`) and give the answer today. An app command is not built: it would only measure the same null more neatly. Re-run the scripts every week or two while the batches add games |
| 2 | Finish the free price-only test (running), then extend it to other horizons (7 and 14 days before a game, where the study says prices are measurably off) | **Yes.** Highest power for the least cost: thousands of games, nothing paid. The extension is a new item that starts when the first run is finished and read |

**Result (2026-10-19, later the same day):** the first test found no pattern on 4,709 games (`docs/discussion/PRICE-TEST-2026-10-19.md`), and the extension to 24 hours, 7 days and 14 days found none either, with the price almost as accurate far out as an hour before (`docs/discussion/PRICE-TEST-HORIZONS-2026-10-19.md`).
| 3 | Start from the market price: show the forecasters the Kalshi price and the bookmakers' fair price, and ask only which specific new fact moves it | **As an experiment on saved evidence only, with the replay tool and a rule written first. The live rule "the forecasters never see the market" stays until the experiment gives a reason to change it.** Not before about 100 finished games: with 62 only a large effect could be seen, so a null would not mean much |
| 4 | React to news (lineups about an hour before soccer, probable pitchers, injury reports, tennis withdrawals), after measuring how fast Kalshi and the bookmakers react | Recorded as a wish: measure first. The most plausible place for a real edge for an AI system, but it needs continuous price logging, more odds credits, and live Kalshi data (the only key we have is the shared production one, which must be replaced before any real use) |
| 5 | Post resting orders instead of buying at the ask (saves about 1.7 cents) | **No.** Our paper mode fills at the ask and cannot show whether a resting order would fill; it leads to real trading code, which does not exist and is a no-go |
| 6 | Bookmaker against Kalshi gaps watched continuously (option A, 30 dollars of history) | Decide after the price test is read and the game matching is improved |
| 7 | Cheaper research | **One concrete saving:** the researchers' odds angle is collected and then ignored by the forecasters (the bookmaker feed now supplies that price). Dropping it saves about a quarter of the research cost. New item |
| – | More forecasters, higher reasoning effort, fixing the model's leans, Kelly sizing, sport-specific statistical models | Not worth it: none adds information the price lacks (the first two were also tested and not kept) |

## 5. What this means for the client

An AI that reads the web a few hours before a game does not beat the sports betting market: several 2026 studies and our own 62 games agree. A real edge, if one exists, is more likely to come from timing (reacting fast to news), from how orders are placed, or from price patterns (what the price test checks). These are different products from "research a game". Keeping the daily research batches mostly buys more evaluation data, not opportunities.

## 6. Limits

62 games and one bookmaker snapshot of 53 games are small samples. Several papers were read only in summary, by the other session or by this one. The closing line value was not re-checked here.
