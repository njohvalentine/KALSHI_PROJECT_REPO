# Kalshi price test: raw results, 24 hours before the start

Games read: 3306. Prices: hourly bid and ask closes 24 hours before the start, not executable fills. Rule and strategies: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md` (and, for the other horizons, `docs/specs/FEAT-20261019-0956-price-test-horizons.md`).
Median spread at this horizon: 1.0 cents. On the 3297 games that also have a one-hour price, the Brier score of the price is 0.1963 at 24 hours and 0.1960 one hour before the start (descriptive only).
Only the pooled group and the four sectors are tested here (45 comparisons over three horizons); the series rows are descriptive.
A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero and the first half is also above zero.

## Strategies

- **F**: buy yes on the favourite of each game
- **L**: buy yes on every outcome priced at 20 cents or less
- **N**: buy no on every outcome priced at 20 cents or less

## Results by group

| Group | Games | Strategy | First half: bets, average | Second half: bets, average, 99% interval | Verdict |
|---|---|---|---|---|---|
| All | 3306 | F | 1653, -1.7¢ | 1653, -2.0¢, -5.3¢ to +1.0¢ | no pattern |
| All | 3306 | L | 859, -2.9¢ | 695, -1.5¢, -4.6¢ to +1.7¢ | no pattern |
| All | 3306 | N | 859, -0.4¢ | 695, -1.5¢, -4.9¢ to +1.6¢ | no pattern |
| Premier League | 387 | F | 193, -1.8¢ | 194, -11.4¢, -21.0¢ to -2.0¢ | descriptive |
| Premier League | 387 | L | 107, -4.5¢ | 101, +1.2¢, -6.9¢ to +10.9¢ | descriptive |
| Premier League | 387 | N | 107, +1.1¢ | 101, -4.2¢, -14.0¢ to +3.7¢ | descriptive |
| Soccer (all) | 2467 | F | 1233, -1.3¢ | 1234, -2.2¢, -5.7¢ to +1.4¢ | no pattern |
| Soccer (all) | 2467 | L | 722, -3.6¢ | 686, -1.1¢, -4.4¢ to +2.4¢ | no pattern |
| Soccer (all) | 2467 | N | 722, +0.2¢ | 686, -1.8¢, -5.4¢ to +1.4¢ | not confirmed |
| Champions League | 266 | F | 133, -1.8¢ | 133, -6.1¢, -17.1¢ to +4.1¢ | descriptive |
| Champions League | 266 | L | 125, -2.0¢ | 106, -0.9¢, -8.9¢ to +7.5¢ | descriptive |
| Champions League | 266 | N | 125, -1.0¢ | 106, -2.1¢, -10.6¢ to +5.8¢ | descriptive |
| Europa League | 170 | F | 85, +6.0¢ | 85, -2.4¢, -16.2¢ to +10.6¢ | descriptive |
| Europa League | 170 | L | 53, -10.3¢ | 45, +0.1¢, -12.8¢ to +15.7¢ | descriptive |
| Europa League | 170 | N | 53, +6.9¢ | 45, -3.1¢, -18.8¢ to +9.7¢ | descriptive |
| MLS | 285 | F | 142, -0.5¢ | 143, +0.5¢, -10.1¢ to +10.8¢ | descriptive |
| MLS | 285 | L | 50, +3.0¢ | 55, +1.9¢, -10.7¢ to +15.3¢ | descriptive |
| MLS | 285 | N | 50, -6.8¢ | 55, -5.1¢, -18.5¢ to +7.2¢ | descriptive |
| La Liga | 380 | F | 190, +2.8¢ | 190, -0.6¢, -9.9¢ to +7.4¢ | descriptive |
| La Liga | 380 | L | 113, -1.9¢ | 78, -4.1¢, -11.8¢ to +5.7¢ | descriptive |
| La Liga | 380 | N | 113, -1.4¢ | 78, +1.3¢, -8.5¢ to +9.0¢ | descriptive |
| Serie A | 376 | F | 188, -3.2¢ | 188, +0.5¢, -8.9¢ to +9.5¢ | descriptive |
| Serie A | 376 | L | 106, -2.5¢ | 128, -0.5¢, -7.2¢ to +8.2¢ | descriptive |
| Serie A | 376 | N | 106, -1.0¢ | 128, -2.2¢, -11.0¢ to +4.4¢ | descriptive |
| Bundesliga | 302 | F | 151, -1.0¢ | 151, -1.9¢, -11.5¢ to +7.8¢ | descriptive |
| Bundesliga | 302 | L | 80, -7.1¢ | 85, -3.0¢, -11.9¢ to +6.7¢ | descriptive |
| Bundesliga | 302 | N | 80, +3.7¢ | 85, +0.1¢, -9.7¢ to +8.9¢ | descriptive |
| Ligue 1 | 301 | F | 150, -4.0¢ | 151, +0.6¢, -9.8¢ to +10.2¢ | descriptive |
| Ligue 1 | 301 | L | 82, -5.2¢ | 94, -2.5¢, -10.6¢ to +5.8¢ | descriptive |
| Ligue 1 | 301 | N | 82, +1.7¢ | 94, -0.5¢, -8.9¢ to +7.4¢ | descriptive |
| MLB | 176 | F | 88, +1.9¢ | 88, -1.1¢, -15.5¢ to +11.4¢ | descriptive |
| MLB | 176 | L | 0, – | 0, –, – | descriptive |
| MLB | 176 | N | 0, – | 0, –, – | descriptive |
| Baseball (all) | 176 | F | 88, +1.9¢ | 88, -1.1¢, -15.5¢ to +11.4¢ | not confirmed |
| Baseball (all) | 176 | L | 0, – | 0, –, – | too few bets |
| Baseball (all) | 176 | N | 0, – | 0, –, – | too few bets |
| NBA | 346 | F | 173, -10.0¢ | 173, +0.6¢, -8.3¢ to +8.6¢ | descriptive |
| NBA | 346 | L | 30, +1.9¢ | 43, -3.9¢, -14.6¢ to +9.8¢ | descriptive |
| NBA | 346 | N | 30, -5.6¢ | 43, +0.9¢, -13.0¢ to +11.1¢ | descriptive |
| Basketball (all) | 346 | F | 173, -10.0¢ | 173, +0.6¢, -8.3¢ to +8.6¢ | no pattern |
| Basketball (all) | 346 | L | 30, +1.9¢ | 43, -3.9¢, -14.6¢ to +9.8¢ | not confirmed |
| Basketball (all) | 346 | N | 30, -5.6¢ | 43, +0.9¢, -13.0¢ to +11.1¢ | no pattern |
| ATP | 145 | F | 72, -6.2¢ | 73, -1.9¢, -14.6¢ to +10.8¢ | descriptive |
| ATP | 145 | L | 13, +4.3¢ | 16, -1.3¢, -16.7¢ to +23.2¢ | descriptive |
| ATP | 145 | N | 13, -6.9¢ | 16, -1.8¢, -27.1¢ to +12.8¢ | descriptive |
| Tennis (all) | 317 | F | 158, -0.4¢ | 159, -1.5¢, -11.0¢ to +7.9¢ | no pattern |
| Tennis (all) | 317 | L | 30, -0.6¢ | 43, -1.3¢, -13.5¢ to +13.8¢ | no pattern |
| Tennis (all) | 317 | N | 30, -2.7¢ | 43, -1.9¢, -16.9¢ to +10.3¢ | no pattern |
| WTA | 139 | F | 69, +6.6¢ | 70, -3.7¢, -18.9¢ to +9.1¢ | descriptive |
| WTA | 139 | L | 14, -2.4¢ | 19, -0.4¢, -16.5¢ to +25.3¢ | descriptive |
| WTA | 139 | N | 14, -1.3¢ | 19, -2.8¢, -28.8¢ to +13.3¢ | descriptive |
| ATP Challenger | 24 | F | 12, +14.4¢ | 12, +5.8¢, -30.5¢ to +34.9¢ | descriptive |
| ATP Challenger | 24 | L | 7, -2.0¢ | 2, -12.2¢, -14.8¢ to -9.6¢ | descriptive |
| ATP Challenger | 24 | N | 7, -1.5¢ | 2, +9.4¢, +6.5¢ to +12.2¢ | descriptive |
| WTA Challenger | 9 | F | 4, -19.5¢ | 5, -17.2¢, -67.7¢ to +21.6¢ | descriptive |
| WTA Challenger | 9 | L | 0, – | 2, -13.8¢, -14.8¢ to -12.7¢ | descriptive |
| WTA Challenger | 9 | N | 0, – | 2, +11.3¢, +10.3¢ to +12.2¢ | descriptive |

## Accuracy and calibration

| Group | Games | Period | Brier score of the middle price |
|---|---|---|---|
| All | 3306 | 2025-04-15 to 2026-08-18 | 0.1963 |
| Premier League | 387 | 2025-05-11 to 2026-05-24 | 0.2034 |
| Soccer (all) | 2467 | 2025-04-30 to 2026-08-18 | 0.1927 |
| Champions League | 266 | 2025-04-30 to 2026-08-18 | 0.1814 |
| Europa League | 170 | 2025-05-08 to 2026-08-14 | 0.1804 |
| MLS | 285 | 2025-05-31 to 2026-08-17 | 0.2013 |
| La Liga | 380 | 2025-05-11 to 2026-08-17 | 0.1915 |
| Serie A | 376 | 2025-08-23 to 2026-05-24 | 0.1943 |
| Bundesliga | 302 | 2025-08-22 to 2026-05-25 | 0.1871 |
| Ligue 1 | 301 | 2025-08-15 to 2026-05-29 | 0.1927 |
| MLB | 176 | 2025-07-11 to 2026-08-17 | 0.2429 |
| Baseball (all) | 176 | 2025-07-11 to 2026-08-17 | 0.2429 |
| NBA | 346 | 2025-04-15 to 2026-06-11 | 0.2104 |
| Basketball (all) | 346 | 2025-04-15 to 2026-06-11 | 0.2104 |
| ATP | 145 | 2025-06-30 to 2026-08-18 | 0.2068 |
| Tennis (all) | 317 | 2025-06-30 to 2026-08-18 | 0.1970 |
| WTA | 139 | 2025-06-30 to 2026-08-18 | 0.1901 |
| ATP Challenger | 24 | 2026-02-19 to 2026-08-18 | 0.1671 |
| WTA Challenger | 9 | 2026-04-21 to 2026-07-29 | 0.2242 |

### Calibration, all games

| Price bucket | Outcomes | Mean price | How often it happened |
|---|---|---|---|
| 0-10¢ | 255 | 0.071 | 0.067 |
| 10-20¢ | 1229 | 0.157 | 0.150 |
| 20-30¢ | 2874 | 0.251 | 0.256 |
| 30-40¢ | 1440 | 0.342 | 0.333 |
| 40-50¢ | 1153 | 0.447 | 0.454 |
| 50-60¢ | 925 | 0.547 | 0.550 |
| 60-70¢ | 591 | 0.643 | 0.638 |
| 70-80¢ | 366 | 0.742 | 0.730 |
| 80-90¢ | 211 | 0.842 | 0.867 |
| 90-100¢ | 35 | 0.926 | 0.886 |

## Games dropped, and why

- KXATPCHALLENGERMATCH: no single winner (voided or unfinished): 159
- KXATPCHALLENGERMATCH: the market was not open 24 hours before the start: 376
- KXATPMATCH: no bid and ask 24 hours before the start: 1
- KXATPMATCH: no single winner (voided or unfinished): 138
- KXATPMATCH: spread wider than 10 cents: 21
- KXATPMATCH: the market was not open 24 hours before the start: 212
- KXBUNDESLIGAGAME: no bid and ask 24 hours before the start: 4
- KXBUNDESLIGAGAME: no single winner (voided or unfinished): 3
- KXBUNDESLIGAGAME: the market was not open 24 hours before the start: 2
- KXLALIGAGAME: no bid and ask 24 hours before the start: 1
- KXLALIGAGAME: no single winner (voided or unfinished): 3
- KXLALIGAGAME: the market was not open 24 hours before the start: 5
- KXLIGUE1GAME: no bid and ask 24 hours before the start: 5
- KXLIGUE1GAME: no single winner (voided or unfinished): 1
- KXLIGUE1GAME: the market was not open 24 hours before the start: 1
- KXMLBGAME: no bid and ask 24 hours before the start: 1
- KXMLBGAME: no single winner (voided or unfinished): 14
- KXMLBGAME: the market was not open 24 hours before the start: 195
- KXMLSGAME: no bid and ask 24 hours before the start: 3
- KXMLSGAME: no single winner (voided or unfinished): 3
- KXMLSGAME: no start time: 2
- KXMLSGAME: spread wider than 10 cents: 12
- KXNBAGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no start time: 1
- KXNBAGAME: spread wider than 10 cents: 12
- KXNBAGAME: the market was not open 24 hours before the start: 3
- KXSERIEAGAME: no bid and ask 24 hours before the start: 2
- KXSERIEAGAME: the market was not open 24 hours before the start: 2
- KXUCLGAME: no bid and ask 24 hours before the start: 3
- KXUCLGAME: no start time: 3
- KXUELGAME: no bid and ask 24 hours before the start: 1
- KXUELGAME: no single winner (voided or unfinished): 1
- KXUELGAME: spread wider than 10 cents: 16
- KXUELGAME: the market was not open 24 hours before the start: 6
- KXWTACHALLENGERMATCH: no single winner (voided or unfinished): 25
- KXWTACHALLENGERMATCH: spread wider than 10 cents: 4
- KXWTACHALLENGERMATCH: the market was not open 24 hours before the start: 356
- KXWTAMATCH: no bid and ask 24 hours before the start: 3
- KXWTAMATCH: no single winner (voided or unfinished): 122
- KXWTAMATCH: spread wider than 10 cents: 31
- KXWTAMATCH: the market was not open 24 hours before the start: 196


---

# Kalshi price test: raw results, 7 days before the start

Games read: 1431. Prices: hourly bid and ask closes 7 days before the start, not executable fills. Rule and strategies: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md` (and, for the other horizons, `docs/specs/FEAT-20261019-0956-price-test-horizons.md`).
Median spread at this horizon: 3.0 cents. On the 1430 games that also have a one-hour price, the Brier score of the price is 0.1942 at 7 days and 0.1933 one hour before the start (descriptive only).
Only the pooled group and the four sectors are tested here (45 comparisons over three horizons); the series rows are descriptive.
A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero and the first half is also above zero.

