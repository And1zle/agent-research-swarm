"""Genealogy research mode — iterative passes, project history, GEDCOM output."""

import json
import re
from datetime import datetime
from pathlib import Path
import asyncio

import click
from rich import box
from rich.panel import Panel
from rich.table import Table

from cli.core import load_config, run_swarm
from cli.presets import apply_preset
from cli.visual import console
from cli.wizard import run_wizard

GENEALOGY_DIR = Path.home() / ".swarm" / "genealogy"

MODE_CONFIG = {
    "quick":     {"passes": 1, "max_subtasks": 3, "label": "Quick",
                  "desc": "1 pass · 3 subtasks · fast overview"},
    "medium":    {"passes": 2, "max_subtasks": 4, "label": "Medium",
                  "desc": "2 passes · 4 subtasks · standard session"},
    "extensive": {"passes": 4, "max_subtasks": 6, "label": "Extensive",
                  "desc": "4 passes · 6 subtasks · deep dive to origins"},
}


# ── Session management ─────────────────────────────────────────────────────────

class GenealogySession:
    def __init__(self, project: str):
        self.project     = project
        self.project_dir = GENEALOGY_DIR / project
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.ged_file     = self.project_dir / "tree.ged"
        self.session_file = self.project_dir / "session.json"
        self.data = self._load_or_create()

    def _load_or_create(self) -> dict:
        if self.session_file.exists():
            with open(self.session_file, encoding="utf-8") as f:
                return json.load(f)
        return {
            "project":          self.project,
            "created":          datetime.now().isoformat(),
            "passes_completed": 0,
            "passes":           [],
        }

    def save(self):
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def next_pass_number(self) -> int:
        return self.data["passes_completed"] + 1

    def record_pass(self, pass_num: int, mode: str, new_ancestors: int, report_file: str):
        self.data["passes_completed"] = pass_num
        self.data["last_run"]         = datetime.now().isoformat()
        self.data["passes"].append({
            "pass":          pass_num,
            "date":          datetime.now().isoformat(),
            "mode":          mode,
            "new_ancestors": new_ancestors,
            "report":        report_file,
        })
        self.save()

    def get_ged_content(self) -> str:
        if self.ged_file.exists():
            return self.ged_file.read_text(encoding="utf-8")
        return ""

    def individual_count(self) -> int:
        return self.get_ged_content().count("0 @I")

    def save_pass_report(self, pass_num: int, report: str) -> str:
        path = self.project_dir / f"pass_{pass_num:02d}_report.md"
        path.write_text(report, encoding="utf-8")
        return str(path)

    def append_gedcom(self, new_gedcom: str) -> int:
        """Append new INDI/FAM records to tree.ged. Returns count of new individuals."""
        clean = _extract_gedcom_records(new_gedcom)
        if not clean:
            return 0
        existing = self.get_ged_content()
        if existing:
            existing = re.sub(r'\n?0 TRLR\s*$', '', existing.strip())
            content  = existing + "\n\n" + clean + "\n\n0 TRLR\n"
        else:
            content  = _gedcom_header(self.project) + "\n" + clean + "\n\n0 TRLR\n"
        self.ged_file.write_text(content, encoding="utf-8")
        return clean.count("0 @I")

    def get_frontier(self) -> list[dict]:
        """Individuals with no FAMC tag — the oldest known ancestors per line."""
        return _extract_frontier(self.get_ged_content())

    def print_status(self):
        console.print()
        table = Table(
            title=f"Project: {self.project}",
            box=box.SIMPLE_HEAD, border_style="dim"
        )
        table.add_column("", style="dim")
        table.add_column("", style="cyan")
        table.add_row("Passes completed", str(self.data["passes_completed"]))
        table.add_row("Individuals in tree", str(self.individual_count()))
        frontier = self.get_frontier()
        table.add_row("Frontier ancestors", str(len(frontier)))
        table.add_row("Tree file", str(self.ged_file))
        table.add_row("Reports", str(self.project_dir))
        console.print(table)

        if frontier:
            console.print("\n[dim]Current frontier (oldest known ancestors):[/dim]")
            for f in frontier:
                birth = f"~{f['birth']}" if f["birth"] else "unknown date"
                console.print(f"  [cyan]{f['name']}[/cyan] ({birth})")
        console.print()

        if self.data.get("passes"):
            console.print("[dim]Pass history:[/dim]")
            for p in self.data["passes"]:
                console.print(
                    f"  Pass {p['pass']} [{p['mode']}] — "
                    f"{p['new_ancestors']} new individuals — "
                    f"{p['date'][:10]}"
                )
        console.print()


