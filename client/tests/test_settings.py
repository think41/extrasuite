"""Tests for settings.py — TrustedContacts and load_trusted_contacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extrasuite.client.settings import TrustedContacts, load_trusted_contacts

# ---------------------------------------------------------------------------
# TrustedContacts.is_trusted
# ---------------------------------------------------------------------------


class TestTrustedContactsIsTrusted:
    def test_domain_match(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("alice@company.com") is True

    def test_domain_no_subdomain_bleed(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("alice@evil-company.com") is False

    def test_subdomain_not_matched(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("alice@mail.company.com") is False

    def test_email_exact_match(self) -> None:
        tc = TrustedContacts(domains=[], emails=["personal@gmail.com"])
        assert tc.is_trusted("personal@gmail.com") is True

    def test_email_no_domain_spill(self) -> None:
        tc = TrustedContacts(domains=[], emails=["personal@gmail.com"])
        assert tc.is_trusted("other@gmail.com") is False

    def test_case_insensitive_domain(self) -> None:
        tc = TrustedContacts(domains=["Company.COM"], emails=[])
        assert tc.is_trusted("Alice@company.com") is True

    def test_case_insensitive_email(self) -> None:
        tc = TrustedContacts(domains=[], emails=["Alice@Example.com"])
        assert tc.is_trusted("alice@example.com") is True

    def test_rfc5322_display_name(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("Alice Smith <alice@company.com>") is True

    def test_empty_trusted_contacts_not_trusted(self) -> None:
        tc = TrustedContacts()
        assert tc.is_trusted("alice@company.com") is False

    def test_empty_sender_not_trusted(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("") is False

    def test_bare_name_no_address(self) -> None:
        tc = TrustedContacts(domains=["company.com"], emails=[])
        assert tc.is_trusted("No Address Here") is False

    def test_user_domain_always_trusted(self) -> None:
        tc = TrustedContacts(domains=[], emails=[], user_domain="mycompany.com")
        assert tc.is_trusted("colleague@mycompany.com") is True

    def test_user_domain_does_not_trust_other_domains(self) -> None:
        tc = TrustedContacts(domains=[], emails=[], user_domain="mycompany.com")
        assert tc.is_trusted("spam@other.com") is False

    def test_user_domain_case_insensitive(self) -> None:
        tc = TrustedContacts(domains=[], emails=[], user_domain="MyCompany.COM")
        assert tc.is_trusted("Alice@mycompany.com") is True

    def test_allow_all_trusts_any_sender(self) -> None:
        tc = TrustedContacts(allow_all=True)
        assert tc.is_trusted("anyone@anydomain.com") is True

    def test_allow_all_trusts_empty_sender(self) -> None:
        # allow_all short-circuits before addr parsing
        tc = TrustedContacts(allow_all=True)
        assert tc.is_trusted("") is True

    def test_allow_all_false_by_default(self) -> None:
        tc = TrustedContacts()
        assert tc.allow_all is False


# ---------------------------------------------------------------------------
# load_trusted_contacts
# ---------------------------------------------------------------------------


class TestLoadTrustedContacts:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        tc = load_trusted_contacts(tmp_path / "nonexistent.toml")
        assert tc.domains == []
        assert tc.emails == []

    def test_valid_toml_loaded(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text(
            '[trusted_contacts]\ndomains = ["a.com", "b.com"]\nemails = ["c@d.com"]\n',
            encoding="utf-8",
        )
        tc = load_trusted_contacts(path)
        assert tc.domains == ["a.com", "b.com"]
        assert tc.emails == ["c@d.com"]

    def test_corrupt_toml_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text("not = valid [ toml !!!!", encoding="utf-8")
        tc = load_trusted_contacts(path)
        assert tc.domains == []

    def test_missing_trusted_contacts_section_returns_empty(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "settings.toml"
        path.write_text("[other_section]\nfoo = 1\n", encoding="utf-8")
        tc = load_trusted_contacts(path)
        assert tc.domains == []
        assert tc.emails == []

    def test_partial_keys_default_to_empty_list(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text('[trusted_contacts]\ndomains = ["x.com"]\n', encoding="utf-8")
        tc = load_trusted_contacts(path)
        assert tc.domains == ["x.com"]
        assert tc.emails == []

    def test_trust_all_true_sets_allow_all(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text("[trusted_contacts]\ntrust_all = true\n", encoding="utf-8")
        tc = load_trusted_contacts(path)
        assert tc.allow_all is True

    def test_trust_all_absent_defaults_false(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text('[trusted_contacts]\ndomains = ["a.com"]\n', encoding="utf-8")
        tc = load_trusted_contacts(path)
        assert tc.allow_all is False