## Strategies

- **F**: buy yes on the favourite of each game
- **L**: buy yes on every outcome priced at 20 cents or less
- **N**: buy no on every outcome priced at 20 cents or less

## Results by group

| Group | Games | Strategy | First half: bets, average | Second half: bets, average, 99% interval | Verdict |
|---|---|---|---|---|---|
| All | 1431 | F | 715, -2.3¢ | 716, -3.5¢, -8.4¢ to +0.9¢ | no pattern |
| All | 1431 | L | 406, -3.9¢ | 396, -3.4¢, -8.1¢ to +0.8¢ | no pattern |
| All | 1431 | N | 406, -0.8¢ | 396, -3.1¢, -7.3¢ to +1.4¢ | no pattern |
| Premier League | 336 | F | 168, -0.9¢ | 168, -14.2¢, -23.6¢ to -4.9¢ | descriptive |
| Premier League | 336 | L | 89, -3.0¢ | 97, +3.7¢, -6.1¢ to +13.7¢ | descriptive |
| Premier League | 336 | N | 89, -0.9¢ | 97, -9.0¢, -19.1¢ to +0.8¢ | descriptive |
| Soccer (all) | 1426 | F | 713, -2.2¢ | 713, -3.7¢, -8.3¢ to +1.0¢ | no pattern |
| Soccer (all) | 1426 | L | 405, -3.9¢ | 397, -3.5¢, -7.7¢ to +0.8¢ | no pattern |
| Soccer (all) | 1426 | N | 405, -0.8¢ | 397, -3.0¢, -7.5¢ to +1.2¢ | no pattern |
| Champions League | 152 | F | 76, -0.7¢ | 76, +1.7¢, -12.9¢ to +15.7¢ | descriptive |
| Champions League | 152 | L | 65, -3.1¢ | 60, +0.3¢, -10.1¢ to +11.3¢ | descriptive |
| Champions League | 152 | N | 65, -0.2¢ | 60, -5.1¢, -16.3¢ to +5.0¢ | descriptive |
| Europa League | 29 | F | 14, +12.9¢ | 15, +1.8¢, -32.8¢ to +34.8¢ | descriptive |
| Europa League | 29 | L | 5, -18.4¢ | 3, -22.5¢, -22.7¢ to -22.2¢ | descriptive |
| Europa League | 29 | N | 5, +7.3¢ | 3, +12.5¢, +10.8¢ to +16.0¢ | descriptive |
| MLS | 40 | F | 20, -6.5¢ | 20, +3.5¢, -26.9¢ to +31.9¢ | descriptive |
| MLS | 40 | L | 8, -19.2¢ | 11, -2.6¢, -22.3¢ to +33.2¢ | descriptive |
| MLS | 40 | N | 8, +12.0¢ | 11, -3.5¢, -39.9¢ to +15.5¢ | descriptive |
| La Liga | 241 | F | 120, +0.5¢ | 121, -4.5¢, -15.9¢ to +5.8¢ | descriptive |
| La Liga | 241 | L | 67, -4.3¢ | 55, -1.6¢, -12.6¢ to +12.5¢ | descriptive |
| La Liga | 241 | N | 67, -1.4¢ | 55, -5.5¢, -19.6¢ to +5.4¢ | descriptive |
| Serie A | 259 | F | 129, -3.3¢ | 130, -0.7¢, -12.0¢ to +9.3¢ | descriptive |
| Serie A | 259 | L | 70, -4.9¢ | 82, -5.9¢, -13.8¢ to +4.2¢ | descriptive |
| Serie A | 259 | N | 70, -0.3¢ | 82, -0.6¢, -10.8¢ to +7.1¢ | descriptive |
| Bundesliga | 188 | F | 94, +0.2¢ | 94, -0.6¢, -13.4¢ to +12.1¢ | descriptive |
| Bundesliga | 188 | L | 47, -8.5¢ | 49, -7.4¢, -18.6¢ to +4.5¢ | descriptive |
| Bundesliga | 188 | N | 47, +4.0¢ | 49, -0.7¢, -13.0¢ to +10.4¢ | descriptive |
| Ligue 1 | 181 | F | 90, -7.0¢ | 91, -2.6¢, -15.8¢ to +10.7¢ | descriptive |
| Ligue 1 | 181 | L | 45, +0.2¢ | 49, -11.3¢, -19.3¢ to -0.9¢ | descriptive |
| Ligue 1 | 181 | N | 45, -5.5¢ | 49, +3.7¢, -7.1¢ to +11.6¢ | descriptive |
| NBA | 5 | F | 2, +17.0¢ | 3, +11.3¢, -54.7¢ to +46.3¢ | descriptive |
| NBA | 5 | L | 0, – | 0, –, – | descriptive |
| NBA | 5 | N | 0, – | 0, –, – | descriptive |
| Basketball (all) | 5 | F | 2, +17.0¢ | 3, +11.3¢, -54.7¢ to +46.3¢ | not confirmed |
| Basketball (all) | 5 | L | 0, – | 0, –, – | too few bets |
| Basketball (all) | 5 | N | 0, – | 0, –, – | too few bets |

