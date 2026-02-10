"""CLI entry point for extrascripts.

Usage:
    python -m extrascripts pull <script_id_or_url> [output_dir]
    python -m extrascripts push <folder>
    python -m extrascripts diff <folder>
    python -m extrascripts create <title> [--bind-to <file_id_or_url>]
    python -m extrascripts run <folder> <function> [--arg value]...
    python -m extrascripts logs [<folder>] [--limit N]
    python -m extrascripts deploy <folder> [--description desc]
    python -m extrascripts versions <folder>
    python -m extrascripts lint <folder>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from extrascripts.client import ScriptsClient
from extrascripts.credentials import CredentialsManager
from extrascripts.linter import Severity
from extrascripts.transport import AppsScriptTransport


def parse_script_id(id_or_url: str) -> str:
    """Extract script ID from a URL or return as-is.

    Supports URLs like:
      https://script.google.com/d/SCRIPT_ID/edit
      https://script.google.com/home/projects/SCRIPT_ID/edit
    """
    patterns = [
        r"script\.google\.com/d/([a-zA-Z0-9_-]+)",
        r"script\.google\.com/home/projects/([a-zA-Z0-9_-]+)",
        r"script\.google\.com/macros/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, id_or_url)
        if match:
            return match.group(1)
    return id_or_url


def parse_file_id(id_or_url: str) -> str:
    """Extract Google Drive file ID from a URL or return as-is.

    Supports Sheets, Docs, Slides, and Forms URLs.
    """
    patterns = [
        r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/forms/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, id_or_url)
        if match:
            return match.group(1)
    return id_or_url


def _read_script_id_from_folder(folder: Path) -> str:
    """Read scriptId from a project folder's project.json."""
    project_json = folder / "project.json"
    if not project_json.exists():
        print(f"Error: project.json not found in {folder}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(project_json.read_text())
    script_id: str = data.get("scriptId", "")
    if not script_id:
        print("Error: scriptId missing from project.json", file=sys.stderr)
        sys.exit(1)
    return script_id


def _get_client() -> tuple[ScriptsClient, AppsScriptTransport]:
    """Authenticate and create a ScriptsClient."""
    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)
    transport = AppsScriptTransport(access_token=token_obj.access_token)
    client = ScriptsClient(transport)
    return client, transport


# --- Command handlers ---


