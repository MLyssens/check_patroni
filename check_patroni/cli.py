import click
from configparser import ConfigParser
import nagiosplugin
import re
from typing import List

from . import __version__
from .cluster import (
    ClusterConfigHasChanged,
    ClusterConfigHasChangedSummary,
    ClusterHasLeader,
    ClusterHasLeaderSummary,
    ClusterHasReplica,
    ClusterNodeCount,
    ClusterIsInMaintenance,
)
from .node import (
    NodeIsAlive,
    NodeIsAliveSummary,
    NodeIsPendingRestart,
    NodeIsPendingRestartSummary,
    NodeIsPrimary,
    NodeIsPrimarySummary,
    NodeIsReplica,
    NodeIsReplicaSummary,
    NodePatroniVersion,
    NodePatroniVersionSummary,
    NodeTLHasChanged,
    NodeTLHasChangedSummary,
)
from .types import ConnectionInfo


def print_version(ctx: click.Context, param: str, value: str) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"Version {__version__}")
    ctx.exit()


DEFAULT_CFG = "config.ini"


def configure(ctx: click.Context, param: str, filename: str) -> None:
    """Use a config file for the parameters
    stolen from https://jwodder.github.io/kbits/posts/click-config/
    """
    # FIXME should use click-configfile / click-config-file ?
    cfg = ConfigParser()
    cfg.read(filename)
    ctx.default_map = {}
    for sect in cfg.sections():
        command_path = sect.split(".")
        if command_path[0] != "options":
            continue
        defaults = ctx.default_map
        for cmdname in command_path[1:]:
            defaults = defaults.setdefault(cmdname, {})
        defaults.update(cfg[sect])
        try:
            # endpoints is an array of addresses separated by ,
            if isinstance(defaults["endpoints"], str):
                defaults["endpoints"] = re.split(r"\s*,\s*", defaults["endpoints"])
        except KeyError:
            pass


@click.group()
@click.option(
    "--config",
    type=click.Path(dir_okay=False),
    default=DEFAULT_CFG,
    callback=configure,
    is_eager=True,
    expose_value=False,
    help="Read option defaults from the specified INI file",
    show_default=True,
)
@click.option(
    "-e",
    "--endpoints",
    "endpoints",
    type=str,
    multiple=True,
    default=["http://127.0.0.1:8008"],
    help="API endpoint. Can be specified multiple times.",
)
@click.option(
    "--cert_file",
    "cert_file",
    type=str,
    help="File with the client certificate.",
)
@click.option(
    "--key_file",
    "key_file",
    type=str,
    help="File with the client key.",
)
@click.option(
    "--ca_file",
    "ca_file",
    type=str,
    help="The CA certificate.",
)
@click.option(
    "-v",
    "--verbose",
    "verbose",
    count=True,
    help="Increase verbosity -v (info)/-vv (warning)/-vvv (debug)",
)
@click.option(
    "--version", is_flag=True, callback=print_version, expose_value=False, is_eager=True
)
@click.option(
    "--timeout",
    "timeout",
    default=2,
    type=int,
    help="Timeout in seconds for the API queries (0 to disable)",
)
@click.pass_context
@nagiosplugin.guarded
def main(
    ctx: click.Context,
    endpoints: List[str],
    cert_file: str,
    key_file: str,
    ca_file: str,
    verbose: bool,
    timeout: int,
) -> None:
    """Nagios plugin for patroni."""
    ctx.obj = ConnectionInfo(endpoints, cert_file, key_file, ca_file)

    # FIXME Not all "is/has" services have the same return code for ok. Check if it's ok


@main.command(name="cluster_node_count")  # required otherwise _ are converted to -
@click.option(
    "-w",
    "--warning",
    "warning",
    type=str,
    help="Warning threshold for the number of nodes.",
)
@click.option(
    "-c",
    "--critical",
    "critical",
    type=str,
    help="Critical threshold for the nimber of nodes.",
)
@click.option(
    "--running-warning",
    "running_warning",
    type=str,
    help="Warning threshold for the number of running nodes.",
)
@click.option(
    "--running-critical",
    "running_critical",
    type=str,
    help="Critical threshold for the nimber of running nodes.",
)
@click.pass_context
@nagiosplugin.guarded
def cluster_node_count(
    ctx: click.Context,
    warning: str,
    critical: str,
    running_warning: str,
    running_critical: str,
) -> None:
    """Count the number of nodes in the cluster.

    \b
    Check:
    * Compares the number of nodes against the normal and running node warning and critical thresholds.
    * `OK`!  If they are not provided.

    \b
    Perfdata:
    * `members`: the member count.
    * all the roles of the nodes in the cluster with their number.
    * all the statuses of the nodes in the cluster with their number.
    """
    check = nagiosplugin.Check()
    check.add(
        ClusterNodeCount(ctx.obj),
        nagiosplugin.ScalarContext(
            "members",
            warning,
            critical,
        ),
        nagiosplugin.ScalarContext(
            "state_running",
            running_warning,
            running_critical,
        ),
        nagiosplugin.ScalarContext("members_roles"),
        nagiosplugin.ScalarContext("members_statuses"),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="cluster_has_leader")
