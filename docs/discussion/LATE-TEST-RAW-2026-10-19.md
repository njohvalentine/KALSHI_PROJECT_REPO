# Kalshi late-game test: raw results

Games read: 2250. Bet: one contract of NO on every outcome whose YES middle price is 10 to 40 cents, at the NO ask plus the series fee, held to the result. Rule: `docs/specs/FEAT-20261019-1231-late-game-price-test.md`. The tested entry is 5 minutes before the close; 10 and 2 minutes are descriptive.
**The close time is the real end of the game, known only afterwards, so this is NOT a tradable strategy.** No depth data; minute bid and ask closes are not fills.
A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero, the first half is also above zero, and each half has at least 100 bets.

Series left out because their close is a fixed time after the start, not the real end: KXEPLGAME, KXUCLGAME, KXUELGAME, KXMLSGAME, KXLALIGAGAME, KXSERIEAGAME, KXBUNDESLIGAGAME, KXLIGUE1GAME.

| Group | Games | Entry | First half: bets, average | Second half: bets, average, 99% interval | Quote unchanged 5 min before (all bets) | Verdict |
|---|---|---|---|---|---|---|
| All | 2250 | 5 min | 48, +12.0¢ | 105, +14.6¢, +9.6¢ to +18.2¢ | 0 of 153 | too few bets |
| All | 2250 | 10 min | 164, +15.5¢ | 265, +12.7¢, +8.7¢ to +15.9¢ | 0 of 429 | descriptive |
| All | 2250 | 2 min | 13, +8.4¢ | 32, +17.0¢, +14.1¢ to +20.2¢ | 0 of 45 | descriptive |
| Baseball (all) | 372 | 5 min | 0, – | 8, +2.4¢, -38.1¢ to +18.8¢ | 0 of 8 | too few bets |
| Baseball (all) | 372 | 10 min | 20, +17.1¢ | 31, +12.0¢, -2.1¢ to +20.5¢ | 0 of 51 | descriptive |
| Baseball (all) | 372 | 2 min | 0, – | 0, –, – | 0 of 0 | descriptive |
| Basketball (all) | 361 | 5 min | 1, -81.1¢ | 1, -75.3¢, -75.3¢ to -75.3¢ | 0 of 2 | too few bets |
| Basketball (all) | 361 | 10 min | 8, -12.8¢ | 5, +4.7¢, -54.4¢ to +35.0¢ | 0 of 13 | descriptive |
| Basketball (all) | 361 | 2 min | 1, -66.6¢ | 2, +21.8¢, +18.9¢ to +24.7¢ | 0 of 3 | descriptive |
| Tennis (all) | 1517 | 5 min | 60, +14.2¢ | 83, +16.8¢, +13.0¢ to +19.7¢ | 0 of 143 | too few bets |
| Tennis (all) | 1517 | 10 min | 162, +14.3¢ | 203, +14.6¢, +11.0¢ to +17.7¢ | 0 of 365 | descriptive |
| Tennis (all) | 1517 | 2 min | 16, +15.6¢ | 26, +16.5¢, +13.3¢ to +20.2¢ | 0 of 42 | descriptive |

## Bets not used, and why (5-minute entry, in-band prices only)

- KXATPCHALLENGERMATCH: no single winner (voided or unfinished): 159
- KXATPMATCH: no single winner (voided or unfinished): 138
- KXBUNDESLIGAGAME: no single winner (voided or unfinished): 3
- KXLALIGAGAME: no single winner (voided or unfinished): 3
- KXLIGUE1GAME: no single winner (voided or unfinished): 1
- KXMLBGAME: no single winner (voided or unfinished): 14
- KXMLSGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no single winner (voided or unfinished): 3
- KXNBAGAME: no start time: 1
- KXUELGAME: no single winner (voided or unfinished): 1
- KXWTACHALLENGERMATCH: no single winner (voided or unfinished): 25
- KXWTAMATCH: no single winner (voided or unfinished): 122
- fewer than 10 contracts traded in the 5 minutes before: 1
- no bid and ask before the entry: 66
- spread wider than 10 cents: 19