# ── GEDCOM helpers ─────────────────────────────────────────────────────────────

def _gedcom_header(project: str) -> str:
    return (
        f"0 HEAD\n"
        f"1 GEDC\n"
        f"2 VERS 5.5.1\n"
        f"2 FORM LINEAGE-LINKED\n"
        f"1 CHAR UTF-8\n"
        f"1 SOUR AgentResearchSwarm\n"
        f"2 NAME Agent Research Swarm\n"
        f"1 DATE {datetime.now().strftime('%d %b %Y').upper()}\n"
        f"1 NOTE Project: {project}\n"
    )


def _extract_gedcom_records(text: str) -> str:
    """Pull valid GEDCOM lines from agent output, drop prose and HEAD/TRLR."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r'^[0-3] ', s):
            if s.startswith("0 HEAD") or s.startswith("0 TRLR"):
                continue
            lines.append(s)
    return "\n".join(lines)


def _extract_frontier(ged_content: str) -> list[dict]:
    """Parse a GEDCOM string and return individuals with no known parents."""
    if not ged_content:
        return []
    individuals: dict[str, dict] = {}
    current_id = None
    in_birt    = False

    for line in ged_content.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) < 2:
            continue
        level, tag = parts[0], parts[1]
        value      = parts[2] if len(parts) > 2 else ""

        if level == "0":
            in_birt = False
            if tag.startswith("@") and "INDI" in value:
                current_id = tag.strip("@")
                individuals[current_id] = {
                    "id": current_id, "name": "", "birth": "", "famc": False
                }
            else:
                current_id = None
        elif current_id:
            if   level == "1" and tag == "NAME":
                individuals[current_id]["name"] = value.replace("/", "").strip()
            elif level == "1" and tag == "FAMC":
                individuals[current_id]["famc"] = True
            elif level == "1" and tag == "BIRT":
                in_birt = True
            elif level == "2" and tag == "DATE" and in_birt:
                individuals[current_id]["birth"] = value
                in_birt = False
            elif level == "1":
                in_birt = False

    return [i for i in individuals.values() if not i["famc"] and i["name"]]


# ── Pass context builder ───────────────────────────────────────────────────────

def _build_pass_brief(original_brief: str, session: GenealogySession, pass_num: int) -> str:
    """Augment the original brief with frontier data for passes > 1."""
    parts = [original_brief]

    if pass_num > 1:
        frontier = session.get_frontier()
        if frontier:
            parts.append("\n\n=== CURRENT RESEARCH FRONTIER ===")
            parts.append(
                "The following are the OLDEST KNOWN ancestors in the current tree. "
                "Focus this pass on pushing THESE ancestors further back. "
                "Do NOT re-research individuals already documented.\n"
            )
            for f in frontier:
                birth = f"(~{f['birth']})" if f["birth"] else ""
                parts.append(f"  - {f['name']} {birth}")

        n = session.individual_count()
        parts.append(f"\n\n=== PASS {pass_num} CONTEXT ===")
        parts.append(
            f"This is research pass {pass_num}. "
            f"The current tree already contains {n} documented individuals. "
            "Go deeper — discover the parents and origins of the frontier ancestors above."
        )

    return "\n".join(parts)


# ── Utility ────────────────────────────────────────────────────────────────────

def _list_existing_projects():
    if not GENEALOGY_DIR.exists():
        return
    projects = sorted([p for p in GENEALOGY_DIR.iterdir() if p.is_dir()])
    if not projects:
        return
    console.print("[dim]Existing projects:[/dim]")
    for p in projects:
        sf = p / "session.json"
        if sf.exists():
            with open(sf, encoding="utf-8") as f:
                d = json.load(f)
            passes = d.get("passes_completed", 0)
            last   = d.get("last_run", "")[:10]
            console.print(f"  [cyan]{p.name}[/cyan]  {passes} passes  last run: {last}")
    console.print()


def _prompt_for_brief() -> str:
    console.print("[bold]Paste your family tree data below.[/bold]")
    console.print("[dim]Include known ancestors, dates, places, historical context.[/dim]")
    console.print("[dim]Type END on a blank line when finished:[/dim]\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


# ── Click command ──────────────────────────────────────────────────────────────

@click.command("genealogy")
@click.option("--project",   default=None,
              help="Project name (e.g. sanchez-griego). Prompted if not set.")
@click.option("--quick",     "mode", flag_value="quick",
              help="1 pass · 3 subtasks · fast overview")
@click.option("--medium",    "mode", flag_value="medium",    default=True,
              help="2 passes · 4 subtasks · standard (default)")
@click.option("--extensive", "mode", flag_value="extensive",
              help="4 passes · 6 subtasks · deep dive to origins")
@click.option("--from-file", "from_file", default=None, type=click.Path(exists=True),
              help="Load family tree brief from a .txt or .ged file")
@click.option("--resume",    is_flag=True,
              help="Resume project using existing tree.ged as context (skip brief prompt)")
@click.option("--status",    is_flag=True,
              help="Show project status and frontier ancestors, then exit")
@click.option("--parallel",  "n_parallel", default=None, type=int,
              help="Number of researcher agents to run in parallel (1-6). Prompted if not set.")
@click.option("--config",    "config_path", default="config.yaml")
@click.option("--debug",     is_flag=True)
def genealogy_cmd(project, mode, from_file, resume, status, n_parallel, config_path, debug):
    """Deep family tree research — iterative passes, project history, GEDCOM output.

    \b
    Examples:
      swarm genealogy                              # guided setup
      swarm genealogy --project sanchez-griego --medium
      swarm genealogy --project sanchez-griego --extensive --from-file brief.txt
      swarm genealogy --project sanchez-griego --resume --quick
      swarm genealogy --project sanchez-griego --status
    """
    # ── Config ────────────────────────────────────────────────────────────
    config = load_config(config_path)
    if config is None:
        console.print("[yellow]No config found. Running setup...[/yellow]\n")
        config = run_wizard(config_path)
    config = apply_preset(config, "genealogy")

    # ── Project ───────────────────────────────────────────────────────────
    if not project:
        _list_existing_projects()
        project = console.input(
            "[bold]Project name[/bold] [dim](new or existing, e.g. sanchez-griego):[/dim] "
        ).strip().lower().replace(" ", "-")
    if not project:
        console.print("[red]No project name provided.[/red]")
        return

    session = GenealogySession(project)

    # ── Status only ───────────────────────────────────────────────────────
    if status:
        session.print_status()
        return

    # ── Mode banner ───────────────────────────────────────────────────────
    cfg = MODE_CONFIG[mode]
    console.print()
    console.print(Panel(
        f"[bold cyan]Genealogy Research[/bold cyan]  "
        f"Project: [magenta]{project}[/magenta]\n"
        f"Mode: [yellow]{cfg['label']}[/yellow]  [dim]{cfg['desc']}[/dim]\n"
        f"Passes completed so far: [cyan]{session.data['passes_completed']}[/cyan]",
        box=box.DOUBLE_EDGE,
        border_style="cyan",
    ))
    console.print()

    # ── Parallel agents prompt ────────────────────────────────────────────
    if n_parallel is None:
        console.print("[bold]Run multiple researcher agents in parallel?[/bold]")
        console.print("  [dim]1[/dim]  Sequential [dim](safe, default — one at a time)[/dim]")
        console.print("  [dim]2[/dim]  2 parallel  [dim](2x faster research step)[/dim]")
        console.print("  [dim]3[/dim]  3 parallel  [dim](fastest — good if LM Studio handles queuing well)[/dim]\n")
        raw = console.input("  Parallel researchers [dim](1/2/3, default 1):[/dim] ").strip()
        n_parallel = int(raw) if raw.isdigit() and int(raw) in (1, 2, 3) else 1
        console.print()

    if n_parallel > 1:
        console.print(
            f"[green]v[/green] {n_parallel} parallel researchers — "
            f"subtasks will run concurrently\n"
            f"[dim]  Note: LM Studio queues requests with max_concurrent_predictions=1,\n"
            f"  so requests run back-to-back rather than truly simultaneously.\n"
            f"  Parallel mode still reduces coordination overhead.[/dim]\n"
        )

    # ── Load brief ────────────────────────────────────────────────────────
    if from_file:
        with open(from_file, encoding="utf-8") as f:
            brief = f.read().strip()
        console.print(
            f"[green]v[/green] Brief loaded from [dim]{from_file}[/dim] "
            f"({len(brief)} chars)\n"
        )
    elif resume and session.ged_file.exists():
        brief = session.get_ged_content()
        console.print(
            f"[green]v[/green] Resuming from existing tree "
            f"({session.individual_count()} individuals)\n"
        )
    elif session.ged_file.exists():
        console.print(
            f"[dim]Existing tree found ({session.individual_count()} individuals).[/dim]"
        )
        ans = console.input(
            "  Use existing tree as starting context? [dim](Y/n):[/dim] "
        ).strip().lower()
        if ans in ("", "y", "yes"):
            brief = session.get_ged_content()
        else:
            brief = _prompt_for_brief()
    else:
        brief = _prompt_for_brief()

    if not brief:
        console.print("[red]No family data provided.[/red]")
        return

    # ── Iterative passes ──────────────────────────────────────────────────
    total_passes = cfg["passes"]
    max_subtasks = cfg["max_subtasks"]

    for offset in range(total_passes):
        current_pass = session.next_pass_number()
        console.print(
            f"\n[bold cyan]--- Pass {current_pass} "
            f"({offset + 1} of {total_passes} this session) ---[/bold cyan]\n"
        )

        pass_brief = _build_pass_brief(brief, session, current_pass)

        result = asyncio.run(run_swarm(
            pass_brief, config,
            debug=debug,
            deep_brief=True,
            max_subtasks=max_subtasks,
            n_parallel=n_parallel,
        ))

        report_file  = session.save_pass_report(current_pass, result["report"])
        new_count    = session.append_gedcom(result.get("code", ""))
        session.record_pass(current_pass, mode, new_count, report_file)

        console.print(f"\n[green]v[/green] Pass {current_pass} complete")
        console.print(f"  New individuals added to tree: [cyan]{new_count}[/cyan]")
        console.print(f"  Report → [dim]{report_file}[/dim]")
        console.print(f"  Tree   → [dim]{session.ged_file}[/dim]")

        # Show updated frontier before next pass
        if offset < total_passes - 1:
            frontier = session.get_frontier()
            if frontier:
                console.print(
                    f"\n[dim]Updated frontier — next pass will research these:[/dim]"
                )
                for f in frontier[:5]:
                    birth = f"~{f['birth']}" if f["birth"] else "unknown date"
                    console.print(f"  [cyan]{f['name']}[/cyan] ({birth})")
            console.print()

    # ── Final summary ─────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold green]Session complete[/bold green]\n\n"
        f"Passes this session:  [cyan]{total_passes}[/cyan]\n"
        f"Total passes on project: [cyan]{session.data['passes_completed']}[/cyan]\n"
        f"Individuals in tree: [cyan]{session.individual_count()}[/cyan]\n"
        f"Tree file:  [dim]{session.ged_file}[/dim]\n"
        f"Reports:    [dim]{session.project_dir}[/dim]",
        border_style="green",
        box=box.SIMPLE,
    ))
