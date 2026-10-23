"""How much a source is trusted: the tier of a website, and the best tier among the pages that support a fact.

Three tiers. `official`: the organisation that runs the competition or the team (a league, a tour, a federation, a tournament, a club). `news`: an independent
news or sports-media organisation. `other`: everything else, **including every host not listed here**: betting, odds, tip and prediction sites, prediction
markets, statistics databases, forums, open encyclopedias. Nothing is trusted by default. The list was reviewed by the user on 2026-10-23
(docs/discussion/SOURCE-TRUST-HOSTS-2026-10-23.md). A subdomain counts as its host (`de.uefa.com` is `uefa.com`); a look-alike (`evil-uefa.com`) does not.
The tier is a statement about who runs the site, not about whether a page is true or current. It is a label for the forecasters and for a person, never a
reason to drop a fact. New hosts appear with every league: `python -m app.cli source-hosts` lists the hosts in saved runs that are not reviewed yet."""

from urllib.parse import urlsplit

OFFICIAL = frozenset({
    "arsenal.com", "asroma.com", "atlutd.com", "atptour.com",
    "austinfc.com", "avfc.co.uk", "baystars.co.jp", "bundesliga.com",
    "bvb.de", "cfmontreal.com", "charlottefootballclub.com", "chelseafc.com",
    "chicagofirefc.com", "clubbrugge.be", "coloradorapids.com", "columbuscrew.com",
    "comofootball.com", "dcunited.com", "fcbarcelona.com", "fccincinnati.com",
    "fcdallas.com", "feyenoord.com", "fighters.co.jp", "galatasaray.org",
    "glimt.no", "hanshintigers.jp", "houstondynamofc.com", "inter.it",
    "intermiamicf.com", "itftennis.com", "koreabaseball.com", "lafc.com",
    "lagalaxy.com", "laliga.com", "lask.at", "legaseriea.it",
    "liverpoolfc.com", "losc.fr", "mancity.com", "manutd.com",
    "mlb.com", "mlssoccer.com", "mnufc.com", "nashvillesc.com",
    "nba.com", "newyorkcityfc.com", "newyorkredbulls.com", "npb.jp",
    "olbiachallenger.com", "openderoanne.com", "orlandocitysc.com", "parmacalcio1913.com",
    "philadelphiaunion.com", "premierleague.com", "psg.fr", "rbleipzig.com",
    "rclens.fr", "realbetisbalompie.es", "realmadrid.com", "revolutionsoccer.net",
    "rolexshanghaimasters.com", "roveretopen.it", "sandiegofc.com", "shakhtar.com",
    "sjearthquakes.com", "skslovan.com", "soundersfc.com", "sporting.pt",
    "sportingkc.com", "stlcitysc.com", "timbers.com", "torinofc.it",
    "torontofc.ca", "tottenhamhotspur.com", "uefa.com", "vfb.de",
    "vikingfotball.no", "whitecapsfc.com", "wtatennis.com",
})
NEWS = frozenset({
    "apnews.com", "as.com", "bbc.co.uk", "bbc.com",
    "cbssports.com", "en.sedaily.com", "espn.com", "foxsports.com",
    "gazzetta.it", "kicker.de", "lequipe.fr", "marca.com",
    "nytimes.com", "outsports.com", "reuters.com", "si.com",
    "skysports.com", "sport.sky.it", "sportsnet.ca", "theathletic.com",
    "theguardian.com", "tntsports.co.uk", "usatoday.com",
})
# Reviewed and deliberately "other" (the reason is the value). Listing them keeps `source-hosts` from asking about them again; the lookup does not need them.
OTHER = {
    "actionnetwork.com": "betting media",
    "agentbets.ai": "odds and predictions (AI-written pages)",
    "asaptext.com": "unknown site",
    "betdiary.io": "betting",
    "betexplorer.com": "odds database",
    "betfair.com": "betting",
    "betfair.ro": "betting",
    "betmgm.com": "betting",
    "betmonitor.com": "betting",
    "betus.com.pa": "betting",
    "bovada.lv": "betting",
    "coinstats.app": "crypto app",
    "coretennis.net": "unknown tennis site",
    "covers.com": "betting information",
    "cupbracket.com": "tournament brackets site",
    "dave.sport": "predictions",
    "fixturedownload.com": "fixture lists",
    "gainblers.com": "betting tips",
    "getsbet.ro": "betting",
    "ladbrokes.com": "betting",
    "limitless.exchange": "prediction market",
    "matchstat.com": "statistics and predictions",
    "mykbostats.com": "KBO statistics site (fan run)",
    "oddsator.com": "odds site",
    "oddschecker.com": "odds site",
    "oddsdigger.com": "odds site",
    "paddypower.com": "betting",
    "pandabet.com.au": "betting",
    "pitchvora.com": "odds and tips",
    "polymarket.com": "prediction market",
    "polymarket.us": "prediction market",
    "poznavach.com": "predictions",
    "raptorsrepublic.com": "fan site",
    "raquetc.com": "tennis site",
    "reddit.com": "forum",
    "robinhood.com": "prediction market",
    "ruedesjoueurs.com": "betting predictions",
    "simplyodds.com": "odds site",
    "sofascore.com": "statistics database",
    "sportbusy.com": "odds and predictions",
    "sportsbetting.dog": "betting tips",
    "sportsbookish.com": "odds site",
    "sportsmole.co.uk": "match previews and predictions",
    "sportytrader.com": "betting tips",
    "stake.com": "betting",
    "tactix.football": "analysis site",
    "tennis-db.com": "statistics database",
    "tennisendirect.net": "tennis site",
    "tennisexplorer.com": "statistics database",
    "tennislive.it": "statistics database",
    "tennislive.net": "statistics database",
    "tennistemple.com": "statistics database",
    "thepinktimes.com": "general news site, not a sports authority",
    "totalfootballanalysis.com": "analysis blog",
    "tuttomercatoweb.com": "transfer gossip",
    "valuebetennis.com": "betting tips",
    "wikipedia.org": "open encyclopedia anyone can edit",
}
_RANK = {"official": 2, "news": 1, "other": 0}


