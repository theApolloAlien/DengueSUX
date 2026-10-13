import numpy as np
import pandas as pd

from denguesux.cluster_archive import parse_capture, parse_location, road_key
from denguesux import area_forecast as af
from denguesux import ledger

OLD = """<p>The information provided in this listing is accurate as at 28 Feb 2019</p>
<table class="table surveillance-table two-row-head"><tbody>
<tr><th rowspan="2">S/N</th><th rowspan="2">Alert Level</th><th rowspan="2">Locality</th>
<th rowspan="2">Cases with onset in last 2 weeks </th><th rowspan="2">Cases since start of cluster</th><th colspan="2">Breakdown</th></tr>
<tr><th>Location</th><th>No. of Cases</th></tr>
<tr class="hashlink" id="x"></tr>
<tr><td rowspan="2">1</td><td rowspan="2"><div class="red"></div></td><td data-type="locality" rowspan="2"><a href="#onemap">Bedok Reservoir Rd(Blk122,124)</a></td>
<td rowspan="2">9</td><td rowspan="2">13</td><td>Bedok Reservoir Road<br/>(Blk 122)</td><td>1</td></tr>
<tr><td>Bedok Reservoir Road<br/>(Blk 124)</td><td>12</td></tr>
<tr><td>2</td><td><div class="yellow"></div></td><td><a>Ah Soo Gdn</a></td><td>2</td><td>2</td><td>Ah Soo Garden</td><td>2</td></tr>
</tbody></table>"""

NEW = """<p>The information provided in this listing is accurate as at 15 Jan 2025</p>
<table class="table surveillance-table two-row-head dengue-fixed-table"><tbody>
<tr class="header-row"><th>S/N</th><th>Alert Level</th><th>Locality</th><th>Cases with symptom onset in last 2 weeks </th><th>Cases since start of cluster</th></tr>
<tr data-row="1"><td>1</td><td><div class="red"></div></td><td data-type="locality"><a href="#onemap">Bt Panjang Ring Rd (Blk 235, 236)</a>
<p class="show-breakdown">See locality details<table class="locality-details"><tr><th>Location</th><th>No. of Cases</th></tr>
<tr><td>Bukit Panjang Ring Road<br/>(Blk 235)</td><td>1</td></tr><tr><td>Bukit Panjang Ring Road<br/>(Blk 236)</td><td>2</td></tr></table></p></td>
<td>7</td><td>10</td></tr>
</tbody></table>"""


def test_old_listing_format_keeps_rowspan_breakdown():
    parsed = parse_capture(OLD)
    assert parsed["as_at"] == "2019-02-28"
    assert [c["serial"] for c in parsed["clusters"]] == [1, 2]
    first = parsed["clusters"][0]
    assert first["alert"] == "red" and first["recent_cases"] == 9 and first["total_cases"] == 13
    assert first["locations"] == [{"street": "Bedok Reservoir Road", "block": "122", "cases": 1},
                                  {"street": "Bedok Reservoir Road", "block": "124", "cases": 12}]
    assert parsed["clusters"][1]["locations"] == [{"street": "Ah Soo Garden", "block": None, "cases": 2}]


def test_new_listing_format_reads_nested_details_table():
    parsed = parse_capture(NEW)
    assert parsed["as_at"] == "2025-01-15"
    cluster = parsed["clusters"][0]
    assert cluster["locality"].startswith("Bt Panjang Ring Rd") and cluster["total_cases"] == 10
    assert [loc["cases"] for loc in cluster["locations"]] == [1, 2]


def test_location_and_road_normalisation_never_guess():
    assert parse_location("Lorong 1 Toa Payoh (Blk 160)") == {"street": "Lorong 1 Toa Payoh", "block": "160"}
    assert parse_location("Braddell Hill (Braddell View)") == {"street": "Braddell Hill (Braddell View)", "block": None}
    assert road_key("LOR 1 TOA PAYOH") == road_key("Lorong 1 Toa Payoh") == "LORONG 1 TOA PAYOH"
    assert road_key("Braddell Hill (Braddell View)") == "BRADDELL HILL"


def _panel():
    days = pd.to_datetime(["2025-01-01", "2025-01-15", "2025-01-20", "2025-02-10"])
    rows = []
    for day, people in zip(days, [12, 3, 0, 15]):
        rows.append({"date": day, "area_code": "AA", "area_name": "A", "people": people, "clusters": int(people > 0), "red": int(people >= 10), "source": "t"})
        rows.append({"date": day, "area_code": "BB", "area_name": "B", "people": 0, "clusters": 0, "red": 0, "source": "t"})
    return pd.DataFrame(rows)


def test_pairs_use_listings_ten_to_twenty_one_days_later_closest_to_fourteen():
    pairs = af.make_pairs(_panel())
    origins = pairs.drop_duplicates("date")
    assert list(origins.horizon_days) == [14, 21]  # 1 Jan -> 15 Jan; 20 Jan -> 10 Feb; 15 Jan has no 10–21 day partner
    first = pairs[(pairs.date == "2025-01-01") & (pairs.area_code == "AA")].iloc[0]
    assert first.target_people == 3 and first.y_any == 1 and first.y_high == 0


def test_band_rules_match_the_live_map():
    assert list(af.band_now([12, 3, 0], [1, 1, 0])) == ["High", "Medium", "Low"]
    assert list(af.band_from_probabilities([0.9, 0.6, 0.2], [0.7, 0.1, 0.05])) == ["High", "Medium", "Low"]


def test_track_record_uses_only_earlier_listings():
    featured = af._features(_panel(), pd.DataFrame({"week_end": pd.to_datetime(["2024-12-01", "2024-12-08", "2024-12-15"]), "cases": [10, 20, 30]}),
                            pd.Series(dtype=float))
    a = featured[featured.area_code == "AA"].sort_values("date")
    # Second listing's record is the first listing only (had a cluster), never itself.
    assert a.track_record.iloc[1] == 1.0
    assert np.isclose(a.track_record.iloc[3], 2 / 3)


def test_ledger_is_append_only_and_scores_once(tmp_path, monkeypatch):
    book = ledger.load(tmp_path)
    assert {r["target"] for r in book["records"]} == {"2026-W40", "2026-W41"}
    model = {"name": "m", "run_id": "r", "live_forecast": {"forecasts": [
        {"target_epi_week": "2026-W41", "trained_on_labels_through": "2026-10-03", "target_date": "2026-10-11", "prediction": 99, "lower": 1, "upper": 200}]}}
    assert ledger.record_national(book, model) == 0  # same labels: the first publication stands
    assert next(r for r in book["records"] if r["target"] == "2026-W41")["prediction"] == 68.3
    monkeypatch.setattr(af, "national_weekly", lambda root: pd.DataFrame({"week_end": pd.to_datetime(["2026-10-10"]), "cases": [70.0]}))
    monkeypatch.setattr(ledger, "_area_snapshots", lambda root: {})
    assert ledger.score(book, tmp_path) == 1
    row = next(r for r in book["records"] if r["target"] == "2026-W40")
    assert row["actual"] == 70.0 and row["covered"] is True and row["abs_error"] == 8.3
    assert ledger.score(book, tmp_path) == 0
