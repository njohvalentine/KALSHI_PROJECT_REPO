from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.dashboard import verdict
from app.models import OutcomeRecord
from app.research.records import save_records, score_records
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.test_records import make_records

H = {"X-Requested-With": "web"}


def test_too_few_games_says_so_and_claims_nothing():
    assert verdict(12, 0.15, 0.20)["kind"] == "too_few"
    assert verdict(0, None, None)["kind"] == "too_few"


def test_the_message_follows_the_scores():
    assert verdict(62, 0.1945, 0.1755)["kind"] == "no_edge"
    assert "No sign of an edge yet" in verdict(62, 0.1945, 0.1755)["text"]
    assert verdict(62, 0.1700, 0.1760)["kind"] == "ahead"  # ahead by 0.006: past the 0.005 bar
    assert verdict(62, 0.1700, 0.1740)["kind"] == "no_edge"  # ahead by 0.004: still noise
    assert "not proof" in verdict(62, 0.15, 0.20)["text"]


def many_games(engine, n, book=False, first=0):
    records = []
    for i in range(first, first + n):
        for r in make_records(baseline={"KX-A": 0.55, "KX-B": 0.45}):
            r.run_id, r.event_ticker, r.market_ticker = f"run{i}", f"KX-{i}", f"{r.market_ticker}-{i}"
            r.sport, r.league = "Tennis", "ATP"
            r.resolved_at, r.resolved_yes = r.created_at, (r.outcome == "A wins") == (i % 2 == 0)
            if book:
                r.book_probability, r.book_count = (Decimal("0.6") if r.outcome == "A wins" else Decimal("0.4")), 19
            records.append(r)
    save_records(engine, records)


@needs_db
def test_the_dashboard_needs_a_session(make_client):
    with make_client() as client:
        assert client.get("/api/dashboard").status_code == 401


@needs_db
def test_an_empty_database_gives_zeros_and_the_too_few_message(make_client):
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        body = client.get("/api/dashboard").json()
    assert body["games"] == 0 and body["by_sport"] == [] and body["message"]["kind"] == "too_few"
    assert body["spend"]["total_usd"] == 0 and body["flagged"]["bets"] == 0 and body["flagged"]["too_few"] is True


@needs_db
def test_the_numbers_are_the_ones_score_records_gives(make_client):
    many_games(make_client.engine, 6)
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        body = client.get("/api/dashboard").json()
    expected = score_records(make_client.engine)
    assert body["games"] == expected["games"] == 6 and body["outcomes"] == expected["used"] == 12
    assert body["scores"] == {"n": expected["same_records"]["n"], "ours": expected["same_records"]["ours"],
                              "baseline": expected["same_records"]["baseline"], "market": expected["same_records"]["market"]}
    sport = body["by_sport"][0]
    assert sport["sport"] == "Tennis" and sport["games"] == 6 and sport["too_few"] is False  # 6 games: enough to show
    assert body["spend"]["limit"] == 5 and body["spend"]["last_24h"] == 0  # no run was made in this database
    assert body["chosen_side"] == expected["paper_all"] and body["chosen_side"]["bets"] == 12
    assert body["message"]["kind"] == "too_few"  # 6 games is below the 30 needed


@needs_db
def test_the_bookmaker_block_appears_only_with_bookmaker_prices_and_marks_under_30_games(make_client):
    many_games(make_client.engine, 4)  # no bookmaker price on these
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        assert client.get("/api/dashboard").json()["bookmakers"] is None
    many_games(make_client.engine, 3, book=True, first=10)
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        block = client.get("/api/dashboard").json()["bookmakers"]
    assert block["games"] == 3 and block["too_few"] is True
    for key in ("ours", "market", "book", "baseline"):
        assert block[key] is not None


@needs_db
def test_the_tables_by_sport_and_by_kind_carry_the_scores_and_the_paper_results(make_client):
    many_games(make_client.engine, 4)
    with DbSession(make_client.engine) as db:  # two of the games are about a total, not the winner
        for r in db.scalars(select(OutcomeRecord).where(OutcomeRecord.event_ticker.in_(["KX-2", "KX-3"]))):
            r.market_kind = "total"
            r.meaningful = False  # and none of their bets is flagged
        db.commit()
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        body = client.get("/api/dashboard").json()
    expected = score_records(make_client.engine)
    kinds = {k["kind"]: k for k in body["by_kind"]}
    assert set(kinds) == {"winner", "total"} and kinds["winner"]["games"] == 2 and kinds["total"]["games"] == 2
    assert kinds["winner"]["paper"] == expected["by_kind"]["winner"]["paper_all"]
    assert kinds["winner"]["flagged"]["bets"] == 4 and kinds["total"]["flagged"]["bets"] == 0  # flagged bets are counted per group
    assert kinds["total"]["too_few"] is True  # 2 games: under 5
    sport = body["by_sport"][0]
    assert sport["sport"] == "Tennis" and sport["games"] == 4 and sport["paper"]["bets"] == 8 and sport["flagged"]["bets"] == 4


@needs_db
def test_an_empty_database_gives_empty_tables(make_client):
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        body = client.get("/api/dashboard").json()
    assert body["by_sport"] == [] and body["by_kind"] == []
