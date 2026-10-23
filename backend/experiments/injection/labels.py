"""The label measurement (FEAT-20261023-1130): conditions PN (the app as it is now, no labels in the facts) and PT (the same, with the trust label on each fact).

The app's own host list does not know the harness's fake hosts, so the harness decides which of them are official: the three fake hosts of the true base pages. Everything else
(the attack and clean pages on news.test) is judged by the app's own `tier_of`, which says "other" for an unlisted host."""

from app.research.source_trust import host_of, tier_of
from experiments.injection import corpus

FAKE_OFFICIAL = frozenset(corpus.OFFICIAL_HOSTS.values())
OFFICIAL_BASE_CONDITIONS = frozenset({"PN", "PT"})  # the true base pages sit on the fake official hosts
LABEL_CONDITIONS = frozenset({"PT"})  # the facts carry their label
CURRENT_APP = OFFICIAL_BASE_CONDITIONS  # the researcher prompt is the app's own (with the hostile-instruction rule) and the forecaster prompt explains the labels


def harness_tier(url: str) -> str:
    return "official" if host_of(url) in FAKE_OFFICIAL else tier_of(url)
