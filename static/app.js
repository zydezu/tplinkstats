let lastMtime = null;
let lastMesh = [];
let lastDevices = [];
const sortState = {
    mesh: { key: null, dir: 1 },
    devices: { key: null, dir: 1 },
};

// columns that aren't plain fields on the row
const SORT_KEYS = {
    data_transfering_sort: r => (r.data_downloading || 0) + (r.data_uploading || 0),
    signal_sort: r => (isWired(r) ? -1000 : (4 - signalQuality(r))), // Wired first, then high signal -> low signal
    mesh_name: r => r.mesh_name || '',
};

function ipToComparable(ip) {
    const parts = String(ip ?? '').split('.');
    if (parts.length !== 4 || parts.some(p => p === '' || isNaN(p))) return -1;
    return parts.reduce((acc, p) => acc * 256 + Number(p), 0);
}

function sortRows(rows, key, type, dir) {
    const accessor = SORT_KEYS[key] || (r => r[key]);

    return [...rows].sort((a, b) => {
        const av = accessor(a);
        const bv = accessor(b);
        if (type === 'ip') {
            return (ipToComparable(av) - ipToComparable(bv)) * dir;
        }
        if (type === 'number') {
            return ((av || 0) - (bv || 0)) * dir;
        }
        return String(av ?? '').localeCompare(String(bv ?? '')) * dir;
    });
}

function updateSortIndicators(tableId, state) {
    document.querySelectorAll(`#${tableId} th.sortable`).forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.key === state.key) {
            th.classList.add(state.dir === 1 ? 'sort-asc' : 'sort-desc');
        }
    });
}

function initSortHandlers(tableId, state, render) {
    document.querySelectorAll(`#${tableId} th.sortable`).forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (state.key === key) {
                state.dir *= -1;
            } else {
                state.key = key;
                state.dir = 1;
            }
            updateSortIndicators(tableId, state);
            render();
        });
    });
}

function triggerPoll() {
    // Wakes the backend poller immediately instead of waiting out its current sleep
    fetch('/trigger-poll', { method: 'POST' }).catch(() => { });
}

// Connection indicators -----------------------------------------------------

// Three-bar wifi icon (filled), based on the provided SVG. Each path is a
// separate bar lit progressively: 1 bar = innermost, 3 = all.
const WIFI_ARCS = [
    'M512 192c-163 0-326 67.2-443 176.6-6.6 6-6.8 16.2-0.6 22.8l53.4 55.8c6.2 6.6 16.6 6.8 23.2 0.6 46.6-43.2 99.8-77.6 158.6-102 66-27.6 136.2-41.4 208.6-41.4s142.6 14 208.6 41.4c58.8 24.6 112 58.8 158.6 102 6.6 6.2 17 6 23.2-0.6l53.4-55.8c6.2-6.4 6-16.6-0.6-22.8C838 259.2 675 192 512 192z',
    'M226.4 555l57.2 56.6c6.2 6 16 6.4 22.4 0.6 56.6-50.2 129.2-77.8 205.8-77.8s149.2 27.4 205.8 77.8c6.4 5.8 16.2 5.4 22.4-0.6l57.2-56.6c6.6-6.6 6.4-17.2-0.6-23.4-75-67.8-175.2-109.2-285-109.2s-210 41.4-285 109.2c-6.6 6.2-6.8 16.8-0.2 23.4z',
    'M512 648.4c-46.8 0-89.2 19.6-118.8 51-6 6.4-5.8 16.2 0.4 22.4l106.8 105.4c6.4 6.4 16.8 6.4 23.2 0l106.8-105.4c6.2-6.2 6.4-16 0.4-22.4-29.6-31.2-72-51-118.8-51z',
];

function wifiIcon(bars) {
    const b = Math.max(0, Math.min(3, bars));
    const paths = WIFI_ARCS.map((d, i) => {
        const on = b >= (3 - i); // inner(2): b>=1, mid(1): b>=2, outer(0): b>=3
        return `<path d="${d}" opacity="${on ? 1 : 0.16}"></path>`;
    }).join('');
    return `<svg class="icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">${paths}</svg>`;
}

