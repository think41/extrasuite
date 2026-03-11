"""Unified CLI for ExtraSuite.

Usage:
    extrasuite drive    ls|search
    extrasuite sheet    pull|diff|push|create|batchUpdate|share
    extrasuite slide    pull|diff|push|create|share
    extrasuite doc      pull|diff|push|create|share
    extrasuite form     pull|diff|push|create|share
    extrasuite script   pull|diff|push|create|lint|share
    extrasuite gmail    compose|edit-draft|reply|list|read
    extrasuite calendar view|list|search|freebusy|create|update|delete|rsvp
    extrasuite contacts sync|search|touch
    extrasuite auth     login|logout|status
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from extrasuite.client.cli._common import _load_help, cmd_module_help
from extrasuite.client.cli.auth import (
    cmd_auth_login,
    cmd_auth_logout,
    cmd_auth_status,
)
from extrasuite.client.cli.calendar import (
    cmd_calendar_create,
    cmd_calendar_delete,
    cmd_calendar_freebusy,
    cmd_calendar_list,
    cmd_calendar_rsvp,
    cmd_calendar_search,
    cmd_calendar_update,
    cmd_calendar_view,
)
from extrasuite.client.cli.contacts import (
    cmd_contacts_search,
    cmd_contacts_sync,
    cmd_contacts_touch,
)
from extrasuite.client.cli.doc import (
    cmd_doc_create,
    cmd_doc_diff,
    cmd_doc_pull,
    cmd_doc_pull_md,
    cmd_doc_push,
    cmd_doc_push_md,
    cmd_doc_share,
)
from extrasuite.client.cli.drive import cmd_drive_ls, cmd_drive_search
from extrasuite.client.cli.form import (
    cmd_form_create,
    cmd_form_diff,
    cmd_form_pull,
    cmd_form_push,
    cmd_form_share,
)
from extrasuite.client.cli.gmail import (
    cmd_gmail_compose,
    cmd_gmail_edit_draft,
    cmd_gmail_list,
    cmd_gmail_read,
    cmd_gmail_reply,
)
from extrasuite.client.cli.script import (
    cmd_script_create,
    cmd_script_diff,
    cmd_script_lint,
    cmd_script_pull,
    cmd_script_push,
    cmd_script_share,
)
from extrasuite.client.cli.sheet import (
    cmd_sheet_batchupdate,
    cmd_sheet_create,
    cmd_sheet_diff,
    cmd_sheet_pull,
    cmd_sheet_push,
    cmd_sheet_share,
)
from extrasuite.client.cli.slide import (
    cmd_slide_create,
    cmd_slide_diff,
    cmd_slide_pull,
    cmd_slide_push,
    cmd_slide_share,
)

# Command dispatch table
_COMMANDS: dict[tuple[str, str | None], Callable[..., Any]] = {
    ("drive", "ls"): cmd_drive_ls,
    ("drive", "search"): cmd_drive_search,
    ("sheet", "pull"): cmd_sheet_pull,
    ("sheet", "diff"): cmd_sheet_diff,
    ("sheet", "push"): cmd_sheet_push,
    ("sheet", "create"): cmd_sheet_create,
    ("sheet", "batchUpdate"): cmd_sheet_batchupdate,
    ("sheet", "share"): cmd_sheet_share,
    ("slide", "pull"): cmd_slide_pull,
    ("slide", "diff"): cmd_slide_diff,
    ("slide", "push"): cmd_slide_push,
    ("slide", "create"): cmd_slide_create,
    ("slide", "share"): cmd_slide_share,
    ("form", "pull"): cmd_form_pull,
    ("form", "diff"): cmd_form_diff,
    ("form", "push"): cmd_form_push,
    ("form", "create"): cmd_form_create,
    ("form", "share"): cmd_form_share,
    ("script", "pull"): cmd_script_pull,
    ("script", "diff"): cmd_script_diff,
    ("script", "push"): cmd_script_push,
    ("script", "create"): cmd_script_create,
    ("script", "lint"): cmd_script_lint,
    ("script", "share"): cmd_script_share,
    ("doc", "pull"): cmd_doc_pull,
    ("doc", "pull-md"): cmd_doc_pull_md,
    ("doc", "diff"): cmd_doc_diff,
    ("doc", "push"): cmd_doc_push,
    ("doc", "push-md"): cmd_doc_push_md,
    ("doc", "create"): cmd_doc_create,
    ("doc", "share"): cmd_doc_share,
    ("gmail", "compose"): cmd_gmail_compose,
    ("gmail", "edit-draft"): cmd_gmail_edit_draft,
    ("gmail", "reply"): cmd_gmail_reply,
    ("gmail", "list"): cmd_gmail_list,
    ("gmail", "read"): cmd_gmail_read,
    ("calendar", "view"): cmd_calendar_view,
    ("calendar", "list"): cmd_calendar_list,
    ("calendar", "search"): cmd_calendar_search,
    ("calendar", "freebusy"): cmd_calendar_freebusy,
    ("calendar", "create"): cmd_calendar_create,
    ("calendar", "update"): cmd_calendar_update,
    ("calendar", "delete"): cmd_calendar_delete,
    ("calendar", "rsvp"): cmd_calendar_rsvp,
    ("contacts", "sync"): cmd_contacts_sync,
    ("contacts", "search"): cmd_contacts_search,
    ("contacts", "touch"): cmd_contacts_touch,
    ("sheet", "help"): cmd_module_help,
    ("slide", "help"): cmd_module_help,
    ("form", "help"): cmd_module_help,
    ("script", "help"): cmd_module_help,
    ("doc", "help"): cmd_module_help,
    ("gmail", "help"): cmd_module_help,
    ("calendar", "help"): cmd_module_help,
    ("auth", "login"): cmd_auth_login,
    ("auth", "logout"): cmd_auth_logout,
    ("auth", "status"): cmd_auth_status,
}


def build_parser() -> Any:
    """Build the argument parser."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="extrasuite",
        description=_load_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Shared auth flags for commands that need authentication
    auth_parent = argparse.ArgumentParser(add_help=False)
    auth_parent.add_argument(
        "--gateway", metavar="PATH", help="Path to gateway.json with server URLs"
    )
    auth_parent.add_argument(
        "--service-account",
        metavar="PATH",
        help="Path to service account JSON key file",
    )
    auth_parent.add_argument(
        "--reason",
        "-r",
        metavar="TEXT",
        default=None,
        help=(
            "Why this operation is being performed. "
            "Pass the user's actual intent for audit trails. "
            "Can also be set via the EXTRASUITE_REASON environment variable."
        ),
    )

    # --- drive ---
    drive_parser = subparsers.add_parser(
        "drive",
        help="Google Drive operations (list, search)",
        description=_load_help("drive"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    drive_sub = drive_parser.add_subparsers(dest="subcommand")

    sp = drive_sub.add_parser(
        "ls",
        help="List files visible to the service account",
        parents=[auth_parent],
        description=_load_help("drive", "ls"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--folder",
        metavar="URL",
        help="Limit listing to files inside a folder (URL or ID)",
    )
    sp.add_argument(
        "--max",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of files to return (default: 20)",
    )
    sp.add_argument(
        "--page",
        default="",
        metavar="TOKEN",
        help="Page token for pagination (from previous output)",
    )

    sp = drive_sub.add_parser(
        "search",
        help="Search files visible to the service account",
        parents=[auth_parent],
        description=_load_help("drive", "search"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "query", help="Drive query string (e.g. \"name contains 'budget'\")"
    )
    sp.add_argument(
        "--max",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of files to return (default: 20)",
    )
    sp.add_argument(
        "--page",
        default="",
        metavar="TOKEN",
        help="Page token for pagination (from previous output)",
    )

    # --- sheet ---
    sheet_parser = subparsers.add_parser(
        "sheet",
        help="Google Sheets operations",
        description=_load_help("sheet"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sheet_sub = sheet_parser.add_subparsers(dest="subcommand")

    sp = sheet_sub.add_parser(
        "pull",
        help="Download a spreadsheet",
        parents=[auth_parent],
        description=_load_help("sheet", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--max-rows", type=int, default=100, help="Max rows per sheet (default: 100)"
    )
    sp.add_argument("--no-limit", action="store_true", help="Fetch all rows")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = sheet_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("sheet", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")

    sp = sheet_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("sheet", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    sp = sheet_sub.add_parser(
        "batchUpdate",
        help="Advanced: execute raw batchUpdate requests (sort, move, etc.)",
        parents=[auth_parent],
        description=_load_help("sheet", "batchupdate"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument("requests_file", help="JSON file with requests")
    sp.add_argument("-v", "--verbose", action="store_true", help="Print API response")

    sp = sheet_sub.add_parser(
        "create",
        help="Create a new spreadsheet",
        parents=[auth_parent],
        description=_load_help("sheet", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Spreadsheet title")
    sp.add_argument(
        "--copy-from",
        metavar="URL",
        help="Copy an existing file instead of creating blank (must be a file extrasuite created)",
    )

    sp = sheet_sub.add_parser(
        "share",
        help="Share a spreadsheet with trusted contacts",
        parents=[auth_parent],
        description=_load_help("sheet", "share"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument(
        "emails", nargs="+", metavar="EMAIL", help="Recipient email addresses"
    )
    sp.add_argument(
        "--role",
        choices=["reader", "writer", "commenter"],
        default="reader",
        help="Permission role (default: reader)",
    )

    sp = sheet_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- slide ---
    slide_parser = subparsers.add_parser(
        "slide",
        help="Google Slides operations",
        description=_load_help("slide"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    slide_sub = slide_parser.add_subparsers(dest="subcommand")

    sp = slide_sub.add_parser(
        "pull",
        help="Download a presentation",
        parents=[auth_parent],
        description=_load_help("slide", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Presentation URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = slide_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("slide", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    sp = slide_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("slide", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    sp = slide_sub.add_parser(
        "create",
        help="Create a new presentation",
        parents=[auth_parent],
        description=_load_help("slide", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Presentation title")
    sp.add_argument(
        "--copy-from",
        metavar="URL",
        help="Copy an existing file instead of creating blank (must be a file extrasuite created)",
    )

    sp = slide_sub.add_parser(
        "share",
        help="Share a presentation with trusted contacts",
        parents=[auth_parent],
        description=_load_help("sheet", "share"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Presentation URL or ID")
    sp.add_argument(
        "emails", nargs="+", metavar="EMAIL", help="Recipient email addresses"
    )
    sp.add_argument(
        "--role",
        choices=["reader", "writer", "commenter"],
        default="reader",
        help="Permission role (default: reader)",
    )

    sp = slide_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- form ---
    form_parser = subparsers.add_parser(
        "form",
        help="Google Forms operations",
        description=_load_help("form"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    form_sub = form_parser.add_subparsers(dest="subcommand")

    sp = form_sub.add_parser(
        "pull",
        help="Download a form",
        parents=[auth_parent],
        description=_load_help("form", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Form URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument("--responses", action="store_true", help="Include form responses")
    sp.add_argument(
        "--max-responses", type=int, default=100, help="Max responses to fetch"
    )
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = form_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("form", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")

    sp = form_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("form", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    sp = form_sub.add_parser(
        "create",
        help="Create a new form",
        parents=[auth_parent],
        description=_load_help("form", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Form title")
    sp.add_argument(
        "--copy-from",
        metavar="URL",
        help="Copy an existing file instead of creating blank (must be a file extrasuite created)",
    )

    sp = form_sub.add_parser(
        "share",
        help="Share a form with trusted contacts",
        parents=[auth_parent],
        description=_load_help("sheet", "share"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Form URL or ID")
    sp.add_argument(
        "emails", nargs="+", metavar="EMAIL", help="Recipient email addresses"
    )
    sp.add_argument(
        "--role",
        choices=["reader", "writer", "commenter"],
        default="reader",
        help="Permission role (default: reader)",
    )

    sp = form_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- script ---
    script_parser = subparsers.add_parser(
        "script",
        help="Google Apps Script operations",
        description=_load_help("script"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    script_sub = script_parser.add_subparsers(dest="subcommand")

    sp = script_sub.add_parser(
        "pull",
        help="Download a script project",
        parents=[auth_parent],
        description=_load_help("script", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Script URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = script_sub.add_parser(
        "diff",
        help="Show which files changed (offline)",
        description=_load_help("script", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")

    sp = script_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("script", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")
    sp.add_argument("--skip-lint", action="store_true", help="Skip lint before push")

    sp = script_sub.add_parser(
        "create",
        help="Create a new script project",
        parents=[auth_parent],
        description=_load_help("script", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Project title")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument("--bind-to", help="Google Drive file URL or ID to bind to")

    sp = script_sub.add_parser(
        "lint",
        help="Lint script files (offline)",
        description=_load_help("script", "lint"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")

    sp = script_sub.add_parser(
        "share",
        help="Share a script project with trusted contacts",
        parents=[auth_parent],
        description=_load_help("sheet", "share"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Script URL or ID")
    sp.add_argument(
        "emails", nargs="+", metavar="EMAIL", help="Recipient email addresses"
    )
    sp.add_argument(
        "--role",
        choices=["reader", "writer", "commenter"],
        default="reader",
        help="Permission role (default: reader)",
    )

    sp = script_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- doc ---
    doc_parser = subparsers.add_parser(
        "doc",
        help="Google Docs operations",
        description=_load_help("doc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doc_sub = doc_parser.add_subparsers(dest="subcommand")

    sp = doc_sub.add_parser(
        "pull",
        help="Download a document",
        parents=[auth_parent],
        description=_load_help("doc", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Document URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = doc_sub.add_parser(
        "pull-md",
        help="Download a document as markdown",
        parents=[auth_parent],
        description=_load_help("doc", "pull-md"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Document URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = doc_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("doc", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")

    sp = doc_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("doc", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")
    sp.add_argument("--verify", action="store_true", help="Pull after push to verify")

    sp = doc_sub.add_parser(
        "push-md",
        help="Apply changes from a markdown folder",
        parents=[auth_parent],
        description=_load_help("doc", "push-md"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")
    sp.add_argument("--verify", action="store_true", help="Pull after push to verify")

    sp = doc_sub.add_parser(
        "create",
        help="Create a new document",
        parents=[auth_parent],
        description=_load_help("doc", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Document title")
    sp.add_argument(
        "--copy-from",
        metavar="URL",
        help="Copy an existing file instead of creating blank (must be a file extrasuite created)",
    )

    sp = doc_sub.add_parser(
        "share",
        help="Share a document with trusted contacts",
        parents=[auth_parent],
        description=_load_help("sheet", "share"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Document URL or ID")
    sp.add_argument(
        "emails", nargs="+", metavar="EMAIL", help="Recipient email addresses"
    )
    sp.add_argument(
        "--role",
        choices=["reader", "writer", "commenter"],
        default="reader",
        help="Permission role (default: reader)",
    )

    sp = doc_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- gmail ---
    gmail_parser = subparsers.add_parser(
        "gmail",
        help="Gmail operations",
        description=_load_help("gmail"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gmail_sub = gmail_parser.add_subparsers(dest="subcommand")

    sp = gmail_sub.add_parser(
        "compose",
        help="Save an email draft from a markdown file",
        parents=[auth_parent],
        description=_load_help("gmail", "compose"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("file", help="Markdown file with front matter")
    sp.add_argument(
        "--attach",
        action="append",
        metavar="FILE",
        help="Attach a file (can be repeated for multiple attachments)",
    )

    sp = gmail_sub.add_parser(
        "edit-draft",
        help="Update an existing Gmail draft from a markdown file",
        parents=[auth_parent],
        description=_load_help("gmail", "edit-draft"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("draft_id", help="Draft ID to update (from compose output)")
    sp.add_argument("file", help="Markdown file with front matter")
    sp.add_argument(
        "--attach",
        action="append",
        metavar="FILE",
        help="Attach a file (can be repeated for multiple attachments)",
    )

    sp = gmail_sub.add_parser(
        "reply",
        help="Create a reply draft in an existing email thread",
        parents=[auth_parent],
        description=_load_help("gmail", "reply"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("thread_id", help="Thread ID to reply to (from 'gmail list')")
    sp.add_argument("file", help="Markdown file with the reply body")
    sp.add_argument(
        "--attach",
        action="append",
        metavar="FILE",
        help="Attach a file (can be repeated)",
    )

    sp = gmail_sub.add_parser(
        "list",
        help="Search and list Gmail messages (metadata only)",
        parents=[auth_parent],
        description=_load_help("gmail", "list"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "query",
        nargs="?",
        default="",
        help="Gmail search query (e.g. 'is:unread from:alice@example.com'). Omit to list recent messages.",
    )
    sp.add_argument(
        "--max",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of messages to return (default: 20, max: 100)",
    )
    sp.add_argument(
        "--page",
        default="",
        metavar="TOKEN",
        help="Page token for pagination (from previous output)",
    )
    sp.add_argument(
        "--all",
        action="store_true",
        help="Show all senders including untrusted (default: trusted senders only)",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    sp = gmail_sub.add_parser(
        "read",
        help="Read a Gmail message (body redacted for untrusted senders)",
        parents=[auth_parent],
        description=_load_help("gmail", "read"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("thread_id", help="Thread ID (from 'gmail list' output)")
    sp.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    sp = gmail_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- calendar ---
    calendar_parser = subparsers.add_parser(
        "calendar",
        help="Google Calendar operations",
        description=_load_help("calendar"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    calendar_sub = calendar_parser.add_subparsers(dest="subcommand")

    sp = calendar_sub.add_parser(
        "view",
        help="View calendar events",
        parents=[auth_parent],
        description=_load_help("calendar", "view"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--calendar",
        default="primary",
        help="Calendar ID (default: primary)",
    )
    sp.add_argument(
        "--when",
        default="today",
        help="Time range: today, tomorrow, yesterday, this-week, next-week, or YYYY-MM-DD (default: today)",
    )

    calendar_sub.add_parser(
        "list",
        help="List all calendars",
        parents=[auth_parent],
        description=_load_help("calendar", "list"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sp = calendar_sub.add_parser(
        "search",
        help="Search calendar events by title or attendee",
        parents=[auth_parent],
        description=_load_help("calendar", "search"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("--query", help="Search text (title and description)")
    sp.add_argument("--attendee", help="Filter by attendee email")
    sp.add_argument(
        "--from", dest="fr", metavar="DATE", help="Start date (default: today)"
    )
    sp.add_argument(
        "--to", metavar="DATE", help="End date (default: 30 days from --from)"
    )
    sp.add_argument(
        "--calendar", default="primary", help="Calendar ID (default: primary)"
    )

    sp = calendar_sub.add_parser(
        "freebusy",
        help="Check free/busy for a list of people",
        parents=[auth_parent],
        description=_load_help("calendar", "freebusy"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--attendees",
        nargs="+",
        metavar="EMAIL",
        required=True,
        help="One or more email addresses to check",
    )
    sp.add_argument(
        "--when",
        default="next-week",
        help="Time range: today, tomorrow, this-week, next-week, or YYYY-MM-DD (default: next-week)",
    )

    sp = calendar_sub.add_parser(
        "create",
        help="Create a calendar event from a JSON file",
        parents=[auth_parent],
        description=_load_help("calendar", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--json",
        required=True,
        metavar="PATH",
        help="Path to event JSON file, or - to read from stdin",
    )
    sp.add_argument(
        "--calendar", default="primary", help="Calendar ID (default: primary)"
    )

    sp = calendar_sub.add_parser(
        "update",
        help="Update an existing calendar event",
        parents=[auth_parent],
        description=_load_help("calendar", "update"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("event_id", help="Event ID to update (from view/search output)")
    sp.add_argument(
        "--json",
        required=True,
        metavar="PATH",
        help="Path to patch JSON file, or - to read from stdin",
    )
    sp.add_argument(
        "--calendar", default="primary", help="Calendar ID (default: primary)"
    )
    sp.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress update notifications to attendees",
    )

    sp = calendar_sub.add_parser(
        "delete",
        help="Cancel/delete a calendar event",
        parents=[auth_parent],
        description=_load_help("calendar", "delete"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("event_id", help="Event ID to delete (from view/search output)")
    sp.add_argument(
        "--calendar", default="primary", help="Calendar ID (default: primary)"
    )
    sp.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress cancellation notifications to attendees",
    )
    sp.add_argument(
        "--this-and-following",
        action="store_true",
        help="For recurring events: cancel this occurrence and all following",
    )

    sp = calendar_sub.add_parser(
        "rsvp",
        help="Accept, decline, or mark tentative for an event",
        parents=[auth_parent],
        description=_load_help("calendar", "rsvp"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("event_id", help="Event ID (from view/search output)")
    sp.add_argument(
        "--response",
        required=True,
        choices=["accept", "decline", "tentative"],
        help="Your RSVP response",
    )
    sp.add_argument("--comment", help="Optional message to include with your response")
    sp.add_argument(
        "--calendar", default="primary", help="Calendar ID (default: primary)"
    )

    sp = calendar_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- contacts ---
    contacts_parser = subparsers.add_parser(
        "contacts",
        help="Google Contacts operations (sync, search, touch)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    contacts_sub = contacts_parser.add_subparsers(dest="subcommand")

    contacts_sub.add_parser(
        "sync",
        help="Sync contacts from Google to local DB",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sp = contacts_sub.add_parser(
        "search",
        help="Search local contacts (auto-syncs if needed)",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "queries",
        nargs="+",
        metavar="QUERY",
        help='One or more search strings, e.g. "Alice company" "Bob corp"',
    )

    sp = contacts_sub.add_parser(
        "touch",
        help="Record that these email addresses were contacted",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "emails",
        nargs="+",
        metavar="EMAIL",
        help="Email addresses to mark as contacted",
    )

    # --- auth ---
    auth_parser = subparsers.add_parser(
        "auth",
        help="Authentication management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    auth_sub = auth_parser.add_subparsers(dest="subcommand")

    sp = auth_sub.add_parser(
        "login",
        help="Log in and obtain a 30-day session token",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--headless",
        action="store_true",
        help="Headless mode: print URL and prompt for code instead of opening browser",
    )

    auth_sub.add_parser(
        "logout",
        help="Revoke session token and clear cached credentials",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    auth_sub.add_parser(
        "status",
        help="Show current auth status",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    return parser


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    subcommand = getattr(args, "subcommand", None)

    if not subcommand:
        # Print subparser help
        for action in parser._subparsers._actions:
            if isinstance(action, type(parser._subparsers._actions[0])):
                sub = action.choices.get(args.command)
                if sub:
                    sub.print_help()
                    sys.exit(1)
        parser.print_help()
        sys.exit(1)

    handler = _COMMANDS.get((args.command, subcommand))

    if handler is None:
        print(f"Unknown command: {args.command} {subcommand or ''}", file=sys.stderr)
        sys.exit(1)

    try:
        handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except ValueError as e:
        error_msg = str(e)
        print(f"Error: {error_msg}", file=sys.stderr)
        if "No authentication method configured" in error_msg:
            print(
                "\nRun with --help for authentication options.",
                file=sys.stderr,
            )
        sys.exit(1)
    except TimeoutError:
        print("Error: Operation timed out.", file=sys.stderr)
        print(
            "Tip: Use --service-account for headless environments.",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
