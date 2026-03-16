const $ = id => document.getElementById(id);

async function apiCall(method, endpoint) {
  const stored = await chrome.storage.sync.get(['mokaBackendUrl']);
  const base = (stored.mokaBackendUrl || 'http://localhost:8000').replace(/\/+$/, '');
  return fetch(`${base}${endpoint}`, { method }).then(r => r.json());
}

async function checkBackend() {
  try {
    await apiCall('GET', '/api/health');
    $('statusDot').className = 'status-dot ok';
    $('statusText').textContent = '后台已连接';
    $('statsSection').style.display = '';
    loadStats();
  } catch {
    $('statusDot').className = 'status-dot err';
    $('statusText').textContent = '后台未连接';
  }
}

async function loadStats() {
  try {
    const tasks = await apiCall('GET', '/api/extension/pending-tasks?platform=moka');
    let create = 0, recommend = 0, interview = 0;
    for (const t of tasks) {
      if (t.task_type === 'moka_create_candidate') create++;
      else if (t.task_type === 'moka_recommend') recommend++;
      else if (t.task_type === 'moka_schedule_interview') interview++;
    }
    $('statCreate').textContent = create;
    $('statRecommend').textContent = recommend;
    $('statInterview').textContent = interview;
  } catch {}
}

async function loadSettings() {
  const data = await chrome.storage.sync.get(['mokaEnabled', 'mokaAutoExec', 'mokaBackendUrl']);
  $('enabled').checked = data.mokaEnabled !== false;
  $('autoExec').checked = data.mokaAutoExec || false;
  if (data.mokaBackendUrl) $('backendUrl').value = data.mokaBackendUrl;
}

function saveSettings() {
  chrome.storage.sync.set({
    mokaEnabled: $('enabled').checked,
    mokaAutoExec: $('autoExec').checked,
    mokaBackendUrl: $('backendUrl').value.trim(),
  }, () => {
    const el = $('msg');
    el.textContent = '设置已保存';
    el.className = 'msg success';
    setTimeout(() => { el.className = 'msg'; }, 3000);
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (tabs[0] && tabs[0].url && tabs[0].url.includes('mokahr.com')) {
        chrome.tabs.reload(tabs[0].id);
      }
    });
  });
}

$('saveBtn').addEventListener('click', saveSettings);
$('openDashboard').addEventListener('click', async () => {
  const stored = await chrome.storage.sync.get(['mokaBackendUrl']);
  const base = stored.mokaBackendUrl || 'http://localhost:8000';
  chrome.tabs.create({ url: base.replace(':8000', ':3000') });
});

loadSettings();
checkBackend();