function wiredIcon() {
    return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M9 2.5v4.5"></path><path d="M15 2.5v4.5"></path>
        <path d="M6 7h12v4a6 6 0 0 1-12 0z"></path><path d="M12 17v4.5"></path>
    </svg>`;
}

// Main mesh node (the router itself): a distinct glyph so it doesn't read as
// "no signal" the way the dimmed wifi arcs do.
function routerIcon() {
    return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="10" width="18" height="8" rx="2"></rect>
        <circle cx="8" cy="14" r="1"></circle>
        <circle cx="12" cy="14" r="1"></circle>
        <circle cx="16" cy="14" r="1"></circle>
        <path d="M8 10V6M16 10V6"></path>
    </svg>`;
}

function isWired(d) {
    if (d.wired != null || d.connection) return d.wired === true || d.connection === 'Wired';
    return !(Number(d.signal) < 0);
}

// Full band label, e.g. "5 GHz" (was "5G")
function shortBand(conn) {
    if (!conn) return '';
    const m = String(conn).match(/(\d+(?:\.\d+)?)\s*GHz/i);
    if (m) return m[1] + 'GHz';
    return '';
}

// 3-bar scale
function signalQuality(d) {
    const dbm = Number(d.signal);
    if (!Number.isFinite(dbm) || dbm >= 0) return 0; // wired / unknown
    if (dbm >= -67) return 3;
    if (dbm >= -75) return 2;
    if (dbm >= -85) return 1;
    return 0;
}

function signalCell(d) {
    if (isWired(d)) {
        const tip = d.link_speed_readable && d.link_speed_readable !== 'Wired'
            ? d.link_speed_readable : '';
        return `<span class="sig sig-wired" title="${esc(tip)}">${wiredIcon()}<span
            class="sig-text">Wired</span></span>`;
    }
    const tip = [d.connection, d.link_speed_readable].filter(Boolean).join(' · ');
    const band = shortBand(d.connection);
    return `<span class="sig sig-${signalQuality(d)}" title="${esc(tip)}">${wifiIcon(signalQuality(d))}<span
            class="sig-text">${d.signal} dBm${band ? ' <span class="sig-band">' + band + '</span>' : ''}</span></span>`;
}

function meshCell(d) {
    if (!d.mesh_name) return '<span class="mesh-tag mesh-unknown">—</span>';
    const tip = d.mesh_location ? `${d.mesh_name} · ${d.mesh_location}` : d.mesh_name;
    return `<span class="mesh-tag" title="${esc(tip)}">${esc(d.mesh_name)}</span>`;
}

async function fetchData(manual = false) {
    const icon = document.getElementById('refresh-icon');
    if (manual) {
        icon.classList.add('spinning');
        triggerPoll();
    }

    try {
        const res = await fetch('/data');
        const d = await res.json();

        // Skip all DOM updates if data hasn't changed, unless manually triggered
        if (!manual && d.file_mtime && d.file_mtime === lastMtime) return;
        const isNew = d.file_mtime !== lastMtime;
        lastMtime = d.file_mtime;

        const status = d.status || {};
        const devices = d.devices || [];
        const mesh = d.mesh_data || [];

        // Traffic summary (data_downloading/uploading are bytes/sec; convert to bits/sec)
        const totalDown = devices.reduce((s, x) => s + (x.data_downloading || 0), 0) * 8;
        const totalUp = devices.reduce((s, x) => s + (x.data_uploading || 0), 0) * 8;
        const totalTraffic = d.total_transferred_readable || '—';

        document.getElementById('total-down').textContent = fmtMbps(totalDown);
        document.getElementById('total-up').textContent = fmtMbps(totalUp);
        document.getElementById('total-traffic').textContent = totalTraffic;

        // System metrics
        document.getElementById('m-uptime').textContent = status.uptime_readable || '—';
        document.getElementById('m-cpu').textContent = (status.cpu_usage ?? '—') + (status.cpu_usage != null ? '%' : '');
        document.getElementById('m-mem').textContent = (status.memory_usage ?? '—') + (status.memory_usage != null ? '%' : '');
        document.getElementById('m-clients').textContent = status.clients_total ?? '—';

        lastMesh = mesh;
        lastDevices = devices;
        renderMeshTable();
        renderDevicesTable();

        // Only update timestamp when data is new. Use the file's own mtime
        // (not the browser's current time) so data carried over from a
        // previous session shows its true age instead of "just now".
        if (isNew) {
            const updatedAt = d.file_mtime ? new Date(d.file_mtime * 1000) : new Date();
            document.getElementById('last-updated').textContent =
                'Last updated: ' + updatedAt.toLocaleTimeString([], { hour12: false });
        }

        // Show error banner
        const banner = document.getElementById('error-banner');
        const errs = d.errors || {};
        const errList = Object.entries(errs).map(([k, v]) => `${k}: ${v}`);
        if (errList.length) {
            banner.style.display = 'block';
            // Auth/connection failure
            const loginErr = errs.authorization || errs.connection;
            if (loginErr) {
                banner.className = 'error-banner error-severe';
                banner.textContent = '⚠ Router unreachable, retrying — ' + loginErr.split('\n')[0];
            } else {
                banner.className = 'error-banner';
                banner.textContent = '⚠ Partial router error (stale data shown) — ' + errList.join(' | ');
            }
        } else {
            banner.style.display = 'none';
        }

    } catch (err) {
        console.error('Fetch error:', err);
        document.getElementById('last-updated').textContent = 'Error fetching data — retrying…';
    } finally {
        if (manual) icon.classList.remove('spinning');
    }
}