## Accuracy and calibration

| Group | Games | Period | Brier score of the middle price |
|---|---|---|---|
| All | 1431 | 2025-08-16 to 2026-08-17 | 0.1942 |
| Premier League | 336 | 2025-08-16 to 2026-05-24 | 0.2064 |
| Soccer (all) | 1426 | 2025-08-16 to 2026-08-17 | 0.1943 |
| Champions League | 152 | 2025-09-16 to 2026-05-30 | 0.1782 |
| Europa League | 29 | 2025-12-11 to 2026-05-20 | 0.1864 |
| MLS | 40 | 2025-09-25 to 2026-08-17 | 0.1952 |
| La Liga | 241 | 2025-08-22 to 2026-08-17 | 0.1934 |
| Serie A | 259 | 2025-08-23 to 2026-05-17 | 0.1924 |
| Bundesliga | 188 | 2025-08-22 to 2026-05-10 | 0.1869 |
| Ligue 1 | 181 | 2025-08-31 to 2026-05-10 | 0.1980 |
| NBA | 5 | 2026-04-24 to 2026-06-11 | 0.1617 |
| Basketball (all) | 5 | 2026-04-24 to 2026-06-11 | 0.1617 |

### Calibration, all games

| Price bucket | Outcomes | Mean price | How often it happened |
|---|---|---|---|
| 0-10¢ | 115 | 0.073 | 0.070 |
| 10-20¢ | 612 | 0.157 | 0.149 |
| 20-30¢ | 1635 | 0.251 | 0.256 |
| 30-40¢ | 694 | 0.340 | 0.324 |
| 40-50¢ | 481 | 0.445 | 0.476 |
| 50-60¢ | 365 | 0.546 | 0.496 |
| 60-70¢ | 218 | 0.643 | 0.688 |
| 70-80¢ | 129 | 0.741 | 0.736 |
| 80-90¢ | 37 | 0.835 | 0.838 |
| 90-100¢ | 2 | 0.930 | 1.000 |

