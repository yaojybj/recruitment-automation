/**
 * Boss直聘 招聘自动化助手 - Content Script
 * 在 Boss 直聘推荐页/候选人列表/聊天页注入操作按钮和匹配分数
 */

(() => {
  'use strict';

  const BOSS_GREEN = '#00BEAB';
  let enabled = true;
  let autoImport = false;
  let showBadge = true;
  let defaultPositionId = null;
  let backendUrl = 'http://localhost:8000';
  let processedCards = new WeakSet();
  let importedCandidates = new Map();
  let screener = null;

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
  }

  // ─── API 调用 ───

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

  // ─── 浮动工具栏 ───

  function injectFloatingToolbar() {
    if (document.getElementById('boss-ext-toolbar')) return;

    const bar = document.createElement('div');
    bar.id = 'boss-ext-toolbar';
    bar.innerHTML = `
      <div class="boss-ext-toolbar-inner">
        <div class="boss-ext-toolbar-title">招聘助手</div>
        <button class="boss-ext-btn" id="boss-ext-scan" title="扫描当前页候选人">
          🔍 扫描页面
        </button>
        <button class="boss-ext-btn" id="boss-ext-import-all" title="导入所有识别到的候选人">
          📥 全部导入
        </button>
        <span class="boss-ext-counter" id="boss-ext-count">0 人</span>
        <button class="boss-ext-btn boss-ext-btn-sm" id="boss-ext-minimize" title="最小化">—</button>
      </div>
    `;
    document.body.appendChild(bar);

    document.getElementById('boss-ext-scan').addEventListener('click', () => processPage());
    document.getElementById('boss-ext-import-all').addEventListener('click', importAllVisible);
    document.getElementById('boss-ext-minimize').addEventListener('click', toggleToolbar);
  }

  function toggleToolbar() {
    const bar = document.getElementById('boss-ext-toolbar');
    if (!bar) return;
    bar.classList.toggle('boss-ext-minimized');
    const btn = document.getElementById('boss-ext-minimize');
    btn.textContent = bar.classList.contains('boss-ext-minimized') ? '□' : '—';
  }

  // ─── 页面扫描 ───

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
      '.candidate-card',
      '.resume-card-wrap',
      '.card-inner',
      '[class*="candidate-wrap"]',
      '[class*="recommend-card"]',
      '.job-card-wrap',
      '.resume-item',
      '[ka*="recommend"]',
      'li[class*="item"]',
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
      name: '',
      education: '',
      workYears: 0,
      city: '',
      skills: [],
      experiences: [],
      projectCount: 0,
      hasPortfolio: false,
      company: '',
      position: '',
      age: null,
      phone: '',
      bossId: '',
    };

    const nameEl = card.querySelector(
      '[class*="name"], [class*="geek-name"], [class*="user-name"], ' +
      '[class*="title-name"], a[ka*="name"]'
    );
    if (nameEl) {
      let raw = nameEl.textContent.trim();
      raw = raw.replace(/[®©™✓✗●○◆★☆\s·|]/g, '').substring(0, 10);
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
      '[class*="tag"], [class*="label"], [class*="skill"], ' +
      'span[class*="desc"], [class*="info-desc"]'
    );
    tags.forEach(tag => {
      const tt = tag.textContent.trim();
      if (tt.length >= 1 && tt.length <= 25 && !tt.includes('天前') && !tt.includes('在线')) {
        candidate.skills.push(tt);
      }
    });

    const companyMatch = text.match(/(?:在|·|丨)\s*(.{2,20}(?:公司|集团|科技|有限|网络|互联|教育|医疗|金融|银行|证券|基金|投资|咨询|传媒|文化|信息|软件|硬件|电子|通信|游戏|电商|平台))/);
    if (companyMatch) candidate.company = companyMatch[1];

    const posMatch = text.match(/(?:求职|期望|目标)[：:]\s*(.{2,20})/);
    if (posMatch) candidate.position = posMatch[1];

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

  // ─── 注入分数徽章 ───

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

    badge.addEventListener('click', e => {
      e.stopPropagation();
      e.preventDefault();
      showDetailPanel(result);
    });

    card.style.position = card.style.position || 'relative';
    card.appendChild(badge);
  }

  function showDetailPanel(result) {
    let panel = document.getElementById('boss-ext-detail');
    if (panel) panel.remove();

    panel = document.createElement('div');
    panel.id = 'boss-ext-detail';

    let html = `
      <div class="boss-ext-panel-header">
        <h3>筛选详情</h3>
        <button onclick="this.closest('#boss-ext-detail').remove()">✕</button>
      </div>
      <div class="boss-ext-panel-body">
    `;

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
          const w = Math.min(val * 4, 100);
          html += `<tr><td class="bd-label">${key}</td><td class="bd-bar"><div class="bd-fill" style="width:${w}%"></div></td><td class="bd-val">${val}</td></tr>`;
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

  // ─── 注入操作按钮 ───

  function injectActionButtons(card, candidate) {
    const existing = card.querySelector('.boss-ext-actions');
    if (existing) return;

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
              const score = mr.score || mr.jd_match_score || 0;
              matchBtn.textContent = `🎯 ${Math.round(score)}分`;
              matchBtn.classList.add('boss-ext-btn-done');
            } catch (err) {
              matchBtn.textContent = '匹配失败';
            }
          });
          wrap.appendChild(matchBtn);
        }

        if (result.resume_id) {
          const msgBtn = createBtn('💬 约面消息', async () => {
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
    btn.addEventListener('click', e => {
      e.stopPropagation();
      e.preventDefault();
      onClick();
    });
    return btn;
  }

  // ─── 导入候选人 ───

  async function importCandidate(candidate) {
    const payload = {
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
      raw_text: buildRawText(candidate),
    };
    return apiCall('POST', '/api/extension/import-candidate', payload);
  }

  function buildRawText(c) {
    const parts = [];
    if (c.name) parts.push(`姓名: ${c.name}`);
    if (c.education) parts.push(`学历: ${c.education}`);
    if (c.workYears) parts.push(`工作年限: ${c.workYears}年`);
    if (c.city) parts.push(`城市: ${c.city}`);
    if (c.age) parts.push(`年龄: ${c.age}岁`);
    if (c.company) parts.push(`公司: ${c.company}`);
    if (c.position) parts.push(`职位: ${c.position}`);
    if (c.skills.length) parts.push(`技能: ${c.skills.join(', ')}`);
    return parts.join('\n');
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

  // ─── 辅助函数 ───

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

  // ─── MutationObserver ───

  function observePageChanges() {
    const observer = new MutationObserver(mutations => {
      let hasNew = false;
      for (const m of mutations) {
        if (m.addedNodes.length > 0) {
          for (const node of m.addedNodes) {
            if (node.nodeType === 1 && node.textContent && node.textContent.length > 30) {
              hasNew = true;
              break;
            }
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

  // ─── 启动 ───

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
