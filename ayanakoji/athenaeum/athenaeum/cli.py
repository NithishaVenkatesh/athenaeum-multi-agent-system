"""Athenaeum command line: validate -> provision -> ingest -> status / teardown."""

from __future__ import annotations

import subprocess

import typer
from rich.console import Console
from rich.table import Table

from athenaeum import content
from athenaeum.config import REPO_DIR, get_settings

app = typer.Typer(add_completion=False, help="Athenaeum — course synthesis & Foundry IQ ingestion.")
console = Console()


@app.command()
def validate() -> None:
    """Check catalog/content/schema/provenance integrity (no Azure calls)."""
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
    console.print("[green]OK[/] — content is valid and ready to ingest.")


@app.command()
def provision() -> None:
    """Provision Azure AI Search (Basic) + the embedding deployment via scripts/provision.sh."""
    script = REPO_DIR / "scripts" / "provision.sh"
    console.print(f"[cyan]Running[/] {script}")
    result = subprocess.run(["bash", str(script)], cwd=str(REPO_DIR))
    raise typer.Exit(code=result.returncode)


@app.command()
def ingest() -> None:
    """Validate, build the index, upload documents, and build the Foundry IQ knowledge base."""
    from athenaeum.ingest import run

    settings = get_settings()
    console.print(
        f"[cyan]Ingesting[/] into index '{settings.index_name}' at {settings.search_endpoint}"
    )
    result = run(settings)
    console.print(f"[green]Uploaded[/] {result.documents_uploaded} documents.")
    if result.kb.created:
        console.print(f"[green]Foundry IQ KB[/] {result.kb.detail}")
        console.print(f"[bold]MCP endpoint:[/] {result.kb.mcp_endpoint}")
    else:
        console.print(f"[yellow]Knowledge base not created[/] — {result.kb.detail}")


@app.command()
def status() -> None:
    """Show the index document count."""
    from athenaeum.search_index import document_count

    settings = get_settings()
    count = document_count(settings)
    console.print(f"Index '{settings.index_name}': [bold]{count}[/] documents.")


@app.command()
def teardown(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete the Search resource group (credit hygiene). Irreversible."""
    settings = get_settings()
    rg = settings.search_resource_group
    if not yes:
        typer.confirm(f"Delete resource group '{rg}' and all resources in it?", abort=True)
    result = subprocess.run(
        ["az", "group", "delete", "--name", rg, "--yes", "--no-wait"],
    )
    raise typer.Exit(code=result.returncode)


def _main() -> None:
    if not (REPO_DIR / ".env").exists() and not (REPO_DIR / ".env.example").exists():
        console.print("[yellow]No .env found — copy .env.example to .env first.[/]")
    app()


if __name__ == "__main__":
    _main()
