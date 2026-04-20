from __future__ import annotations

import unittest
from unittest.mock import patch

import scraper


class _FakeResponse:
    def __init__(self, *, json_data=None, text: str = "", status_code: int = 200) -> None:
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ScraperTests(unittest.TestCase):
    def test_collect_session_results_uses_name_hint_and_ranks_multiple_drivers(self) -> None:
        csv_text = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver B,56.100,8,12",
                "Driver A,55.900,10,7",
                "Driver C,,5,9",
            ]
        )

        def fake_get(url: str, **kwargs):
            del kwargs
            if url.endswith("/csv"):
                return _FakeResponse(text=csv_text)
            self.fail(f"Unexpected URL call: {url}")

        with patch.object(scraper.requests, "get", side_effect=fake_get):
            result = scraper.collect_session_results(
                "https://speedhive.mylaps.com/sessions/12345",
                session_name_hint="Practice Heat 1",
            )

        self.assertEqual(result["session_name"], "Practice Heat 1")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["driver"], "Driver A")
        self.assertEqual(result["results"][0]["position"], 1)
        self.assertEqual(result["results"][1]["driver"], "Driver B")
        self.assertEqual(result["results"][1]["position"], 2)

    def test_collect_event_participation_aggregates_all_session_types_and_drivers(self) -> None:
        session_111_csv = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver A,1:00.100,12,5",
                "Driver B,1:01.200,8,7",
                "Driver X,,3,10",
            ]
        )
        session_222_csv = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver A,59.900,10,5",
                "Driver C,1:03.500,6,9",
            ]
        )
        session_333_csv = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver B,59.100,15,7",
                "Driver D,1:04.000,5,11",
            ]
        )

        def fake_get(url: str, **kwargs):
            del kwargs
            if url.endswith("/events/999"):
                return _FakeResponse(json_data={"name": "Weekly Event"})
            if url.endswith("/events/999/sessions"):
                return _FakeResponse(
                    json_data={
                        "sessions": [
                            {"id": 111, "name": "Practice 1", "type": "Practice"},
                            {"id": 222, "name": "Qualifying 1", "type": "Qualifying"},
                            {"id": 333, "name": "Race 1", "type": "Race"},
                        ]
                    }
                )
            if url.endswith("/sessions/111/csv"):
                return _FakeResponse(text=session_111_csv)
            if url.endswith("/sessions/222/csv"):
                return _FakeResponse(text=session_222_csv)
            if url.endswith("/sessions/333/csv"):
                return _FakeResponse(text=session_333_csv)
            self.fail(f"Unexpected URL call: {url}")

        with patch.object(scraper.requests, "get", side_effect=fake_get):
            result = scraper.collect_event_participation(
                "https://speedhive.mylaps.com/events/999",
                minimum_sessions=2,
            )

        self.assertEqual(result["event_name"], "Weekly Event")
        self.assertEqual(result["total_sessions"], 3)
        self.assertEqual(result["total_practice_sessions"], 3)
        self.assertEqual([row["driver"] for row in result["results"]], ["Driver B", "Driver A", "Driver C", "Driver D"])
        self.assertEqual(result["results"][0]["sessions_attended_count"], 2)
        self.assertEqual(result["results"][0]["fastest_lap"], "59.100")
        self.assertEqual(result["results"][0]["total_laps"], 23)
        self.assertEqual(result["results"][0]["over_minimum"], "Yes")
        self.assertEqual(result["results"][1]["sessions_attended_count"], 2)
        self.assertEqual(result["results"][1]["fastest_lap"], "59.900")
        self.assertEqual(result["results"][2]["sessions_attended_count"], 1)
        self.assertEqual(result["results"][2]["fastest_lap"], "1:03.500")

    def test_collect_participation_accepts_manual_session_urls_and_ids(self) -> None:
        session_444_csv = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver A,58.200,11,5",
            ]
        )
        session_555_csv = "\n".join(
            [
                "Competitor,Best Lap,Laps,Kart",
                "Driver B,58.500,10,7",
                "Driver A,58.000,12,5",
            ]
        )

        def fake_get(url: str, **kwargs):
            del kwargs
            if url.endswith("/sessions/444"):
                return _FakeResponse(json_data={"name": "Qualifying 2"})
            if url.endswith("/sessions/555"):
                return _FakeResponse(json_data={"name": "Race Final"})
            if url.endswith("/sessions/444/csv"):
                return _FakeResponse(text=session_444_csv)
            if url.endswith("/sessions/555/csv"):
                return _FakeResponse(text=session_555_csv)
            self.fail(f"Unexpected URL call: {url}")

        with patch.object(scraper.requests, "get", side_effect=fake_get):
            result = scraper.collect_participation(
                session_urls="https://speedhive.mylaps.com/sessions/444\n555",
                minimum_sessions=2,
            )

        self.assertEqual(result["event_name"], "Selected Sessions")
        self.assertEqual(result["total_sessions"], 2)
        self.assertEqual([source["session_id"] for source in result["session_sources"]], ["444", "555"])
        self.assertEqual([row["driver"] for row in result["results"]], ["Driver A", "Driver B"])
        self.assertEqual(result["results"][0]["sessions_attended_count"], 2)
        self.assertEqual(result["results"][0]["fastest_lap"], "58.000")
        self.assertEqual(result["results"][0]["over_minimum"], "Yes")
        self.assertEqual(result["results"][1]["sessions_attended"], "Race Final")

    def test_collect_participation_accepts_session_url_in_primary_input(self) -> None:
        qualifying_csv = "\n".join(
            [
                "Pos,Start Number,Competitor,Class,Diff,Laps,Best Lap,Best Lap No.,Best Speed",
                "1,42,Carson Bowers,,0.000,11,24.616,3,39.457 mi/h",
                "2,72,Dylan White,,0.210,11,24.826,7,39.123 mi/h",
                "3,67,No Time Driver,,0.000,-,0.000,-,-",
            ]
        )

        def fake_get(url: str, **kwargs):
            del kwargs
            if url.endswith("/sessions/11963214"):
                return _FakeResponse(json_data={"name": "Afternoon Qualifications (Heats 10-17)"})
            if url.endswith("/sessions/11963214/csv"):
                return _FakeResponse(text=qualifying_csv)
            self.fail(f"Unexpected URL call: {url}")

        with patch.object(scraper.requests, "get", side_effect=fake_get):
            result = scraper.collect_participation(
                event_url="https://speedhive.mylaps.com/sessions/11963214",
                minimum_sessions=1,
            )

        self.assertEqual(result["event_name"], "Selected Sessions")
        self.assertEqual(result["total_sessions"], 1)
        self.assertEqual(result["session_sources"][0]["session_id"], "11963214")
        self.assertEqual([row["driver"] for row in result["results"]], ["Carson Bowers", "Dylan White"])
        self.assertEqual(result["results"][0]["kart_number"], "42")
        self.assertEqual(result["results"][0]["fastest_lap"], "24.616")
        self.assertEqual(result["results"][0]["total_laps"], 11)
        self.assertEqual(result["results"][0]["sessions_attended"], "Afternoon Qualifications (Heats 10-17)")


if __name__ == "__main__":
    unittest.main()
