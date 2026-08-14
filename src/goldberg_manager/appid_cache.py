from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .appid import AppIdCandidate

CACHE_ROOT = Path.home() / ".cache" / "goldberg-manager"

APPID_CACHE_PATH = CACHE_ROOT / "steam-appid-search.json"

CACHE_MAX_AGE = timedelta(days=7)


def _normalize_cache_key(
    query: str,
) -> str:
    return " ".join(query.casefold().split())


def _load_cache(
    cache_path: Path,
) -> dict[str, object]:
    if not cache_path.is_file():
        return {
            "version": 1,
            "entries": {},
        }

    try:
        data = json.loads(
            cache_path.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {
            "version": 1,
            "entries": {},
        }

    if not isinstance(data, dict):
        return {
            "version": 1,
            "entries": {},
        }

    entries = data.get("entries")

    if not isinstance(entries, dict):
        entries = {}

    return {
        "version": 1,
        "entries": entries,
    }


def _save_cache(
    cache_path: Path,
    data: dict[str, object],
) -> None:
    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = cache_path.with_suffix(".tmp")

    temporary_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(cache_path)


def get_cached_appid_search(
    query: str,
    *,
    cache_path: Path = APPID_CACHE_PATH,
    now: datetime | None = None,
    max_age: timedelta = CACHE_MAX_AGE,
) -> list[AppIdCandidate] | None:
    key = _normalize_cache_key(query)

    if not key:
        return None

    data = _load_cache(cache_path)

    entries = data["entries"]

    if not isinstance(
        entries,
        dict,
    ):
        return None

    entry = entries.get(key)

    if not isinstance(
        entry,
        dict,
    ):
        return None

    fetched_at_value = entry.get("fetched_at")

    if not isinstance(
        fetched_at_value,
        str,
    ):
        return None

    try:
        fetched_at = datetime.fromisoformat(fetched_at_value)
    except ValueError:
        return None

    if fetched_at.tzinfo is None:
        return None

    if now is None:
        now = datetime.now(UTC)

    if now - fetched_at > max_age:
        return None

    raw_candidates = entry.get("candidates")

    if not isinstance(
        raw_candidates,
        list,
    ):
        return None

    candidates: list[AppIdCandidate] = []

    for item in raw_candidates:
        if not isinstance(
            item,
            dict,
        ):
            continue

        app_id = item.get("app_id")

        name = item.get("name")

        score = item.get("score")

        source = item.get("source")

        if not isinstance(
            app_id,
            int,
        ):
            continue

        if not isinstance(
            name,
            str,
        ):
            continue

        if not isinstance(
            score,
            int,
        ):
            continue

        if not isinstance(
            source,
            str,
        ):
            continue

        candidates.append(
            AppIdCandidate(
                app_id=app_id,
                name=name,
                score=score,
                source=source,
            )
        )

    return candidates


def save_appid_search_cache(
    query: str,
    candidates: list[AppIdCandidate],
    *,
    cache_path: Path = APPID_CACHE_PATH,
    now: datetime | None = None,
) -> None:
    key = _normalize_cache_key(query)

    if not key:
        return

    if now is None:
        now = datetime.now(UTC)

    data = _load_cache(cache_path)

    entries = data["entries"]

    if not isinstance(
        entries,
        dict,
    ):
        entries = {}

        data["entries"] = entries

    entries[key] = {
        "fetched_at": (now.isoformat()),
        "candidates": [
            {
                key: value
                for key, value in asdict(candidate).items()
                if key != "manifest_path"
            }
            for candidate in candidates
        ],
    }

    _save_cache(
        cache_path,
        data,
    )
