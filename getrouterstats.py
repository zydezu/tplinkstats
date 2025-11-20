import os
from dotenv import load_dotenv
from logging import Logger
from tplinkrouterc6u import (
    TplinkRouterProvider,
    TplinkRouter,
    TplinkC1200Router,
    TplinkC5400XRouter,
    TPLinkMRClient, # Class for MR series routers which supports old firmwares with AES cipher CBC mode
    TPLinkMRClientGCM, # Class for MR series routers which supports AES cipher GCM mode
    TPLinkMR200Client,
    TPLinkVRClient,
    TPLinkEXClient, # Class for EX series routers which supports old firmwares with AES cipher CBC mode
    TPLinkEXClientGCM, # Class for EX series routers which supports AES cipher GCM mode
    TPLinkXDRClient,
    TPLinkDecoClient,
    TplinkC80Router,
    TplinkWDRRouter,
    TplinkRE330Router,
    Connection
)

os.system("")
class bcolors:
    OKBLUE = '\033[94m'
    WARNING = '\033[93m'
    LINE = '\033[90m'
    ENDC = '\033[0m'

SEPARATOR = "-"

load_dotenv()
PASSWORD = os.getenv('ROUTER_PASSWORD')

client = TplinkC5400XRouter('http://192.168.0.1', PASSWORD)

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
    return ' '.join(parts)