@click.pass_context
@nagiosplugin.guarded
def cluster_has_leader(ctx: click.Context) -> None:
    """Check if the cluster has a leader.

    \b
    Check:
    * `OK`: if there is a leader node.
    * `CRITICAL`: otherwise

    Perfdata : `has_leader` is 1 if there is a leader node, 0 otherwise
    """
    # FIXME: Manage primary or standby leader in the same place ?
    check = nagiosplugin.Check()
    check.add(
        ClusterHasLeader(ctx.obj),
        nagiosplugin.ScalarContext("has_leader", None, "@0:0"),
        ClusterHasLeaderSummary(),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="cluster_has_replica")
@click.option(
    "-w",
    "--warning",
    "warning",
    type=str,
    help="Warning threshold for the number of nodes.",
)
@click.option(
    "-c",
    "--critical",
    "critical",
    type=str,
    help="Critical threshold for the number of replica nodes.",
)
@click.option(
    "--lag-warning", "lag_warning", type=str, help="Warning threshold for the lag."
)
# FIWME how do we manage maximum_lag_on_failover without doing many api calls
@click.option(
    "--lag-critical", "lag_critical", type=str, help="Critical threshold for the lag."
)
@click.pass_context
@nagiosplugin.guarded
def cluster_has_replica(
    ctx: click.Context, warning: str, critical: str, lag_warning: str, lag_critical: str
) -> None:
    """Check if the cluster has replicas and their lag.

    \b
    Check:
    * `OK`: if the replica count and their lag are compatible with the replica count and lag thresholds.
    * `WARNING` / `CRITICAL`: otherwise

    \b
    Perfdata :
    * replica count
    * the lag of each replica labelled with  "member name"_lag
    """
    # FIXME the idea here would be to make sur we have a replica.
    #       lag should be check to prune invalid replicas
    check = nagiosplugin.Check()
    check.add(
        ClusterHasReplica(ctx.obj),
        nagiosplugin.ScalarContext(
            "replica_count",
            warning,
            critical,
        ),
        nagiosplugin.ScalarContext(
            "replica_lag",
            lag_warning,
            lag_critical,
        ),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="cluster_config_has_changed")
@click.option("--hash", "config_hash", type=str, help="A hash to compare with.")
@click.option(
    "-s",
    "--state-file",
    "state_file",
    type=str,
    help="A state file to store the tl number into.",
)
@click.pass_context
@nagiosplugin.guarded
def cluster_config_has_changed(
    ctx: click.Context, config_hash: str, state_file: str
) -> None:
    """Check if the hash of the configuration has changed.

    Note: either a hash or a state file must be provided for this service to work.

    \b
    Check:
    * `OK`: The hash didn't change
    * `CRITICAL`: The hash of the configuration has changed compared to the input (`--hash`) or last time (`--state_file`)

    \b
    Perfdata :
    * `is_configuration_changed` is 1 if the configuration has changed
    """
    # FIXME hash in perfdata ?
    if (config_hash is None and state_file is None) or (
        config_hash is not None and state_file is not None
    ):
        raise click.UsageError(
            "Either --hash or --state-file should be provided for this service", ctx
        )

    check = nagiosplugin.Check()
    check.add(
        ClusterConfigHasChanged(ctx.obj, config_hash, state_file),
        nagiosplugin.ScalarContext("is_configuration_changed", None, "@1:1"),
        ClusterConfigHasChangedSummary(),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="cluster_is_in_maintenance")
