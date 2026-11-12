#!/usr/bin/env python3
"""
LBVD Stack Management CLI

A unified CLI for managing the nginx, docker, mysql/mariadb, redis, and FastAPI stack
for both local development and production environments.
"""

import os
import sys
import subprocess
import shlex
from pathlib import Path
from typing import Optional, List
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich import print as rprint

# ─── Constants ───
ROOT = Path(__file__).parent.resolve()
LOCAL_COMPOSE = ROOT / "docker-compose.local.yml"
PROD_COMPOSE = ROOT / "docker-compose.prod.yml"
LOCAL_ENV = ROOT / ".env"
PROD_ENV = ROOT / ".env.prod"
PROD_ENV_EXAMPLE = ROOT / ".env.prod.example"

console = Console()
app = typer.Typer(
    name="lbvd",
    help="🐳 LBVD Stack Manager — nginx, Docker, MySQL/MariaDB, Redis, FastAPI",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


class Environment(str, Enum):
    LOCAL = "local"
    PROD = "prod"


def get_compose_file(env: Environment) -> Path:
    """Return the appropriate docker-compose file for the environment."""
    if env == Environment.LOCAL:
        return LOCAL_COMPOSE
    return PROD_COMPOSE


def get_env_file(env: Environment) -> Path:
    """Return the appropriate .env file for the environment."""
    if env == Environment.LOCAL:
        return LOCAL_ENV
    return PROD_ENV


def run_compose(
    env: Environment,
    args: List[str],
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a docker compose command with the correct file and env."""
    compose_file = get_compose_file(env)
    env_file = get_env_file(env)

    if not compose_file.exists():
        console.print(f"[red]✗ Compose file not found: {compose_file}[/red]")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(compose_file)]

    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    elif env == Environment.PROD:
        console.print("[yellow]⚠ .env.prod not found. Copy .env.prod.example first.[/yellow]")

    cmd.extend(args)

    console.print(f"[dim]$ {' '.join(shlex.quote(c) for c in cmd)}[/dim]")

    result = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True)

    if check and result.returncode != 0:
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")
        raise typer.Exit(result.returncode)

    return result


def check_docker() -> bool:
    """Check if Docker and Docker Compose are available."""
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True)
        subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ─── Core Commands ───

@app.command()
def up(
    env: Environment = typer.Option(
        Environment.LOCAL, "--env", "-e", help="Environment to start"
    ),
    build: bool = typer.Option(False, "--build", "-b", help="Build images before starting"),
    detach: bool = typer.Option(True, "--detach/--no-detach", "-d/ ", help="Run in background"),
    services: Optional[List[str]] = typer.Argument(None, help="Specific services to start"),
):
    """🚀 Start the stack (local or production)."""
    if not check_docker():
        console.print("[red]✗ Docker or Docker Compose not found[/red]")
        raise typer.Exit(1)

    args = ["up"]
    if build:
        args.append("--build")
    if detach:
        args.append("-d")
    if services:
        args.extend(services)

    console.print(f"[green]Starting {env.value} stack...[/green]")
    run_compose(env, args)
    console.print(f"[green]✓ {env.value} stack started[/green]")


@app.command()
def down(
    env: Environment = typer.Option(
        Environment.LOCAL, "--env", "-e", help="Environment to stop"
    ),
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Remove volumes (⚠ data loss)"),
    remove_orphans: bool = typer.Option(True, "--remove-orphans/--no-remove-orphans"),
):
    """🛑 Stop the stack."""
    if not check_docker():
        console.print("[red]✗ Docker not found[/red]")
        raise typer.Exit(1)

    if volumes and not Confirm.ask("[red]⚠ This will delete all data volumes. Continue?[/red]"):
        raise typer.Abort()

    args = ["down"]
    if volumes:
        args.append("-v")
    if remove_orphans:
        args.append("--remove-orphans")

    console.print(f"[yellow]Stopping {env.value} stack...[/yellow]")
    run_compose(env, args)
    console.print(f"[green]✓ {env.value} stack stopped[/green]")


@app.command()
def restart(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    services: Optional[List[str]] = typer.Argument(None),
):
    """🔄 Restart services."""
    args = ["restart"]
    if services:
        args.extend(services)
    run_compose(env, args)
    console.print(f"[green]✓ {env.value} stack restarted[/green]")


@app.command()
def logs(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f/ ", help="Follow log output"),
    tail: int = typer.Option(100, "--tail", "-t", help="Number of lines to show"),
    services: Optional[List[str]] = typer.Argument(None),
):
    """📜 View service logs."""
    args = ["logs"]
    if follow:
        args.append("-f")
    args.extend(["--tail", str(tail)])
    if services:
        args.extend(services)
    run_compose(env, args, check=False)


@app.command()
def ps(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    all: bool = typer.Option(False, "--all", "-a", help="Show stopped containers"),
):
    """📋 List running containers."""
    args = ["ps"]
    if all:
        args.append("-a")
    run_compose(env, args)


@app.command()
def status(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """📊 Show detailed service status with health checks."""
    result = run_compose(env, ["ps", "--format", "json"], capture=True)
    if result.returncode != 0:
        return

    import json
    try:
        containers = json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print(result.stdout)
        return

    table = Table(title=f"Service Status — {env.value}")
    table.add_column("Service", style="cyan")
    table.add_column("Container", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Health", style="yellow")
    table.add_column("Ports", style="blue")

    for c in containers:
        name = c.get("Service", c.get("Name", "unknown"))
        container = c.get("Name", "")
        state = c.get("State", "unknown")
        health = c.get("Health", "N/A")
        ports = c.get("Publishers", [])

        port_str = ", ".join(f"{p.get('PublishedPort', '')}→{p.get('TargetPort', '')}" for p in ports) or "—"

        # Color status
        if state == "running":
            state = "[green]running[/green]"
        elif state == "exited":
            state = "[red]exited[/red]"
        else:
            state = f"[yellow]{state}[/yellow]"

        # Color health
        if health == "healthy":
            health = "[green]healthy[/green]"
        elif health == "unhealthy":
            health = "[red]unhealthy[/red]"
        elif health == "starting":
            health = "[yellow]starting[/yellow]"

        table.add_row(name, container, state, health, port_str)

    console.print(table)


@app.command()
def build(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    services: Optional[List[str]] = typer.Argument(None),
):
    """🔨 Build Docker images."""
    args = ["build"]
    if no_cache:
        args.append("--no-cache")
    if services:
        args.extend(services)
    run_compose(env, args)


@app.command()
def pull(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """⬇️ Pull latest base images."""
    run_compose(env, ["pull"])


# ─── Database Commands ───

@app.command()
def db_shell(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """🗄️ Open a database shell (mysql/mariadb)."""
    compose_file = get_compose_file(env)
    db_service = "db"  # both local and prod use 'db'

    run_compose(
        env,
        ["exec", "-it", db_service, "sh", "-c", 'exec mysql -u root -p"$MYSQL_ROOT_PASSWORD"'],
        check=False,
    )


@app.command()
def db_backup(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """💾 Backup database to a .sql.gz file."""
    from datetime import datetime

    if output is None:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "backups" / f"lbvd-{timestamp}.sql.gz"

    output.parent.mkdir(parents=True, exist_ok=True)

    if env == Environment.LOCAL:
        # Local uses MySQL
        cmd = [
            "exec", "-T", "db",
            "sh", "-c",
            'exec mysqldump --single-transaction --routines --triggers '
            '-u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
        ]
    else:
        # Prod uses MariaDB
        cmd = [
            "exec", "-T", "db",
            "sh", "-c",
            'exec mariadb-dump --single-transaction --routines --triggers '
            '-u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"'
        ]

    console.print(f"[green]Creating backup: {output}[/green]")
    result = run_compose(env, cmd, capture=True)
    if result.returncode == 0:
        import gzip
        with gzip.open(output, "wt") as f:
            f.write(result.stdout)
        console.print(f"[green]✓ Backup written to {output}[/green]")
    else:
        console.print(f"[red]Backup failed: {result.stderr}[/red]")
        raise typer.Exit(1)


@app.command()
def db_restore(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    backup_file: Path = typer.Argument(..., help="Path to .sql.gz backup file"),
):
    """📥 Restore database from a .sql.gz backup."""
    if not backup_file.exists():
        console.print(f"[red]Backup file not found: {backup_file}[/red]")
        raise typer.Exit(1)

    if not Confirm.ask(f"[red]⚠ This will overwrite the {env.value} database. Continue?[/red]"):
        raise typer.Abort()

    import gzip
    with gzip.open(backup_file, "rt") as f:
        sql = f.read()

    if env == Environment.LOCAL:
        cmd = ["exec", "-T", "db", "sh", "-c", 'exec mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"']
    else:
        cmd = ["exec", "-T", "db", "sh", "-c", 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"']

    console.print(f"[green]Restoring from {backup_file}...[/green]")
    result = subprocess.run(
        ["docker", "compose", "-f", str(get_compose_file(env))] + cmd,
        cwd=ROOT,
        input=sql,
        text=True,
        capture_output=True,
    )

    if result.returncode == 0:
        console.print("[green]✓ Database restored[/green]")
    else:
        console.print(f"[red]Restore failed: {result.stderr}[/red]")
        raise typer.Exit(1)


@app.command()
def db_seed(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """🌱 Re-seed the database from SQL files."""
    if not Confirm.ask("[yellow]This will re-initialize the database. Continue?[/yellow]"):
        raise typer.Abort()

    # For local, the init-db.sql is mounted and runs on empty volume
    # For prod, seed.sql runs on empty volume
    console.print("[yellow]To re-seed, you need to remove the database volume and restart.[/yellow]")
    console.print("Run: lbvd down --volumes && lbvd up")


# ─── App Commands ───

@app.command()
def shell(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    service: str = typer.Argument("app", help="Service to shell into"),
):
    """🐚 Open a shell in a running container."""
    run_compose(env, ["exec", "-it", service, "sh"], check=False)


@app.command()
def python_shell(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """🐍 Open a Python REPL in the app container."""
    run_compose(env, ["exec", "-it", "app", "python"], check=False)


@app.command()
def migrate(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """🔧 Run database migrations (Alembic)."""
    run_compose(env, ["exec", "app", "alembic", "upgrade", "head"])


@app.command()
def create_migration(
    message: str = typer.Argument(..., help="Migration message"),
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """📝 Create a new Alembic migration."""
    run_compose(env, ["exec", "app", "alembic", "revision", "--autogenerate", "-m", message])


# ─── Utility Commands ───

@app.command()
def init_local(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .env"),
):
    """🔧 Initialize local .env file from example."""
    env_example = ROOT / ".env.example"
    if not env_example.exists():
        # Create a basic .env for local development
        content = """# Local Development Environment
# Copy this to .env and modify as needed

# Database (matches docker-compose.local.yml)
MYSQL_PASSWORD=ucstgo

# App
SESSION_SECRET=local-dev-secret-change-in-production
JWT_SECRET_KEY=local-dev-jwt-secret-change-in-production
DEBUG=true
COOKIE_HTTPS_ONLY=false

# Optional: override defaults
# APP_VERSION=1.0.0
# WEB_CONCURRENCY=1
"""
        if LOCAL_ENV.exists() and not force:
            console.print("[yellow].env already exists. Use --force to overwrite.[/yellow]")
            raise typer.Exit(1)
        LOCAL_ENV.write_text(content)
        console.print("[green]✓ Created .env for local development[/green]")
    else:
        if LOCAL_ENV.exists() and not force:
            console.print("[yellow].env already exists. Use --force to overwrite.[/yellow]")
            raise typer.Exit(1)
        import shutil
        shutil.copy(env_example, LOCAL_ENV)
        console.print("[green]✓ Copied .env.example to .env[/green]")


@app.command()
def init_prod(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain name for Caddy"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """🔧 Initialize production .env.prod from example."""
    if not PROD_ENV_EXAMPLE.exists():
        console.print("[red]✗ .env.prod.example not found[/red]")
        raise typer.Exit(1)

    if PROD_ENV.exists() and not force:
        console.print("[yellow].env.prod already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(1)

    import secrets
    content = PROD_ENV_EXAMPLE.read_text()
    content = content.replace("SESSION_SECRET=", f"SESSION_SECRET={secrets.token_hex(32)}")
    content = content.replace("JWT_SECRET_KEY=", f"JWT_SECRET_KEY={secrets.token_hex(32)}")
    content = content.replace("DB_PASSWORD=", f"DB_PASSWORD={secrets.token_hex(24)}")
    content = content.replace("DB_ROOT_PASSWORD=", f"DB_ROOT_PASSWORD={secrets.token_hex(24)}")

    if domain:
        content = content.replace("DOMAIN=lbvd.example.com", f"DOMAIN={domain}")

    PROD_ENV.write_text(content)
    PROD_ENV.chmod(0o600)
    console.print("[green]✓ Created .env.prod with generated secrets[/green]")
    console.print("[yellow]⚠ Edit .env.prod to verify all values, especially DOMAIN[/yellow]")


@app.command()
def clean(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
    all: bool = typer.Option(False, "--all", "-a", help="Also remove images and volumes"),
):
    """🧹 Clean up Docker resources."""
    if all:
        if not Confirm.ask("[red]⚠ This will remove ALL containers, images, and volumes for this project. Continue?[/red]"):
            raise typer.Abort()
        run_compose(env, ["down", "-v", "--rmi", "all", "--remove-orphans"])
    else:
        run_compose(env, ["down", "--remove-orphans"])
    console.print("[green]✓ Cleanup complete[/green]")


@app.command()
def version(
    env: Environment = typer.Option(Environment.LOCAL, "--env", "-e"),
):
    """📦 Show image versions."""
    run_compose(env, ["images"])


# ─── Info Command ───

@app.command()
def info():
    """ℹ️ Show project information and available commands."""
    panel = Panel.fit(
        "[bold cyan]LBVD Stack Manager[/bold cyan]\n\n"
        "[dim]Manages nginx, Docker, MySQL/MariaDB, Redis, FastAPI[/dim]\n\n"
        "[bold]Environments:[/bold]\n"
        "  [green]local[/green]  — Development (MySQL, Redis, Nginx, FastAPI)\n"
        "  [blue]prod[/blue]   — Production (MariaDB, Redis, Caddy, FastAPI)\n\n"
        "[bold]Quick Start:[/bold]\n"
        "  [cyan]lbvd init-local[/cyan]        # Create local .env\n"
        "  [cyan]lbvd up[/cyan]                # Start local stack\n"
        "  [cyan]lbvd logs[/cyan]              # View logs\n"
        "  [cyan]lbvd status[/cyan]            # Check service health\n\n"
        "[bold]Production:[/bold]\n"
        "  [cyan]lbvd init-prod --domain example.com[/cyan]\n"
        "  [cyan]lbvd up --env prod --build[/cyan]\n\n"
        "[bold]Database:[/bold]\n"
        "  [cyan]lbvd db-backup[/cyan]         # Backup database\n"
        "  [cyan]lbvd db-restore backup.sql.gz[/cyan]  # Restore\n"
        "  [cyan]lbvd db-shell[/cyan]          # Open DB shell\n\n"
        "[bold]Other:[/bold]\n"
        "  [cyan]lbvd shell[/cyan]             # Shell into app container\n"
        "  [cyan]lbvd clean --all[/cyan]       # Full cleanup\n"
        "  [cyan]lbvd --help[/cyan]            # Show all commands",
        title="📖 LBVD CLI",
        border_style="cyan",
    )
    console.print(panel)


# ─── Entry Point ───
if __name__ == "__main__":
    app()