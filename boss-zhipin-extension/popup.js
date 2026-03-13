const $ = id => document.getElementById(id);

async function apiCall(method, endpoint, body) {
  const stored = await chrome.storage.sync.get(['backendUrl']);
  const base = (stored.backendUrl || 'http://localhost:8000').replace(/\/+$/, '');
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  return fetch(`${base}${endpoint}`, opts).then(r => r.json());
}

async function checkBackend() {
  try {
    const data = await apiCall('GET', '/api/health');
    $('statusDot').className = 'status-dot ok';
    $('statusText').textContent = '后台已连接';
    $('statsSection').style.display = '';
    loadPositions();
    loadStats();
  } catch {
    $('statusDot').className = 'status-dot err';
    $('statusText').textContent = '后台未连接 — 请检查地址或启动 start.sh';
  }
}

async function loadPositions() {
  try {
    const data = await apiCall('GET', '/api/positions?is_active=true');
    const sel = $('defaultPosition');
    const stored = await chrome.storage.sync.get(['defaultPositionId']);
    const current = stored.defaultPositionId;
    const positions = Array.isArray(data) ? data : (data.items || []);
    positions.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.title}${p.department ? ' - ' + p.department : ''}`;
      if (String(p.id) === String(current)) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch {}
}

async function loadStats() {
  try {
    const data = await apiCall('GET', '/api/resumes/stats');
    $('statImported').textContent = data.today_new || 0;
    const summary = await apiCall('GET', '/api/pipeline/summary');
    $('statMatched').textContent = summary.jd_matched || 0;
    $('statInterview').textContent = (summary.dept_approved || 0) + (summary.contacting || 0);
  } catch {}
}

async function loadSettings() {
  const data = await chrome.storage.sync.get([
    'enabled', 'autoImport', 'showBadge', 'backendUrl', 'defaultPositionId',
  ]);
  $('enabled').checked = data.enabled !== false;
  $('autoImport').checked = data.autoImport || false;
  $('showBadge').checked = data.showBadge !== false;
  if (data.backendUrl) $('backendUrl').value = data.backendUrl;
}

function saveSettings() {
  chrome.storage.sync.set({
    enabled: $('enabled').checked,
    autoImport: $('autoImport').checked,
    showBadge: $('showBadge').checked,
    backendUrl: $('backendUrl').value.trim(),
    defaultPositionId: $('defaultPosition').value || null,
  }, () => {
    showMsg('设置已保存', 'success');
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (tabs[0] && tabs[0].url && tabs[0].url.includes('zhipin.com')) {
        chrome.tabs.reload(tabs[0].id);
      }
    });
  });
}

function showMsg(text, type) {
  const el = $('msg');
  el.textContent = text;
  el.className = `msg ${type}`;
  setTimeout(() => { el.className = 'msg'; }, 3000);
}

$('saveBtn').addEventListener('click', saveSettings);
$('openDashboard').addEventListener('click', async () => {
  const stored = await chrome.storage.sync.get(['backendUrl']);
  const base = stored.backendUrl || 'http://localhost:8000';
  const frontendUrl = base.replace(':8000', ':5173');
  chrome.tabs.create({ url: frontendUrl });
});

loadSettings();
checkBackend();
