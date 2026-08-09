import json
import os

from dotenv import load_dotenv
from tplinkrouterc6u import TplinkC5400XRouter

JSON_PATH = "network.json"


# Helpers
def seconds_to_readable_format(seconds: int) -> str:
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def bytes_to_readable_format(bytes_amount: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_amount < 1024:
            return f"{bytes_amount:.2f} {unit}"
        bytes_amount /= 1024
    return f"{bytes_amount:.2f} PB"


def down_up_speed_to_readable_format(data_downloading: int, data_uploading: int) -> str:
    data_downloading *= 8
    data_uploading *= 8
    max_speed = max(data_downloading, data_uploading)

    if max_speed < 1_000:
        down_str, up_str, unit = f"{data_downloading}", f"{data_uploading}", "bps"
    elif max_speed < 1_000_000:
        down_str = f"{data_downloading / 1_000:.2f}"
        up_str = f"{data_uploading / 1_000:.2f}"
        unit = "Kbps"
    else:
        down_str = f"{data_downloading / 1_000_000:.2f}"
        up_str = f"{data_uploading / 1_000_000:.2f}"
        unit = "Mbps"

    return f"{down_str}/{up_str} {unit}"


def link_speed_to_readable_format(link_speed_down: int, link_speed_up: int) -> str:
    max_speed = max(link_speed_down, link_speed_up)

    if max_speed < 1_000:
        down_str, up_str, unit = f"{link_speed_down}", f"{link_speed_up}", "Kbps"
    elif max_speed < 1_000_000:
        down_str = f"{link_speed_down / 1_000:.2f}"
        up_str = f"{link_speed_up / 1_000:.2f}"
        unit = "Mbps"
    else:
        down_str = f"{link_speed_down / 1_000_000:.2f}"
        up_str = f"{link_speed_up / 1_000_000:.2f}"
        unit = "Gbps"

    return f"{down_str}/{up_str} {unit}"


def get_client_names(data) -> list[str]:
    client_names = []

    if "mesh_nclient_list" in data:
        client_names.extend(
            [c.get("name") for c in data["mesh_nclient_list"] if "name" in c]
        )

    mesh_sclient = data.get("mesh_sclient_list", [])
    if isinstance(mesh_sclient, dict):
        for c in mesh_sclient.values():
            if isinstance(c, dict) and "name" in c:
                client_names.append(c["name"])
    elif isinstance(mesh_sclient, list):
        client_names.extend([c.get("name") for c in mesh_sclient if "name" in c])

    return client_names


# Fetch functions
def _make_client() -> TplinkC5400XRouter:
    """Create and return an authorised router client."""
    load_dotenv()
    password = str(os.getenv("ROUTER_PASSWORD"))
    client = TplinkC5400XRouter("http://192.168.0.1", password)
    client.authorize()
    return client


def fetch_status(client: TplinkC5400XRouter) -> dict:
    """Fetch firmware + system status."""
    firmware = client.get_firmware()
    status = client.get_status()
    return {
        "firmware": firmware.__dict__,
        "status": {
            "uptime_readable": seconds_to_readable_format(status.wan_ipv4_uptime),
            "uptime_seconds": status.wan_ipv4_uptime,
            "cpu_usage": round(status.cpu_usage * 100, 2),
            "memory_usage": round(status.mem_usage * 100, 2),
            "clients_total": status.clients_total,
            "wired_total": status.wired_total,
            "wifi_total": status.wifi_clients_total,
        },
    }


def fetch_mesh(client: TplinkC5400XRouter) -> list[dict]:
    """Fetch mesh device list (may raise ClientError on router timeout)."""
    mesh_data = client.request(
        "admin/easymesh_network?form=get_mesh_device_list_all&operation=read",
        "operation=read",
    )
    mesh_output = []
    for device in mesh_data:
        mac = device.get("mac", "N/A")
        name = device.get("device_name", device.get("name", "Unknown"))

        client_names = ""
        if mac != "N/A":
            mesh_clients = client.request(
                f"admin/easymesh_network?form=mesh_sclient_detail&operation=read&mac={mac}",
                "operation=read",
            )
            client_names = ", ".join(get_client_names(mesh_clients))

        location = device.get("location", "")
        if len(location) <= 1:
            location = "Not set"

        mesh_output.append(
            {
                "device_name": name,
                "device_type": device.get("device_type", "Unknown"),
                "ip": device.get("ip", "N/A"),
                "mac": mac,
                "connected_clients": device.get("client_num", 0),
                "location": location,
                "signal_strength": device.get("signal_strength", 0),
                "client_names": client_names,
            }
        )

    return mesh_output


def fetch_devices(client: TplinkC5400XRouter) -> list[dict]:
    """Fetch per-device traffic via the smart network accelerator endpoint."""
    smart_data = client.request(
        "admin/smart_network?form=game_accelerator&operation=loadDevice",
        "operation=loadDevice",
    )
    smart_output = []
    for device in smart_data:
        data_downloading = device.get("downloadSpeed", 0)
        data_uploading = device.get("uploadSpeed", 0)
        link_speed_down = device.get("txrate", 0)
        link_speed_up = device.get("rxrate", 0)
        signal = device.get("signal", " - ")

        link_text = (
            link_speed_to_readable_format(link_speed_down, link_speed_up)
            if signal != " - "
            else "Wired"
        )

        smart_output.append(
            {
                "device_name": device.get("deviceName", "Unknown"),
                "device_type": device.get("deviceType", "Unknown"),
                "ip": device.get("ip", "N/A"),
                "data_transferred": device.get("trafficUsage", 0),
                "data_transferred_readable": bytes_to_readable_format(
                    device.get("trafficUsage", 0)
                ),
                "data_transfering_readable": down_up_speed_to_readable_format(
                    data_downloading, data_uploading
                ),
                "data_downloading": data_downloading,
                "data_uploading": data_uploading,
                "link_speed_readable": link_text,
                "link_speed_down": link_speed_down,
                "link_speed_up": link_speed_up,
                "signal": device.get("signal", 0),
            }
        )

    return smart_output


# Entry point for poller.py
def get_stats_json():
    """
    Fetch all router data and write it to JSON_PATH.

    Each section (status, mesh, devices) is fetched independently so a
    failure in one (e.g. mesh timeout) does not discard the others.
    The previous JSON is loaded first so partial failures leave the last
    good data for that section intact.
    """

    # Seed output from whatever is already on disk so partial failures
    # preserve the last good data per section.
    try:
        with open(JSON_PATH) as f:
            output = json.load(f)
    except FileNotFoundError, json.JSONDecodeError:
        output = {}

    errors = {}
    client = None
    try:
        try:
            client = _make_client()
        except Exception as e:
            errors["authorization"] = str(e)

        if client:
            try:
                output.update(fetch_status(client))
            except Exception as e:
                errors["status"] = str(e)

            try:
                output["mesh_data"] = fetch_mesh(client)
            except Exception as e:
                errors["mesh"] = str(e)

            try:
                output["devices"] = fetch_devices(client)
            except Exception as e:
                errors["devices"] = str(e)
    finally:
        if client:
            client.logout()

    output["errors"] = errors  # empty dict == all good

    with open(JSON_PATH, "w") as f:
        json.dump(output, f, indent=4)

    if errors:
        print(f"[getrouterstats] errors: {errors}")
    if "authorization" in errors:
        raise RuntimeError(f"Authorization failed: {errors['authorization']}")
