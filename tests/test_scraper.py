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

    def test_collect_event_participation_aggregates_multiple_sessions_and_drivers(self) -> None:
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

        def fake_get(url: str, **kwargs):
            del kwargs
            if url.endswith("/events/999"):
                return _FakeResponse(json_data={"name": "Weekly Practice"})
            if url.endswith("/events/999/sessions"):
                return _FakeResponse(
                    json_data={
                        "sessions": [
                            {"id": 111, "name": "Practice 1", "type": "Practice"},
                            {"id": 222, "name": "Practice 2", "type": "Practice"},
                        ]
                    }
                )
            if url.endswith("/sessions/111/csv"):
                return _FakeResponse(text=session_111_csv)
            if url.endswith("/sessions/222/csv"):
                return _FakeResponse(text=session_222_csv)
            self.fail(f"Unexpected URL call: {url}")

        with patch.object(scraper.requests, "get", side_effect=fake_get):
            result = scraper.collect_event_participation(
                "https://speedhive.mylaps.com/events/999",
                minimum_sessions=2,
            )

        self.assertEqual(result["event_name"], "Weekly Practice")
        self.assertEqual(result["total_practice_sessions"], 2)
        self.assertEqual([row["driver"] for row in result["results"]], ["Driver A", "Driver B", "Driver C"])
        self.assertEqual(result["results"][0]["sessions_attended_count"], 2)
        self.assertEqual(result["results"][0]["total_laps"], 22)
        self.assertEqual(result["results"][0]["over_minimum"], "Yes")
        self.assertEqual(
            result["results"][0]["fast_times_list"],
            ["Practice 1: 1:00.100", "Practice 2: 59.900"],
        )
        self.assertEqual(
            result["results"][0]["fast_times"],
            "Practice 1: 1:00.100 | Practice 2: 59.900",
        )
        self.assertEqual(result["results"][1]["sessions_attended_count"], 1)
        self.assertEqual(result["results"][2]["sessions_attended_count"], 1)


if __name__ == "__main__":
    unittest.main()
