from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

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


@dataclass(frozen=True)
class SessionSource:
    session_id: str
    session_name: str
    session_url: str


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


def _get_html(url: str, timeout: int = 20) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    response.raise_for_status()
    return response.text


def _find_session_links(event_html: str, event_url: str) -> List[str]:
    del event_url  # unused, kept for signature compatibility
    session_ids = set(re.findall(r"/sessions?/(\d+)", event_html, flags=re.IGNORECASE))
    return sorted(f"https://speedhive.mylaps.com/sessions/{session_id}" for session_id in session_ids)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _extract_session_id(session_url: str) -> Optional[str]:
    session_url = _clean_text(session_url)
    if re.fullmatch(r"\d+", session_url):
        return session_url

    match = re.search(r"/sessions?/(\d+)", session_url, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_event_id(event_url: str) -> Optional[str]:
    event_url = _clean_text(event_url)
    if re.fullmatch(r"\d+", event_url):
        return event_url

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
    # Speedhive sometimes exposes the kart identifier as "Start Number".
    # We still normalize it into our canonical `kart_number` output field.
    return _clean_text(
        row.get("Kart")
        or row.get("Kart #")
        or row.get("Kart Number")
        or row.get("KartNumber")
        or row.get("Kart Num")
        or row.get("Start Number")
        or row.get("Start No")
        or row.get("Start No.")
        or row.get("Start #")
        or row.get("Kart No")
        or row.get("Kart No.")
        or row.get("Number")
        or row.get("Kart # ")
        or row.get("KartNo")
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


def _session_url(session_id: str) -> str:
    return f"https://speedhive.mylaps.com/sessions/{session_id}"


def _split_session_entries(session_urls: str | Iterable[str] | None) -> List[str]:
    if session_urls is None:
        return []

    if isinstance(session_urls, str):
        raw_entries = re.split(r"[\s,;]+", session_urls)
    else:
        raw_entries = []
        for entry in session_urls:
            raw_entries.extend(re.split(r"[\s,;]+", str(entry)))

    return [_clean_text(entry) for entry in raw_entries if _clean_text(entry)]


def _build_event_session_sources(event_id: str) -> List[SessionSource]:
    sessions_payload = _get_json(f"{EVENT_RESULTS_API_BASE}/events/{event_id}/sessions")
    all_sessions = _flatten_sessions(sessions_payload)
    sources: List[SessionSource] = []

    for session in all_sessions:
        session_id = session.get("id")
        if not session_id:
            continue

        session_id_str = str(session_id)
        session_name = _clean_text(session.get("name", "")) or f"Session {session_id_str}"
        sources.append(
            SessionSource(
                session_id=session_id_str,
                session_name=session_name,
                session_url=_session_url(session_id_str),
            )
        )

    return sources


def _build_manual_session_source(session_id: str) -> SessionSource:
    session_meta = _get_json(f"{EVENT_RESULTS_API_BASE}/sessions/{session_id}")
    session_name = _clean_text(session_meta.get("name", "")) or f"Session {session_id}"
    return SessionSource(
        session_id=session_id,
        session_name=session_name,
        session_url=_session_url(session_id),
    )


def _collect_session_sources(
    event_url: str | None,
    session_urls: str | Iterable[str] | None,
) -> tuple[str, str, List[SessionSource]]:
    event_url = _clean_text(event_url or "")
    event_name = "Selected Sessions"
    canonical_event_url = event_url
    sources: List[SessionSource] = []
    seen_session_ids: set[str] = set()

    if event_url:
        event_id = _extract_event_id(event_url)
        if not event_id:
            raise SpeedhiveScrapeError(f"Could not determine event ID from URL: {event_url}")

        canonical_event_url = f"https://speedhive.mylaps.com/events/{event_id}"
        event_meta = _get_json(f"{EVENT_RESULTS_API_BASE}/events/{event_id}")
        event_name = _clean_text(event_meta.get("name", "")) or f"Event {event_id}"

        for source in _build_event_session_sources(event_id):
            if source.session_id in seen_session_ids:
                continue
            sources.append(source)
            seen_session_ids.add(source.session_id)

    for entry in _split_session_entries(session_urls):
        session_id = _extract_session_id(entry)
        if not session_id:
            raise SpeedhiveScrapeError(f"Could not determine session ID from: {entry}")

        if session_id in seen_session_ids:
            continue
        source = _build_manual_session_source(session_id)
        sources.append(source)
        seen_session_ids.add(session_id)

    if not sources:
        raise SpeedhiveScrapeError("No sessions were found. Provide an event URL or at least one session URL/ID.")

    return canonical_event_url, event_name, sources


def collect_session_results(session_url: str, session_name_hint: str | None = None) -> Dict[str, object]:
    """Collect leaderboard rows for a single Speedhive session."""
    session_id = _extract_session_id(session_url)
    if not session_id:
        raise SpeedhiveScrapeError(f"Could not determine session ID from URL: {session_url}")

    session_name = _clean_text(session_name_hint or "")
    if not session_name:
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


def collect_participation(
    event_url: str | None = None,
    minimum_sessions: int = 4,
    session_urls: str | Iterable[str] | None = None,
) -> Dict[str, object]:
    """Collect participation summary across event sessions and optional manual sessions."""
    canonical_event_url, event_name, session_sources = _collect_session_sources(event_url, session_urls)

    session_order = {source.session_id: index for index, source in enumerate(session_sources)}

    drivers: dict[str, dict] = {}
    for source in session_sources:
        csv_response = requests.get(
            f"{EVENT_RESULTS_API_BASE}/sessions/{source.session_id}/csv",
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
            best_lap_seconds = _parse_time_to_seconds(best_lap)
            if best_lap_seconds is None:
                continue

            key = driver_name.lower()
            entry = drivers.setdefault(
                key,
                {
                    "driver": driver_name,
                    "kart_number": "",
                    "sessions": {},
                },
            )
            kart_number = _extract_kart_number(row)
            if not entry["kart_number"] and kart_number:
                entry["kart_number"] = kart_number

            laps = _parse_laps(row.get("Laps") or "0")
            existing_session = entry["sessions"].get(source.session_id)
            if not existing_session or best_lap_seconds < existing_session["best_lap_seconds"]:
                entry["sessions"][source.session_id] = {
                    "session_name": source.session_name,
                    "session_url": source.session_url,
                    "best_lap": best_lap,
                    "best_lap_seconds": best_lap_seconds,
                    "laps": laps,
                }

    total_sessions = len(session_sources)
    rows = []
    for driver in drivers.values():
        sorted_sessions = sorted(
            driver["sessions"].items(),
            key=lambda item: session_order.get(item[0], 10**9),
        )
        sessions_attended = [session["session_name"] for _, session in sorted_sessions]
        fast_times_list = [
            f"{session['session_name']}: {session['best_lap']}"
            for _, session in sorted_sessions
        ]
        fastest_lap_session = min(sorted_sessions, key=lambda item: item[1]["best_lap_seconds"], default=None)
        fastest_lap = fastest_lap_session[1]["best_lap"] if fastest_lap_session else ""
        total_laps = sum(session["laps"] for _, session in sorted_sessions)
        attended_count = len(sessions_attended)
        rows.append(
            {
                "kart_number": driver["kart_number"],
                "driver": driver["driver"],
                "fastest_lap": fastest_lap,
                "total_laps": total_laps,
                "over_minimum": "Yes" if attended_count >= minimum_sessions else "No",
                "sessions_attended": ", ".join(sessions_attended),
                "sessions_attended_count": attended_count,
                "fast_times": " | ".join(fast_times_list),
                "fast_times_list": fast_times_list,
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
        "event_url": canonical_event_url,
        "event_name": event_name,
        "minimum_sessions": minimum_sessions,
        "total_sessions": total_sessions,
        "total_practice_sessions": total_sessions,
        "session_sources": [
            {
                "session_id": source.session_id,
                "session_name": source.session_name,
                "session_url": source.session_url,
            }
            for source in session_sources
        ],
        "results": rows,
    }


def collect_event_participation(
    event_url: str,
    minimum_sessions: int = 4,
    session_urls: str | Iterable[str] | None = None,
) -> Dict[str, object]:
    """Collect event-wide participation summary for every timed session type."""
    return collect_participation(
        event_url=event_url,
        minimum_sessions=minimum_sessions,
        session_urls=session_urls,
    )