## Games dropped, and why

- KXATPCHALLENGERMATCH: no single winner (voided or unfinished): 159
- KXATPCHALLENGERMATCH: the market was not open 7 days before the start: 400
- KXATPMATCH: no single winner (voided or unfinished): 138
- KXATPMATCH: the market was not open 7 days before the start: 379
- KXBUNDESLIGAGAME: no bid and ask 7 days before the start: 1
- KXBUNDESLIGAGAME: no single winner (voided or unfinished): 3
- KXBUNDESLIGAGAME: spread wider than 10 cents: 115
- KXBUNDESLIGAGAME: the market was not open 7 days before the start: 4
- KXEPLGAME: no bid and ask 7 days before the start: 6
- KXEPLGAME: spread wider than 10 cents: 39
- KXEPLGAME: the market was not open 7 days before the start: 6
- KXLALIGAGAME: no bid and ask 7 days before the start: 24
- KXLALIGAGAME: no single winner (voided or unfinished): 3
- KXLALIGAGAME: spread wider than 10 cents: 83
- KXLALIGAGAME: the market was not open 7 days before the start: 38
- KXLIGUE1GAME: no bid and ask 7 days before the start: 2
- KXLIGUE1GAME: no single winner (voided or unfinished): 1
- KXLIGUE1GAME: spread wider than 10 cents: 109
- KXLIGUE1GAME: the market was not open 7 days before the start: 15
- KXMLBGAME: no single winner (voided or unfinished): 14
- KXMLBGAME: spread wider than 10 cents: 2
- KXMLBGAME: the market was not open 7 days before the start: 370
- KXMLSGAME: no bid and ask 7 days before the start: 27
- KXMLSGAME: no single winner (voided or unfinished): 3
- KXMLSGAME: no start time: 2
- KXMLSGAME: spread wider than 10 cents: 57
- KXMLSGAME: the market was not open 7 days before the start: 176
- KXNBAGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no start time: 1
- KXNBAGAME: the market was not open 7 days before the start: 356
- KXSERIEAGAME: no bid and ask 7 days before the start: 11
- KXSERIEAGAME: spread wider than 10 cents: 71
- KXSERIEAGAME: the market was not open 7 days before the start: 39
- KXUCLGAME: no bid and ask 7 days before the start: 6
- KXUCLGAME: no start time: 3
- KXUCLGAME: spread wider than 10 cents: 14
- KXUCLGAME: the market was not open 7 days before the start: 97
- KXUELGAME: no bid and ask 7 days before the start: 5
- KXUELGAME: no single winner (voided or unfinished): 1
- KXUELGAME: spread wider than 10 cents: 82
- KXUELGAME: the market was not open 7 days before the start: 77
- KXWTACHALLENGERMATCH: no single winner (voided or unfinished): 25
- KXWTACHALLENGERMATCH: the market was not open 7 days before the start: 369
- KXWTAMATCH: no single winner (voided or unfinished): 122
- KXWTAMATCH: the market was not open 7 days before the start: 369


