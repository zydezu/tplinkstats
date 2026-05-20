let lastMtime = null;

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

        // Traffic summary
        const totalDown = devices.reduce((s, x) => s + (x.data_downloading || 0), 0);
        const totalUp = devices.reduce((s, x) => s + (x.data_uploading || 0), 0);
        const totalTraffic = d.total_transferred_readable || '—';

        document.getElementById('total-down').textContent = fmtMbps(totalDown);
        document.getElementById('total-up').textContent = fmtMbps(totalUp);
        document.getElementById('total-traffic').textContent = totalTraffic;

        // System metrics
        document.getElementById('m-uptime').textContent = status.uptime_readable || '—';
        document.getElementById('m-cpu').textContent = (status.cpu_usage ?? '—') + (status.cpu_usage != null ? '%' : '');
        document.getElementById('m-mem').textContent = (status.memory_usage ?? '—') + (status.memory_usage != null ? '%' : '');
        document.getElementById('m-clients').textContent = status.clients_total ?? '—';

        // Mesh table
        const meshTbody = document.getElementById('mesh-tbody');
        if (mesh.length) {
            meshTbody.innerHTML = mesh.map(m => `
        <tr>
          <td>${esc(m.device_name)}</td>
          <td>${esc(m.device_type)}</td>
          <td>${esc(m.ip)}</td>
          <td class="center">${m.connected_clients}</td>
          <td>${esc(m.location)}</td>
          <td class="center">${m.signal_strength ? m.signal_strength + '/5' : '—'}</td>
        </tr>`).join('');
        } else {
            meshTbody.innerHTML = '<tr><td colspan="6" class="skeleton">No mesh devices found</td></tr>';
        }

        // Devices table
        const devTbody = document.getElementById('devices-tbody');
        if (devices.length) {
            devTbody.innerHTML = devices.map(dv => `
        <tr>
          <td>${esc(dv.device_name)}</td>
          <td>${esc(dv.device_type)}</td>
          <td>${esc(dv.ip)}</td>
          <td class="c-green">${esc(dv.data_transfering_readable)}</td>
          <td class="c-blue">${esc(dv.data_transferred_readable)}</td>
        </tr>`).join('');
        } else {
            devTbody.innerHTML = '<tr><td colspan="5" class="skeleton">No devices found</td></tr>';
        }

        // Only update timestamp when data is new
        if (isNew) {
            document.getElementById('last-updated').textContent =
                'Last updated: ' + new Date().toLocaleTimeString();
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

fetchData();
setInterval(fetchData, 5000);