function renderMeshTable() {
    const meshTbody = document.getElementById('mesh-tbody');
    if (!lastMesh.length) {
        meshTbody.innerHTML = '<tr><td colspan="5" class="skeleton">No mesh devices found</td></tr>';
        return;
    }
    const { key, dir } = sortState.mesh;
    const rows = key ? sortRows(lastMesh, key, document.querySelector(`#mesh-thead th[data-key="${key}"]`)?.dataset.type, dir) : lastMesh;
    meshTbody.innerHTML = rows.map(m => `
        <tr>
          <td${tipAttr(m.device_name)}>${esc(m.device_name)}</td>
          <td data-label="IP">${esc(m.ip)}</td>
          <td class="center" data-label="Clients">${m.connected_clients}</td>
          <td data-label="Location">${esc(m.location)}</td>
          <td class="center">${m.signal_strength ? (wifiIcon(Math.max(1, Math.ceil(m.signal_strength * 3 / 5))) + ' ' + m.signal_strength + '/5') : (routerIcon() + ' Main')}</td>
        </tr>`).join('');
}

function renderDevicesTable() {
    const devTbody = document.getElementById('devices-tbody');
    if (!lastDevices.length) {
        devTbody.innerHTML = '<tr><td colspan="5" class="skeleton">No devices found</td></tr>';
        return;
    }
    const { key, dir } = sortState.devices;
    const rows = key ? sortRows(lastDevices, key, document.querySelector(`#devices-thead th[data-key="${key}"]`)?.dataset.type, dir) : lastDevices;
    devTbody.innerHTML = rows.map(dv => `
        <tr>
          <td${tipAttr(dv.device_name)}>${esc(dv.device_name)}</td>
          <td>${esc(dv.ip)}</td>
          <td class="c-green" data-label="Traffic">${esc(dv.data_transfering_readable)}</td>
          <td>${signalCell(dv)}</td>
          <td data-label="AP">${meshCell(dv)}</td>
        </tr>`).join('');
}

async function exportData() {
    try {
        const res = await fetch('/data');
        const d = await res.json();
        const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const ts = new Date().toISOString().replace(/[:.]/g, '-');

        const a = document.createElement('a');
        a.href = url;
        a.download = `router-stats-${ts}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Export error:', err);
    }
}

function fmtMbps(bps) {
    return (bps / 1_000_000).toFixed(2) + ' Mbps';
}

function esc(s) {
    if (s == null) return '—';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Full value on hover for the cells CSS truncates with an ellipsis
function tipAttr(s) {
    return s ? ` title="${esc(s)}"` : '';
}

const isKiosk = new URLSearchParams(window.location.search).get('kiosk') === '1';
if (isKiosk) {
    document.body.classList.add('kiosk');
    sortState.devices.key = 'data_transfering_sort';
    sortState.devices.dir = -1;
    updateSortIndicators('devices-thead', sortState.devices);
}

initSortHandlers('mesh-thead', sortState.mesh, renderMeshTable);
initSortHandlers('devices-thead', sortState.devices, renderDevicesTable);

// Kick the poller awake as soon as the window opens
triggerPoll();
fetchData();
setInterval(fetchData, 5000);
