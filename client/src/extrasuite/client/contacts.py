"""Google Contacts sync, search, and interaction tracking.

Syncs from two Google sources:
  - people.connections  (explicit saved contacts)
  - otherContacts       (auto-populated from Gmail interactions)

Data is stored locally in ~/.config/extrasuite/contacts.db (SQLite).
Text search loads contacts into memory and uses Python stdlib difflib —
no SQLite FTS extensions required.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import sqlite3
import ssl
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

_DB_PATH = Path.home() / ".config" / "extrasuite" / "contacts.db"
_SYNC_STALE_DAYS = 4

_CONTACTS_SCOPES = [
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly",
]

_PEOPLE_FIELDS = "names,emailAddresses,organizations,metadata"
_OTHER_FIELDS = "names,emailAddresses,metadata"
_PEOPLE_API = "https://people.googleapis.com/v1/people/me/connections"
_OTHER_API = "https://people.googleapis.com/v1/otherContacts"


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------


def _open_db(path: Path = _DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    _init_schema(con)
    return con


def _init_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS people (
            resource_name TEXT PRIMARY KEY,
            display_name  TEXT,
            given_name    TEXT,
            family_name   TEXT,
            emails        TEXT,
            organizations TEXT,
            etag          TEXT
        );

        CREATE TABLE IF NOT EXISTS other_contacts (
            resource_name TEXT PRIMARY KEY,
            display_name  TEXT,
            given_name    TEXT,
            family_name   TEXT,
            emails        TEXT,
            etag          TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS contact_interactions (
            email             TEXT PRIMARY KEY,
            last_contacted_at TEXT,
            contact_count     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS touch_sessions (
            session_id TEXT PRIMARY KEY,
            emails     TEXT,
            created_at TEXT
        );
    """)
    con.commit()


# ---------------------------------------------------------------------------
# Sync meta helpers
# ---------------------------------------------------------------------------


def _get_meta(con: sqlite3.Connection, key: str) -> str:
    row = con.execute("SELECT value FROM sync_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def _set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO sync_meta(key,value) VALUES(?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_stale(con: sqlite3.Connection) -> bool:
    last = _get_meta(con, "people_last_synced_at")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - dt).days >= _SYNC_STALE_DAYS
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Google API helpers
# ---------------------------------------------------------------------------


