let lastMtime = null;
let lastMesh = [];
let lastDevices = [];
const sortState = {
    mesh: { key: null, dir: 1 },
    devices: { key: null, dir: 1 },
};

function ipToComparable(ip) {
    const parts = String(ip ?? '').split('.');
    if (parts.length !== 4 || parts.some(p => p === '' || isNaN(p))) return -1;
    return parts.reduce((acc, p) => acc * 256 + Number(p), 0);
}

function sortRows(rows, key, type, dir) {
    const accessor = key === 'data_transfering_sort'
        ? (r) => (r.data_downloading || 0) + (r.data_uploading || 0)
        : (r) => r[key];

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

async function fetchData(manual = false) {
    const icon = document.getElementById('refresh-icon');
    if (manual) icon.classList.add('spinning');

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
                'Last updated: ' + updatedAt.toLocaleTimeString();
        }

        // Show error banner
        const banner = document.getElementById('error-banner');
        const errs = d.errors || {};
        const errList = Object.entries(errs).map(([k, v]) => `${k}: ${v}`);
        if (errList.length) {
            banner.style.display = 'block';
            // Auth/connection failure
            if (errs.authorization) {
                banner.className = 'error-banner error-severe';
                banner.textContent = '⚠ Router unreachable — ' + errs.authorization;
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
        meshTbody.innerHTML = '<tr><td colspan="6" class="skeleton">No mesh devices found</td></tr>';
        return;
    }
    const { key, dir } = sortState.mesh;
    const rows = key ? sortRows(lastMesh, key, document.querySelector(`#mesh-thead th[data-key="${key}"]`)?.dataset.type, dir) : lastMesh;
    meshTbody.innerHTML = rows.map(m => `
        <tr>
          <td>${esc(m.device_name)}</td>
          <td>${esc(m.device_type)}</td>
          <td>${esc(m.ip)}</td>
          <td class="center">${m.connected_clients}</td>
          <td>${esc(m.location)}</td>
          <td class="center">${m.signal_strength ? m.signal_strength + '/5' : '—'}</td>
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
          <td>${esc(dv.device_name)}</td>
          <td>${esc(dv.device_type)}</td>
          <td>${esc(dv.ip)}</td>
          <td class="c-green">${esc(dv.data_transfering_readable)}</td>
          <td class="c-blue">${esc(dv.data_transferred_readable)}</td>
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
        .replace(/>/g, '&gt;');
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

fetchData();
setInterval(fetchData, 5000);
