/**
 * Boss直聘 招聘自动化助手 - Content Script
 * 功能：
 * 1. 候选人列表页：扫描、导入、评分徽章
 * 2. 聊天页：自动发送约面消息、捕获候选人回复
 * 3. 任务轮询：从后台获取待执行任务并自动执行
 */

(() => {
  'use strict';

  let enabled = true;
  let autoImport = false;
  let showBadge = true;
  let defaultPositionId = null;
  let backendUrl = 'http://localhost:8000';
  let processedCards = new WeakSet();
  let importedCandidates = new Map();
  let screener = null;
  let taskPollInterval = null;

  async function init() {
    const stored = await chrome.storage.sync.get([
      'enabled', 'autoImport', 'showBadge', 'backendUrl',
      'defaultPositionId', 'screeningRules',
    ]);

    enabled = stored.enabled !== false;
    autoImport = stored.autoImport || false;
    showBadge = stored.showBadge !== false;
    backendUrl = (stored.backendUrl || 'http://localhost:8000').replace(/\/+$/, '');
    defaultPositionId = stored.defaultPositionId || null;

    if (!enabled) return;

    screener = new ResumeScreener(stored.screeningRules || null);

    injectFloatingToolbar();
    observePageChanges();
    setTimeout(() => processPage(), 1500);

    startTaskPolling();
    startReplyCapture();
  }

  // ═══════════════════════════════════
  //  API
  // ═══════════════════════════════════

  async function apiCall(method, endpoint, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body && method !== 'GET') {
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(`${backendUrl}${endpoint}`, opts);
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`${resp.status}: ${text}`);
    }
    return resp.json();
  }

  // ═══════════════════════════════════
  //  任务轮询：从后台获取待办任务
  // ═══════════════════════════════════

  function startTaskPolling() {
    if (taskPollInterval) return;
    pollTasks();
    taskPollInterval = setInterval(pollTasks, 30000);
  }

  async function pollTasks() {
    try {
      const tasks = await apiCall('GET', '/api/extension/pending-tasks?platform=boss');
      if (!tasks || tasks.length === 0) return;

      updateToolbarTaskCount(tasks.length);

      if (!isOnChatPage()) {
        showToast(`有 ${tasks.length} 个待发消息，请打开聊天页面`);
        return;
      }

      for (const task of tasks) {
        if (task.task_type === 'boss_send_message') {
          await handleSendMessageTask(task);
        }
      }
    } catch {
      // backend offline, ignore
    }
  }

  function isOnChatPage() {
    return location.pathname.includes('/chat') ||
           location.pathname.includes('/message') ||
           !!document.querySelector('[class*="chat"], [class*="message-list"]');
  }

  async function handleSendMessageTask(task) {
    const { candidate_name, message, boss_candidate_id } = task.payload || {};
    if (!message) return;

    showTaskConfirmDialog(task, candidate_name, message);
  }

  function showTaskConfirmDialog(task, name, message) {
    let dialog = document.getElementById('boss-ext-task-dialog');
    if (dialog) dialog.remove();

    dialog = document.createElement('div');
    dialog.id = 'boss-ext-task-dialog';
    dialog.innerHTML = `
      <div class="boss-ext-dialog-overlay"></div>
      <div class="boss-ext-dialog-box">
        <div class="boss-ext-dialog-header">
          <h3>待发送约面消息</h3>
          <button class="boss-ext-dialog-close" id="boss-ext-dialog-close">✕</button>
        </div>
        <div class="boss-ext-dialog-body">
          <div class="boss-ext-dialog-field">
            <label>候选人</label>
            <div class="boss-ext-dialog-value">${name}</div>
          </div>
          <div class="boss-ext-dialog-field">
            <label>消息内容</label>
            <textarea id="boss-ext-msg-text" rows="8">${message}</textarea>
          </div>
          <div class="boss-ext-dialog-hint">
            请先在左侧聊天列表中找到 <strong>${name}</strong>，打开聊天窗口后点击发送。
          </div>
        </div>
        <div class="boss-ext-dialog-footer">
          <button class="boss-ext-dialog-btn secondary" id="boss-ext-copy-msg">📋 复制消息</button>
          <button class="boss-ext-dialog-btn secondary" id="boss-ext-auto-send">🚀 自动填入并发送</button>
          <button class="boss-ext-dialog-btn primary" id="boss-ext-mark-sent">✅ 已手动发送</button>
          <button class="boss-ext-dialog-btn" id="boss-ext-skip-task">跳过</button>
        </div>
      </div>
    `;
    document.body.appendChild(dialog);

    document.getElementById('boss-ext-dialog-close').onclick = () => dialog.remove();
    document.getElementById('boss-ext-skip-task').onclick = () => dialog.remove();

    document.getElementById('boss-ext-copy-msg').onclick = () => {
      const text = document.getElementById('boss-ext-msg-text').value;
      copyToClipboard(text);
      showToast('消息已复制，请粘贴到聊天窗口');
    };

    document.getElementById('boss-ext-auto-send').onclick = async () => {
      const text = document.getElementById('boss-ext-msg-text').value;
      const sent = await autoFillAndSend(text);
      if (sent) {
        await reportTaskDone(task.id, true);
        dialog.remove();
        showToast(`✅ 已自动发送给 ${name}`);
      }
    };

    document.getElementById('boss-ext-mark-sent').onclick = async () => {
      await reportTaskDone(task.id, true);
      dialog.remove();
      showToast(`✅ 已标记为已发送: ${name}`);
    };
  }

  async function autoFillAndSend(message) {
    const inputSelectors = [
      '[class*="chat-input"] textarea',
      '[class*="message-input"] textarea',
      '[class*="chat"] textarea',
      '.chat-input textarea',
      'textarea[placeholder*="请输入"]',
      'textarea[class*="input"]',
      '[contenteditable="true"]',
    ];

    let input = null;
    for (const sel of inputSelectors) {
      input = document.querySelector(sel);
      if (input) break;
    }

    if (!input) {
      showToast('未找到聊天输入框，请先打开聊天窗口', true);
      return false;
    }

    if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
      input.value = message;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      input.textContent = message;
      input.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
    }

    await new Promise(r => setTimeout(r, 500));

    const sendBtnSelectors = [
      '[class*="btn-send"]',
      '[class*="send-btn"]',
      'button[class*="send"]',
      '[class*="chat"] button[class*="primary"]',
      'button:has(span:contains("发送"))',
    ];

    let sendBtn = null;
    for (const sel of sendBtnSelectors) {
      try {
        sendBtn = document.querySelector(sel);
        if (sendBtn) break;
      } catch { /* invalid selector */ }
    }

    if (!sendBtn) {
      const allBtns = document.querySelectorAll('button, [role="button"]');
      for (const btn of allBtns) {
        if (btn.textContent.trim() === '发送' || btn.textContent.includes('发送')) {
          sendBtn = btn;
          break;
        }
      }
    }

    if (sendBtn) {
      sendBtn.click();
      return true;
    } else {
      showToast('消息已填入，请手动点击发送按钮');
      return false;
    }
  }

  async function reportTaskDone(taskId, success, result = {}) {
    try {
      await apiCall('POST', `/api/extension/task-start/${taskId}`);
      await apiCall('POST', `/api/extension/task-complete/${taskId}`, {
        success,
        result,
      });
    } catch (err) {
      console.error('Report task failed:', err);
    }
  }

  function updateToolbarTaskCount(count) {
    let badge = document.getElementById('boss-ext-task-badge');
    if (!badge) {
      const toolbar = document.getElementById('boss-ext-toolbar');
      if (!toolbar) return;
      badge = document.createElement('span');
      badge.id = 'boss-ext-task-badge';
      badge.className = 'boss-ext-task-badge';
      toolbar.querySelector('.boss-ext-toolbar-inner').appendChild(badge);
    }
    badge.textContent = `${count} 待办`;
    badge.style.display = count > 0 ? 'inline-block' : 'none';
  }

  // ═══════════════════════════════════
  //  自动捕获候选人回复
  // ═══════════════════════════════════

  let lastChatObserver = null;
  let capturedReplies = new Set();

  function startReplyCapture() {
    if (!isOnChatPage()) return;

    const chatObserver = new MutationObserver(() => {
      clearTimeout(window._replyDebounce);
      window._replyDebounce = setTimeout(checkForNewReplies, 2000);
    });

    const chatContainer = document.querySelector(
      '[class*="message-list"], [class*="chat-content"], [class*="chat-message"]'
    );
    if (chatContainer) {
      chatObserver.observe(chatContainer, { childList: true, subtree: true });
      lastChatObserver = chatObserver;
    }
  }

  async function checkForNewReplies() {
    try {
      const awaiting = await apiCall('GET', '/api/pipeline/awaiting-replies');
      if (!awaiting || awaiting.length === 0) return;

      const awaitingNames = new Map();
      for (const r of awaiting) {
        awaitingNames.set(r.name, r.id);
      }

      const currentChatName = getCurrentChatName();
      if (!currentChatName) return;

      const resumeId = awaitingNames.get(currentChatName);
      if (!resumeId) return;

      const replyKey = `${resumeId}_${Date.now()}`;
      if (capturedReplies.has(resumeId)) return;

      const lastReply = getLastReceivedMessage();
      if (!lastReply) return;

      capturedReplies.add(resumeId);

      showReplyConfirmDialog(resumeId, currentChatName, lastReply);
    } catch {
      // ignore
    }
  }

  function getCurrentChatName() {
    const selectors = [
      '[class*="chat-header"] [class*="name"]',
      '[class*="chat-info"] [class*="name"]',
      '[class*="nickname"]',
      '.chat-person .name',
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const name = el.textContent.trim();
        if (name.length >= 2 && name.length <= 10) return name;
      }
    }
    return null;
  }

  function getLastReceivedMessage() {
    const msgSelectors = [
      '[class*="message-item"][class*="left"]',
      '[class*="msg-item"][class*="received"]',
      '[class*="message"][class*="other"]',
      '.message-left',
    ];

    for (const sel of msgSelectors) {
      const msgs = document.querySelectorAll(sel);
      if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        const textEl = last.querySelector('[class*="text"], [class*="content"], p');
        if (textEl) return textEl.textContent.trim();
      }
    }
    return null;
  }

  function showReplyConfirmDialog(resumeId, name, replyText) {
    let dialog = document.getElementById('boss-ext-reply-dialog');
    if (dialog) dialog.remove();

    dialog = document.createElement('div');
    dialog.id = 'boss-ext-reply-dialog';
    dialog.innerHTML = `
      <div class="boss-ext-dialog-overlay"></div>
      <div class="boss-ext-dialog-box">
        <div class="boss-ext-dialog-header">
          <h3>候选人回复捕获</h3>
          <button class="boss-ext-dialog-close" onclick="this.closest('#boss-ext-reply-dialog').remove()">✕</button>
        </div>
        <div class="boss-ext-dialog-body">
          <div class="boss-ext-dialog-field">
            <label>候选人</label>
            <div class="boss-ext-dialog-value">${name}</div>
          </div>
          <div class="boss-ext-dialog-field">
            <label>捕获到的回复</label>
            <textarea id="boss-ext-reply-text" rows="3">${replyText}</textarea>
          </div>
          <div class="boss-ext-dialog-hint">确认后系统将自动解析时间并安排面试</div>
        </div>
        <div class="boss-ext-dialog-footer">
          <button class="boss-ext-dialog-btn primary" id="boss-ext-submit-reply">✅ 确认提交</button>
          <button class="boss-ext-dialog-btn" onclick="this.closest('#boss-ext-reply-dialog').remove()">忽略</button>
        </div>
      </div>
    `;
    document.body.appendChild(dialog);

    document.getElementById('boss-ext-submit-reply').onclick = async () => {
      const text = document.getElementById('boss-ext-reply-text').value;
      try {
        await apiCall('POST', `/api/pipeline/candidate-reply/${resumeId}`, { reply_text: text });
        showToast(`✅ ${name} 的回复已提交，系统正在安排面试`);
      } catch (err) {
        showToast('提交失败: ' + err.message, true);
      }
      dialog.remove();
    };
  }

  // ═══════════════════════════════════
  //  浮动工具栏
  // ═══════════════════════════════════

  function injectFloatingToolbar() {
    if (document.getElementById('boss-ext-toolbar')) return;

    const bar = document.createElement('div');
    bar.id = 'boss-ext-toolbar';
    bar.innerHTML = `
      <div class="boss-ext-toolbar-inner">
        <div class="boss-ext-toolbar-title">招聘助手</div>
        <button class="boss-ext-btn" id="boss-ext-scan" title="扫描当前页候选人">
          🔍 扫描
        </button>
        <button class="boss-ext-btn" id="boss-ext-import-all" title="导入所有候选人">
          📥 全部导入
        </button>
        <button class="boss-ext-btn" id="boss-ext-check-tasks" title="检查待办任务">
          📋 检查待办
        </button>
        <span class="boss-ext-counter" id="boss-ext-count">0 人</span>
        <button class="boss-ext-btn boss-ext-btn-sm" id="boss-ext-minimize" title="最小化">—</button>
      </div>
    `;
    document.body.appendChild(bar);

    document.getElementById('boss-ext-scan').addEventListener('click', () => processPage());
    document.getElementById('boss-ext-import-all').addEventListener('click', importAllVisible);
    document.getElementById('boss-ext-check-tasks').addEventListener('click', pollTasks);
    document.getElementById('boss-ext-minimize').addEventListener('click', toggleToolbar);
  }

  function toggleToolbar() {
    const bar = document.getElementById('boss-ext-toolbar');
    if (!bar) return;
    bar.classList.toggle('boss-ext-minimized');
    const btn = document.getElementById('boss-ext-minimize');
    btn.textContent = bar.classList.contains('boss-ext-minimized') ? '□' : '—';
  }

  // ═══════════════════════════════════
  //  页面扫描（候选人列表页）
  // ═══════════════════════════════════

  function processPage() {
    if (!enabled) return;
    const cards = findCandidateCards();
    let count = 0;
    cards.forEach(card => {
      if (processedCards.has(card)) return;
      processedCards.add(card);
      const candidate = parseCardInfo(card);
      if (!candidate.name) return;
      count++;

      if (showBadge && screener) {
        const result = screener.screen(candidate);
        injectScoreBadge(card, result);
      }
      injectActionButtons(card, candidate);
    });

    const counter = document.getElementById('boss-ext-count');
    if (counter) counter.textContent = `${cards.length} 人`;

    if (autoImport && count > 0) {
      importAllVisible();
    }
  }

  function findCandidateCards() {
    const selectors = [
      '.candidate-card', '.resume-card-wrap', '.card-inner',
      '[class*="candidate-wrap"]', '[class*="recommend-card"]',
      '.job-card-wrap', '.resume-item', '[ka*="recommend"]', 'li[class*="item"]',
    ];

    for (const sel of selectors) {
      const cards = document.querySelectorAll(sel);
      if (cards.length > 0) {
        const filtered = Array.from(cards).filter(c => {
          const t = c.textContent || '';
          return t.length > 20 && t.length < 3000 &&
            (t.includes('本科') || t.includes('硕士') || t.includes('大专') ||
             t.includes('博士') || t.includes('年') || /\d+岁/.test(t));
        });
        if (filtered.length > 0) return filtered;
      }
    }

    const containers = document.querySelectorAll(
      '[class*="list"], [class*="recommend"], [class*="candidate"]'
    );
    for (const container of containers) {
      const items = container.querySelectorAll(':scope > div, :scope > li, :scope > a');
      const filtered = Array.from(items).filter(el => {
        const text = el.textContent || '';
        return text.length > 30 && text.length < 2000 &&
          (text.includes('本科') || text.includes('硕士') || text.includes('大专') ||
           text.includes('博士') || /\d+年/.test(text) || /\d+岁/.test(text));
      });
      if (filtered.length >= 2) return filtered;
    }

    return [];
  }

  function parseCardInfo(card) {
    const text = card.textContent || '';
    const candidate = {
      name: '', education: '', workYears: 0, city: '', skills: [],
      experiences: [], projectCount: 0, hasPortfolio: false,
      company: '', position: '', age: null, phone: '', bossId: '',
    };

    const nameEl = card.querySelector(
      '[class*="name"], [class*="geek-name"], [class*="user-name"], ' +
      '[class*="title-name"], a[ka*="name"]'
    );
    if (nameEl) {
      let raw = nameEl.textContent.trim().replace(/[®©™✓✗●○◆★☆\s·|]/g, '').substring(0, 10);
      if (raw.length >= 2 && raw.length <= 6) candidate.name = raw;
    }
    if (!candidate.name) {
      const bold = card.querySelector('b, strong, h3, h4');
      if (bold) {
        const t = bold.textContent.trim();
        if (t.length >= 2 && t.length <= 6) candidate.name = t;
      }
    }

    const eduMatch = text.match(/(博士|硕士|MBA|本科|大专|中专|高中)/);
    if (eduMatch) candidate.education = eduMatch[1];

    const yearsMatch = text.match(/(\d+)[年-](?:经验|工作|以上)?/);
    if (yearsMatch) candidate.workYears = parseInt(yearsMatch[1]);

    const ageMatch = text.match(/(\d{2})岁/);
    if (ageMatch) candidate.age = parseInt(ageMatch[1]);

    const cityMatch = text.match(/(北京|上海|深圳|广州|杭州|成都|武汉|南京|西安|苏州|重庆|天津|长沙|郑州|东莞|青岛|合肥|佛山|宁波|厦门|珠海|无锡|济南|大连|沈阳|昆明|福州|哈尔滨|石家庄|贵阳)/);
    if (cityMatch) candidate.city = cityMatch[1];

    const tags = card.querySelectorAll(
      '[class*="tag"], [class*="label"], [class*="skill"], span[class*="desc"], [class*="info-desc"]'
    );
    tags.forEach(tag => {
      const tt = tag.textContent.trim();
      if (tt.length >= 1 && tt.length <= 25 && !tt.includes('天前') && !tt.includes('在线')) {
        candidate.skills.push(tt);
      }
    });

    const companyMatch = text.match(/(?:在|·|丨)\s*(.{2,20}(?:公司|集团|科技|有限|网络|互联|教育|医疗|金融|银行|证券|基金|投资|咨询|传媒|文化|信息|软件|硬件|电子|通信|游戏|电商|平台))/);
    if (companyMatch) candidate.company = companyMatch[1];

    const link = card.querySelector('a[href*="/geek/"], a[href*="/resume/"]');
    if (link) {
      const href = link.getAttribute('href') || '';
      const idMatch = href.match(/\/geek\/([^/?#]+)|\/resume\/([^/?#]+)/);
      if (idMatch) candidate.bossId = idMatch[1] || idMatch[2];
    }

    const dateRanges = text.matchAll(/(\d{4})[-./](\d{1,2})\s*(?:至|[-–~]|到)\s*(?:(\d{4})[-./](\d{1,2})|至今|今)/g);
    for (const m of dateRanges) {
      const startYear = parseInt(m[1]);
      let endYear = m[3] ? parseInt(m[3]) : new Date().getFullYear();
      const duration = (endYear - startYear) * 12;
      if (duration > 0 && duration < 600) {
        candidate.experiences.push({ durationMonths: duration, startYear, endYear });
      }
    }

    if (candidate.experiences.length > 0 && candidate.workYears === 0) {
      const allYears = candidate.experiences.flatMap(e => [e.startYear, e.endYear]);
      candidate.workYears = Math.max(...allYears) - Math.min(...allYears);
    }

    return candidate;
  }

  // ═══════════════════════════════════
  //  分数徽章 + 操作按钮
  // ═══════════════════════════════════

  function injectScoreBadge(card, result) {
    const existing = card.querySelector('.boss-ext-badge');
    if (existing) existing.remove();

    const badge = document.createElement('div');
    badge.className = 'boss-ext-badge';

    if (result.autoFilterReason) {
      badge.classList.add('boss-ext-reject');
      badge.innerHTML = `<span class="boss-ext-score-text">淘汰</span><span class="boss-ext-reason">${result.autoFilterReason}</span>`;
    } else if (result.hardFail) {
      badge.classList.add('boss-ext-reject');
      badge.innerHTML = `<span class="boss-ext-score-text">不符</span><span class="boss-ext-reason">${result.hardFail}</span>`;
    } else {
      const score = result.score;
      badge.classList.add(score >= 85 ? 'boss-ext-pass' : score >= 70 ? 'boss-ext-maybe' : 'boss-ext-low');
      badge.innerHTML = `<span class="boss-ext-score-text">${score}分</span>`;
    }

    badge.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); showDetailPanel(result); });
    card.style.position = card.style.position || 'relative';
    card.appendChild(badge);
  }

  function showDetailPanel(result) {
    let panel = document.getElementById('boss-ext-detail');
    if (panel) panel.remove();
    panel = document.createElement('div');
    panel.id = 'boss-ext-detail';
    let html = `<div class="boss-ext-panel-header"><h3>筛选详情</h3><button onclick="this.closest('#boss-ext-detail').remove()">✕</button></div><div class="boss-ext-panel-body">`;
    if (result.autoFilterReason) {
      html += `<div class="boss-ext-panel-status reject">自动淘汰: ${result.autoFilterReason}</div>`;
    } else if (result.hardFail) {
      html += `<div class="boss-ext-panel-status reject">硬门槛: ${result.hardFail}</div>`;
    } else {
      const cls = result.score >= 85 ? 'pass' : result.score >= 70 ? 'maybe' : 'low';
      html += `<div class="boss-ext-panel-status ${cls}">匹配分: ${result.score} / 100</div>`;
      if (result.breakdown) {
        html += '<div class="boss-ext-breakdown"><h4>分项评分</h4><table>';
        for (const [key, val] of Object.entries(result.breakdown)) {
          html += `<tr><td class="bd-label">${key}</td><td class="bd-bar"><div class="bd-fill" style="width:${Math.min(val*4,100)}%"></div></td><td class="bd-val">${val}</td></tr>`;
        }
        html += '</table></div>';
      }
      if (result.risks && result.risks.length) {
        html += '<div class="boss-ext-risks"><h4>风险提示</h4><ul>';
        result.risks.forEach(r => html += `<li>⚠ ${r}</li>`);
        html += '</ul></div>';
      }
    }
    html += '</div>';
    panel.innerHTML = html;
    document.body.appendChild(panel);
  }

  function injectActionButtons(card, candidate) {
    if (card.querySelector('.boss-ext-actions')) return;
    const wrap = document.createElement('div');
    wrap.className = 'boss-ext-actions';

    const importBtn = createBtn('📥 导入', async () => {
      importBtn.textContent = '导入中...';
      importBtn.disabled = true;
      try {
        const result = await importCandidate(candidate);
        importBtn.textContent = '✅ 已导入';
        importBtn.classList.add('boss-ext-btn-done');
        importedCandidates.set(candidate.name, result);

        if (result.resume_id && defaultPositionId) {
          const matchBtn = createBtn('🎯 JD匹配', async () => {
            matchBtn.textContent = '匹配中...';
            try {
              const mr = await apiCall('POST', `/api/pipeline/jd-match/${result.resume_id}`, null);
              matchBtn.textContent = `🎯 ${Math.round(mr.score || 0)}分`;
              matchBtn.classList.add('boss-ext-btn-done');
            } catch { matchBtn.textContent = '匹配失败'; }
          });
          wrap.appendChild(matchBtn);
        }

        if (result.resume_id) {
          const msgBtn = createBtn('💬 约面', async () => {
            msgBtn.textContent = '生成中...';
            try {
              const mr = await apiCall('POST', `/api/pipeline/generate-message/${result.resume_id}`);
              copyToClipboard(mr.message || mr.content || '');
              showToast('约面消息已复制到剪贴板');
              msgBtn.textContent = '✅ 已复制';
            } catch (err) {
              msgBtn.textContent = '生成失败';
              showToast('消息生成失败: ' + err.message, true);
            }
          });
          wrap.appendChild(msgBtn);
        }
      } catch (err) {
        importBtn.textContent = '❌ 失败';
        showToast('导入失败: ' + err.message, true);
      }
    });
    wrap.appendChild(importBtn);
    card.style.position = card.style.position || 'relative';
    card.appendChild(wrap);
  }

  function createBtn(text, onClick) {
    const btn = document.createElement('button');
    btn.className = 'boss-ext-action-btn';
    btn.textContent = text;
    btn.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); onClick(); });
    return btn;
  }

  // ═══════════════════════════════════
  //  导入候选人
  // ═══════════════════════════════════

  async function importCandidate(candidate) {
    return apiCall('POST', '/api/extension/import-candidate', {
      candidate_name: candidate.name,
      education: candidate.education || null,
      work_years: candidate.workYears || null,
      city: candidate.city || null,
      age: candidate.age || null,
      current_company: candidate.company || null,
      current_position: candidate.position || null,
      skills: candidate.skills || [],
      boss_candidate_id: candidate.bossId || null,
      source: 'boss_extension',
      position_id: defaultPositionId ? parseInt(defaultPositionId) : null,
      raw_text: [
        candidate.name && `姓名: ${candidate.name}`,
        candidate.education && `学历: ${candidate.education}`,
        candidate.workYears && `工作年限: ${candidate.workYears}年`,
        candidate.city && `城市: ${candidate.city}`,
        candidate.company && `公司: ${candidate.company}`,
      ].filter(Boolean).join('\n'),
    });
  }

  async function importAllVisible() {
    const cards = findCandidateCards();
    let imported = 0;
    for (const card of cards) {
      const btn = card.querySelector('.boss-ext-action-btn');
      if (btn && !btn.classList.contains('boss-ext-btn-done')) {
        btn.click();
        imported++;
        await new Promise(r => setTimeout(r, 300));
      }
    }
    showToast(`已导入 ${imported} 位候选人`);
  }

  // ═══════════════════════════════════
  //  工具函数
  // ═══════════════════════════════════

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;left:-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
  }

  function showToast(msg, isError = false) {
    let toast = document.getElementById('boss-ext-toast');
    if (toast) toast.remove();
    toast = document.createElement('div');
    toast.id = 'boss-ext-toast';
    toast.className = isError ? 'boss-ext-toast-err' : '';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  function observePageChanges() {
    const observer = new MutationObserver(mutations => {
      let hasNew = false;
      for (const m of mutations) {
        if (m.addedNodes.length > 0) {
          for (const node of m.addedNodes) {
            if (node.nodeType === 1 && node.textContent && node.textContent.length > 30) { hasNew = true; break; }
          }
        }
        if (hasNew) break;
      }
      if (hasNew) {
        clearTimeout(window._bossExtDebounce);
        window._bossExtDebounce = setTimeout(() => processPage(), 800);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
