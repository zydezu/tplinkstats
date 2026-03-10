import json
import getrouterstats
from nicegui import ui
from datetime import datetime

stats_data = {}

def load_stats():
    global stats_data
    getrouterstats.get_stats_json()
    with open("network.json", "r") as f:
        stats_data = json.load(f)

@ui.page('/')
def main_page():
    ui.dark_mode(True)

    # --- Global font ---
    ui.add_head_html("""
    <style>
    :root {
        --font-family: "Hiragino Kaku Gothic Pro", "ヒラギノ角ゴ Pro W3", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    body, .q-body, .q-page {
        font-family: var(--font-family);
        max-width: 1800px;
        margin: 0 auto;
    }

    /* Square card edges - like meows.zip */
    .q-card {
        border-radius: 0 !important;
        box-shadow: none !important;
        border: 1px solid rgba(255,255,255,0.15);
        background: rgba(255,255,255,0.03);
    }

    .q-card:hover { 
        border-color: rgba(255,255,255,0.3); 
        background: rgba(255,255,255,0.06);
        transition: border-color 0.2s, background 0.2s;
    }

    /* Table styling */
    .q-table tbody tr:nth-child(odd) { background-color: rgba(255,255,255,0.05); }
    .q-table th, .q-table td {
        border-color: rgba(255,255,255,0.1) !important;
    }

    /* Square buttons */
    .q-btn {
        border-radius: 0 !important;
    }

    </style>
    """)

    with ui.row().classes('w-full justify-between items-center mb-6 px-4 pt-4'):
        ui.label('TP-Link Router Stats').classes('text-3xl font-bold')
        ui.button('Refresh', on_click=lambda: content.refresh()).props('flat icon=refresh')

    @ui.refreshable
    def content():
        status = stats_data.get('status', {})
        devices = stats_data.get('devices', [])

        # --- Traffic Summary (top) ---
        with ui.card().classes('w-full mb-6 p-4'):
            ui.label('Traffic Summary').classes('text-xl font-bold mb-4')
            if devices:
                total_down = sum(d['data_downloading'] for d in devices)
                total_up = sum(d['data_uploading'] for d in devices)
                total_traffic = sum(d['data_transferred'] for d in devices)
                
                with ui.row().classes('w-full gap-4'):
                    for title, value, color in [
                        ('Total Download', f"{total_down / 1_000_000:.2f} Mbps", 'text-green'),
                        ('Total Upload', f"{total_up / 1_000_000:.2f} Mbps", 'text-blue'),
                        ('Total Data Transferred', getrouterstats.bytes_to_readable_format(total_traffic), 'text-purple')
                    ]:
                        with ui.card().classes('flex-1 p-4'):
                            ui.label(title).classes('text-sm font-semibold')
                            ui.label(value).classes(f'text-2xl font-bold {color}')

        # --- Main content: metrics on left, devices on right ---
        with ui.row().classes('w-full gap-4 items-start'):
            # --- Left: Metrics group ---
            with ui.card().classes('w-1/4 p-4'):
                ui.label('System Status').classes('text-xl font-bold mb-4')
                metric_data = [
                    ('Uptime', status.get('uptime_readable', 'N/A'), 'mdi-clock-outline', 'text-cyan'),
                    ('CPU Usage', f"{status.get('cpu_usage', 0)}%", 'mdi-chip', 'text-purple'),
                    ('Memory Usage', f"{status.get('memory_usage', 0)}%", 'mdi-memory', 'text-pink'),
                    ('Total Clients', str(status.get('clients_total', 0)), 'mdi-account-multiple', 'text-green'),
                ]
                for title, value, icon, color in metric_data:
                    with ui.card().classes('w-full p-3'):
                        ui.icon(icon).classes(f'{color} text-lg q-mb-sm')
                        ui.label(title).classes('text-sm font-semibold')
                        ui.label(value).classes(f'text-xl font-bold {color}')

            # --- Right: Mesh & Connected Devices (side by side) ---
            with ui.row().classes('w-3/4 gap-4'):
                # Mesh Devices
                with ui.card().classes('flex-1 p-4'):
                    ui.label('Mesh Devices').classes('text-xl font-bold mb-4')
                    mesh_data = stats_data.get('mesh_data', [])
                    if mesh_data:
                        columns = [
                            {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                            {'name': 'type', 'label': 'Type', 'field': 'type', 'align': 'left'},
                            {'name': 'ip', 'label': 'IP', 'field': 'ip', 'align': 'left'},
                            {'name': 'clients', 'label': 'Clients', 'field': 'clients', 'align': 'center'},
                            {'name': 'location', 'label': 'Location', 'field': 'location', 'align': 'left'},
                            {'name': 'signal', 'label': 'Signal', 'field': 'signal', 'align': 'center'},
                        ]
                        rows = [
                            {
                                'name': d['device_name'],
                                'type': d['device_type'],
                                'ip': d['ip'],
                                'clients': d['connected_clients'],
                                'location': d['location'],
                                'signal': f"{d['signal_strength']}/5" if d['signal_strength'] else '-'
                            }
                            for d in mesh_data
                        ]
                        ui.table(columns=columns, rows=rows).classes('w-full')
                    else:
                        ui.label('No mesh devices found').classes('text-sm italic')

                # Connected Devices
                with ui.card().classes('flex-1 p-4'):
                    ui.label('Connected Devices').classes('text-xl font-bold mb-4')
                    if devices:
                        columns = [
                            {'name': 'name', 'label': 'Device', 'field': 'name', 'align': 'left'},
                            {'name': 'type', 'label': 'Type', 'field': 'type', 'align': 'left'},
                            {'name': 'ip', 'label': 'IP', 'field': 'ip', 'align': 'left'},
                            {'name': 'speed', 'label': 'Speed', 'field': 'speed', 'align': 'left'},
                            {'name': 'traffic', 'label': 'Traffic', 'field': 'traffic', 'align': 'left'},
                        ]
                        rows = [
                            {
                                'name': d['device_name'],
                                'type': d['device_type'],
                                'ip': d['ip'],
                                'speed': d['data_transfering_readable'],
                                'traffic': d['data_transferred_readable']
                            }
                            for d in devices
                        ]
                        ui.table(columns=columns, rows=rows).classes('w-full')
                    else:
                        ui.label('No devices found').classes('text-sm italic')

        # --- Last Updated ---
        ui.label(f'Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}').classes('text-sm italic text-right q-mt-md')

    def refresh_data():
        load_stats()
        content.refresh()
    
    load_stats()
    content()
    ui.timer(5, refresh_data)

if __name__ == "__main__":
    ui.run(title='TP-Link Router Stats', port=8080, reload=False)