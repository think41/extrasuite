"""User settings stored in ~/.config/extrasuite/settings.toml.

Example settings.toml:
  [trusted_contacts]
  domains = ["yourcompany.com"]
  emails  = ["alice@other.com"]
"""

from __future__ import annotations

import email.utils
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found, no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

_SETTINGS_PATH = Path.home() / ".config" / "extrasuite" / "settings.toml"


@dataclass
class TrustedContacts:
    """Contacts whose email bodies the agent is permitted to read.

    Persisted in settings.toml under [trusted_contacts]; user_domain is
    injected at runtime from the authenticated user's own email address.
    """

    domains: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    # The authenticated user's own domain — always trusted, not persisted.
    user_domain: str = ""
    # When True, all senders are trusted regardless of domains/emails lists.
    # Set via trust_all = true in [trusted_contacts] section of settings.toml.
    allow_all: bool = False

    def is_trusted(self, sender_raw: str) -> bool:
        """Return True if sender_raw matches a trusted domain or email.

        sender_raw may be a bare address or RFC 5322 formatted
        ("Display Name <addr@domain.com>"). The authenticated user's own domain
        is always trusted regardless of the settings file contents.

        If allow_all is True, every sender is trusted.
        """
        if self.allow_all:
            return True

        _, addr = email.utils.parseaddr(sender_raw)
        addr = addr.lower().strip()
        if not addr:
            return False

        # Exact email match
        if addr in (e.lower() for e in self.emails):
            return True

        # Domain match (exact — not subdomain)
        if "@" in addr:
            domain = addr.split("@", 1)[1]
            all_domains = list(self.domains)
            if self.user_domain:
                all_domains.append(self.user_domain)
            if domain in (d.lower() for d in all_domains):
                return True

        return False


def load_trusted_contacts(path: Path = _SETTINGS_PATH) -> TrustedContacts:
    """Load trusted contacts from settings.toml.

    Returns an empty TrustedContacts if the file is missing, the
    [trusted_contacts] section is absent, or the file is corrupt.
    """
    if not path.exists():
        return TrustedContacts()
    if tomllib is None:
        return TrustedContacts()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        section = data.get("trusted_contacts", {})
        return TrustedContacts(
            domains=[str(d) for d in section.get("domains", [])],
            emails=[str(e) for e in section.get("emails", [])],
            allow_all=bool(section.get("trust_all", False)),
        )
    except Exception:
        return TrustedContacts()