@click.pass_context
@nagiosplugin.guarded
def cluster_is_in_maintenance(ctx: click.Context) -> None:
    """Check if the cluster is in maintenance mode ie paused.

    \b
    Check:
    * `OK`: If the cluster is in maintenance mode.
    * `CRITICAL`: otherwise.

    \b
    Perfdata :
    * `is_in_maintenance` is 1 the cluster is in maintenance mode,  0 otherwise
    """
    check = nagiosplugin.Check()
    check.add(
        ClusterIsInMaintenance(ctx.obj),
        nagiosplugin.ScalarContext("is_in_maintenance", None, "0:0"),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_is_primary")
@click.pass_context
@nagiosplugin.guarded
def node_is_primary(ctx: click.Context) -> None:
    """Check if the node is the primary with the leader lock.

    \b
    Check:
    * `OK`: if the node is a primary with the leader lock.
    * `CRITICAL:` otherwise

    Perfdata: `is_primary` is 1 if the node is a primary with the leader lock, 0 otherwise.
    """
    check = nagiosplugin.Check()
    check.add(
        NodeIsPrimary(ctx.obj),
        nagiosplugin.ScalarContext("is_primary", None, "@0:0"),
        NodeIsPrimarySummary(),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_is_replica")
@click.option("--lag", "lag", type=str, help="maximum allowed lag")
@click.pass_context
@nagiosplugin.guarded
def node_is_replica(ctx: click.Context, lag: str) -> None:
    """Check if the node is a running replica with no noloadbalance tag.

    \b
    Check:
    * `OK`: if the node is a running replica with noloadbalance tag and the lag is under the maximum threshold.
    * `CRITICAL`:  otherwise

    Perfdata : `is_replica` is 1 if the node is a running replica with noloadbalance tag and the lag is under the maximum threshold, 0 otherwise.
    """
    # FIXME add a lag check ??
    check = nagiosplugin.Check()
    check.add(
        NodeIsReplica(ctx.obj, lag),
        nagiosplugin.ScalarContext("is_replica", None, "@0:0"),
        NodeIsReplicaSummary(lag),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_is_pending_restart")
@click.pass_context
@nagiosplugin.guarded
def node_is_pending_restart(ctx: click.Context) -> None:
    """Check if the node is in pending restart state.

    This situation can arise if the configuration has been modified but
    requiers a restart of PostgreSQL to take effect.

    \b
    Check:
    * `OK`: if the node has pending restart tag.
    * `CRITICAL`: otherwise

    Perfdata: `is_pending_restart` is 1 if the node has pending restart tag, 0 otherwise.
    """
    check = nagiosplugin.Check()
    check.add(
        NodeIsPendingRestart(ctx.obj),
        nagiosplugin.ScalarContext("is_pending_restart", None, "@1:1"),
        NodeIsPendingRestartSummary(),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_tl_has_changed")
@click.option(
    "--timeline", "timeline", type=str, help="A timeline number to compare with."
)
@click.option(
    "-s",
    "--state-file",
    "state_file",
    type=str,
    help="A state file to store the last tl number into.",
)
@click.pass_context
@nagiosplugin.guarded
def node_tl_has_changed(ctx: click.Context, timeline: str, state_file: str) -> None:
    """Check if the timeline has changed.

    Note: either a timeline or a state file must be provided for this service to work.

    \b
    Check:
    * `OK`: The timeline is the same as last time (`--state_file`) or the inputed timeline (`--timeline`)
    * `CRITICAL`: The tl is not the same.

    \b
    Perfdata :
    * `is_configuration_changed` is 1 if the configuration has changed, 0 otherwise
    """
    if (timeline is None and state_file is None) or (
        timeline is not None and state_file is not None
    ):
        raise click.UsageError(
            "Either --timeline or --state-file should be provided for this service", ctx
        )

    check = nagiosplugin.Check()
    check.add(
        NodeTLHasChanged(ctx.obj, timeline, state_file),
        nagiosplugin.ScalarContext("is_timeline_changed", None, "@1:1"),
        nagiosplugin.ScalarContext("timeline"),
        NodeTLHasChangedSummary(timeline),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_patroni_version")
@click.option(
    "--patroni-version",
    "patroni_version",
    type=str,
    help="Patroni version to compare to",
    required=True,
)
@click.pass_context
@nagiosplugin.guarded
def node_patroni_version(ctx: click.Context, patroni_version: str) -> None:
    """Check if the version is equal to the input

    \b
    Check:
    * `OK`: The version is the same as the input `--patroni-version`
    * `CRITICAL`: otherwise.

    \b
    Perfdata :
    * `is_version_ok` is 1 if version is ok, 0 otherwise
    """
    # TODO the version cannot be written in perfdata find something else ?
    check = nagiosplugin.Check()
    check.add(
        NodePatroniVersion(ctx.obj, patroni_version),
        nagiosplugin.ScalarContext("is_version_ok", None, "@0:0"),
        nagiosplugin.ScalarContext("patroni_version"),
        NodePatroniVersionSummary(patroni_version),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )


@main.command(name="node_is_alive")
@click.pass_context
@nagiosplugin.guarded
def node_is_alive(ctx: click.Context) -> None:
    """Check if the node is alive ie patroni is running.

    \b
    Check:
    * `OK`: If patroni is running.
    * `CRITICAL`: otherwise.

    \b
    Perfdata :
    * `is_running` is 1 if patroni is running, 0 otherwise
    """
    check = nagiosplugin.Check()
    check.add(
        NodeIsAlive(ctx.obj),
        nagiosplugin.ScalarContext("is_alive", None, "@0:0"),
        NodeIsAliveSummary(),
    )
    check.main(
        verbose=ctx.parent.params["verbose"], timeout=ctx.parent.params["timeout"]
    )
