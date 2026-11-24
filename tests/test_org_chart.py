"""Checks for the front office org chart (task 4.3). No API key needed: the
hierarchy and every "this week" line are read from the save, never asked of a
model."""

from agents import league_db, org_chart, orders, season
from agents.tools import load_league

EXAMPLE = "Upgrade safety. Stay under $5M a year."


def an_order(text: str = EXAMPLE) -> int:
    terms = orders.ground_terms(orders.OrderTerms(summary=text, wants_trades=True, positions=["S"],
                                                  max_incoming_salary=5.0, max_added_payroll=None,
                                                  protected_player_ids=[]), load_league())
    return orders.save_order(text, terms)


def play_to(week: int) -> None:
    """Simulate and advance until the save reaches `week`, so last week's games are
    always played - org_chart reads game_loop.overview(), which assumes that."""
    while season.current_week() < week:
        season.play_week()
        season.advance_week()


def test_hierarchy_matches_the_gms_team():
    nodes = org_chart.hierarchy()
    assert [n["name"] for n in nodes] == ["Owner", "General Manager", "Analytics", "Cap & Contracts",
                                          "Draft", "Coaching", "Medical"]
    assert nodes[0]["reports_to"] is None and nodes[1]["reports_to"] == "Owner"
    assert all(n["reports_to"] == "General Manager" for n in nodes[2:])
    assert all(n["role"] for n in nodes)  # every member has something to show


def test_week_one_activity_defaults(scratch_db):
    chart = org_chart.chart()
    assert chart["week"] == 1
    activity = chart["activity"]
    assert activity["General Manager"] == ["Nothing from the GM yet this week."]
    assert "safety coverage" in activity["Analytics"][0] and "6th of 6" in activity["Analytics"][0]
    assert activity["Cap & Contracts"][0] == "Holding $249.5M payroll, $5.5M space under the $255M hard cap."
    assert activity["Draft"][0].startswith("Last active at the rookie draft:") and "picks" in activity["Draft"][0]
    assert activity["Medical"] == ["Clean bill of health this week."]
    assert activity["Coaching"][0] == "No depth chart changes this week."
    assert activity["Coaching"][1].startswith("Planning this week's game around")


def test_gm_activity_shows_the_weeks_orders_and_decisions(scratch_db):
    oid = an_order()
    mid = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    orders.approve(mid, "Go.")
    gm_lines = org_chart.chart()["activity"]["General Manager"]
    assert any(EXAMPLE in line for line in gm_lines)
    assert any("approved its proposed move with Summit" in line for line in gm_lines)


def test_cap_activity_counts_moves_filed_this_week(scratch_db):
    oid = an_order()
    orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    cap_lines = org_chart.chart()["activity"]["Cap & Contracts"]
    assert cap_lines[1] == "Checked 1 proposed move this week against the cap."


def test_medical_and_coaching_flag_a_new_injury(scratch_db):
    play_to(3)
    week = season.current_week()
    db = league_db.connect()
    with db:
        league_db.save_injury(db, "HAR-01", "HAR", since_week=week, games_out=2, description="Ankle sprain.")
    db.close()
    activity = org_chart.chart()["activity"]
    assert "new injur" in activity["Medical"][0] and "Mateo Okafor" in activity["Medical"][0]  # HAR-01's name
    assert activity["Coaching"][0].startswith("Reset the depth chart after Mateo Okafor")


def test_an_older_injury_is_not_news(scratch_db):
    play_to(5)
    db = league_db.connect()
    with db:
        league_db.save_injury(db, "HAR-01", "HAR", since_week=1, games_out=10, description="Knee.")
    db.close()
    activity = org_chart.chart()["activity"]
    assert activity["Medical"][0].startswith("No new injuries this week;")
    assert activity["Coaching"][0] == "No depth chart changes this week."
