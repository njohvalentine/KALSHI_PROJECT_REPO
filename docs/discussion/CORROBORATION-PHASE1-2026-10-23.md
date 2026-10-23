# Corroboration, phase 1: raw results

Runs: 30 saved runs with at least one supported claim. Supported claims: 243. Judge calls: 253 (0 judge call(s) failed and are not counted: a claim on such a page may have had a second website that was not seen). Model cost: 1.22 USD.

**Claims that got a second independent website: 11 of 243 = 5%.**

| Sport | Corroborated | Claims | Share |
|---|---|---|---|
| Baseball | 0 | 28 | 0% |
| Soccer | 7 | 145 | 5% |
| Tennis | 4 | 70 | 6% |

Number of independent websites per claim: 1: 232, 2: 10, 3: 1.

## The rule for phase 2 (fixed before the run)

Phase 2 is proposed only if at least 25 percent of the supported claims get a second independent website **and** the hand check below finds that the second page states the same fact in at least 17 of 20 cases. Result of the first condition: not met. The hand check follows.

## Hand check sample (11 corroborated claims, seed 20261023)

1. **Claim:** CoreTennis lists the tournament surface as Clay.  
   Supported by: coretennis.net  
   Second site: tennisendirect.net (https://www.tennisendirect.net/atp/match/felix-gill-VS-gabriele-piraino/san-gregorio-di-catania-challenger-2026/?utm_source=openai)  
   Quote: “Affichage
ATPSan Gregorioterre battueTERMINÉItalie”  
   Judge: The page explicitly lists the surface as clay (terre battue).

2. **Claim:** UEFA’s league-phase fixtures page lists Como vs Manchester United on 21/10/2026 at 18:45.  
   Supported by: uefa.com  
   Second site: comofootball.com (https://comofootball.com/en/uefa-champions-league-como-1907-vs-manchester-united-first-phase-of-sale/?utm_source=openai)  
   Quote: “tickets with pre-match hospitality for the match Como vs Manchester United (scheduled for 21/10/2026 at 18:45 at Stadio G. Sinigaglia) will be on sale”  
   Judge: The page states Como vs Manchester United is scheduled for 21/10/2026 at 18:45.

3. **Claim:** Nashville SC vs. Sporting Kansas City is listed for Wednesday, Oct. 14 at GEODIS Park in Nashville, Tennessee, with a 7:30 p.m. CT kickoff.  
   Supported by: nashvillesc.com  
   Second site: sportingkc.com (https://www.sportingkc.com/news/preview-sporting-kc-travels-to-take-on-supporters-shield-leaders-nashville-sc-on-wednesday?utm_source=openai)  
   Quote: “Sporting Kansas City at Nashville SC”  
   Judge: The page lists the match, date, kickoff time, and venue exactly as claimed.

4. **Claim:** UEFA’s Inter vs Club Brugge head-to-head page lists the upcoming match as 2026/27 UEFA Champions League Matchday 2: Inter vs Club Brugge.  
   Supported by: uefa.com  
   Second site: inter.it (https://www.inter.it/en/news/inter-vs-club-brugge-previous-meetings-and-key-facts?utm_source=openai)  
   Quote: “Inter vs. Club Brugge, valid for Matchday 2 of the 2026/27 Champions League league phase, will take place at San Siro on Tuesday 13 October at 21:00”  
   Judge: The page states the upcoming match and its Matchday 2 2026/27 Champions League context.

5. **Claim:** FC Dallas’ official preview for the match lists Seattle at 11-9-8 with 41 points.  
   Supported by: fcdallas.com  
   Second site: soundersfc.com (https://www.soundersfc.com/news/dalvsea-preview-all-you-need-to-know-when-the-sounders-visit-fc-dallas-on-wednesday-pres-by-ticketmaster)  
   Quote: “2026 MLS STANDINGS: Sounders: 11-9-8 (41 points, 7th West), Dallas: 13-7-8 (47 points, 3rd West)”  
   Judge: The standings line matches Seattle at 11-9-8 with 41 points.

6. **Claim:** The WTA player list for Lisbon lists Milana Ivantsiv under Portugal.  
   Supported by: wtatennis.com  
   Second site: tennismajors.com (https://www.tennismajors.com/matches/wta/lisboa-belem-open/jessica-bouzas-maneiro-vs-milana-ivantsiv?utm_source=openai)  
   Quote: “Milana
Ivantsiv
Portugal
Coming soon”  
   Judge: The page shows Milana Ivantsiv with Portugal on the Lisboa Belem Open page.

7. **Claim:** In that Austin-Nashville match, Brandon Vazquez scored Austin FC’s goal in the 76th minute.  
   Supported by: austinfc.com  
   Second site: lafc.com (https://www.lafc.com/news/preview-lafc-vs-austin-fc-2026-mls-season-october-14)  
   Quote: “Striker Brandon Vazquez pulled Austin to within 2-1 at the 76-minute mark with a sensational strike off the outside of his right boot”  
   Judge: The page states Vazquez scored Austin’s goal in the 76th minute of that Nashville match.

8. **Claim:** FC Dallas’ official preview for the match lists Dallas at 13-7-8 with 47 points.  
   Supported by: fcdallas.com  
   Second site: soundersfc.com (https://www.soundersfc.com/news/dalvsea-preview-all-you-need-to-know-when-the-sounders-visit-fc-dallas-on-wednesday-pres-by-ticketmaster)  
   Quote: “2026 MLS STANDINGS: Sounders: 11-9-8 (41 points, 7th West), Dallas: 13-7-8 (47 points, 3rd West)”  
   Judge: The standings line matches Dallas at 13-7-8 with 47 points.

9. **Claim:** The WTA overview page lists the 2026 tournament dates as October 12–18, 2026.  
   Supported by: wtatennis.com  
   Second site: roveretopen.it (https://www.roveretopen.it/?utm_source=openai)  
   Quote: “12 – 18 Ottobre 2026 – ROVERETO”  
   Judge: The page explicitly lists the tournament dates as October 12–18, 2026.

10. **Claim:** New England Revolution’s official match preview says kickoff at FC Cincinnati is set for 7:30 p.m. ET on Wednesday night.  
   Supported by: revolutionsoccer.net  
   Second site: fccincinnati.com (https://www.fccincinnati.com/news/recap-atlanta-united-fc-1-fc-cincinnati-3?utm_source=openai)  
   Quote: “FC Cincinnati return to TQL Stadium on Wednesday, October 14 against the New England Revolution, with kickoff set for 7:30 p.m. ET as the match airs on Apple TV”  
   Judge: The page gives the Wednesday, October 14 home match kickoff time as 7:30 p.m. ET.

11. **Claim:** The official tournament program page lists the venue as PalaBaldresca, Rovereto.  
   Supported by: roveretopen.it  
   Second site: wtatennis.com (https://www.wtatennis.com/tournaments/1140/Rovereto/2026)  
   Quote: “RoveretOpen Citta della Pace is a WTA 125 tournament played on indoor hard courts in Rovereto, Italy. Since 2025, 32 singles players and 16 doubles teams compete at this event annually in an effort to win a title from PalaBaldresca.”  
   Judge: The page names PalaBaldresca and gives the location as Rovereto, Italy.

