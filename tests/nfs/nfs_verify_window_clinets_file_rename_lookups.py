from threading import Thread
from time import sleep

from nfs_operations import cleanup_cluster, setup_nfs_cluster

from cli.exceptions import ConfigError
from cli.utilities.utils import create_files, perform_lookups, rename_file
from cli.utilities.windows_utils import setup_windows_clients
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kw):
    """Verify mount the NFS volume via V3 on both windows and linux client and run IO's in parallel
    Args:
        **kw: Key/value pairs of configuration information to be used in the test.
    """
    config = kw.get("config")
    # nfs cluster details
    nfs_nodes = ceph_cluster.get_nodes("nfs")
    no_servers = int(config.get("servers", "1"))
    if no_servers > len(nfs_nodes):
        raise ConfigError("The test requires more servers than available")
    servers = nfs_nodes[:no_servers]
    port = config.get("port", "2049")
    version = config.get("nfs_version", "3")
    fs_name = "cephfs"
    nfs_name = "cephfs-nfs"
    nfs_export = "/export"
    nfs_mount = "/mnt/nfs"
    window_nfs_mount = "Z:"
    fs = "cephfs"
    nfs_server_name = [nfs_node.hostname for nfs_node in servers]
    ha = bool(config.get("ha", False))
    vip = config.get("vip", None)

    # Linux clients
    linux_clients = ceph_cluster.get_nodes("client")
    no_linux_clients = int(config.get("linux_clients", "1"))
    linux_clients = linux_clients[:no_linux_clients]
    if no_linux_clients > len(linux_clients):
        raise ConfigError("The test requires more linux clients than available")

    # Windows clients
    for windows_client_obj in setup_windows_clients(config.get("windows_clients")):
        ceph_cluster.node_list.append(windows_client_obj)
    windows_clients = ceph_cluster.get_nodes("windows_client")

    try:
        # Setup nfs cluster
        setup_nfs_cluster(
            linux_clients,
            nfs_server_name,
            port,
            version,
            nfs_name,
            nfs_mount,
            fs_name,
            nfs_export,
            fs,
            ha,
            vip,
            ceph_cluster=ceph_cluster,
        )

        # Mount NFS-Ganesha V3 to window clients
        for windows_client in windows_clients:
            cmd = f"mount {nfs_nodes[0].ip_address}:/export_0 {window_nfs_mount}"
            windows_client.exec_command(cmd=cmd)
            sleep(3)

        # Create files from window client1
        create_files(windows_clients[0], window_nfs_mount, 10, True)
        sleep(3)

        # Run parallel rename files for window client1 and lookups from window client2
        rename = Thread(
            target=rename_file,
            args=(windows_clients[0], window_nfs_mount, 10, True),
        )

        lookups = Thread(
            target=perform_lookups,
            args=(windows_clients[1], window_nfs_mount, 10, True),
        )
        rename.start()
        lookups.start()

        rename.join()
        lookups.join()
    except Exception as e:
        log.error(f"Failed to setup nfs-ganesha cluster {e}")
        # Cleanup
        for windows_client in windows_clients:
            cmd = f"del /q /f {window_nfs_mount}\\*.*"
            windows_client.exec_command(cmd=cmd)
            cmd = f"umount {window_nfs_mount}"
            windows_client.exec_command(cmd=cmd)
        cleanup_cluster(linux_clients, nfs_mount, nfs_name, nfs_export)
        return 1
    finally:
        # Cleanup
        for windows_client in windows_clients:
            cmd = f"del /q /f {window_nfs_mount}\\*.*"
            windows_client.exec_command(cmd=cmd)
            cmd = f"umount {window_nfs_mount}"
            windows_client.exec_command(cmd=cmd)
        cleanup_cluster(linux_clients, nfs_mount, nfs_name, nfs_export)
    return 0
