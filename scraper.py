from __future__ import annotations

import re
import csv
import io
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import requests

EVENT_RESULTS_API_BASE = "https://eventresults-api.speedhive.com/api/v0.2.3/eventresults"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class SessionAttendance:
    session_name: str
    session_url: str
    driver_name: str
    kart_number: str
    time_value: str
    laps_value: int
    time_seconds: float


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
    return re.sub(r"\s+", " ", value).strip()


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


def _extract_event_id(event_url: str) -> Optional[str]:
    match = re.search(r"/events?/(\d+)", event_url, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_session_id(session_url: str) -> Optional[str]:
    match = re.search(r"/sessions?/(\d+)", session_url, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _find_session_links_from_api(event_url: str) -> Tuple[List[str], Dict[str, str]]:
    event_id = _extract_event_id(event_url)
    if not event_id:
        return [], {}

    endpoint = f"{EVENT_RESULTS_API_BASE}/events/{event_id}?sessions=true"
    payload = _get_json(endpoint)
    sessions = payload.get("sessions", {})
    groups = sessions.get("groups", []) if isinstance(sessions, dict) else []

    links: Set[str] = set()
    session_name_by_url: Dict[str, str] = {}
    for group in groups:
        for session in group.get("sessions", []):
            session_id = session.get("id")
            if session_id:
                session_url = f"https://speedhive.mylaps.com/sessions/{session_id}"
                links.add(session_url)
                session_name = _clean_text(str(session.get("name") or ""))
                if session_name:
                    session_name_by_url[session_url] = session_name

    return sorted(links), session_name_by_url
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
                minutes = int(parts[0])
                seconds = float(parts[1])
                parsed = minutes * 60 + seconds
                return parsed if parsed > 0 else None
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                parsed = hours * 3600 + minutes * 60 + seconds
                return parsed if parsed > 0 else None
        except ValueError:
            return None

    try:
        parsed = float(value)
        if parsed <= 0:
            return None
        return parsed
    except ValueError:
        return None


def _parse_laps(raw_value: str) -> int:
    match = re.search(r"\d+", _clean_text(raw_value))
    if not match:
        return 0
    return int(match.group())


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


def _looks_like_kart_number(value: str) -> bool:
    cleaned = _clean_text(value)
    if not cleaned:
        return False
    # Common values that indicate a kart/grid number instead of a driver name.
    return bool(re.fullmatch(r"#?\d{1,4}[a-zA-Z]?", cleaned))


def _extract_driver_name(row: dict) -> str:
    """
    Prefer human-name fields; avoid mistakenly using numeric competitor IDs.
    """
    prioritized_fields = ("Driver", "Name", "Participant", "Competitor")
    values = {field: _clean_text(row.get(field) or "") for field in prioritized_fields}

    for field in prioritized_fields:
        value = values[field]
        if not value:
            continue
        if field == "Competitor" and _looks_like_kart_number(value):
            continue
        return value

    # Last fallback: if all we have is Competitor, keep it.
    return values["Competitor"]


def _parse_single_session_csv(
    session_url: str,
    session_name_hint: Optional[str] = None,
) -> List[SessionAttendance]:
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

    records: List[SessionAttendance] = []
    for row in csv_rows:
        driver_name = _extract_driver_name(row)
        kart_number = _extract_kart_number(row)
        time_value = _clean_text(row.get("Best Lap") or row.get("Time") or "")
        laps_value = _parse_laps(row.get("Laps") or "0")
        time_seconds = _parse_time_to_seconds(time_value)

        if not driver_name or time_seconds is None:
            continue

        records.append(
            SessionAttendance(
                session_name=session_name,
                session_url=session_url,
                driver_name=driver_name,
                kart_number=kart_number,
                time_value=time_value,
                laps_value=laps_value,
                time_seconds=time_seconds,
            )
        )

    return records


def _parse_single_session(
    session_url: str,
    session_name_hint: Optional[str] = None,
) -> List[SessionAttendance]:
    try:
        return _parse_single_session_csv(session_url, session_name_hint=session_name_hint)
    except requests.RequestException:
        return _parse_single_session_html(session_url)


def _parse_single_session_html(session_url: str) -> List[SessionAttendance]:
    raise SpeedhiveScrapeError(
        f"Could not retrieve CSV/API data for session {session_url}. "
        "HTML fallback parsing is not available for this session."
    )


def _normalize_manual_links(multiline_value: str) -> List[str]:
    links = [line.strip() for line in multiline_value.splitlines() if line.strip()]
    deduped: List[str] = []
    seen: Set[str] = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def _session_count_key(session_name: str, session_url: str) -> str:
    """
    Build a session key that keeps similarly named sessions distinct.

    Example:
      "Practice #6 Saturday - Session 2/3 - Provisional Results"
    is treated differently from:
      "Practice #6 Saturday - Session 3/3 - Provisional Results"
    """
    cleaned_name = _clean_text(session_name)
    session_fraction = re.search(
        r"\bsession\s*(\d+)\s*/\s*(\d+)\b",
        cleaned_name,
        flags=re.IGNORECASE,
    )
    if not session_fraction:
        return session_url

    session_number, session_total = session_fraction.groups()
    return f"{session_url}::session-{session_number}-of-{session_total}"


def _session_display_label(session_name: str) -> str:
    cleaned_name = _clean_text(session_name)
    session_fraction = re.search(
        r"\bsession\s*(\d+)\s*/\s*(\d+)\b",
        cleaned_name,
        flags=re.IGNORECASE,
    )
    if not session_fraction:
        return cleaned_name

    session_number, session_total = session_fraction.groups()
    return f"{cleaned_name} [Session {session_number} of {session_total}]"


def collect_attendance(
    event_url: str,
    minimum_practices: int = 4,
    manual_session_links_text: str = "",
) -> Dict[str, object]:
    event_url = event_url.strip()
    if not event_url:
        raise ValueError("An event URL is required.")

    session_name_hints: Dict[str, str] = {}
    if manual_session_links_text.strip():
        session_links = _normalize_manual_links(manual_session_links_text)
    else:
        try:
            session_links, session_name_hints = _find_session_links_from_api(event_url)
        except requests.RequestException:
            session_links, session_name_hints = [], {}
        if not session_links:
            event_html = _get_html(event_url)
            session_links = _find_session_links(event_html, event_url)

    driver_sessions: Dict[str, Set[str]] = defaultdict(set)
    driver_session_names: Dict[str, Set[str]] = defaultdict(set)
    driver_total_laps: Dict[str, int] = defaultdict(int)
    driver_kart_number: Dict[str, str] = {}
    driver_fastest_seconds: Dict[str, float] = {}
    driver_fastest_time_text: Dict[str, str] = {}
    raw_records: List[SessionAttendance] = []
    errors: List[str] = []

    max_workers = min(8, max(1, len(session_links)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _parse_single_session,
                session_url,
                session_name_hints.get(session_url),
            ): session_url
            for session_url in session_links
        }
        for future in as_completed(futures):
            session_url = futures[future]
            try:
                session_records = future.result()
            except requests.RequestException as exc:
                errors.append(f"Failed to fetch {session_url}: {exc}")
                continue
            except Exception as exc:  # pragma: no cover - defensive fallback
                errors.append(f"Failed to parse {session_url}: {exc}")
                continue

            raw_records.extend(session_records)
            for rec in session_records:
                session_key = _session_count_key(rec.session_name, rec.session_url)
                driver_sessions[rec.driver_name].add(session_key)
                driver_session_names[rec.driver_name].add(_session_display_label(rec.session_name))
                driver_total_laps[rec.driver_name] += rec.laps_value
                if rec.kart_number and rec.driver_name not in driver_kart_number:
                    driver_kart_number[rec.driver_name] = rec.kart_number
                current_best = driver_fastest_seconds.get(rec.driver_name)
                if current_best is None or rec.time_seconds < current_best:
                    driver_fastest_seconds[rec.driver_name] = rec.time_seconds
                    driver_fastest_time_text[rec.driver_name] = rec.time_value

    summary_rows = []
    for driver_name in sorted(driver_sessions):
        count = len(driver_sessions[driver_name])
        sessions = sorted(driver_session_names[driver_name])
        fastest_seconds = driver_fastest_seconds.get(driver_name, float("inf"))
        meets_minimum = count >= minimum_practices
        summary_rows.append(
            {
                "driver": driver_name,
                "kart_number": driver_kart_number.get(driver_name, ""),
                "counted_practices": count,
                "fastest_time_overall": driver_fastest_time_text.get(driver_name, ""),
                "total_laps_overall": driver_total_laps.get(driver_name, 0),
                "meets_minimum": "Yes" if meets_minimum else "No",
                "counted_sessions": " | ".join(sessions),
                "_sort_fastest_seconds": fastest_seconds,
                "_sort_meets_minimum": meets_minimum,
            }
        )

    # Default ranking requested by coaches:
    # 1) Qualified drivers first (made the cut), then non-qualified.
    # 2) Within each group, fastest lap first.
    # 3) Tie-break by practice count (higher first), then name.
    summary_rows.sort(
        key=lambda row: (
            not row["_sort_meets_minimum"],
            row["_sort_fastest_seconds"],
            -row["counted_practices"],
            row["driver"].lower(),
        )
    )

    for row in summary_rows:
        row.pop("_sort_fastest_seconds", None)
        row.pop("_sort_meets_minimum", None)

    raw_rows = [
        {
            "session_name": record.session_name,
            "session_url": record.session_url,
            "driver": record.driver_name,
            "kart_number": record.kart_number,
            "time": record.time_value,
            "laps": record.laps_value,
        }
        for record in raw_records
    ]

    return {
        "event_url": event_url,
        "minimum_practices": minimum_practices,
        "session_links": session_links,
        "summary_rows": summary_rows,
        "raw_rows": raw_rows,
        "errors": errors,
    }
