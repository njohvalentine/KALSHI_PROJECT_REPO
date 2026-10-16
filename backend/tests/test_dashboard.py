from app.dashboard import verdict
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


def many_games(engine, n):
    records = []
    for i in range(n):
        for r in make_records(baseline={"KX-A": 0.55, "KX-B": 0.45}):
            r.run_id, r.event_ticker, r.market_ticker = f"run{i}", f"KX-{i}", f"{r.market_ticker}-{i}"
            r.sport, r.league = "Tennis", "ATP"
            r.resolved_at, r.resolved_yes = r.created_at, (r.outcome == "A wins") == (i % 2 == 0)
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
    assert body["chosen_side"] == expected["paper_all"] and body["chosen_side"]["bets"] == 12
    assert body["message"]["kind"] == "too_few"  # 6 games is below the 30 needed