def _api_get(url: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except (json.JSONDecodeError, AttributeError):
            msg = body
        raise Exception(f"Google API error ({e.code}): {msg}") from e


def _extract_person(p: dict[str, Any]) -> dict[str, Any]:
    names = p.get("names", [])
    name = next(
        (n for n in names if n.get("metadata", {}).get("primary")),
        names[0] if names else {},
    )
    emails = [
        {"value": e["value"], "type": e.get("type", "")}
        for e in p.get("emailAddresses", [])
        if e.get("value")
    ]
    orgs = [
        {
            "name": o.get("name", ""),
            "title": o.get("title", ""),
            "domain": o.get("domain", ""),
        }
        for o in p.get("organizations", [])
    ]
    return {
        "resource_name": p.get("resourceName", ""),
        "display_name": name.get("displayName", ""),
        "given_name": name.get("givenName", ""),
        "family_name": name.get("familyName", ""),
        "emails": json.dumps(emails),
        "organizations": json.dumps(orgs),
        "etag": p.get("etag", ""),
    }


def _extract_other_contact(p: dict[str, Any]) -> dict[str, Any]:
    names = p.get("names", [])
    name = next(
        (n for n in names if n.get("metadata", {}).get("primary")),
        names[0] if names else {},
    )
    emails = [
        {"value": e["value"], "type": e.get("type", "")}
        for e in p.get("emailAddresses", [])
        if e.get("value")
    ]
    return {
        "resource_name": p.get("resourceName", ""),
        "display_name": name.get("displayName", ""),
        "given_name": name.get("givenName", ""),
        "family_name": name.get("familyName", ""),
        "emails": json.dumps(emails),
        "etag": p.get("etag", ""),
    }


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------


def _upsert_people(con: sqlite3.Connection, records: list[dict[str, Any]]) -> None:
    con.executemany(
        """INSERT INTO people(resource_name,display_name,given_name,family_name,
           emails,organizations,etag) VALUES(:resource_name,:display_name,:given_name,
           :family_name,:emails,:organizations,:etag)
           ON CONFLICT(resource_name) DO UPDATE SET
           display_name=excluded.display_name, given_name=excluded.given_name,
           family_name=excluded.family_name, emails=excluded.emails,
           organizations=excluded.organizations, etag=excluded.etag""",
        records,
    )


def _upsert_other_contacts(
    con: sqlite3.Connection, records: list[dict[str, Any]]
) -> None:
    con.executemany(
        """INSERT INTO other_contacts(resource_name,display_name,given_name,family_name,
           emails,etag) VALUES(:resource_name,:display_name,:given_name,
           :family_name,:emails,:etag)
           ON CONFLICT(resource_name) DO UPDATE SET
           display_name=excluded.display_name, given_name=excluded.given_name,
           family_name=excluded.family_name, emails=excluded.emails,
           etag=excluded.etag""",
        records,
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def _sync_source(
    con: sqlite3.Connection,
    token: str,
    *,
    api_url: str,
    fields_param: str,
    items_key: str,
    extract_fn: Any,
    upsert_fn: Any,
    delete_fn: Any,
    clear_table: str,
    token_key: str,
    synced_at_key: str,
    verbose: bool,
) -> int:
    sync_token = _get_meta(con, token_key)

    def _full_sync() -> int:
        nonlocal sync_token
        if verbose:
            print(f"  Full sync from {api_url}...", flush=True)
        con.execute(f"DELETE FROM {clear_table}")
        count = 0
        page_token = None
        while True:
            params: dict[str, str] = {
                (
                    "personFields" if "connections" in api_url else "readMask"
                ): fields_param,
                "pageSize": "1000",
                "requestSyncToken": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            data = _api_get(api_url, token, params)
            items = data.get(items_key, [])
            records = [extract_fn(p) for p in items if p.get("resourceName")]
            upsert_fn(con, records)
            count += len(records)
            page_token = data.get("nextPageToken")
            if not page_token:
                sync_token = data.get("nextSyncToken", "")
                break
        _set_meta(con, token_key, sync_token)
        _set_meta(con, synced_at_key, _now_iso())
        con.commit()
        return count

    if not sync_token:
        return _full_sync()

    if verbose:
        print(f"  Incremental sync from {api_url}...", flush=True)
    try:
        count = 0
        page_token = None
        while True:
            params = {
                (
                    "personFields" if "connections" in api_url else "readMask"
                ): fields_param,
                "pageSize": "1000",
                "requestSyncToken": "true",
                "syncToken": sync_token,
            }
            if page_token:
                params["pageToken"] = page_token
            data = _api_get(api_url, token, params)
            for p in data.get(items_key, []):
                rn = p.get("resourceName", "")
                if not rn:
                    continue
                if p.get("metadata", {}).get("deleted"):
                    delete_fn(con, rn)
                else:
                    upsert_fn(con, [extract_fn(p)])
                    count += 1
            page_token = data.get("nextPageToken")
            if not page_token:
                sync_token = data.get("nextSyncToken", sync_token)
                break
        _set_meta(con, token_key, sync_token)
        _set_meta(con, synced_at_key, _now_iso())
        con.commit()
        return count
    except Exception as e:
        if "410" in str(e):
            if verbose:
                print("  Sync token expired, doing full sync...", flush=True)
            _set_meta(con, token_key, "")
            con.commit()
            return _full_sync()
        raise


def sync(token: str, verbose: bool = False) -> tuple[int, int]:
    """Sync contacts from Google. Returns (people_count, other_count).

    otherContacts sync requires the contacts.other.readonly scope in addition
    to contacts.readonly. If not authorized, it is skipped with a warning.
    """
    con = _open_db()

    def _del_person(c: sqlite3.Connection, rn: str) -> None:
        c.execute("DELETE FROM people WHERE resource_name=?", (rn,))

    def _del_other(c: sqlite3.Connection, rn: str) -> None:
        c.execute("DELETE FROM other_contacts WHERE resource_name=?", (rn,))

    people_count = _sync_source(
        con,
        token,
        api_url=_PEOPLE_API,
        fields_param=_PEOPLE_FIELDS,
        items_key="connections",
        extract_fn=_extract_person,
        upsert_fn=_upsert_people,
        delete_fn=_del_person,
        clear_table="people",
        token_key="people_sync_token",
        synced_at_key="people_last_synced_at",
        verbose=verbose,
    )

    other_count = 0
    try:
        other_count = _sync_source(
            con,
            token,
            api_url=_OTHER_API,
            fields_param=_OTHER_FIELDS,
            items_key="otherContacts",
            extract_fn=_extract_other_contact,
            upsert_fn=_upsert_other_contacts,
            delete_fn=_del_other,
            clear_table="other_contacts",
            token_key="other_contacts_sync_token",
            synced_at_key="other_contacts_last_synced_at",
            verbose=verbose,
        )
    except Exception as e:
        if "403" in str(e) or "insufficient authentication scopes" in str(e).lower():
            if verbose:
                print(
                    "  Skipping other contacts: scope contacts.other.readonly not authorized.\n"
                    "  Add it to workspace delegation to sync Gmail-suggested contacts.",
                    flush=True,
                )
        else:
            raise

    return people_count, other_count


# ---------------------------------------------------------------------------
# In-memory search
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """NFC-normalize and lowercase a string."""
    return unicodedata.normalize("NFC", s).lower()


def _tokenize(s: str) -> list[str]:
    """Split a string into search tokens, treating punctuation as separators."""
    for ch in ".-_@+":
        s = s.replace(ch, " ")
    return [t for t in _normalize(s).split() if len(t) >= 2]


def _contact_search_tokens(row: sqlite3.Row, source: str) -> list[str]:
    """Extract all searchable tokens from a contact row."""
    tokens: set[str] = set()

    for field in (row["display_name"], row["given_name"], row["family_name"]):
        if field:
            tokens.update(_tokenize(field))

    try:
        for email in json.loads(row["emails"] or "[]"):
            v = email.get("value", "")
            if v and "@" in v:
                local, domain = v.split("@", 1)
                tokens.update(_tokenize(local))
                tokens.update(_tokenize(domain))
    except (json.JSONDecodeError, TypeError):
        pass

    if source == "people":
        try:
            for org in json.loads(row["organizations"] or "[]"):
                for field in (org.get("name", ""), org.get("domain", "")):
                    if field:
                        tokens.update(_tokenize(field))
        except (json.JSONDecodeError, TypeError):
            pass

    return list(tokens)


def _is_subsequence(s: str, t: str) -> bool:
    """Return True if every character of s appears in t in order."""
    it = iter(t)
    return all(c in it for c in s)


def _match_token(query_tok: str, contact_tokens: list[str]) -> float:
    """Score how well a single query token matches the contact's token set.

    Match tiers (highest wins):
      1.0  exact match
      0.85 query is a prefix of a contact token  (e.g. "him" → "himanshu")
      0.70 query is a substring of a contact token
      0.55 query is a subsequence of a contact token  (e.g. "r41" → "recruit41")
      0.8x difflib ratio if >= 0.75  (handles typos / transliterations)

    Returns 0 if no tier fires.
    """
    best = 0.0
    for ct in contact_tokens:
        if ct == query_tok:
            return 1.0
        if ct.startswith(query_tok):
            best = max(best, 0.85)
        elif query_tok in ct:
            best = max(best, 0.70)
        elif (
            len(query_tok) >= 2
            and len(ct) <= len(query_tok) * 3
            and _is_subsequence(query_tok, ct)
        ):
            best = max(best, 0.55)
        else:
            ratio = difflib.SequenceMatcher(None, query_tok, ct).ratio()
            if ratio >= 0.75:
                best = max(best, ratio * 0.8)
    return best


def _score_contact(query_tokens: list[str], contact_tokens: list[str]) -> float:
    """Score a contact against all query tokens.

    All tokens must match something (AND semantics). Returns 0 if any fails.
    """
    if not query_tokens:
        return 0.0
    total = 0.0
    for qt in query_tokens:
        score = _match_token(qt, contact_tokens)
        if score == 0.0:
            return 0.0
        total += score
    return total / len(query_tokens)


# ---------------------------------------------------------------------------
# Email selection and domain helpers
# ---------------------------------------------------------------------------


def _recent_domains(con: sqlite3.Connection, limit: int = 10) -> set[str]:
    """Return email domains from the most recent touch sessions."""
    rows = con.execute(
        "SELECT emails FROM touch_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    domains: set[str] = set()
    for row in rows:
        try:
            for email in json.loads(row["emails"]):
                if "@" in email:
                    domains.add(email.split("@", 1)[1].lower())
        except (json.JSONDecodeError, TypeError):
            pass
    return domains


def _pick_email(
    emails_json: str,
    recent_domains: set[str],
    interactions: dict[str, dict[str, Any]],
) -> str:
    """Choose the best email address to return for a contact."""
    try:
        emails = [e["value"] for e in json.loads(emails_json) if e.get("value")]
    except (json.JSONDecodeError, TypeError):
        return ""
    if not emails:
        return ""

    # Prefer most recently contacted email
    interacted = [
        (v, interactions[v]["last_contacted_at"]) for v in emails if v in interactions
    ]
    if interacted:
        interacted.sort(key=lambda x: x[1], reverse=True)
        return interacted[0][0]

    # Prefer email from a recently touched domain
    for v in emails:
        if "@" in v and v.split("@", 1)[1].lower() in recent_domains:
            return v

    return emails[0]


def _load_interactions(
    con: sqlite3.Connection, emails: list[str]
) -> dict[str, dict[str, Any]]:
    if not emails:
        return {}
    placeholders = ",".join("?" * len(emails))
    rows = con.execute(
        f"SELECT email, last_contacted_at, contact_count FROM contact_interactions"
        f" WHERE email IN ({placeholders})",
        emails,
    ).fetchall()
    return {r["email"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Public search API
# ---------------------------------------------------------------------------


def search(
    queries: list[str],
    token: str | None = None,
    auto_sync: bool = True,
) -> list[dict[str, Any]]:
    """Search contacts for each query string.

    Args:
        queries:    One or more search strings, each searched independently.
        token:      OAuth access token (needed only when auto_sync may trigger).
        auto_sync:  Sync automatically if DB is missing or stale (>4 days).

    Returns:
        List of {"query": str, "matches": [{"name", "email", "last_contacted"}]}
    """
    if auto_sync:
        needs_sync = not _DB_PATH.exists()
        if not needs_sync:
            needs_sync = _is_stale(_open_db())
        if needs_sync:
            if token is None:
                raise ValueError("OAuth token required for auto-sync")
            sync(token, verbose=True)

    con = _open_db()
    recent_domains = _recent_domains(con)

    # Load all contacts into memory once (shared across all queries)
    people_rows = con.execute("SELECT * FROM people").fetchall()
    other_rows = con.execute("SELECT * FROM other_contacts").fetchall()

    # Pre-compute search tokens per contact
    candidates: list[tuple[sqlite3.Row, str, list[str]]] = []
    for row in people_rows:
        candidates.append((row, "people", _contact_search_tokens(row, "people")))
    for row in other_rows:
        candidates.append(
            (row, "other_contacts", _contact_search_tokens(row, "other_contacts"))
        )

    results = []
    for q in queries:
        query_tokens = _tokenize(q)
        if not query_tokens:
            results.append({"query": q, "matches": []})
            continue

        scored: list[tuple[float, sqlite3.Row, str]] = []
        for row, source, ctokens in candidates:
            score = _score_contact(query_tokens, ctokens)
            if score > 0:
                scored.append((score, row, source))

        # Collect all email addresses we need interactions for
        all_emails: list[str] = []
        for _, row, _ in scored:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                all_emails.extend(
                    e["value"]
                    for e in json.loads(row["emails"] or "[]")
                    if e.get("value")
                )
        interactions = _load_interactions(con, all_emails)

        def _rank_key(
            item: tuple[float, sqlite3.Row, str], _ia: dict = interactions
        ) -> tuple[int, int, str, float]:
            _score, row, source = item
            source_rank = 0 if source == "people" else 1
            try:
                row_emails = [
                    e["value"]
                    for e in json.loads(row["emails"] or "[]")
                    if e.get("value")
                ]
            except (json.JSONDecodeError, TypeError):
                row_emails = []
            total_count = sum(
                _ia.get(e, {}).get("contact_count", 0) for e in row_emails
            )
            last = max(
                (_ia.get(e, {}).get("last_contacted_at") or "" for e in row_emails),
                default="",
            )
            # Lower is better: source first, then negate count, negate recency (want latest first), negate score
            return (source_rank, -total_count, last, -_score)

        scored.sort(key=_rank_key)

        matches = []
        for _score, row, _source in scored[:10]:
            best_email = _pick_email(
                row["emails"] or "[]", recent_domains, interactions
            )
            last_contacted = None
            if best_email and best_email in interactions:
                raw = interactions[best_email].get("last_contacted_at")
                last_contacted = _relative_time(raw) if raw else None
            name = (
                row["display_name"]
                or f"{row['given_name'] or ''} {row['family_name'] or ''}".strip()
            )
            matches.append(
                {"name": name, "email": best_email, "last_contacted": last_contacted}
            )

        results.append({"query": q, "matches": matches})

    return results


# ---------------------------------------------------------------------------
# Relative time formatting
# ---------------------------------------------------------------------------


def _relative_time(iso: str) -> str:
    """Format an ISO timestamp as a human-relative string (e.g. '3h ago', '2d ago')."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}d ago"
    if seconds < 86400 * 365:
        return f"{seconds // (86400 * 30)}mo ago"
    return f"{seconds // (86400 * 365)}y ago"


# ---------------------------------------------------------------------------
# Touch
# ---------------------------------------------------------------------------


def touch(emails: list[str]) -> None:
    """Record that these email addresses were contacted now.

    All emails are grouped into one touch session for clustering.
    """
    now = _now_iso()
    session_id = str(uuid.uuid4())
    normalized = [e.strip().lower() for e in emails if e.strip()]
    con = _open_db()
    with con:
        for email in normalized:
            con.execute(
                """INSERT INTO contact_interactions(email, last_contacted_at, contact_count)
                   VALUES(?,?,1)
                   ON CONFLICT(email) DO UPDATE SET
                   last_contacted_at=excluded.last_contacted_at,
                   contact_count=contact_count+1""",
                (email, now),
            )
        con.execute(
            "INSERT INTO touch_sessions(session_id,emails,created_at) VALUES(?,?,?)",
            (session_id, json.dumps(normalized), now),
        )
