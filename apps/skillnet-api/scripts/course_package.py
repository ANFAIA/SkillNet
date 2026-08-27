#!/usr/bin/env python3
"""Work with course packages: a directory that installs as a course, with no LLM call.

``lint`` needs neither a database nor a key, so it runs on the host while a package is
being written, and reports every fault in one pass:

    uv run python scripts/course_package.py lint ../../packages/ticketing-basics

``install`` needs the application's database, so it runs inside the container:

    docker compose exec -T api sh -c \\
        'cd /app && uv run python scripts/course_package.py install /packages/ticketing-basics'

It installs as the first organization and its admin unless told otherwise, and it is safe to
re-run: a package always installs as the same course, so a second install updates it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.course_package import read_package  # noqa: E402
from src.services.course_package.install import InstallError, install_package  # noqa: E402


def _lint(args: argparse.Namespace) -> int:
    package = read_package(args.directory)
    if not package.ok:
        _report_faults(package)
        return 1

    atoms = sum(len(node.pack.must_preserve) for node in package.nodes)
    options = sum(len(node.pack.selectable) for node in package.nodes)
    print(f"{package.slug}: {package.title}")
    print(f"  {len(package.nodes)} nodes, {atoms} must-preserve atoms, {options} selectable")
    for node in package.nodes:
        pack = node.pack
        requires = f" <- {', '.join(node.requires)}" if node.requires else ""
        print(
            f"  - {node.slug}: {len(pack.must_preserve)} preserve,"
            f" {len(pack.selectable)} selectable,"
            f" {len(pack.evidence_specs)} evidence{requires}"
        )
    return 0


def _report_faults(package) -> None:
    print(f"{package.path}: {len(package.errors)} problem(s)", file=sys.stderr)
    for error in package.errors:
        print(f"  {error.location}: {error.message}", file=sys.stderr)


def _install(args: argparse.Namespace) -> int:
    package = read_package(args.directory)
    if not package.ok:
        _report_faults(package)
        return 1

    async def run() -> int:
        # Imported here so that ``lint`` stays runnable on a host with no database
        # configured, which is where a package is written.
        from src.deps.db import async_session_factory

        async with async_session_factory() as db:
            try:
                result = await install_package(
                    db,
                    package,
                    org_id=uuid.UUID(args.org_id) if args.org_id else None,
                    actor_id=uuid.UUID(args.admin_id) if args.admin_id else None,
                )
            except InstallError as exc:
                print(f"install failed: {exc}", file=sys.stderr)
                return 1
            await db.commit()
        print(result.summary())
        return 0

    return asyncio.run(run())


def _export(args: argparse.Namespace) -> int:
    async def run() -> int:
        from src.deps.db import async_session_factory
        from src.services.course_package.export import ExportError, export_course

        async with async_session_factory() as db:
            try:
                result = await export_course(
                    db, uuid.UUID(args.course_id), args.destination, slug=args.slug
                )
            except ExportError as exc:
                print(f"export failed: {exc}", file=sys.stderr)
                return 1
        print(result.summary())
        return 0

    return asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="Validate a package without touching the database")
    lint.add_argument("directory", help="Package directory to read")
    lint.set_defaults(handler=_lint)

    export = sub.add_parser("export", help="Write an existing course out as a package")
    export.add_argument("course_id", help="Course to export (UUID)")
    export.add_argument("destination", help="Directory to write the package into")
    export.add_argument("--slug", default=None, help="Package name (default: from the title)")
    export.set_defaults(handler=_export)

    install = sub.add_parser("install", help="Install a package into the database")
    install.add_argument("directory", help="Package directory to install")
    install.add_argument("--org-id", default=None, help="Target organization (UUID)")
    install.add_argument("--admin-id", default=None, help="Admin to install as (UUID)")
    install.set_defaults(handler=_install)

    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
