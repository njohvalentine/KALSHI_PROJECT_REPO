# Kalshi price test: raw results

Games read: 4709. Prices: hourly bid and ask closes an hour before the start, not executable fills. Rule and strategies: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md`.
A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero and the first half is also above zero.

## Strategies

- **F**: buy yes on the favourite of each game
- **L**: buy yes on every outcome priced at 20 cents or less
- **N**: buy no on every outcome priced at 20 cents or less

## Results by group

| Group | Games | Strategy | First half: bets, average | Second half: bets, average, 99% interval | Verdict |
|---|---|---|---|---|---|
| All | 4709 | F | 2354, -1.1¢ | 2355, -1.8¢, -4.3¢ to +0.7¢ | no pattern |
| All | 4709 | L | 996, -2.8¢ | 818, -1.6¢, -4.5¢ to +1.5¢ | no pattern |
| All | 4709 | N | 996, -0.2¢ | 818, -1.3¢, -4.5¢ to +1.5¢ | no pattern |
| Premier League | 385 | F | 192, -0.5¢ | 193, -10.7¢, -19.7¢ to -1.2¢ | no pattern |
| Premier League | 385 | L | 98, -4.9¢ | 97, +1.0¢, -7.7¢ to +11.2¢ | no pattern |
| Premier League | 385 | N | 98, +1.9¢ | 97, -3.8¢, -14.1¢ to +4.7¢ | not confirmed |
| Soccer (all) | 2524 | F | 1262, +0.2¢ | 1262, -2.0¢, -5.6¢ to +1.6¢ | not confirmed |
| Soccer (all) | 2524 | L | 715, -3.0¢ | 730, -1.5¢, -4.4¢ to +1.7¢ | no pattern |
| Soccer (all) | 2524 | N | 715, -0.1¢ | 730, -1.3¢, -4.6¢ to +1.6¢ | no pattern |
| Champions League | 269 | F | 134, -0.7¢ | 135, -4.7¢, -15.2¢ to +5.6¢ | no pattern |
| Champions League | 269 | L | 127, -2.0¢ | 111, -0.1¢, -7.8¢ to +8.1¢ | no pattern |
| Champions League | 269 | N | 127, -0.7¢ | 111, -2.6¢, -11.2¢ to +5.1¢ | no pattern |
| Europa League | 193 | F | 96, +7.8¢ | 97, -4.8¢, -17.8¢ to +7.8¢ | not confirmed |
| Europa League | 193 | L | 71, -9.0¢ | 66, +3.1¢, -6.9¢ to +14.3¢ | no pattern |
| Europa League | 193 | N | 71, +6.0¢ | 66, -5.8¢, -17.7¢ to +4.1¢ | not confirmed |
| MLS | 298 | F | 149, +1.2¢ | 149, -1.0¢, -12.0¢ to +9.2¢ | not confirmed |
| MLS | 298 | L | 52, +3.0¢ | 61, -1.9¢, -12.7¢ to +11.5¢ | not confirmed |
| MLS | 298 | N | 52, -6.4¢ | 61, -1.2¢, -14.8¢ to +9.2¢ | no pattern |
| La Liga | 385 | F | 192, +1.2¢ | 193, -0.2¢, -9.1¢ to +8.7¢ | not confirmed |
| La Liga | 385 | L | 111, -0.8¢ | 80, -3.4¢, -11.7¢ to +5.4¢ | no pattern |
| La Liga | 385 | N | 111, -2.1¢ | 80, +0.6¢, -8.4¢ to +8.9¢ | no pattern |
| Serie A | 380 | F | 190, -1.7¢ | 190, +2.1¢, -6.7¢ to +10.8¢ | no pattern |
| Serie A | 380 | L | 111, -2.0¢ | 124, +0.1¢, -7.2¢ to +8.2¢ | no pattern |
| Serie A | 380 | N | 111, -1.3¢ | 124, -2.8¢, -11.0¢ to +4.5¢ | no pattern |
| Bundesliga | 308 | F | 154, +3.9¢ | 154, -1.0¢, -10.7¢ to +9.1¢ | not confirmed |
| Bundesliga | 308 | L | 69, -9.3¢ | 87, -3.4¢, -11.3¢ to +5.5¢ | no pattern |
| Bundesliga | 308 | N | 69, +6.2¢ | 87, +0.6¢, -8.6¢ to +8.4¢ | not confirmed |
| Ligue 1 | 306 | F | 153, -2.0¢ | 153, -0.5¢, -10.5¢ to +10.0¢ | no pattern |
| Ligue 1 | 306 | L | 85, -4.2¢ | 95, -3.4¢, -11.7¢ to +5.1¢ | no pattern |
| Ligue 1 | 306 | N | 85, +1.1¢ | 95, +0.5¢, -8.0¢ to +8.7¢ | not confirmed |
| MLB | 372 | F | 186, -5.4¢ | 186, +1.2¢, -8.6¢ to +10.5¢ | no pattern |
| MLB | 372 | L | 0, – | 0, –, – | too few bets |
| MLB | 372 | N | 0, – | 0, –, – | too few bets |
| Baseball (all) | 372 | F | 186, -5.4¢ | 186, +1.2¢, -8.6¢ to +10.5¢ | no pattern |
| Baseball (all) | 372 | L | 0, – | 0, –, – | too few bets |
| Baseball (all) | 372 | N | 0, – | 0, –, – | too few bets |
| NBA | 361 | F | 180, -12.3¢ | 181, -0.0¢, -8.6¢ to +8.4¢ | no pattern |
| NBA | 361 | L | 33, +4.9¢ | 45, -0.8¢, -11.9¢ to +12.5¢ | not confirmed |
| NBA | 361 | N | 33, -7.7¢ | 45, -1.8¢, -15.2¢ to +9.3¢ | no pattern |
| Basketball (all) | 361 | F | 180, -12.3¢ | 181, -0.0¢, -8.6¢ to +8.4¢ | no pattern |
| Basketball (all) | 361 | L | 33, +4.9¢ | 45, -0.8¢, -11.9¢ to +12.5¢ | not confirmed |
| Basketball (all) | 361 | N | 33, -7.7¢ | 45, -1.8¢, -15.2¢ to +9.3¢ | no pattern |
| ATP | 359 | F | 179, +0.9¢ | 180, -3.6¢, -12.8¢ to +5.6¢ | not confirmed |
| ATP | 359 | L | 33, -0.5¢ | 31, +10.6¢, -7.5¢ to +31.0¢ | no pattern |
| ATP | 359 | N | 33, -2.7¢ | 31, -13.4¢, -34.5¢ to +4.3¢ | no pattern |
| Tennis (all) | 1452 | F | 726, -1.3¢ | 726, -0.9¢, -5.3¢ to +3.3¢ | no pattern |
| Tennis (all) | 1452 | L | 148, -5.0¢ | 143, -1.7¢, -8.5¢ to +6.2¢ | no pattern |
| Tennis (all) | 1452 | N | 148, +1.6¢ | 143, -1.3¢, -9.2¢ to +5.5¢ | not confirmed |
| WTA | 347 | F | 173, -2.5¢ | 174, +5.2¢, -3.6¢ to +13.1¢ | no pattern |
| WTA | 347 | L | 32, -3.0¢ | 42, -6.1¢, -15.9¢ to +6.7¢ | no pattern |
| WTA | 347 | N | 32, -0.3¢ | 42, +3.2¢, -9.9¢ to +13.0¢ | no pattern |
| ATP Challenger | 391 | F | 195, +0.6¢ | 196, -3.8¢, -13.3¢ to +4.4¢ | not confirmed |
| ATP Challenger | 391 | L | 49, -8.1¢ | 39, -2.1¢, -13.8¢ to +13.2¢ | no pattern |
| ATP Challenger | 391 | N | 49, +4.7¢ | 39, -1.2¢, -16.9¢ to +10.6¢ | not confirmed |
| WTA Challenger | 355 | F | 177, -2.9¢ | 178, -2.6¢, -11.1¢ to +5.5¢ | no pattern |
| WTA Challenger | 355 | L | 34, -11.7¢ | 31, -2.1¢, -14.9¢ to +15.0¢ | no pattern |
| WTA Challenger | 355 | N | 34, +8.1¢ | 31, -0.9¢, -17.8¢ to +12.0¢ | not confirmed |

## Accuracy and calibration

| Group | Games | Period | Brier score of the middle price |
|---|---|---|---|
| All | 4709 | 2025-04-15 to 2026-08-18 | 0.1975 |
| Premier League | 385 | 2025-05-11 to 2026-05-24 | 0.2026 |
| Soccer (all) | 2524 | 2025-04-30 to 2026-08-18 | 0.1920 |
| Champions League | 269 | 2025-04-30 to 2026-08-18 | 0.1812 |
| Europa League | 193 | 2025-05-08 to 2026-08-14 | 0.1791 |
| MLS | 298 | 2025-05-28 to 2026-08-17 | 0.1997 |
| La Liga | 385 | 2025-05-11 to 2026-08-17 | 0.1905 |
| Serie A | 380 | 2025-08-23 to 2026-05-24 | 0.1938 |
| Bundesliga | 308 | 2025-08-22 to 2026-05-25 | 0.1870 |
| Ligue 1 | 306 | 2025-08-15 to 2026-05-29 | 0.1940 |
| MLB | 372 | 2025-04-16 to 2026-08-17 | 0.2469 |
| Baseball (all) | 372 | 2025-04-16 to 2026-08-17 | 0.2469 |
| NBA | 361 | 2025-04-15 to 2026-06-11 | 0.2096 |
| Basketball (all) | 361 | 2025-04-15 to 2026-06-11 | 0.2096 |
| ATP | 359 | 2025-06-19 to 2026-08-18 | 0.2108 |
| Tennis (all) | 1452 | 2025-06-19 to 2026-08-18 | 0.1961 |
| WTA | 347 | 2025-06-23 to 2026-08-18 | 0.1920 |
| ATP Challenger | 391 | 2026-01-13 to 2026-08-18 | 0.1891 |
| WTA Challenger | 355 | 2026-01-30 to 2026-08-07 | 0.1931 |

### Calibration, all games

| Price bucket | Outcomes | Mean price | How often it happened |
|---|---|---|---|
| 0-10¢ | 355 | 0.070 | 0.056 |
| 10-20¢ | 1406 | 0.157 | 0.151 |
| 20-30¢ | 3104 | 0.252 | 0.253 |
| 30-40¢ | 1929 | 0.343 | 0.328 |
| 40-50¢ | 1621 | 0.446 | 0.471 |
| 50-60¢ | 1399 | 0.549 | 0.543 |
| 60-70¢ | 1042 | 0.647 | 0.636 |
| 70-80¢ | 615 | 0.745 | 0.741 |
| 80-90¢ | 358 | 0.841 | 0.866 |
| 90-100¢ | 113 | 0.933 | 0.947 |

## Games dropped, and why

- KXATPCHALLENGERMATCH: no bid and ask an hour before the start: 1
- KXATPCHALLENGERMATCH: no single winner (voided or unfinished): 159
- KXATPCHALLENGERMATCH: spread wider than 10 cents: 8
- KXATPMATCH: no bid and ask an hour before the start: 5
- KXATPMATCH: no single winner (voided or unfinished): 138
- KXATPMATCH: no usable bid and ask (empty or crossed): 1
- KXATPMATCH: spread wider than 10 cents: 14
- KXBUNDESLIGAGAME: no single winner (voided or unfinished): 3
- KXEPLGAME: no bid and ask an hour before the start: 1
- KXEPLGAME: spread wider than 10 cents: 1
- KXLALIGAGAME: no bid and ask an hour before the start: 1
- KXLALIGAGAME: no single winner (voided or unfinished): 3
- KXLIGUE1GAME: no bid and ask an hour before the start: 1
- KXLIGUE1GAME: no single winner (voided or unfinished): 1
- KXMLBGAME: no single winner (voided or unfinished): 14
- KXMLSGAME: no bid and ask an hour before the start: 1
- KXMLSGAME: no single winner (voided or unfinished): 3
- KXMLSGAME: no start time: 2
- KXMLSGAME: spread wider than 10 cents: 1
- KXNBAGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no start time: 1
- KXUCLGAME: no start time: 3
- KXUELGAME: no single winner (voided or unfinished): 1
- KXWTACHALLENGERMATCH: no bid and ask an hour before the start: 7
- KXWTACHALLENGERMATCH: no single winner (voided or unfinished): 25
- KXWTACHALLENGERMATCH: spread wider than 10 cents: 7
- KXWTAMATCH: no bid and ask an hour before the start: 4
- KXWTAMATCH: no single winner (voided or unfinished): 122
- KXWTAMATCH: no usable bid and ask (empty or crossed): 1
- KXWTAMATCH: spread wider than 10 cents: 17
