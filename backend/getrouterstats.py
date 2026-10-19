import json
import os
import re

from dotenv import load_dotenv
from requests import post
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout
from tplinkrouterc6u import TplinkC5400XRouter
from tplinkrouterc6u.common.encryption import EncryptionWrapper

JSON_PATH = os.path.join("data", "network.json")
ROUTER_HOST = "http://192.168.0.1"


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


def normalize_mac(mac) -> str:
    """Strip separators from a MAC so the router's two spellings compare equal."""
    return re.sub(r"[^0-9a-fA-F]", "", str(mac or "")).upper()


# map deviceTag values the router sends for clients
KNOWN_BANDS = {"2.4GHz": "2.4 GHz", "5GHz": "5 GHz", "6GHz": "6 GHz"}


def describe_connection(device: dict) -> tuple[str, bool]:
    """Return (label, is_wired) for a device."""
    tag = str(device.get("deviceTag") or "").strip()
    if tag == "wired":
        return "Wired", True
    if tag in KNOWN_BANDS:
        return KNOWN_BANDS[tag], False
    if device.get("signal") in (None, "", " - "):
        return "Wired", True
    return "Wi-Fi", False


def get_client_entries(data) -> list[dict]:
    """Flatten a mesh node's client detail response into one tagged list."""
    clients: list[dict] = []

    for entry in data.get("mesh_nclient_list") or []:
        if isinstance(entry, dict) and entry.get("name"):
            clients.append(_client_entry(entry, wired=bool(entry.get("is_wired"))))

    sclients = data.get("mesh_sclient_list") or []
    if isinstance(sclients, dict):
        sclients = [
            {**entry, "mac": mac}
            for mac, entry in sclients.items()
            if isinstance(entry, dict)
        ]
    for entry in sclients:
        if isinstance(entry, dict) and entry.get("name"):
            clients.append(_client_entry(entry, wired=True))

    return clients


def _client_entry(entry: dict, wired: bool) -> dict:
    return {
        "name": entry.get("name", "Unknown"),
        "mac": entry.get("mac", entry.get("macaddr", "")),
        "ip": entry.get("ip", entry.get("ipaddr", "")),
        "wired": wired,
    }


# Fetch functions
def _get_encrypted_password(host: str, password: str) -> str:
    """RSA-encrypt the plaintext web password the same way the router's own
    login page does: fetch its public key, then encrypt the password with it.
    This is what the C5400X login API expects in place of the plaintext password.
    """
    response = post(
        f"{host}/cgi-bin/luci/;stok=/login?form=keys",
        params={"operation": "read"},
        timeout=10,
    )
    nn, ee = response.json()["data"]["password"]
    return EncryptionWrapper.rsa_encrypt(password, nn, ee)


def _make_client() -> TplinkC5400XRouter:
    """Create and return an authorised router client."""
    load_dotenv()
    web_password = os.getenv("WEB_PASSWORD")
    encrypted_password = _get_encrypted_password(ROUTER_HOST, web_password)
    client = TplinkC5400XRouter(ROUTER_HOST, encrypted_password)
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

        client_entries: list[dict] = []
        if mac != "N/A":
            mesh_clients = client.request(
                f"admin/easymesh_network?form=mesh_sclient_detail&operation=read&mac={mac}",
                "operation=read",
            )
            client_entries = get_client_entries(mesh_clients)

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
                "client_names": ", ".join(c["name"] for c in client_entries),
                "clients": client_entries,
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
        connection, is_wired = describe_connection(device)

        # dBm for wifi
        try:
            signal = int(device.get("signal"))
        except TypeError, ValueError:
            signal = None

        link_text = (
            "Wired"
            if is_wired
            else link_speed_to_readable_format(link_speed_down, link_speed_up)
        )

        smart_output.append(
            {
                "device_name": device.get("deviceName", "Unknown"),
                "device_type": device.get("deviceType", "Unknown"),
                "ip": device.get("ip", "N/A"),
                "mac": device.get("mac", ""),
                "connection": connection,
                "wired": is_wired,
                "is_guest": bool(device.get("isGuest")),
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
                "signal": signal,
            }
        )

    return smart_output


def link_mesh_clients(devices: list[dict], mesh: list[dict]) -> None:
    """Tag each device in-place with the mesh node it hangs off."""
    by_mac: dict[str, dict] = {}
    by_ip: dict[str, dict] = {}
    by_name: dict[str, dict] = {}

    for node in mesh:
        for client in node.get("clients", []):
            key = normalize_mac(client.get("mac"))
            if key:
                by_mac.setdefault(key, node)
            if client.get("ip"):
                by_ip.setdefault(client["ip"], node)
            name = (client.get("name") or "").strip().casefold()
            if name:
                by_name.setdefault(name, node)

    for device in devices:
        node = (
            by_mac.get(normalize_mac(device.get("mac")))
            or by_ip.get(device.get("ip"))
            or by_name.get((device.get("device_name") or "").strip().casefold())
        )
        device["mesh_name"] = node["device_name"] if node else None
        device["mesh_location"] = node["location"] if node else None


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
        except (RequestsConnectionError, Timeout) as e:
            errors["connection"] = str(e)
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

            # Needs both halves, so runs last and survives either failing
            link_mesh_clients(output.get("devices", []), output.get("mesh_data", []))
    finally:
        if client:
            client.logout()

    output["errors"] = errors  # empty dict == all good

    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(output, f, indent=4)

    if errors:
        print(f"[getrouterstats] errors: {errors}")
    if "connection" in errors:
        # Transient: router rebooting, DHCP renew, or our own network not up
        # yet at boot. Signal it as retryable so the poller keeps trying,
        # rather than treating it like a fatal auth failure and exiting.
        raise RuntimeError(f"Router unreachable: {errors['connection']}")
    if "authorization" in errors:
        raise RuntimeError(f"Authorization failed: {errors['authorization']}")
