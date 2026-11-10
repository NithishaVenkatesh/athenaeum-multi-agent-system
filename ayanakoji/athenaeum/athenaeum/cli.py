"""Athenaeum command line: validate the authored course content.

Vector indexing lives with the backend that serves it:
``ayanakoji/backend/scripts/reindex_vectors.py`` embeds every catalog module with
Cohere and uploads it to Qdrant Cloud (see the backend README).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from athenaeum import content

app = typer.Typer(add_completion=False, help="Athenaeum — course content synthesis + validation.")
console = Console()


@app.command()
def validate() -> None:
    """Check catalog/content/schema/provenance integrity (no network calls)."""
    report = content.validate()
    table = Table(title="Athenaeum content validation")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("courses", f"{report.course_files}/{report.expected_courses}")
    table.add_row("modules", f"{report.module_files}/{report.expected_modules}")
    table.add_row("errors", str(len(report.errors)))
    table.add_row("warnings", str(len(report.warnings)))
    console.print(table)
    for issue in report.issues:
        color = "red" if issue.level == "error" else "yellow"
        console.print(f"[{color}]{issue.level.upper()}[/] {issue.where}: {issue.message}")
    if not report.ok:
        raise typer.Exit(code=1)
    console.print("[green]OK[/] — content is valid.")


@app.callback()
def _root() -> None:
    """Athenaeum content tooling."""


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
