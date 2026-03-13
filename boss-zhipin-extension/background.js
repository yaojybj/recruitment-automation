chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'API_REQUEST') {
    handleApiRequest(message).then(sendResponse).catch(err => {
      sendResponse({ error: err.message });
    });
    return true;
  }
});

async function handleApiRequest({ method, endpoint, body }) {
  const stored = await chrome.storage.sync.get(['backendUrl']);
  const baseUrl = (stored.backendUrl || 'http://localhost:8000').replace(/\/+$/, '');

  const opts = {
    method: method || 'GET',
    headers: { 'Content-Type': 'application/json' },
  };
  if (body && method !== 'GET') {
    opts.body = JSON.stringify(body);
  }

  const resp = await fetch(`${baseUrl}${endpoint}`, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API ${resp.status}: ${text}`);
  }
  return resp.json();
}