def bytes_to_readable_format(bytes_amount: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_amount < 1024:
            return f"{bytes_amount:.2f} {unit}"
        bytes_amount /= 1024
    return f"{bytes_amount:.2f} PB"

def down_up_speed_to_readable_format(data_downloading: int, data_uploading: int) -> str:
    data_downloading *= 8
    data_uploading *= 8
    max_speed = max(data_downloading, data_uploading)

    if max_speed < 1_000:
        down_str = f"{data_downloading}"
        up_str = f"{data_uploading}"
        unit = "bps"
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
        down_str = f"{link_speed_down}"
        up_str = f"{link_speed_up}"
        unit = "Kbps"
    elif max_speed < 1_000_000:
        down_str = f"{link_speed_down / 1_000:.2f}"
        up_str = f"{link_speed_up / 1_000:.2f}"
        unit = "Mbps"
    else:
        down_str = f"{link_speed_down / 1_000_000:.2f}"
        up_str = f"{link_speed_up / 1_000_000:.2f}"
        unit = "Gbps"

    return f"{down_str}/{up_str} {unit}"

def get_client_names(data):
    client_names = []

    if 'mesh_nclient_list' in data:
        client_names.extend([c.get('name') for c in data['mesh_nclient_list'] if 'name' in c])

    if 'mesh_sclient_list' in data and isinstance(data['mesh_sclient_list'], dict):
        for c in data['mesh_sclient_list'].values():
            if isinstance(c, dict) and 'name' in c:
                client_names.append(c['name'])
    elif 'mesh_sclient_list' in data and isinstance(data['mesh_sclient_list'], list):
        client_names.extend([c.get('name') for c in data['mesh_sclient_list'] if 'name' in c])

    return client_names

try:
    client.authorize()
    firmware = client.get_firmware()
    status = client.get_status()

    print(f"{bcolors.OKBLUE}Uptime:{bcolors.ENDC} {bcolors.WARNING}{seconds_to_readable_format(status.wan_ipv4_uptime)}{bcolors.ENDC} | {bcolors.OKBLUE}CPU:{bcolors.ENDC} {bcolors.WARNING}{status.cpu_usage * 100}%{bcolors.ENDC} | {bcolors.OKBLUE}RAM:{bcolors.ENDC} {bcolors.WARNING}{status.mem_usage * 100}%{bcolors.ENDC}")
    print(f"Devices connected: {bcolors.WARNING}{status.clients_total}{bcolors.ENDC} ({bcolors.WARNING}{status.wired_total}{bcolors.ENDC} wired/{bcolors.WARNING}{status.wifi_clients_total}{bcolors.ENDC} wifi)\n")

    # Get Address reservations, sort by ipaddr
    # reservations = router.get_ipv4_reservations()
    # reservations.sort(key=lambda a: a.ipaddr)
    # for res in reservations:
    #     print(f"{res.macaddr} {res.ipaddr:16s} {res.hostname:36} {'Permanent':12}")

    # Get DHCP leases, sort by ipaddr
    # leases = router.get_ipv4_dhcp_leases()
    # leases.sort(key=lambda a: a.ipaddr)
    # for lease in leases:
    #     # print(f"{lease.signal} {lease.ipaddr:16s} {lease.hostname:36} {lease.down_speed} {lease.up_speed}")
    #     print(f"{lease.macaddr} {lease.ipaddr:16s} {lease.hostname:36} {lease.lease_time:12}")

    print(f"{'Device Name':20} "f"{'Type':16} "f"{'IP Address':16} "f"{'Clients':7} "f"{'Location':20} "f"{'Signal':6} "f"{'Devices':80}")
    print(f"{SEPARATOR*20} "f"{SEPARATOR*16} "f"{SEPARATOR*16} "f"{SEPARATOR*7} "f"{SEPARATOR*20} "f"{SEPARATOR*6} "f"{SEPARATOR*80}")

    mesh_data = client.request('admin/easymesh_network?form=get_mesh_device_list_all&operation=read', 'operation=read')
    for device in mesh_data:
        device_name = device.get('name', 'Unknown')
        device_type = device.get('device_type', 'Unknown')
        connected_devices = device.get('client_num', 0)
        ip = device.get('ip', 'N/A')
        mac = device.get('mac', 'N/A')
        devices_string = ""
        if (mac != 'N/A'): 
            mesh_clients = client.request(f'admin/easymesh_network?form=mesh_sclient_detail&operation=read&mac={mac}', 'operation=read')
            devices_string = ", ".join(get_client_names(mesh_clients))
        location = device.get('location', '').capitalize()
        if len(location) <= 1: location = 'Not set'
        signal_strength = device.get('signal_strength', ' - ')
        if (signal_strength != ' - '): signal_strength = f"{signal_strength}/5"

        print(f"{device_name:20} "f"{device_type:16} "f"{ip:16} "f"{connected_devices:<7} "f"{location:<20} "f"{signal_strength:<6} "f"{devices_string:<80}")

    print("")
    ethernet_data = client.request('admin/status?form=router&operation=read', 'operation=read')
    smart_data = client.request('admin/smart_network?form=game_accelerator&operation=loadDevice', 'operation=loadDevice')

    print(f"{'Device Name':20} {'Type':16} {'IP Address':16} {'Transfered':<12} {'Download/Upload':<26} {'Signal':6} {'Link speed':20}")
    print(f"{SEPARATOR*20} {SEPARATOR*16} {SEPARATOR*16} {SEPARATOR*12} {SEPARATOR*26} {SEPARATOR*6} {SEPARATOR*20}")

    for device in smart_data:
        device_name = device.get('deviceName', 'Unknown')
        device_type = device.get('deviceType', 'Unknown')
        ip = device.get('ip', 'N/A')
        data_transfered = bytes_to_readable_format(device.get('trafficUsage', 0))
        data_downloading = device.get('downloadSpeed', 0)
        data_uploading = device.get('uploadSpeed', 0)
        link_speed_down = device.get('rxrate', 0)
        link_speed_up = device.get('txrate', 0)
        signal = device.get('signal', ' - ')

        down_up_text = down_up_speed_to_readable_format(data_downloading, data_uploading)
        link_text = link_speed_to_readable_format(link_speed_down, link_speed_up) if signal != ' - ' else 'Wired'
        print(f"{device_name:20} {device_type:16} {ip:16} {data_transfered:<12} {down_up_text:<26} {signal:<6} {link_text:<20}")

    print("")
finally:
    client.logout()  # always logout as TP-Link Web Interface only supports upto 1 user logged