async def cmd_pull(args: argparse.Namespace) -> int:
    """Pull a script project to local files."""
    script_id = parse_script_id(args.script)
    output_path = Path(args.output) if args.output else Path()

    client, transport = _get_client()
    try:
        print(f"Pulling script project: {script_id}")
        files = await client.pull(script_id, output_path, save_raw=not args.no_raw)
        print(f"\nWrote {len(files)} files to {output_path / script_id}:")
        for path in files:
            print(f"  {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_push(args: argparse.Namespace) -> int:
    """Push local files to the Apps Script project."""
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    # Run lint first (unless --skip-lint)
    if not args.skip_lint:
        client_for_lint = ScriptsClient.__new__(ScriptsClient)
        lint_result = ScriptsClient.lint(client_for_lint, folder)
        if lint_result.has_errors:
            print("Lint errors found. Fix them before pushing:", file=sys.stderr)
            for d in lint_result.diagnostics:
                if d.severity == Severity.ERROR:
                    print(f"  {d}", file=sys.stderr)
            print(
                "\nUse --skip-lint to push anyway (not recommended).",
                file=sys.stderr,
            )
            return 1
        if lint_result.warning_count > 0:
            print(f"Lint: {lint_result.warning_count} warning(s)", file=sys.stderr)
            for d in lint_result.diagnostics:
                if d.severity == Severity.WARNING:
                    print(f"  {d}", file=sys.stderr)
            print(file=sys.stderr)

    client, transport = _get_client()
    try:
        result = await client.push(folder)
        if result.success:
            print(
                f"Successfully pushed {result.files_pushed} files "
                f"to script {result.script_id}"
            )
            return 0
        else:
            print(f"Push failed: {result.message}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_diff(args: argparse.Namespace) -> int:
    """Show changes between current files and pristine."""
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    # diff is local-only, no transport needed
    client = ScriptsClient.__new__(ScriptsClient)
    try:
        diff_result = ScriptsClient.diff(client, folder)

        if not diff_result.has_changes:
            print("No changes detected.")
            return 0

        if diff_result.added:
            for f in diff_result.added:
                print(f"  + {f}")
        if diff_result.removed:
            for f in diff_result.removed:
                print(f"  - {f}")
        if diff_result.modified:
            for f in diff_result.modified:
                print(f"  ~ {f}")

        total = (
            len(diff_result.added)
            + len(diff_result.removed)
            + len(diff_result.modified)
        )
        print(
            f"\n{total} file(s) changed "
            f"({len(diff_result.added)} added, "
            f"{len(diff_result.removed)} removed, "
            f"{len(diff_result.modified)} modified)"
        )
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def cmd_create(args: argparse.Namespace) -> int:
    """Create a new Apps Script project."""
    title = args.title
    parent_id = parse_file_id(args.bind_to) if args.bind_to else None
    output_path = Path(args.output) if args.output else Path()

    client, transport = _get_client()
    try:
        if parent_id:
            print(f"Creating bound script '{title}' (parent: {parent_id})")
        else:
            print(f"Creating standalone script '{title}'")

        files = await client.create(title, output_path, parent_id=parent_id)
        print(f"\nCreated project. Wrote {len(files)} files:")
        for path in files:
            print(f"  {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_run(args: argparse.Namespace) -> int:
    """Execute a function in the script project."""
    folder = Path(args.folder)
    script_id = _read_script_id_from_folder(folder)
    function = args.function

    # Parse arguments
    parameters: list[str] | None = args.arg if args.arg else None

    client, transport = _get_client()
    try:
        print(f"Running {function}() in {script_id}...")
        result = await client.run(script_id, function, parameters, dev_mode=args.dev)

        if result.error:
            details = result.error.get("details", [{}])
            if details:
                detail = details[0]
                print(
                    f"Execution error: {detail.get('errorMessage', 'Unknown error')}",
                    file=sys.stderr,
                )
                for frame in detail.get("scriptStackTraceElements", []):
                    print(
                        f"  at {frame.get('function', '?')}:{frame.get('lineNumber', '?')}",
                        file=sys.stderr,
                    )
            else:
                print(f"Execution error: {result.error}", file=sys.stderr)
            return 1

        if result.return_value is not None:
            print(json.dumps(result.return_value, indent=2))
        else:
            print("Function executed successfully (no return value).")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_logs(args: argparse.Namespace) -> int:
    """View execution logs."""
    script_id: str | None = None
    if args.folder:
        folder = Path(args.folder)
        script_id = _read_script_id_from_folder(folder)

    client, transport = _get_client()
    try:
        processes = await client.logs(script_id, limit=args.limit)

        if not processes:
            print("No recent executions found.")
            return 0

        for p in processes:
            status_icon = {
                "COMPLETED": "OK",
                "FAILED": "FAIL",
                "TIMED_OUT": "TIMEOUT",
                "RUNNING": "RUN",
                "CANCELED": "CANCEL",
            }.get(p.process_status, p.process_status)

            print(
                f"[{status_icon:>7}] {p.function_name:30s} "
                f"{p.process_type:10s} {p.start_time} {p.duration}"
            )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_deploy(args: argparse.Namespace) -> int:
    """Create a version and deployment."""
    folder = Path(args.folder)
    script_id = _read_script_id_from_folder(folder)

    client, transport = _get_client()
    try:
        # Create version first
        version = await client.create_version(script_id, description=args.description)
        print(f"Created version {version.version_number}")

        # Create deployment
        deployment = await client.create_deployment(
            script_id,
            version.version_number,
            description=args.description,
        )
        print(f"Created deployment {deployment.deployment_id}")
        print(f"  Version: {deployment.version_number}")
        if deployment.description:
            print(f"  Description: {deployment.description}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_versions(args: argparse.Namespace) -> int:
    """List versions of a project."""
    folder = Path(args.folder)
    script_id = _read_script_id_from_folder(folder)

    client, transport = _get_client()
    try:
        versions = await client.list_versions(script_id)

        if not versions:
            print("No versions found.")
            return 0

        for v in versions:
            desc = f" - {v.description}" if v.description else ""
            print(f"  v{v.version_number}{desc}  ({v.create_time})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_lint(args: argparse.Namespace) -> int:
    """Run lint checks on script files."""
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    client = ScriptsClient.__new__(ScriptsClient)
    lint_result = ScriptsClient.lint(client, folder)

    if not lint_result.diagnostics:
        print("No issues found.")
        return 0

    for d in lint_result.diagnostics:
        print(f"  {d}")

    print(
        f"\n{lint_result.error_count} error(s), {lint_result.warning_count} warning(s)"
    )

    return 1 if lint_result.has_errors else 0


# --- CLI setup ---


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="extrascripts",
        description="Manage Google Apps Script projects for LLM agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull
    pull_parser = subparsers.add_parser(
        "pull", help="Pull a script project to local files"
    )
    pull_parser.add_argument("script", help="Script ID or Apps Script URL")
    pull_parser.add_argument("output", nargs="?", default=None, help="Output directory")
    pull_parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Don't save raw API responses",
    )
    pull_parser.set_defaults(func=cmd_pull)

    # push
    push_parser = subparsers.add_parser(
        "push", help="Push local files to the Apps Script project"
    )
    push_parser.add_argument("folder", help="Path to project folder")
    push_parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip lint checks before pushing",
    )
    push_parser.set_defaults(func=cmd_push)

    # diff
    diff_parser = subparsers.add_parser(
        "diff", help="Show changes between current files and pristine"
    )
    diff_parser.add_argument("folder", help="Path to project folder")
    diff_parser.set_defaults(func=cmd_diff)

    # create
    create_parser = subparsers.add_parser(
        "create", help="Create a new Apps Script project"
    )
    create_parser.add_argument("title", help="Project title")
    create_parser.add_argument(
        "--bind-to",
        metavar="FILE",
        help="Google Drive file ID or URL to bind the script to "
        "(creates a container-bound script for Sheets/Docs/Slides/Forms)",
    )
    create_parser.add_argument(
        "output", nargs="?", default=None, help="Output directory"
    )
    create_parser.set_defaults(func=cmd_create)

    # run
    run_parser = subparsers.add_parser("run", help="Execute a function in the script")
    run_parser.add_argument("folder", help="Path to project folder")
    run_parser.add_argument("function", help="Function name to execute")
    run_parser.add_argument(
        "--arg",
        action="append",
        help="Argument to pass (can be repeated)",
    )
    run_parser.add_argument(
        "--dev",
        action="store_true",
        default=True,
        help="Run against HEAD code (default: True)",
    )
    run_parser.set_defaults(func=cmd_run)

    # logs
    logs_parser = subparsers.add_parser("logs", help="View recent execution logs")
    logs_parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Path to project folder (optional, filters by project)",
    )
    logs_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max entries to show (default: 20)",
    )
    logs_parser.set_defaults(func=cmd_logs)

    # deploy
    deploy_parser = subparsers.add_parser(
        "deploy", help="Create a versioned deployment"
    )
    deploy_parser.add_argument("folder", help="Path to project folder")
    deploy_parser.add_argument(
        "--description",
        default=None,
        help="Description for the version and deployment",
    )
    deploy_parser.set_defaults(func=cmd_deploy)

    # versions
    versions_parser = subparsers.add_parser(
        "versions", help="List versions of a project"
    )
    versions_parser.add_argument("folder", help="Path to project folder")
    versions_parser.set_defaults(func=cmd_versions)

    # lint
    lint_parser = subparsers.add_parser("lint", help="Run lint checks on script files")
    lint_parser.add_argument("folder", help="Path to project folder")
    lint_parser.set_defaults(func=cmd_lint)

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