---

# Kalshi price test: raw results, 14 days before the start

Games read: 170. Prices: hourly bid and ask closes 14 days before the start, not executable fills. Rule and strategies: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md` (and, for the other horizons, `docs/specs/FEAT-20261019-0956-price-test-horizons.md`).
Median spread at this horizon: 3.0 cents. On the 170 games that also have a one-hour price, the Brier score of the price is 0.1883 at 14 days and 0.1894 one hour before the start (descriptive only).
Only the pooled group and the four sectors are tested here (45 comparisons over three horizons); the series rows are descriptive.
A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero and the first half is also above zero.

## Strategies

- **F**: buy yes on the favourite of each game
- **L**: buy yes on every outcome priced at 20 cents or less
- **N**: buy no on every outcome priced at 20 cents or less

## Results by group

| Group | Games | Strategy | First half: bets, average | Second half: bets, average, 99% interval | Verdict |
|---|---|---|---|---|---|
| All | 170 | F | 85, +4.1¢ | 85, -7.8¢, -20.8¢ to +5.6¢ | not confirmed |
| All | 170 | L | 63, -3.4¢ | 39, -7.3¢, -18.2¢ to +6.0¢ | no pattern |
| All | 170 | N | 63, -1.0¢ | 39, -1.1¢, -14.6¢ to +9.8¢ | no pattern |
| Premier League | 97 | F | 48, -0.4¢ | 49, -11.8¢, -29.4¢ to +6.9¢ | descriptive |
| Premier League | 97 | L | 25, -6.7¢ | 21, -5.7¢, -22.2¢ to +12.0¢ | descriptive |
| Premier League | 97 | N | 25, +2.2¢ | 21, -1.9¢, -19.2¢ to +13.7¢ | descriptive |
| Soccer (all) | 170 | F | 85, +4.1¢ | 85, -7.8¢, -20.8¢ to +5.6¢ | not confirmed |
| Soccer (all) | 170 | L | 63, -3.4¢ | 39, -7.3¢, -18.2¢ to +6.0¢ | no pattern |
| Soccer (all) | 170 | N | 63, -1.0¢ | 39, -1.1¢, -14.6¢ to +9.8¢ | no pattern |
| Champions League | 73 | F | 36, +6.1¢ | 37, +1.8¢, -20.4¢ to +20.5¢ | descriptive |
| Champions League | 73 | L | 30, -0.5¢ | 26, -7.5¢, -19.8¢ to +9.8¢ | descriptive |
| Champions League | 73 | N | 30, -4.1¢ | 26, +0.2¢, -17.9¢ to +12.8¢ | descriptive |

## Accuracy and calibration

| Group | Games | Period | Brier score of the middle price |
|---|---|---|---|
| All | 170 | 2025-09-17 to 2026-05-30 | 0.1883 |
| Premier League | 97 | 2025-09-28 to 2026-05-18 | 0.2008 |
| Soccer (all) | 170 | 2025-09-17 to 2026-05-30 | 0.1883 |
| Champions League | 73 | 2025-09-17 to 2026-05-30 | 0.1717 |

### Calibration, all games

| Price bucket | Outcomes | Mean price | How often it happened |
|---|---|---|---|
| 0-10¢ | 11 | 0.079 | 0.091 |
| 10-20¢ | 80 | 0.160 | 0.150 |
| 20-30¢ | 208 | 0.249 | 0.221 |
| 30-40¢ | 57 | 0.343 | 0.368 |
| 40-50¢ | 50 | 0.447 | 0.420 |
| 50-60¢ | 54 | 0.548 | 0.667 |
| 60-70¢ | 32 | 0.635 | 0.562 |
| 70-80¢ | 15 | 0.740 | 0.800 |
| 80-90¢ | 3 | 0.840 | 1.000 |

## Games dropped, and why

- KXATPCHALLENGERMATCH: no single winner (voided or unfinished): 159
- KXATPCHALLENGERMATCH: the market was not open 14 days before the start: 400
- KXATPMATCH: no single winner (voided or unfinished): 138
- KXATPMATCH: the market was not open 14 days before the start: 379
- KXBUNDESLIGAGAME: no single winner (voided or unfinished): 3
- KXBUNDESLIGAGAME: the market was not open 14 days before the start: 308
- KXEPLGAME: no bid and ask 14 days before the start: 22
- KXEPLGAME: spread wider than 10 cents: 208
- KXEPLGAME: the market was not open 14 days before the start: 60
- KXLALIGAGAME: no single winner (voided or unfinished): 3
- KXLALIGAGAME: no usable bid and ask (empty or crossed): 1
- KXLALIGAGAME: the market was not open 14 days before the start: 385
- KXLIGUE1GAME: no single winner (voided or unfinished): 1
- KXLIGUE1GAME: the market was not open 14 days before the start: 307
- KXMLBGAME: no single winner (voided or unfinished): 14
- KXMLBGAME: the market was not open 14 days before the start: 372
- KXMLSGAME: no bid and ask 14 days before the start: 1
- KXMLSGAME: no single winner (voided or unfinished): 3
- KXMLSGAME: no start time: 2
- KXMLSGAME: spread wider than 10 cents: 2
- KXMLSGAME: the market was not open 14 days before the start: 297
- KXNBAGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no start time: 1
- KXNBAGAME: the market was not open 14 days before the start: 361
- KXSERIEAGAME: the market was not open 14 days before the start: 380
- KXUCLGAME: no bid and ask 14 days before the start: 14
- KXUCLGAME: no start time: 3
- KXUCLGAME: no usable bid and ask (empty or crossed): 6
- KXUCLGAME: spread wider than 10 cents: 48
- KXUCLGAME: the market was not open 14 days before the start: 128
- KXUELGAME: no single winner (voided or unfinished): 1
- KXUELGAME: the market was not open 14 days before the start: 193
- KXWTACHALLENGERMATCH: no single winner (voided or unfinished): 25
- KXWTACHALLENGERMATCH: the market was not open 14 days before the start: 369
- KXWTAMATCH: no single winner (voided or unfinished): 122
- KXWTAMATCH: the market was not open 14 days before the start: 369