def host_of(url: str) -> str:
    """The host of a URL in lower case without a leading www., or "" when the text is not a URL."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


_SECOND_LEVELS = frozenset({"co", "com", "org", "net", "gov", "ac", "edu", "ne", "or", "go"})


def registered_domain(host: str) -> str:
    """The registrable part of a host: the last two labels, or three when the second-to-last is a common second level under a two-letter country code
    (bbc.co.uk, news.com.au). A short built-in rule, not the full public suffix list: it can be wrong for rare suffixes."""
    labels = [l for l in host.lower().split(".") if l]
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _matches(host: str, entries) -> bool:
    return any(host == e or host.endswith("." + e) for e in entries)


def tier_of(url: str) -> str:
    host = host_of(url)
    if not host:
        return "other"
    if _matches(host, OFFICIAL):
        return "official"
    if _matches(host, NEWS):
        return "news"
    return "other"


def page_tier(cited_url: str, final_url: str | None = None) -> str:
    """The tier of a page: the lower of the tier of the address that was cited and of the address the fetcher really reached after redirects (`final_url`).
    A cited address on a listed host that redirects to a stranger's page must not give the stranger's text the label; an unlisted address that lands on a
    listed one is not promoted either. No final address recorded: the cited one."""
    tiers = (tier_of(cited_url), tier_of(final_url) if final_url else tier_of(cited_url))
    return min(tiers, key=_RANK.__getitem__)


def best_tier(urls, final_urls: dict[str, str] | None = None) -> str:
    """The highest tier among the pages (official over news over other); "other" when there are none. `final_urls` maps a cited address to the address reached."""
    finals = final_urls or {}
    return max((page_tier(u, finals.get(u)) for u in urls), key=_RANK.__getitem__, default="other")


def unlisted_hosts(seen: dict[str, int]) -> list[tuple[str, int]]:
    """From {url: count}: the hosts that are in none of the three lists, with their total counts, the biggest first."""
    counts: dict[str, int] = {}
    for url, n in seen.items():
        host = host_of(url)
        if host and not (_matches(host, OFFICIAL) or _matches(host, NEWS) or _matches(host, OTHER)):
            counts[host] = counts.get(host, 0) + n
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
