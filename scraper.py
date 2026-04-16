from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

EVENT_RESULTS_API_BASE = "https://eventresults-api.speedhive.com/api/v0.2.3/eventresults"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class SessionResult:
    session_name: str
    session_url: str
    position: int
    driver_name: str
    kart_number: str
    best_lap: str
    laps: int
    best_lap_seconds: float


class SpeedhiveScrapeError(RuntimeError):
    """Raised when Speedhive pages cannot be parsed."""


def _get_json(url: str, timeout: int = 20) -> dict:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
    )
    response.raise_for_status()
    return response.json()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _extract_session_id(session_url: str) -> Optional[str]:
    match = re.search(r"/sessions?/(\d+)", session_url, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_event_id(event_url: str) -> Optional[str]:
    match = re.search(r"/events?/(\d+)", event_url, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _is_time_recorded(raw_value: str) -> bool:
    value = _clean_text(raw_value).lower()
    if not value:
        return False

    blank_markers = {
        "-",
        "--",
        "---",
        "na",
        "n/a",
        "none",
        "no time",
        "did not start",
        "dns",
        "dnf",
    }
    if value in blank_markers:
        return False

    if re.fullmatch(r"0+(?:[.:]0+)?", value):
        return False

    return bool(re.search(r"\d", value))


def _parse_time_to_seconds(raw_value: str) -> Optional[float]:
    value = _clean_text(raw_value)
    if not _is_time_recorded(value):
        return None

    value = value.replace(",", ".")
    value = re.sub(r"[^0-9:.]", "", value)

    if ":" in value:
        parts = value.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None

    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def _parse_laps(raw_value: str) -> int:
    match = re.search(r"\d+", _clean_text(raw_value))
    return int(match.group()) if match else 0


def _extract_kart_number(row: dict) -> str:
    return _clean_text(
        row.get("Kart")
        or row.get("Kart #")
        or row.get("Kart No")
        or row.get("Number")
        or row.get("No.")
        or row.get("#")
        or ""
    )


def _flatten_sessions(payload: dict) -> List[dict]:
    sessions = list(payload.get("sessions") or [])
    groups = list(payload.get("groups") or [])

    while groups:
        group = groups.pop()
        sessions.extend(group.get("sessions") or [])
        groups.extend(group.get("subGroups") or [])

    return sessions


def _normalize_driver_name(row: dict) -> str:
    return _clean_text(
        row.get("Competitor")
        or row.get("Driver")
        or row.get("Name")
        or row.get("Participant")
        or ""
    )


def collect_session_results(session_url: str) -> Dict[str, object]:
    """Collect leaderboard rows for a single Speedhive practice session."""
    session_id = _extract_session_id(session_url)
    if not session_id:
        raise SpeedhiveScrapeError(f"Could not determine session ID from URL: {session_url}")

    session_meta = _get_json(f"{EVENT_RESULTS_API_BASE}/sessions/{session_id}")
    session_name = _clean_text(session_meta.get("name", "")) or "Unnamed Session"

    csv_response = requests.get(
        f"{EVENT_RESULTS_API_BASE}/sessions/{session_id}/csv",
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )
    csv_response.raise_for_status()

    csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))

    results: List[SessionResult] = []
    for row in csv_rows:
        driver_name = _clean_text(
            row.get("Competitor")
            or row.get("Driver")
            or row.get("Name")
            or row.get("Participant")
            or ""
        )
        if not driver_name:
            continue

        best_lap = _clean_text(row.get("Best Lap") or row.get("Time") or "")
        best_lap_seconds = _parse_time_to_seconds(best_lap)
        if best_lap_seconds is None:
            continue

        results.append(
            SessionResult(
                session_name=session_name,
                session_url=session_url,
                position=0,
                driver_name=driver_name,
                kart_number=_extract_kart_number(row),
                best_lap=best_lap,
                laps=_parse_laps(row.get("Laps") or "0"),
                best_lap_seconds=best_lap_seconds,
            )
        )

    results.sort(key=lambda r: (r.best_lap_seconds, -r.laps, r.driver_name.lower()))
    for idx, result in enumerate(results, start=1):
        result.position = idx

    return {
        "session_url": session_url,
        "session_name": session_name,
        "results": [
            {
                "position": row.position,
                "driver": row.driver_name,
                "kart_number": row.kart_number,
                "best_lap": row.best_lap,
                "laps": row.laps,
            }
            for row in results
        ],
    }


def collect_event_participation(event_url: str, minimum_sessions: int = 4) -> Dict[str, object]:
    """Collect event-wide practice participation summary for each driver."""
    event_id = _extract_event_id(event_url)
    if not event_id:
        raise SpeedhiveScrapeError(f"Could not determine event ID from URL: {event_url}")

    event_meta = _get_json(f"{EVENT_RESULTS_API_BASE}/events/{event_id}")
    event_name = _clean_text(event_meta.get("name", "")) or f"Event {event_id}"

    sessions_payload = _get_json(f"{EVENT_RESULTS_API_BASE}/events/{event_id}/sessions")
    all_sessions = _flatten_sessions(sessions_payload)
    practice_sessions = [session for session in all_sessions if _clean_text(session.get("type", "")).lower() == "practice"]

    if not practice_sessions:
        raise SpeedhiveScrapeError("No practice sessions were found for this event.")

    drivers: dict[str, dict] = {}
    for session in practice_sessions:
        session_id = session.get("id")
        session_name = _clean_text(session.get("name", "")) or f"Session {session_id}"
        if not session_id:
            continue

        csv_response = requests.get(
            f"{EVENT_RESULTS_API_BASE}/sessions/{session_id}/csv",
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        csv_response.raise_for_status()
        csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))

        for row in csv_rows:
            driver_name = _normalize_driver_name(row)
            if not driver_name:
                continue

            best_lap = _clean_text(row.get("Best Lap") or row.get("Time") or "")
            if _parse_time_to_seconds(best_lap) is None:
                continue

            key = driver_name.lower()
            entry = drivers.setdefault(
                key,
                {
                    "driver": driver_name,
                    "kart_number": "",
                    "total_laps": 0,
                    "sessions_attended": [],
                    "session_ids_attended": set(),
                },
            )
            kart_number = _extract_kart_number(row)
            if not entry["kart_number"] and kart_number:
                entry["kart_number"] = kart_number

            if session_id in entry["session_ids_attended"]:
                continue

            entry["session_ids_attended"].add(session_id)
            entry["sessions_attended"].append(session_name)
            entry["total_laps"] += _parse_laps(row.get("Laps") or "0")

    total_practice_sessions = len(practice_sessions)
    rows = []
    for driver in drivers.values():
        attended_count = len(driver["sessions_attended"])
        rows.append(
            {
                "kart_number": driver["kart_number"],
                "driver": driver["driver"],
                "total_laps": driver["total_laps"],
                "session_total_count": total_practice_sessions,
                "over_minimum": "Yes" if attended_count >= minimum_sessions else "No",
                "sessions_attended": ", ".join(driver["sessions_attended"]),
                "sessions_attended_count": attended_count,
            }
        )

    rows.sort(
        key=lambda r: (
            0 if r["over_minimum"] == "Yes" else 1,
            -r["sessions_attended_count"],
            -r["total_laps"],
            r["driver"].lower(),
        )
    )

    return {
        "event_url": event_url,
        "event_name": event_name,
        "minimum_sessions": minimum_sessions,
        "total_practice_sessions": total_practice_sessions,
        "results": rows,
    }
