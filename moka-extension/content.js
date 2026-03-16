/**
 * Moka 招聘自动化助手 - Content Script
 * 功能：
 * 1. 轮询后台获取 moka 待办任务
 * 2. 自动在 Moka 页面上执行 RPA 操作：
 *    - moka_create_candidate：创建新候选人
 *    - moka_schedule_interview：安排面试
 * 3. 操作完成后回报后台
 */

(() => {
  'use strict';

  const MOKA_BLUE = '#4A90D9';
  let enabled = true;
  let autoExec = false;
  let backendUrl = 'http://localhost:8000';
  let pollInterval = null;
  let currentTask = null;

  async function init() {
    const stored = await chrome.storage.sync.get(['mokaEnabled', 'mokaAutoExec', 'mokaBackendUrl']);
    enabled = stored.mokaEnabled !== false;
    autoExec = stored.mokaAutoExec || false;
    backendUrl = (stored.mokaBackendUrl || 'http://localhost:8000').replace(/\/+$/, '');

    if (!enabled) return;

    injectFloatingPanel();
    startPolling();
  }

  // ═══════════════════════════════════
  //  API
  // ═══════════════════════════════════

  async function apiCall(method, endpoint, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);
    const resp = await fetch(`${backendUrl}${endpoint}`, opts);
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json();
  }

  // ═══════════════════════════════════
  //  任务轮询
  // ═══════════════════════════════════

  function startPolling() {
    if (pollInterval) return;
    pollTasks();
    pollInterval = setInterval(pollTasks, 30000);
  }

  async function pollTasks() {
    if (currentTask) return;
    try {
      const tasks = await apiCall('GET', '/api/extension/pending-tasks?platform=moka');
      updateBadge(tasks.length);

      if (!tasks || tasks.length === 0) return;

      if (autoExec) {
        for (const task of tasks) {
          await executeTask(task);
        }
      } else {
        showTaskQueue(tasks);
      }
    } catch {
      updateStatus('后台未连接', false);
    }
  }

  // ═══════════════════════════════════
  //  任务执行
  // ═══════════════════════════════════

  async function executeTask(task) {
    currentTask = task;
    updateStatus(`正在执行: ${task.task_type}`, true);

    try {
      await apiCall('POST', `/api/extension/task-start/${task.id}`);

      let result = {};
      switch (task.task_type) {
        case 'moka_create_candidate':
          result = await taskCreateCandidate(task);
          break;
        case 'moka_schedule_interview':
          result = await taskScheduleInterview(task);
          break;
        default:
          throw new Error(`未知任务类型: ${task.task_type}`);
      }

      await apiCall('POST', `/api/extension/task-complete/${task.id}`, { success: true, result });
      updateStatus(`✅ 完成: ${task.payload.candidate_name || ''}`, true);
      logAction(`✅ ${task.task_type} 完成: ${task.payload.candidate_name || ''}`);
    } catch (err) {
      await apiCall('POST', `/api/extension/task-complete/${task.id}`, { success: false, error: err.message });
      updateStatus(`❌ 失败: ${err.message}`, false);
      logAction(`❌ ${task.task_type} 失败: ${err.message}`);
    } finally {
      currentTask = null;
    }
  }

  // ═══════════════════════════════════
  //  RPA：创建候选人
  // ═══════════════════════════════════

  async function taskCreateCandidate(task) {
    const p = task.payload;

    const addBtnSelectors = [
      'button:has(span:contains("添加候选人"))',
      '[class*="add-candidate"]',
      'button[class*="create"]',
      'a[href*="candidate/create"]',
    ];

    let navigated = false;

    if (location.pathname.includes('/candidate/create') || location.pathname.includes('/candidate/add')) {
      navigated = true;
    }

    if (!navigated) {
      const addLink = document.querySelector('a[href*="/candidate/create"], a[href*="/candidate/add"]');
      if (addLink) {
        addLink.click();
        await waitForNavigation(3000);
        navigated = true;
      }
    }

    if (!navigated) {
      for (const sel of addBtnSelectors) {
        try {
          const btn = document.querySelector(sel);
          if (btn) {
            btn.click();
            await waitFor(2000);
            navigated = true;
            break;
          }
        } catch {}
      }
    }

    if (!navigated) {
      showManualGuide('create', task);
      return { manual: true, guide: '请手动点击"添加候选人"按钮' };
    }

    await waitFor(1500);

    const fieldMap = {
      '姓名': p.candidate_name,
      '手机': p.phone,
      '邮箱': p.email,
      '学历': p.education,
      '学校': p.school,
      '工作年限': p.work_years ? String(p.work_years) : '',
      '公司': p.current_company,
      '职位': p.current_position,
      '城市': p.city,
    };

    let filledCount = 0;
    for (const [label, value] of Object.entries(fieldMap)) {
      if (!value) continue;
      if (fillFormField(label, value)) filledCount++;
      await waitFor(300);
    }

    if (p.position_title) {
      fillFormField('应聘职位', p.position_title) || fillFormField('投递职位', p.position_title);
    }

    await waitFor(500);

    if (filledCount < 2) {
      showManualGuide('create', task);
      return { manual: true, filled: filledCount };
    }

    if (autoExec) {
      const submitBtn = findButton('保存') || findButton('提交') || findButton('创建');
      if (submitBtn) {
        submitBtn.click();
        await waitFor(2000);
        const mokaId = extractMokaIdFromPage();
        return { moka_candidate_id: mokaId, auto: true };
      }
    }

    showToast(`候选人 ${p.candidate_name} 的信息已填入表单，请检查后手动保存`);
    return { manual_save: true, filled: filledCount };
  }

  // ═══════════════════════════════════
  //  RPA：安排面试
  // ═══════════════════════════════════

  async function taskScheduleInterview(task) {
    const p = task.payload;

    const interviewBtnSelectors = [
      'button:has(span:contains("安排面试"))',
      '[class*="schedule-interview"]',
      'button[class*="interview"]',
    ];

    let found = false;

    const candidateLink = findElementByText('a', p.candidate_name);
    if (candidateLink) {
      candidateLink.click();
      await waitFor(2000);
    }

    for (const sel of interviewBtnSelectors) {
      try {
        const btn = document.querySelector(sel);
        if (btn) {
          btn.click();
          await waitFor(1500);
          found = true;
          break;
        }
      } catch {}
    }

    if (!found) {
      const interviewBtn = findButton('安排面试') || findButton('创建面试');
      if (interviewBtn) {
        interviewBtn.click();
        await waitFor(1500);
        found = true;
      }
    }

    if (!found) {
      showManualGuide('interview', task);
      return { manual: true, guide: '请手动打开安排面试页面' };
    }

    const interviewFields = {
      '面试日期': p.date,
      '日期': p.date,
      '开始时间': p.start_time,
      '结束时间': p.end_time,
      '面试官': p.interviewer_name,
      '面试官邮箱': p.interviewer_email,
    };

    if (p.is_online && p.meeting_link) {
      interviewFields['面试链接'] = p.meeting_link;
      interviewFields['会议链接'] = p.meeting_link;
    } else if (p.location) {
      interviewFields['面试地点'] = p.location;
      interviewFields['地点'] = p.location;
    }

    let filled = 0;
    for (const [label, value] of Object.entries(interviewFields)) {
      if (!value) continue;
      if (fillFormField(label, String(value))) filled++;
      await waitFor(300);
    }

    if (autoExec && filled >= 2) {
      const saveBtn = findButton('确定') || findButton('保存') || findButton('创建');
      if (saveBtn) {
        saveBtn.click();
        await waitFor(2000);
        return { auto: true, filled };
      }
    }

    showToast(`面试信息已填入，请检查后手动保存`);
    return { manual_save: true, filled };
  }

  // ═══════════════════════════════════
  //  DOM 操作工具
  // ═══════════════════════════════════

  function fillFormField(labelText, value) {
    const labels = document.querySelectorAll('label, .field-label, [class*="label"], [class*="form-item-label"]');
    for (const label of labels) {
      const t = label.textContent.trim();
      if (!t.includes(labelText)) continue;

      const fieldRow = label.closest('[class*="form-item"], [class*="field"], .form-group, tr') || label.parentElement;
      if (!fieldRow) continue;

      const input = fieldRow.querySelector('input:not([type="hidden"]):not([type="checkbox"]), textarea');
      if (input) {
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.dispatchEvent(new Event('blur', { bubbles: true }));
        return true;
      }

      const selectTrigger = fieldRow.querySelector('[class*="select"], [class*="dropdown"], [role="combobox"]');
      if (selectTrigger) {
        selectTrigger.click();
        setTimeout(() => {
          const options = document.querySelectorAll('[class*="option"], [role="option"], li[class*="item"]');
          for (const opt of options) {
            if (opt.textContent.trim().includes(value)) {
              opt.click();
              return;
            }
          }
        }, 500);
        return true;
      }
    }
    return false;
  }

  function findButton(text) {
    const btns = document.querySelectorAll('button, [role="button"], a.btn, [class*="btn"]');
    for (const btn of btns) {
      if (btn.textContent.trim().includes(text) && !btn.disabled) return btn;
    }
    return null;
  }

  function findElementByText(tag, text) {
    const els = document.querySelectorAll(tag);
    for (const el of els) {
      if (el.textContent.trim().includes(text)) return el;
    }
    return null;
  }

  function extractMokaIdFromPage() {
    const url = location.href;
    const match = url.match(/candidate[/s](\d+)/);
    if (match) return match[1];
    const breadcrumb = document.querySelector('[class*="breadcrumb"]');
    if (breadcrumb) {
      const idMatch = breadcrumb.textContent.match(/#(\d+)/);
      if (idMatch) return idMatch[1];
    }
    return null;
  }

  function waitFor(ms) { return new Promise(r => setTimeout(r, ms)); }

  function waitForNavigation(ms) {
    return new Promise(resolve => {
      const start = Date.now();
      const check = () => {
        if (Date.now() - start > ms) { resolve(); return; }
        if (document.readyState === 'complete') { setTimeout(resolve, 500); return; }
        setTimeout(check, 200);
      };
      check();
    });
  }

  // ═══════════════════════════════════
  //  手动操作引导
  // ═══════════════════════════════════

  function showManualGuide(type, task) {
    const p = task.payload;

    let guideHtml = '';
    if (type === 'create') {
      guideHtml = `
        <h4>创建候选人 - 手动操作指引</h4>
        <table>
          <tr><td>姓名</td><td><strong>${p.candidate_name || '-'}</strong></td></tr>
          <tr><td>手机</td><td>${p.phone || '-'}</td></tr>
          <tr><td>邮箱</td><td>${p.email || '-'}</td></tr>
          <tr><td>学历</td><td>${p.education || '-'}</td></tr>
          <tr><td>学校</td><td>${p.school || '-'}</td></tr>
          <tr><td>工作年限</td><td>${p.work_years || '-'}</td></tr>
          <tr><td>公司</td><td>${p.current_company || '-'}</td></tr>
          <tr><td>职位</td><td>${p.current_position || '-'}</td></tr>
          <tr><td>应聘</td><td>${p.position_title || '-'}</td></tr>
          <tr><td>JD 匹配分</td><td><strong>${p.jd_match_score || '-'}</strong></td></tr>
        </table>
        <p class="moka-ext-guide-hint">请在 Moka 中手动创建以上候选人并推荐给用人部门</p>
      `;
    } else if (type === 'interview') {
      guideHtml = `
        <h4>安排面试 - 手动操作指引</h4>
        <table>
          <tr><td>候选人</td><td><strong>${p.candidate_name || '-'}</strong></td></tr>
          <tr><td>职位</td><td>${p.position_title || '-'}</td></tr>
          <tr><td>日期</td><td>${p.date || '-'}</td></tr>
          <tr><td>时间</td><td>${p.start_time || '-'} - ${p.end_time || '-'}</td></tr>
          <tr><td>面试官</td><td>${p.interviewer_name || '-'}</td></tr>
          <tr><td>方式</td><td>${p.is_online ? '线上' : '线下'}</td></tr>
          <tr><td>地点/链接</td><td>${p.is_online ? (p.meeting_link || '-') : (p.location || '-')}</td></tr>
        </table>
        <p class="moka-ext-guide-hint">请在 Moka 中安排以上面试</p>
      `;
    }

    let panel = document.getElementById('moka-ext-guide');
    if (panel) panel.remove();

    panel = document.createElement('div');
    panel.id = 'moka-ext-guide';
    panel.innerHTML = `
      <div class="moka-ext-guide-header">
        <span>Moka 招聘助手 - 操作指引</span>
        <div>
          <button class="moka-ext-guide-btn done" onclick="
            document.getElementById('moka-ext-guide').dataset.action = 'done';
            document.getElementById('moka-ext-guide').remove();
          ">✅ 已完成</button>
          <button class="moka-ext-guide-btn" onclick="
            document.getElementById('moka-ext-guide').dataset.action = 'skip';
            document.getElementById('moka-ext-guide').remove();
          ">跳过</button>
        </div>
      </div>
      <div class="moka-ext-guide-body">${guideHtml}</div>
    `;
    document.body.appendChild(panel);

    const observer = new MutationObserver(() => {
      if (!document.getElementById('moka-ext-guide')) {
        observer.disconnect();
        const action = panel.dataset.action;
        if (action === 'done') {
          apiCall('POST', `/api/extension/task-complete/${task.id}`, {
            success: true, result: { manual: true },
          }).catch(() => {});
        }
      }
    });
    observer.observe(document.body, { childList: true });
  }

  // ═══════════════════════════════════
  //  悬浮面板
  // ═══════════════════════════════════

  function injectFloatingPanel() {
    if (document.getElementById('moka-ext-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'moka-ext-panel';
    panel.innerHTML = `
      <div class="moka-ext-panel-header" id="moka-ext-header">
        <span class="moka-ext-panel-title">Moka 助手</span>
        <span class="moka-ext-badge" id="moka-ext-badge" style="display:none">0</span>
        <button class="moka-ext-panel-toggle" id="moka-ext-toggle">—</button>
      </div>
      <div class="moka-ext-panel-body" id="moka-ext-body">
        <div class="moka-ext-status" id="moka-ext-status">就绪</div>
        <div class="moka-ext-task-list" id="moka-ext-tasks"></div>
        <div class="moka-ext-log" id="moka-ext-log"></div>
      </div>
    `;
    document.body.appendChild(panel);

    document.getElementById('moka-ext-toggle').addEventListener('click', () => {
      panel.classList.toggle('moka-ext-minimized');
      const btn = document.getElementById('moka-ext-toggle');
      btn.textContent = panel.classList.contains('moka-ext-minimized') ? '□' : '—';
    });

    makeDraggable(panel, document.getElementById('moka-ext-header'));
  }

  function makeDraggable(el, handle) {
    let startX, startY, startLeft, startTop;
    handle.addEventListener('mousedown', e => {
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      startLeft = rect.left;
      startTop = rect.top;
      e.preventDefault();

      const onMove = e2 => {
        el.style.left = `${startLeft + e2.clientX - startX}px`;
        el.style.top = `${startTop + e2.clientY - startY}px`;
        el.style.right = 'auto';
        el.style.bottom = 'auto';
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  function updateBadge(count) {
    const badge = document.getElementById('moka-ext-badge');
    if (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
  }

  function updateStatus(text, ok) {
    const el = document.getElementById('moka-ext-status');
    if (el) {
      el.textContent = text;
      el.style.color = ok ? '#52c41a' : '#ff4d4f';
    }
  }

  function logAction(text) {
    const log = document.getElementById('moka-ext-log');
    if (!log) return;
    const line = document.createElement('div');
    line.className = 'moka-ext-log-line';
    const now = new Date().toLocaleTimeString('zh-CN');
    line.textContent = `[${now}] ${text}`;
    log.insertBefore(line, log.firstChild);
    while (log.children.length > 20) log.removeChild(log.lastChild);
  }

  function showTaskQueue(tasks) {
    const list = document.getElementById('moka-ext-tasks');
    if (!list) return;
    list.innerHTML = '';

    for (const task of tasks) {
      const item = document.createElement('div');
      item.className = 'moka-ext-task-item';
      const typeLabel = {
        'moka_create_candidate': '创建候选人',
        'moka_schedule_interview': '安排面试',
      }[task.task_type] || task.task_type;

      item.innerHTML = `
        <div class="moka-ext-task-info">
          <span class="moka-ext-task-type">${typeLabel}</span>
          <span class="moka-ext-task-name">${task.payload.candidate_name || ''}</span>
        </div>
        <button class="moka-ext-task-exec" data-task-id="${task.id}">执行</button>
      `;
      list.appendChild(item);

      item.querySelector('.moka-ext-task-exec').addEventListener('click', () => executeTask(task));
    }
  }

  function showToast(msg, isError = false) {
    let toast = document.getElementById('moka-ext-toast');
    if (toast) toast.remove();
    toast = document.createElement('div');
    toast.id = 'moka-ext-toast';
    toast.className = isError ? 'moka-ext-toast-err' : '';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
