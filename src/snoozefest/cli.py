from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from .config import Config


def _friendly_local(dt: datetime, tz_name: str) -> str:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


@click.group()
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to config JSON file.",
)
@click.pass_context
def main(ctx: click.Context, config: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config.load(config)


# ------------------------------------------------------------------ run

@main.command("run")
@click.option("--log-level", default="INFO", show_default=True,
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False))
@click.pass_context
def cmd_run(ctx: click.Context, log_level: str) -> None:
    """Start the alarm daemon (blocking)."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    from .daemon import Daemon
    Daemon(ctx.obj["config"]).run()


# ------------------------------------------------------------------ add-oneoff

@main.command("add-oneoff")
@click.option("--time", "time_str", required=True,
              help="Local time HH:MM (or HH:MM:SS), e.g. 07:30")
@click.option("--label", default="Alarm", show_default=True)
@click.pass_context
def cmd_add_oneoff(ctx: click.Context, time_str: str, label: str) -> None:
    """Add a one-off alarm to the data file."""
    from zoneinfo import ZoneInfo
    from .scheduler import Scheduler
    from .store import Store

    config: Config = ctx.obj["config"]
    tz = ZoneInfo(config.timezone)

    store = Store(config.data_file)
    scheduler = Scheduler(
        store=store,
        tz=tz,
        on_alarm_triggered=lambda *_: None,
        on_timer_finished=lambda *_: None,
        on_state_changed=lambda: None,
    )
    alarm = scheduler.add_oneoff_time(time_str, label)
    click.echo(f"Added non-recurring alarm {alarm.id}: {label!r} at {alarm.time}")


# ------------------------------------------------------------------ add-recurring

@main.command("add-recurring")
@click.option("--time", "time_str", required=True,
              help="Local time HH:MM, e.g. 07:00")
@click.option("--weekdays", "weekdays_str", required=True,
              help="Comma-separated weekday numbers (0=Mon … 6=Sun)")
@click.option("--label", default="Alarm", show_default=True)
@click.pass_context
def cmd_add_recurring(ctx: click.Context, time_str: str, weekdays_str: str, label: str) -> None:
    """Add a recurring alarm to the data file."""
    from zoneinfo import ZoneInfo
    from .scheduler import Scheduler
    from .store import Store

    weekdays = [int(d.strip()) for d in weekdays_str.split(",")]
    if not all(0 <= d <= 6 for d in weekdays):
        raise click.BadParameter("Weekdays must be integers 0-6")

    config: Config = ctx.obj["config"]
    tz = ZoneInfo(config.timezone)
    store = Store(config.data_file)
    scheduler = Scheduler(
        store=store,
        tz=tz,
        on_alarm_triggered=lambda *_: None,
        on_timer_finished=lambda *_: None,
        on_state_changed=lambda: None,
    )
    alarm = scheduler.add_recurring(time_str, weekdays, label)
    days_str = ",".join(str(d) for d in weekdays)
    click.echo(f"Added recurring alarm {alarm.id}: {label!r} at {time_str} on days [{days_str}]")


# ------------------------------------------------------------------ list-alarms

@main.command("list-alarms")
@click.pass_context
def cmd_list_alarms(ctx: click.Context) -> None:
    """List all alarms in the data file."""
    from .store import Store

    config: Config = ctx.obj["config"]
    store = Store(config.data_file)
    state = store.state

    if not state.alarms:
        click.echo("No alarms configured.")
        return

    for a in state.alarms:
        status = "enabled" if a.enabled else "disabled"
        days = ",".join(str(d) for d in a.weekdays)
        kind = "recurring" if a.recurring else "oneoff"
        click.echo(f"[{kind}] {a.id}  {a.label!r}  {a.time}  days=[{days}]  [{status}]")


# ------------------------------------------------------------------ show-next

@main.command("show-next")
@click.pass_context
def cmd_show_next(ctx: click.Context) -> None:
    """Show the next scheduled alarm."""
    from zoneinfo import ZoneInfo
    from .scheduler import Scheduler
    from .store import Store

    config: Config = ctx.obj["config"]
    tz = ZoneInfo(config.timezone)
    store = Store(config.data_file)
    scheduler = Scheduler(
        store=store,
        tz=tz,
        on_alarm_triggered=lambda *_: None,
        on_timer_finished=lambda *_: None,
        on_state_changed=lambda: None,
    )

    nxt = scheduler.next_alarm()
    if nxt is None:
        click.echo("No upcoming alarms.")
    else:
        click.echo(
            f"Next alarm: {nxt['label']!r} ({nxt['kind']}) at {nxt['time_friendly']} "
            f"({nxt['time_local']})"
        )
