/* ═══════════════════════════════════════════════════════════
   牛马工具 2.0 — 前端逻辑 (Marvis 风)
   ═══════════════════════════════════════════════════════════ */

// ── 桥接 ──
// PyWebView 通过 evaluate_js 异步注入 window.pywebview，
// 不会在脚本首次运行时立即可用，需监听 pywebviewready 事件。

let _api = null;
let _readyResolve = null;
const _ready = new Promise(resolve => { _readyResolve = resolve; });

function initApi() {
  // 优先从 pywebviewready 事件获取
  if (window.pywebview && window.pywebview.api) {
    _api = window.pywebview.api;
    console.log('[app] PyWebView API 已就绪');
    return;
  }
  // fallback: pywebview 6.x 可能直接在 window 上暴露方法名
  // 尝试通过 window.pywebview 访问
}

// 监听 PyWebView 就绪事件
window.addEventListener('pywebviewready', function() {
  initApi();
  if (_readyResolve) { _readyResolve(); _readyResolve = null; }
});

// 兜底轮询（2 秒内每 100ms 检查一次）
let _pollCount = 0;
const _pollMax = 20;
const _pollTimer = setInterval(function() {
  _pollCount++;
  if (_api) {
    clearInterval(_pollTimer);
    return;
  }
  if (window.pywebview && window.pywebview.api) {
    initApi();
    if (_readyResolve) { _readyResolve(); _readyResolve = null; }
    clearInterval(_pollTimer);
    // 启动时自动检测登录状态
    autoStartupLogin();
    return;
  }
  if (_pollCount >= _pollMax) {
    clearInterval(_pollTimer);
    // 仍然没有 API，标记为降级模式
    _readyResolve(); _readyResolve = null;
  }
}, 100);

async function call(method, ...args) {
  await _ready;
  if (!_api) return { ok: false, error: '连接后端失败' };
  try { return await _api[method](...args); } catch (e) { return { ok: false, error: String(e) }; }
}

// ── 状态 ──
const state = {
  currentModule: 'daily',
  currentPage: 'workspace',
  running: false,
  aiRunning: false,
  aiGenerated: false,
};

// ── DOM 引用 ──
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ── 视图切换 ──
function showView(name) {
  $$('.view').forEach(v => v.classList.remove('active'));
  const el = $('#view-' + name);
  if (el) el.classList.add('active');
}

// ── 启动时自动登录 ──
async function autoStartupLogin() {
  const status = await call('auto_login_status');
  if (status && status.has_credentials) {
    // 有已保存凭据 → 直接进主界面（不闪登录页）
    const r = await call('try_auto_login');
    if (r && r.ok) {
      showView('main');
      await initMain();
      return;
    }
  }
  // 无凭据或自动登录失败 → 显示登录页
  showView('login');
  bindLoginEnter();
  const u = await call('get_account');
  if (u && u.username) {
    $('#login-username').value = u.username;
  }
}

// ── 页面切换 ──
function switchPage(name) {
  // AI生成期间禁止切换Tab
  if (_aiGenerating) {
    showToast('AI正在生成中，请稍候再切换页面', false);
    return;
  }
  
  if (state.currentModule === 'daily' && !['workspace','config','schedule'].includes(name)) return;
  if (state.currentModule === 'checklist' && !['checklist','reply'].includes(name)) return;
  if (state.currentModule === 'mystery' && !['mystery'].includes(name)) return;

  if (state.currentPage === 'mystery' && name !== 'mystery') {
    const letterCard = $('#bpe-letter-card');
    if (letterCard) {
      letterCard.remove();
      call('mystery_letter_mark_seen');
    }
  }

  state.currentPage = name;
  $$('#sidebar .nav-item.active').forEach(b => b.classList.remove('active'));
  const btn = $(`#sidebar .nav-item[data-page="${name}"]`);
  if (btn) btn.classList.add('active');
  $$('.page.active').forEach(p => p.classList.remove('active'));
  const pg = $('#page-' + name);
  if (pg) pg.classList.add('active');
  // 初始化各页面
  if (name === 'workspace') refreshWorkspace();
  if (name === 'config') initConfigPage();
  if (name === 'schedule') initSchedulePage();
  if (name === 'checklist') initChecklistPage();
  if (name === 'reply') initReplyPage();
  if (name === 'mystery') initMysteryPage();
}

// ── 模块切换 ──
function switchModule(mod) {
  // AI生成期间禁止切换模块
  if (_aiGenerating) {
    showToast('AI正在生成中，请稍候再切换模块', false);
    return;
  }
  
  if (mod === state.currentModule) return;
  // 神秘工具每次进入需确认（作者账号豁免）
  if (mod === 'mystery') {
    const curUser = ($('#topbar-user').textContent || '').replace(/用户[：:]/, '').trim();
    if (curUser !== '15797813736') {
      const agree = confirm('泄露作者私人信息，自愿双亲升天，请问你是否赞同？');
      if (!agree) return;
    }
  }
  state.currentModule = mod;
  $$('.seg-btn').forEach(b => b.classList.toggle('active', b.dataset.module === mod));
  $('#nav-daily').classList.toggle('hidden', mod !== 'daily');
  $('#nav-checklist').classList.toggle('hidden', mod !== 'checklist');
  const navMystery = $('#nav-mystery');
  if (navMystery) navMystery.classList.toggle('hidden', mod !== 'mystery');
  const pageMap = { daily: 'workspace', checklist: 'checklist', mystery: 'mystery' };
  switchPage(pageMap[mod] || 'workspace');
}

// ═══════════════════════════════════════════════════════
// 登录
// ═══════════════════════════════════════════════════════
let _pwVisible = false;
function togglePw() {
  _pwVisible = !_pwVisible;
  const el = $('#login-password');
  el.type = _pwVisible ? 'text' : 'password';
}

// 密码输入框回车登录
function bindLoginEnter() {
  const pwEl = $('#login-password');
  if (pwEl && !pwEl._enterBound) {
    pwEl._enterBound = true;
    pwEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doLogin();
    });
  }
}

async function doLogin() {
  const u = $('#login-username').value.trim();
  const p = $('#login-password').value.trim();
  if (!u || !p) { showLoginError('手机号和密码不能为空'); return; }
  setLoginLoading(true);
  const r = await call('login', u, p);
  setLoginLoading(false);
  if (r && r.ok) {
    // 短暂显示登录成功标识
    $('#login-btn').textContent = '登录成功 ✓';
    $('#login-btn').style.background = '#22C55E';
    $('#login-btn').disabled = true;
    setTimeout(() => {
      showView('main');
      initMain();
      $('#login-btn').textContent = '登 录';
      $('#login-btn').style.background = '';
      $('#login-btn').disabled = false;
    }, 600);
  } else {
    showLoginError((r && r.error) || '保存配置失败');
  }
}
function showLoginError(msg) {
  const el = $('#login-error');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function setLoginLoading(on) {
  $('#login-btn').disabled = on;
  $('#login-loading').classList.toggle('hidden', !on);
  $('#login-error').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════
// 主界面初始化
// ═══════════════════════════════════════════════════════
async function initMain() {
  const cfg = await call('get_all_config');
  if (!cfg) return;
  const acc = cfg.account || {};
  $('#topbar-user').textContent = acc.username ? '用户：' + acc.username : '';
  $('#version-tag').textContent = cfg.version || '--';
  $('#auto-submit-sw').checked = !!cfg.auto_submit;
  // 只检查字段2-8（索引1开始）是否有AI生成的内容，不包括字段1
  if (cfg.fields) {
    const fieldLabels = Object.keys(cfg.fields);
    const fields2to8 = fieldLabels.slice(1).map(label => cfg.fields[label]);
    state.aiGenerated = fields2to8.some(v => v && v.trim());
  } else {
    state.aiGenerated = false;
  }
  await refreshWorkspace();
  startLogPoller();
  startBadgePoller();
  
  // 初始化 API 配置监听器
  initApiConfigListeners();

  // 每次打开软件自动检查更新（静默模式）
  setTimeout(() => checkUpdate(true), 1500);

  // 绑定字段1和职位描述的自动保存
  let _wsSaveTimer = null;
  function wsAutoSave() {
    clearTimeout(_wsSaveTimer);
    _wsSaveTimer = setTimeout(async () => {
      const f1 = $('#field1-input').value;
      const role = $('#role-textarea').value;
      const labels = Object.keys(await call('get_fields') || {});
      const field1Label = labels[0] || '';
      if (f1 !== undefined) {
        await call('save_field', field1Label, f1);
        $('#field1-saved').classList.toggle('hidden', !f1.trim());
      }
      if (role !== undefined) {
        const cfg = await call('get_all_config');
        const ai = cfg.ai || {};
        await call('set_ai_settings',
          ai.api_key || '',
          ai.api_url || '',
          ai.model || '',
          role
        );
        $('#role-saved').classList.toggle('hidden', !role.trim());
      }
    }, 600);
  }
  $('#field1-input').addEventListener('input', wsAutoSave);
  $('#role-textarea').addEventListener('input', wsAutoSave);
}

async function refreshWorkspace() {
  const fields = await call('get_fields');
  if (!fields) return;
  renderPreview(fields);

  // 加载字段1到独立卡片
  const labels = Object.keys(fields || {});
  const field1Label = labels[0] || '';
  const field1Content = fields[field1Label] || '';
  $('#field1-input').value = field1Content;
  if (field1Content.trim()) {
    $('#field1-saved').classList.remove('hidden');
  } else {
    $('#field1-saved').classList.add('hidden');
  }

  // 加载职位描述
  const cfg = await call('get_all_config');
  if (cfg) {
    const role = (cfg.ai && cfg.ai.prompt_template) || '';
    $('#role-textarea').value = role;
    if (role.trim()) {
      $('#role-saved').classList.remove('hidden');
    } else {
      $('#role-saved').classList.add('hidden');
    }
  }
}

// ═══════════════════════════════════════════════════════
// 预览区临时编辑状态
// ═══════════════════════════════════════════════════════
let _previewEditState = {}; // 临时编辑内容 {label: content}

function renderPreview(fields) {
  const container = $('#preview-list');
  if (!container) return;
  const labels = Object.keys(fields || {});
  if (!labels.length) { container.innerHTML = '<div class="preview-empty">暂无内容</div>'; return; }
  const hasContent = labels.some(l => (fields[l] || '').trim());
  if (!hasContent) { container.innerHTML = '<div class="preview-empty">暂无内容,请先在「内容配置」中填写字段1后使用 AI 生成</div>'; return; }
  
  // 使用索引而不是标签文本,避免特殊字符问题
  container.innerHTML = labels.map((l, index) => {
    const content = (fields[l] || '').trim();
    if (!content) return '';
    const shortLabel = l.length > 12 ? l.slice(0,12)+'…' : l;
    const editContent = _previewEditState[l] !== undefined ? _previewEditState[l] : content;
    const safeId = escapeId(l);
    return `<div class="preview-item" data-index="${index}" data-label="${escHtml(l)}">
      <div class="preview-item-header">
        <div class="preview-item-label">${escHtml(shortLabel)}</div>
      </div>
      <div class="preview-item-content" id="preview-content-${safeId}">${escHtml(editContent)}</div>
      <textarea class="preview-item-textarea hidden" id="preview-edit-${safeId}" rows="3" placeholder="临时修改内容(提交后会清除)">${escHtml(editContent)}</textarea>
      <div class="preview-edit-actions hidden" id="preview-actions-${safeId}">
        <button class="btn btn-brand btn-xs" data-action="save" data-index="${index}">保存</button>
        <button class="btn btn-ghost btn-xs" data-action="cancel" data-index="${index}">取消</button>
      </div>
    </div>`;
  }).join('');
  
  // 点击内容区域进入编辑模式
  container.querySelectorAll('.preview-item-content').forEach(contentDiv => {
    contentDiv.addEventListener('click', function(e) {
      e.stopPropagation();
      const item = this.closest('.preview-item');
      if (item) {
        const label = item.getAttribute('data-label');
        if (label) togglePreviewEdit(label);
      }
    });
    // 添加鼠标悬停提示
    contentDiv.style.cursor = 'pointer';
    contentDiv.title = '点击编辑';
  });
  
  // 保存按钮事件
  container.querySelectorAll('[data-action="save"]').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      const index = this.getAttribute('data-index');
      if (index !== null) {
        const item = container.querySelector(`.preview-item[data-index="${index}"]`);
        if (item) {
          const label = item.getAttribute('data-label');
          if (label) savePreviewEdit(label);
        }
      }
    });
  });
  
  // 取消按钮事件
  container.querySelectorAll('[data-action="cancel"]').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      const index = this.getAttribute('data-index');
      if (index !== null) {
        const item = container.querySelector(`.preview-item[data-index="${index}"]`);
        if (item) {
          const label = item.getAttribute('data-label');
          if (label) cancelPreviewEdit(label);
        }
      }
    });
  });
}

function togglePreviewEdit(label) {
  const safeId = escapeId(label);
  const contentDiv = document.getElementById(`preview-content-${safeId}`);
  const textarea = document.getElementById(`preview-edit-${safeId}`);
  const actions = document.getElementById(`preview-actions-${safeId}`);
  
  if (!contentDiv || !textarea || !actions) {
    console.warn('[preview] 找不到编辑元素:', label);
    return;
  }
  
  const isEditing = !textarea.classList.contains('hidden');
  if (isEditing) {
    // 取消编辑状态
    cancelPreviewEdit(label);
  } else {
    // 进入编辑状态
    contentDiv.classList.add('hidden');
    textarea.classList.remove('hidden');
    actions.classList.remove('hidden');
    // 延迟聚焦,避免DOM更新未完成
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.select();
    });
  }
}

function savePreviewEdit(label) {
  const safeId = escapeId(label);
  const textarea = document.getElementById(`preview-edit-${safeId}`);
  if (!textarea) {
    console.warn('[preview] 找不到textarea:', label);
    return;
  }
  
  const newContent = textarea.value.trim();
  _previewEditState[label] = newContent;
  
  // 同步到后端(静默保存,不刷新整个预览区)
  call('save_field', {label, content: newContent}).then(() => {
    // 只更新显示内容,不重新渲染整个列表
    const contentDiv = document.getElementById(`preview-content-${safeId}`);
    if (contentDiv) {
      contentDiv.textContent = newContent;
    }
    // 保存后自动关闭编辑框
    cancelPreviewEdit(label);
  }).catch(err => {
    showToast('修改失败: ' + err, 'error');
  });
}

function cancelPreviewEdit(label) {
  const safeId = escapeId(label);
  const contentDiv = document.getElementById(`preview-content-${safeId}`);
  const textarea = document.getElementById(`preview-edit-${safeId}`);
  const actions = document.getElementById(`preview-actions-${safeId}`);
  
  if (!contentDiv || !textarea || !actions) return;
  
  contentDiv.classList.remove('hidden');
  textarea.classList.add('hidden');
  actions.classList.add('hidden');
  
  // 恢复显示内容(优先使用临时状态,否则使用原始内容)
  const displayContent = _previewEditState[label] !== undefined ? _previewEditState[label] : contentDiv.textContent;
  contentDiv.textContent = displayContent;
}

// ═══════════════════════════════════════════════════════
// 日报操作
// ═══════════════════════════════════════════════════════
let _aiGenerating = false;
let _fillRunning = false;
let _fillTimeout = null;

async function triggerAIGenerate() {
  if (_aiGenerating || _fillRunning) return;
  
  // 校验字段1（付出不亚于任何人的努力）是否填写
  const field1Input = $('#field1-input');
  if (!field1Input || !field1Input.value.trim()) {
    showToast('请先填写「付出不亚于任何人的努力」', false);
    appendLogUI('error', 'AI生成失败：请先填写字段1（付出不亚于任何人的努力）');
    return;
  }
  
  // 校验职位描述是否填写
  const roleTextarea = $('#role-textarea');
  if (!roleTextarea || !roleTextarea.value.trim()) {
    showToast('请先填写「职位描述」', false);
    appendLogUI('error', 'AI生成失败：请先填写职位描述');
    return;
  }
  
  let forceOverwrite = false;
  // 如果已有AI生成的内容，询问用户是否重新生成
  if (state.aiGenerated) {
    if (!confirm('检测到已有AI生成的内容，重新生成将覆盖字段2-8的内容。是否继续？')) {
      return;
    }
    forceOverwrite = true;
  }
  
  _aiGenerating = true;
  setBtnLoading('btn-ai', true);
  const r = await call('trigger_ai_generate', forceOverwrite);
  if (r && !r.ok && r.error) {
    // 即时校验错误（如未填字段1），立即恢复按钮
    appendLogUI('error', r.error);
    showToast(r.error, false);
    setBtnLoading('btn-ai', false);
    _aiGenerating = false;
    return;
  }
  // 正常流程：AI 在后台线程生成，ai_done 事件触发时会恢复按钮
}

async function triggerFill() {
  if (_aiGenerating || _fillRunning) return;
  _fillRunning = true;
  setBtnLoading('btn-fill', true);
  const r = await call('trigger_fill');
  if (r && !r.ok && r.error) {
    // 即时校验错误（如字段不完整），立即恢复按钮
    appendLogUI('error', r.error);
    showToast(r.error, false);
    setBtnLoading('btn-fill', false);
    _fillRunning = false;
    return;
  }
  // 超时保护：3分钟后若 fill_done 仍未触发，强制恢复按钮
  _fillTimeout = setTimeout(() => {
    if (_fillRunning) {
      appendLogUI('warning', '填写超时，已恢复按钮状态');
      setBtnLoading('btn-fill', false);
      _fillRunning = false;
    }
  }, 180000);
}

function setBtnLoading(id, on) {
  const btn = $('#' + id);
  if (!btn) return;
  btn.disabled = on;
  if (on) btn.innerHTML = '<span class="spinner"></span> 处理中...';
  else if (id === 'btn-ai') btn.innerHTML = '&#x2728; AI 智能生成';
  else btn.innerHTML = '&#x1F680; 一键填写日报';
}

async function toggleAutoSubmit() {
  const on = $('#auto-submit-sw').checked;
  await call('set_auto_submit', on);
}

async function workspaceClearFields() {
  const fields = await call('get_fields');
  if (!fields) return;
  // 保留字段1(基准字段),清空其余字段2-8
  const labels = Object.keys(fields || {});
  const field1Label = labels[0] || '';
  const cleared = {};
  labels.forEach(l => {
    cleared[l] = l === field1Label ? (fields[l] || '') : '';
  });
  await call('save_all_fields', cleared);
  _previewEditState = {}; // 清空临时编辑状态
  state.aiGenerated = false;
  await refreshWorkspace();
  showToast('已清空日报内容');
}

// ═══════════════════════════════════════════════════════
// 日志
// ═══════════════════════════════════════════════════════
function appendLogUI(level, msg) {
  const box = $('#log-box');
  if (!box) return;
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const line = document.createElement('div');
  line.className = 'log-line ' + level;
  line.textContent = `[${ts}] ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
  // 限制行数
  while (box.children.length > 500) box.firstChild.remove();
}

function clearLog() {
  const box = $('#log-box');
  if (box) box.innerHTML = '';
}

function copyLog() {
  const box = $('#log-box');
  if (!box) return;
  const logText = box.innerText || box.textContent;
  if (!logText || !logText.trim()) {
    showToast('日志为空，无法复制', false);
    return;
  }
  
  // 使用 Clipboard API 复制
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(logText).then(() => {
      showToast('日志已复制到剪贴板');
    }).catch(err => {
      // 降级方案：使用 execCommand
      fallbackCopyLog(logText);
    });
  } else {
    // 降级方案：使用 execCommand
    fallbackCopyLog(logText);
  }
}

function fallbackCopyLog(text) {
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const success = document.execCommand('copy');
    document.body.removeChild(textarea);
    if (success) {
      showToast('日志已复制到剪贴板');
    } else {
      showToast('复制失败，请手动选择日志内容', false);
    }
  } catch (err) {
    showToast('复制失败: ' + err.message, false);
  }
}

async function flushLogs() {
  const items = await call('pull_logs');
  if (items && items.length) {
    items.forEach(item => appendLogUI(item.level || 'info', item.msg));
  }
}

let _logPoller = null;
function startLogPoller() {
  if (_logPoller) return;
  _logPoller = setInterval(flushLogs, 500);
}

// ── Badge 轮询 ──
let _badgePoller = null;
function startBadgePoller() {
  if (_badgePoller) return;
  // 立即执行一次，不等15秒
  refreshBadge();
  _badgePoller = setInterval(refreshBadge, 5000);
}

async function refreshBadge() {
  const tasks = await call('reply_get_tasks');
  if (!tasks || !tasks.ok) return;
  const total = tasks.total_pending || 0;
  const badge = $('#reply-badge');
  if (badge) {
    badge.textContent = total || '';
    badge.classList.toggle('hidden', total === 0);
  }
  // 同时更新回复/评价页的计数（如果已加载）
  if (_replyLoaded) {
    const replyCount = tasks.reply_count || 0;
    const evalCount = tasks.eval_count || 0;
    $('#reply-count').textContent = '待回复 ' + replyCount + ' 条';
    $('#eval-count').textContent = '待评价 ' + evalCount + ' 条';
    $('#reply-count').classList.toggle('badge-alert', replyCount > 0);
    $('#eval-count').classList.toggle('badge-alert', evalCount > 0);
  }
}

// ═══════════════════════════════════════════════════════
// Python 事件推送处理
// ═══════════════════════════════════════════════════════
function handleEvent(payload) {
  try {
    const { type, data } = payload;
    switch (type) {
      case 'log':
        appendLogUI(data.level || 'info', data.msg);
        break;
      case 'ai_done':
        _aiGenerating = false;
        setBtnLoading('btn-ai', false);
        if (data.error) showToast(data.error, false);
        else { showToast('AI 智能生成完成'); refreshWorkspace(); }
        break;
      case 'fill_done':
        clearTimeout(_fillTimeout);
        _fillRunning = false;
        setBtnLoading('btn-fill', false);
        _previewEditState = {}; // 提交后清除临时编辑状态
        if (data.success) { showToast('日报填写成功'); refreshWorkspace(); }
        else showToast('填写失败，请查看日志', false);
        break;
      case 'bpe_done': {
        _bpeRunning = false;
        const bpeBtn = $('#bpe-start-btn');
        if (bpeBtn) {
          bpeBtn.disabled = false;
          bpeBtn.innerHTML = '&#x1F680; 开始执行';
        }
        if (data.ok) { showToast('BPE 任务完成'); }
        else showToast('BPE 任务失败: ' + (data.msg || ''), false);
        break;
      }
      case 'update_progress':
        if (data) {
          const pct = data.percent || 0;
          $('#update-progress-fill').style.width = pct + '%';
          $('#update-progress-text').textContent = `正在下载... ${pct}% (${data.downloaded_mb || 0}MB / ${data.total_mb || 0}MB)`;
        }
        break;
      case 'update_complete':
        if (data && data.ok) {
          $('#update-progress-text').textContent = '下载完成！请点击更新完成按钮重启。';
          $('#update-progress-fill').style.width = '100%';
          $('#update-progress-fill').style.background = '#22C55E';
          $('#update-finish-btn').classList.remove('hidden');
          _updatePath = data.path;
          appendLogUI('success', '下载完成，等待应用更新...');
        } else {
          $('#update-progress-text').textContent = '下载失败';
          $('#update-cancel-btn').classList.remove('hidden');
          $('#update-confirm-btn').classList.remove('hidden');
          $('#update-confirm-btn').textContent = '重试';
          appendLogUI('error', '下载失败: ' + ((data && data.error) || '未知'));
        }
        break;
      case 'fetch_state':
        if (data && typeof data.running !== 'undefined') {
          _fillRunning = data.running;
          if (!data.running) {
            clearTimeout(_fillTimeout);
            setBtnLoading('btn-fill', false);
          }
        }
        break;
    }
  } catch(e) { console.error('[app] handleEvent error', e); }
}

// ═══════════════════════════════════════════════════════
// 退出 / 更新
// ═══════════════════════════════════════════════════════
function minimizeWindow() {
  call('minimize_window');
}

async function doLogout() {
  const r = await call('logout');
  if (r && r.ok) {
    showView('login');
    bindLoginEnter();
    $('#login-username').value = r.username || '';
    $('#login-password').value = '';
  }
}

// ═══════════════════════════════════════════════════════
// API 配置弹窗
// ═══════════════════════════════════════════════════════

/**
 * 填充模型版本下拉框
 * @param {string} vendor - 厂商标识
 * @param {string} currentModel - 当前选中的模型
 */
function populateModelVersions(vendor, currentModel) {
  const select = $('#api-model-version-select');
  if (!select) return;
  
  // 清空现有选项
  select.innerHTML = '';
  
  const models = VENDOR_MODELS[vendor];
  if (!models || models.length === 0) {
    select.innerHTML = '<option value="">无可用模型</option>';
    return;
  }
  
  // 填充选项
  models.forEach(m => {
    const option = document.createElement('option');
    option.value = m.value;
    option.textContent = m.label;
    if (m.value === currentModel) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

// 存储各厂商的 API Key（内存中临时保存）
const vendorApiKeys = {};

// AI 服务切换事件
if ($('#api-model-select')) {
  $('#api-model-select').addEventListener('change', function() {
    const vendor = this.value;
    const customGroup = $('#custom-model-group');
    const versionGroup = $('#model-version-group');
    const apiKeyInput = $('#api-key-input');
    
    // 保存当前厂商的 API Key
    const previousVendor = this.dataset.previousVendor;
    if (previousVendor && apiKeyInput.value) {
      vendorApiKeys[previousVendor] = apiKeyInput.value;
    }
    
    // 更新 previousVendor
    this.dataset.previousVendor = vendor;
    
    if (vendor === 'custom') {
      customGroup.classList.remove('hidden');
      versionGroup.classList.add('hidden');
      // 自定义模式不清空 Key，保留用户输入
    } else if (VENDOR_MODELS[vendor]) {
      customGroup.classList.add('hidden');
      versionGroup.classList.remove('hidden');
      // 填充该厂商的模型版本
      populateModelVersions(vendor, MODEL_URL_MAP[vendor]?.model);
      // 更新 URL
      $('#api-url-input').value = MODEL_URL_MAP[vendor].url;
      
      // 恢复该厂商之前保存的 API Key，如果没有则清空
      apiKeyInput.value = vendorApiKeys[vendor] || '';
    }
  });
}

// 模型到 API URL 的映射表（厂商 -> URL + 默认模型）
const MODEL_URL_MAP = {
  'deepseek': { url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  'openai': { url: 'https://api.openai.com/v1', model: 'gpt-3.5-turbo' },
  'qwen': { url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-turbo' },
  'glm': { url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  'moonshot': { url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  'doubao': { url: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-2-0-lite-260428' },
};

// 各厂商的模型版本列表
const VENDOR_MODELS = {
  'doubao': [
    { value: 'doubao-seed-2-0-lite-260428', label: 'Doubao-Seed-2.0-lite (推荐)' },
    { value: 'doubao-seed-2-0-mini-260428', label: 'Doubao-Seed-2.0-mini (最省token)' },
    { value: 'doubao-seed-2-0-pro-260215', label: 'Doubao-Seed-2.0-pro (更强)' },
  ],
  'deepseek': [
    { value: 'deepseek-chat', label: 'DeepSeek-Chat (推荐)' },
    { value: 'deepseek-reasoner', label: 'DeepSeek-Reasoner (推理)' },
  ],
  'openai': [
    { value: 'gpt-3.5-turbo', label: 'GPT-3.5-Turbo (推荐)' },
    { value: 'gpt-4', label: 'GPT-4' },
    { value: 'gpt-4-turbo', label: 'GPT-4-Turbo' },
  ],
  'qwen': [
    { value: 'qwen-turbo', label: 'Qwen-Turbo (推荐)' },
    { value: 'qwen-plus', label: 'Qwen-Plus' },
    { value: 'qwen-max', label: 'Qwen-Max (最强)' },
  ],
  'glm': [
    { value: 'glm-4-flash', label: 'GLM-4-Flash (推荐，最快)' },
    { value: 'glm-4', label: 'GLM-4' },
    { value: 'glm-4-plus', label: 'GLM-4-Plus (更强)' },
  ],
  'moonshot': [
    { value: 'moonshot-v1-8k', label: 'Moonshot-8K (推荐)' },
    { value: 'moonshot-v1-32k', label: 'Moonshot-32K' },
    { value: 'moonshot-v1-128k', label: 'Moonshot-128K' },
  ],
};

// 反向映射：模型 -> 厂商标识
const MODEL_TO_PROVIDER = {
  'deepseek-chat': 'deepseek',
  'deepseek-reasoner': 'deepseek',
  'gpt-3.5-turbo': 'openai',
  'gpt-4': 'openai',
  'gpt-4-turbo': 'openai',
  'qwen-turbo': 'qwen',
  'qwen-plus': 'qwen',
  'qwen-max': 'qwen',
  'glm-4-flash': 'glm',
  'glm-4': 'glm',
  'glm-4-plus': 'glm',
  'moonshot-v1-8k': 'moonshot',
  'moonshot-v1-32k': 'moonshot',
  'moonshot-v1-128k': 'moonshot',
  'doubao-seed-2-0-lite-260428': 'doubao',
  'doubao-seed-2-0-mini-260428': 'doubao',
  'doubao-seed-2-0-pro-260215': 'doubao',
};

async function openApiConfigModal() {
  const modal = $('#api-config-modal');
  if (!modal) return;
  
  // 加载当前配置
  const cfg = await call('get_all_config');
  if (!cfg) return;
  
  const ai = cfg.ai || {};
  const model = ai.model || 'doubao-seed-2-0-lite-260428';
  const apiKey = ai.api_key || '';
  const apiUrl = ai.api_url || '';
  
  // 保存当前配置到 vendorApiKeys
  const currentProvider = MODEL_TO_PROVIDER[model];
  if (currentProvider && apiKey) {
    vendorApiKeys[currentProvider] = apiKey;
  }
    
  // 设置服务选择
  const modelSelect = $('#api-model-select');
  const provider = MODEL_TO_PROVIDER[model]; // 将具体模型转换为厂商标识
  const providers = ['doubao', 'deepseek', 'openai', 'qwen', 'glm', 'moonshot'];
    
  // 初始化 previousVendor
  // 如果模型无法识别(旧配置中的未知模型),默认使用豆包
  modelSelect.dataset.previousVendor = (provider && providers.includes(provider)) ? provider : 'doubao';
    
  if (provider && providers.includes(provider)) {
    modelSelect.value = provider;
    $('#custom-model-group').classList.add('hidden');
    $('#model-version-group').classList.remove('hidden');
    // 填充模型版本选项
    populateModelVersions(provider, model);
    // 自动填充对应的 URL
    $('#api-url-input').value = MODEL_URL_MAP[provider].url;
    // 恢复该厂商的 API Key
    $('#api-key-input').value = vendorApiKeys[provider] || apiKey;
  } else {
    // 无法识别的模型(如旧版DeepSeek配置),默认显示豆包并清空Key
    modelSelect.value = 'doubao';
    $('#custom-model-group').classList.add('hidden');
    $('#model-version-group').classList.remove('hidden');
    // 填充豆包的模型版本选项
    populateModelVersions('doubao', 'doubao-seed-2-0-lite-260428');
    // 自动填充豆包 URL
    $('#api-url-input').value = MODEL_URL_MAP['doubao'].url;
    // 清空旧厂商的 API Key(不同厂商Key不通用)
    $('#api-key-input').value = '';
  }
  
  modal.classList.remove('hidden');
}

function closeApiConfigModal() {
  const modal = $('#api-config-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveApiConfig() {
  const providerSelect = $('#api-model-select').value;
  let model;
  let apiUrl;
  
  if (providerSelect === 'custom') {
    model = $('#api-custom-model').value.trim();
    apiUrl = $('#api-url-input').value.trim();
    if (!model) {
      showToast('请输入自定义模型名称', false);
      return;
    }
  } else {
    // 预定义服务：使用用户选择的模型版本
    const versionSelect = $('#api-model-version-select');
    model = versionSelect ? versionSelect.value : MODEL_URL_MAP[providerSelect].model;
    apiUrl = $('#api-url-input').value.trim();
    
    if (!model) {
      showToast('请选择模型版本', false);
      return;
    }
  }
  
  const apiKey = $('#api-key-input').value.trim();
  
  if (!apiKey) {
    showToast('请填写 API Key', false);
    return;
  }
  if (!apiUrl) {
    showToast('请选择或输入有效的 API URL', false);
    return;
  }
  
  // 调用后端保存（职位描述保持原有值，不通过此弹窗修改）
  const cfg = await call('get_all_config');
  const ai = cfg.ai || {};
  const r = await call('set_ai_settings', apiKey, apiUrl, model, ai.prompt_template || '');
  if (r && r.ok) {
    showToast('API 配置已保存');
    closeApiConfigModal();
    // 刷新工作区以更新职位描述显示
    if (state.currentPage === 'workspace') {
      await refreshWorkspace();
    }
  } else {
    showToast('保存失败: ' + ((r && r.error) || '未知'), false);
  }
}

// ═══════════════════════════════════════════════════════
// 快速模型选择（小齿轮按钮）
// ═══════════════════════════════════════════════════════

/**
 * 打开模型选择弹窗
 */
async function openModelSelector() {
  const modal = $('#model-selector-modal');
  if (!modal) return;
  
  // 加载当前配置
  const cfg = await call('get_all_config');
  if (!cfg) return;
  
  const ai = cfg.ai || {};
  const currentModel = ai.model || 'doubao-seed-2-0-lite-260428';
  
  // 识别当前厂商
  const provider = MODEL_TO_PROVIDER[currentModel] || 'doubao';
  const providerNames = {
    'doubao': '豆包',
    'deepseek': 'DeepSeek',
    'openai': 'OpenAI',
    'qwen': '通义千问',
    'glm': '智谱',
    'moonshot': '月之暗面'
  };
  
  // 显示当前厂商名称
  $('#current-provider-name').textContent = providerNames[provider] || '豆包';
  
  // 填充该厂商的模型版本列表
  const select = $('#quick-model-select');
  if (select) {
    select.innerHTML = '';
    const models = VENDOR_MODELS[provider];
    if (models && models.length > 0) {
      models.forEach(m => {
        const option = document.createElement('option');
        option.value = m.value;
        option.textContent = m.label;
        if (m.value === currentModel) {
          option.selected = true;
        }
        select.appendChild(option);
      });
    } else {
      select.innerHTML = '<option value="">无可用模型</option>';
    }
  }
  
  modal.classList.remove('hidden');
}

/**
 * 关闭模型选择弹窗
 */
function closeModelSelector() {
  const modal = $('#model-selector-modal');
  if (modal) modal.classList.add('hidden');
}

/**
 * 保存快速模型选择
 */
async function saveQuickModel() {
  const newModel = $('#quick-model-select').value;
  if (!newModel) {
    showToast('请选择模型版本', false);
    return;
  }
  
  // 获取当前配置
  const cfg = await call('get_all_config');
  if (!cfg) return;
  
  const ai = cfg.ai || {};
  const apiKey = ai.api_key || '';
  const apiUrl = ai.api_url || '';
  const promptTemplate = ai.prompt_template || '';
  
  if (!apiKey) {
    showToast('请先配置 API Key', false);
    closeModelSelector();
    openApiConfigModal();
    return;
  }
  
  // 只更新模型，其他配置保持不变
  const r = await call('set_ai_settings', apiKey, apiUrl, newModel, promptTemplate);
  if (r && r.ok) {
    const provider = MODEL_TO_PROVIDER[newModel] || 'doubao';
    const providerNames = {
      'doubao': '豆包',
      'deepseek': 'DeepSeek',
      'openai': 'OpenAI',
      'qwen': '通义千问',
      'glm': '智谱',
      'moonshot': '月之暗面'
    };
    showToast(`已切换至 ${providerNames[provider]} 模型`);
    appendLogUI('success', `模型已切换为: ${newModel}`);
    closeModelSelector();
  } else {
    showToast('切换失败: ' + ((r && r.error) || '未知'), false);
  }
}

// 模型选择变更时显示/隐藏自定义模型输入框，并自动填充 URL
function initApiConfigListeners() {
  const modelSelect = $('#api-model-select');
  if (modelSelect && !modelSelect._changeBound) {
    modelSelect._changeBound = true;
    modelSelect.addEventListener('change', function() {
      const customGroup = $('#custom-model-group');
      const urlInput = $('#api-url-input');
      if (this.value === 'custom') {
        customGroup.classList.remove('hidden');
        // 自定义模型不清空 URL，保留用户之前输入的
      } else {
        customGroup.classList.add('hidden');
        // 预定义服务自动填充对应的 URL
        const mapping = MODEL_URL_MAP[this.value];
        if (mapping) {
          urlInput.value = mapping.url;
        }
      }
    });
  }
}

async function checkUpdate(auto = false) {
  const r = await call('check_for_updates');
  if (!r) return;
  if (r.ok && r.need_update) {
    appendLogUI('info', '发现新版本！');
    
    // 优先读取本地 CHANGELOG.txt，如果失败则使用远端 changelog
    let changelogText = '';
    const localChangelog = await call('read_local_changelog');
    if (localChangelog && localChangelog.ok) {
      changelogText = localChangelog.content;
    } else {
      changelogText = r.changelog || '暂无更新日志';
    }
    
    // 弹窗展示更新内容
    $('#update-changelog').textContent = changelogText;
    $('#update-progress-container').classList.add('hidden');
    $('#update-cancel-btn').classList.remove('hidden');
    $('#update-confirm-btn').classList.remove('hidden');
    $('#update-finish-btn').classList.add('hidden');
    $('#update-modal').classList.remove('hidden');
  } else if (r.ok) {
    if (!auto) {
      appendLogUI('info', '当前已是最新版本');
      showToast('当前已是最新版本');
    }
  } else {
    if (!auto) {
      appendLogUI('error', '检查更新失败: ' + (r.error || '未知'));
      showToast('检查更新失败: ' + (r.error || '未知'), false);
    }
  }
}

function closeUpdateModal() {
  $('#update-modal').classList.add('hidden');
}

let _updatePath = '';

async function startUpdate() {
  $('#update-cancel-btn').classList.add('hidden');
  $('#update-confirm-btn').classList.add('hidden');
  $('#update-progress-container').classList.remove('hidden');
  $('#update-progress-fill').style.width = '0%';
  $('#update-progress-text').textContent = '准备下载...';
  appendLogUI('info', '正在下载更新...');
  
  const dl = await call('download_and_update');
  if (!dl || !dl.ok) {
    appendLogUI('error', '下载失败: ' + ((dl && dl.error) || '未知'));
    $('#update-progress-text').textContent = '下载失败';
    $('#update-cancel-btn').classList.remove('hidden');
    $('#update-confirm-btn').classList.remove('hidden');
    $('#update-confirm-btn').textContent = '重试';
  }
}

async function finishUpdate() {
  if (_updatePath) {
    await call('apply_update', _updatePath);
  }
}

// ═══════════════════════════════════════════════════════
// Toast
// ═══════════════════════════════════════════════════════
let _toastTimer = null;
function showToast(msg, success = true) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = (success ? '✓ ' : '✗ ') + msg;
  el.style.background = success ? '#22C55E' : '#EF4444';
  el.classList.remove('hidden');
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    el.classList.remove('show');
    el.classList.add('hidden');
  }, 2800);
}

// ═══════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escapeId(s) {
  return s.replace(/[^a-zA-Z0-9]/g, '_');
}

// ═══════════════════════════════════════════════════════
// 启动
// ═══════════════════════════════════════════════════════
(async function boot() {
  // 等待 PyWebView API 注入完成
  await _ready;
  if (!_api) {
    showView('login');
    showLoginError('后端连接不可用，请重启应用');
    return;
  }
  const need = await call('needs_login');
  if (need) {
    const acc = await call('get_account');
    if (acc && acc.username) $('#login-username').value = acc.username;
    showView('login');
  } else {
    showView('main');
    await initMain();
  }
})();

/* ═══════════════════════════════════════════════════════════
   内容配置页
   ═══════════════════════════════════════════════════════════ */

let _configLoaded = false;
let _fieldInputs = {};
let _configAutoSaveTimer = null;
let _fieldLabels = null;  // 从后端动态获取，避免硬编码与后端不一致

async function initConfigPage() {
  if (_configLoaded) { refreshConfigFields(); return; }
  _configLoaded = true;

  // 从后端获取标准字段标签
  if (!_fieldLabels) {
    const r = await call('get_field_labels');
    _fieldLabels = (r && r.labels) || [];
  }

  // 构建字段列表
  const container = $('#fields-list');
  if (!container) return;

  const cfg = await call('get_all_config');
  if (!cfg) return;

  // 职位描述（从配置中获取）
  const ai = cfg.ai || {};
  $('#cfg-ai-role').value = ai.prompt_template || '';

  // Build field items
  const fields = cfg.fields || {};
  let html = '';
  _fieldLabels.forEach((label, idx) => {
    const isFirst = idx === 0;
    const val = (fields[label] || '');
    html += `<div class="field-item">
      <div class="field-item-label">${escHtml(label)}</div>`;
    if (isFirst) {
      html += `<input type="text" class="input field-input" data-field="${escAttr(label)}" value="${escAttr(val)}" placeholder="输入后 AI 会自动补全其他字段">`;
    } else {
      html += `<textarea class="textarea field-input" data-field="${escAttr(label)}" rows="3" placeholder="可通过 AI 自动生成此字段内容">${escHtml(val)}</textarea>`;
    }
    html += '</div>';
  });
  container.innerHTML = html;

  // Bind auto-save
  container.querySelectorAll('.field-input').forEach(el => {
    el.addEventListener('input', debounceAutoSave);
  });
  $('#cfg-ai-role').addEventListener('input', debounceAiSave);
}

async function refreshConfigFields() {
  const cfg = await call('get_all_config');
  if (!cfg) return;
  const fields = cfg.fields || {};
  const container = $('#fields-list');
  if (!container) return;
  container.querySelectorAll('.field-input').forEach(el => {
    const label = el.dataset.field;
    if (label && fields[label] !== undefined && el.value !== fields[label] + '') {
      el.value = fields[label] || '';
    }
  });
}

async function configAutoSave() {
  const fields = {};
  const container = $('#fields-list');
  if (!container) return;
  container.querySelectorAll('.field-input').forEach(el => {
    const label = el.dataset.field;
    if (label) fields[label] = el.value || '';
  });
  await call('save_all_fields', fields);
}

function debounceAutoSave() {
  clearTimeout(_configAutoSaveTimer);
  _configAutoSaveTimer = setTimeout(configAutoSave, 600);
}
function debounceAiSave() {
  clearTimeout(_configAutoSaveTimer);
  _configAutoSaveTimer = setTimeout(async () => {
    await configAutoSave();
    const role = $('#cfg-ai-role').value.trim();
    const cfg = await call('get_all_config');
    const ai = cfg.ai || {};
    // 只保存职位描述，API Key/URL/Model 通过弹窗配置
    await call('set_ai_settings',
      ai.api_key || '',
      ai.api_url || '',
      ai.model || '',
      role
    );
  }, 600);
}

async function configReset() {
  if (!confirm('确定恢复全部字段为默认值？此操作不可撤销。')) return;
  await call('reset_fields');
  _configLoaded = false;
  await initConfigPage();
  showToast('已恢复为默认值');
}

function configExport() {
  const path = prompt('请输入导出文件路径：', 'config_export.json');
  if (!path) return;
  call('export_config', path).then(r => {
    if (r && r.ok) showToast('导出成功');
    else showToast('导出失败: ' + ((r && r.error) || '未知'), false);
  });
}

function configImport() {
  const path = prompt('请输入导入文件路径：', 'config_export.json');
  if (!path) return;
  call('import_config', path).then(r => {
    if (r && r.ok) {
      _configLoaded = false;
      initConfigPage();
      showToast('导入成功');
    } else showToast('导入失败: ' + ((r && r.error) || '未知'), false);
  });
}

/* ═══════════════════════════════════════════════════════════
   定时设置页
   ═══════════════════════════════════════════════════════════ */
async function initSchedulePage() {
  const cfg = await call('get_all_config');
  if (!cfg) return;
  const s = cfg.schedule || {};
  $('#sched-switch').checked = !!s.enabled;

  // Populate hour/min selects
  const hSel = $('#sched-hour');
  const mSel = $('#sched-min');
  if (hSel.children.length === 0) {
    for (let h = 0; h < 24; h++) {
      const opt = document.createElement('option');
      opt.value = h; opt.textContent = String(h).padStart(2, '0');
      hSel.appendChild(opt);
    }
    for (let m = 0; m < 60; m++) {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = String(m).padStart(2, '0');
      mSel.appendChild(opt);
    }
  }

  const time = (s.time || '20:30').split(':');
  hSel.value = parseInt(time[0]) || 20;
  mSel.value = parseInt(time[1]) || 30;

  // Status
  const lastOk = s.last_run_success;
  const lastTime = s.last_run_time || '';
  const el1 = $('#sched-status');
  const el2 = $('#sched-last-run');
  if (s.enabled) {
    el1.textContent = '定时状态: 已开启';
    el1.className = 'status-line success';
  } else {
    el1.textContent = '定时状态: 已关闭';
    el1.className = 'status-line';
  }
  if (lastTime) {
    el2.textContent = '上次执行: ' + lastTime + ' — ' + (lastOk ? '成功' : '失败');
    el2.className = 'status-line ' + (lastOk ? 'success' : 'error');
  } else {
    el2.textContent = '';
  }
}

async function schedSave() {
  const enabled = $('#sched-switch').checked;
  const h = $('#sched-hour').value;
  const m = $('#sched-min').value;
  const timeStr = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  await call('set_schedule_settings', enabled, timeStr);
  showToast('定时设置已保存');
  await initSchedulePage();
}

/* ═══════════════════════════════════════════════════════════
   五项清单页
   ═══════════════════════════════════════════════════════════ */
let _clLoggedIn = false;
let _clOwners = [];    // [{name, id, center, type: "self"|"dept"|"center"}]
let _clItems = [];     // ["content1", "content2", ...]
let _clMyUserId = '';
let _clMyCenter = '';
let _clUserInfoLoaded = false;  // 确保只拉取一次

async function initChecklistPage() {
  // 先尝试自动登录（使用 config.json 中存储的账号密码）
  const auto = await call('checklist_auto_login_if_needed');
  if (auto && auto.logged_in) {
    _clLoggedIn = true;
  } else {
    // 再查一次状态（可能是 token 缓存）
    const auth = await call('checklist_auth_status');
    _clLoggedIn = !!(auth && auth.logged_in);
  }

  if (_clLoggedIn) {
    // 只首次拉取用户信息，避免重复调用覆盖 _clMyCenter
    if (!_clUserInfoLoaded) {
      const auth = await call('checklist_auth_status');
      _clMyUserId = (auth && auth.user_id) || '';
      _clMyCenter = (auth && auth.center_name) || '';
      _clUserInfoLoaded = true;
      $('#cl-realname').textContent = (auth && auth.real_name) || '--';
      $('#cl-center').textContent = _clMyCenter || '--';
    }
    $('#cl-status').textContent = '已登录';
    $('#cl-status').style.color = '#22C55E';
    $('#cl-login-btn').textContent = '刷新信息';

    // Load dicts
    const dicts = await call('checklist_dicts');
    if (dicts && dicts.ok) {
      populateSelect($('#cl-urgency'), dicts.urgencies || [], 'enCode', 'fullName');
      // 默认选中 B-重要不紧急
      const sel = $('#cl-urgency');
      const bOpt = Array.from(sel.options).find(o => o.textContent.includes('B'));
      if (bOpt) bOpt.selected = true;
    }

    // 期望完成时间默认值：当月最后一天 23:59:59
    if (!$('#cl-finish-time').value) {
      const now = new Date();
      const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      const y = lastDay.getFullYear();
      const m = String(lastDay.getMonth() + 1).padStart(2, '0');
      const d = String(lastDay.getDate()).padStart(2, '0');
      $('#cl-finish-time').value = `${y}-${m}-${d} 23:59:59`;
    }

    // 加载提交间隔设置
    const intervalInfo = await call('checklist_get_interval');
    if (intervalInfo && intervalInfo.ok) {
      $('#cl-interval-min').value = String(intervalInfo.interval_min || 20);
      $('#cl-interval-max').value = String(intervalInfo.interval_max || 30);
    }

    // Month count
    const mc = await call('checklist_month_count');
    if (mc && mc.ok) updateMonthCount(mc.count);
  } else {
    $('#cl-status').textContent = auto && auto.message ? '未登录 — ' + auto.message : '未登录';
    $('#cl-status').style.color = '#EF4444';
    $('#cl-realname').textContent = '--';
    $('#cl-center').textContent = '--';
    $('#cl-login-btn').textContent = '登录五项清单';
    _clUserInfoLoaded = false;  // 未登录时重置，下次登录会重新拉取
    _clMyUserId = '';
    _clMyCenter = '';
  }

  // Init owner rows — rebuild from remembered owners (if loaded already) or from saved config
  if (_clOwners.length === 0) {
    const container = $('#cl-owner-rows');
    if (container) container.innerHTML = '';
    // 尝试从 config.json 加载记忆的责任人
    const saved = await call('checklist_load_owners');
    if (saved && saved.ok && saved.owners && saved.owners.length) {
      _clOwners = saved.owners.map(o => ({
        name: o.name || '',
        id: o.user_id || '',
        center: o.center_name || '',
        type: ''
      }));
      clRebuildOwnerRows();
    } else {
      clAddOwnerRow();
    }
  } else {
    clRebuildOwnerRows();
  }
  // Init content items
  if (_clItems.length === 0) {
    _clItems = [''];
  }
  updateClCount();
}

async function clAutoLogin() {
  const username = (await call('get_account')).username || '';
  if (!username) { showToast('请先在工作台登录中填写账号', false); return; }
  const pwd = prompt('请输入清单平台密码：');
  if (!pwd) return;
  const r = await call('checklist_login', username, pwd);
  if (r && r.ok) {
    showToast('登录成功');
    await initChecklistPage();
  } else {
    showToast('登录失败: ' + ((r && (r.message || r.error)) || '未知'), false);
  }
}

function populateSelect(sel, options, valKey, textKey) {
  sel.innerHTML = '';
  if (!options || !options.length) {
    sel.innerHTML = '<option>无选项</option>';
    return;
  }
  options.forEach(opt => {
    const o = document.createElement('option');
    o.value = opt[valKey] || '';
    o.textContent = opt[textKey] || opt[valKey] || '';
    sel.appendChild(o);
  });
}

// ── 责任人行管理 ──

function clAddOwnerRow(name, id, center, type) {
  const container = $('#cl-owner-rows');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'owner-row';
  row.innerHTML = `
    <input type="text" class="input" placeholder="输入姓名回车查询" value="${escAttr(name || '')}">
    <button class="btn-search-sm" title="搜索" onclick="clSearchOwner(this.closest('.owner-row'))">&#x1F50D;</button>
    <span class="owner-center-label">${escHtml(center || '--')}</span>
    <span class="owner-type-label"></span>
    <button class="btn-icon-sm" title="删除" onclick="clRemoveOwnerRow(this.closest('.owner-row'))">&times;</button>
  `;

  // 存储 data 属性
  if (id) row.setAttribute('data-owner-id', id);
  if (center) row.setAttribute('data-owner-center', center);
  if (type) row.setAttribute('data-owner-type', type);

  // 绑定回车搜索
  const input = row.querySelector('input');
  if (input) {
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        clSearchOwner(row);
      }
    });
  }

  container.appendChild(row);
}

function clRebuildOwnerRows() {
  const container = $('#cl-owner-rows');
  if (!container) return;
  container.innerHTML = '';
  if (_clOwners.length === 0) {
    clAddOwnerRow();
  } else {
    _clOwners.forEach(o => {
      clAddOwnerRow(o.name, o.id, o.center);
      // 设置类型标签（使用存储的值，不重新计算）
      const rows = container.querySelectorAll('.owner-row');
      const lastRow = rows[rows.length - 1];
      const typeLabel = lastRow.querySelector('.owner-type-label');
      const ownerType = o.type || computeOwnerType(o.id, o.center);
      if (typeLabel && o.id) applyOwnerTypeLabel(typeLabel, ownerType);
    });
  }
}

function clRemoveOwnerRow(row) {
  const container = $('#cl-owner-rows');
  if (!container) return;
  const rows = container.querySelectorAll('.owner-row');
  if (rows.length <= 1) return; // 至少保留一行
  row.remove();
  clSyncOwnersFromUI();
}

function clSyncOwnersFromUI() {
  const container = $('#cl-owner-rows');
  if (!container) return;
  _clOwners = [];
  container.querySelectorAll('.owner-row').forEach(row => {
    const input = row.querySelector('input');
    const name = (input ? input.value.trim() : '');
    const id = row.getAttribute('data-owner-id') || '';
    const center = row.getAttribute('data-owner-center') || '';
    const type = row.getAttribute('data-owner-type') || '';
    if (name || id) {
      _clOwners.push({ name, id, center, type });
    }
  });
  // 持久化到 config.json
  _persistOwners();
}

async function _persistOwners() {
  const toSave = _clOwners
    .filter(o => o.id || o.name)
    .map(o => ({ name: o.name || '', user_id: o.id || '', center_name: o.center || '' }));
  if (toSave.length > 0) {
    await call('checklist_save_owners', JSON.stringify(toSave));
  }
}

async function clSearchOwner(row) {
  if (!_clLoggedIn) { showToast('请先登录五项清单', false); return; }
  const input = row.querySelector('input');
  const centerLabel = row.querySelector('.owner-center-label');
  if (!input) return;
  const keyword = input.value.trim();
  if (!keyword) return;

  input.placeholder = '搜索中...';
  if (centerLabel) centerLabel.textContent = '查询中...';

  const r = await call('checklist_search_user', keyword);
  input.placeholder = '输入姓名回车查询';

  if (!r || !r.ok) {
    if (centerLabel) centerLabel.textContent = '搜索失败';
    showToast('搜索失败: ' + ((r && r.error) || '未知'), false);
    return;
  }
  const users = r.users || [];
  if (users.length === 0) {
    if (centerLabel) centerLabel.textContent = '未找到';
    showToast('未找到匹配用户', false);
    return;
  }
  let u;
  if (users.length === 1) {
    u = users[0];
  } else {
    // 多个匹配，显示美观的选择弹窗
    u = await showOwnerSelectModal(users);
    if (!u) { if (centerLabel) centerLabel.textContent = '--'; return; }
  }

  const cleanName = (u.fullName || '').replace(/\/$/, '');
  input.value = cleanName;
  row.setAttribute('data-owner-id', u.id || '');
  row.setAttribute('data-owner-center', u.centerName || '');
  if (centerLabel) centerLabel.textContent = u.centerName || '--';

  // 计算并存储类型
  const ownerType = computeOwnerType(u.id, u.centerName);
  row.setAttribute('data-owner-type', ownerType);

  const typeLabel = row.querySelector('.owner-type-label');
  if (typeLabel) {
    applyOwnerTypeLabel(typeLabel, ownerType);
  }

  clSyncOwnersFromUI();
  showToast('已匹配: ' + cleanName);
}

function computeOwnerType(ownerId, ownerCenter) {
  if (!ownerId || !_clMyUserId) return '';
  if (String(ownerId) === String(_clMyUserId)) return 'self';
  if (ownerCenter && _clMyCenter && ownerCenter === _clMyCenter) return 'dept';
  return 'center';
}

function applyOwnerTypeLabel(el, type) {
  if (type === 'self') {
    el.textContent = '自己对自己';
    el.className = 'owner-type-label type-self';
  } else if (type === 'dept') {
    el.textContent = '部门内部对部门内部';
    el.className = 'owner-type-label type-dept';
  } else if (type === 'center') {
    el.textContent = '中心对中心';
    el.className = 'owner-type-label type-center';
  } else {
    el.textContent = '';
    el.className = 'owner-type-label';
  }
}

function setOwnerTypeLabel(el, ownerId, ownerCenter) {
  applyOwnerTypeLabel(el, computeOwnerType(ownerId, ownerCenter));
}

// ── 责任人选择弹窗 ──

function showOwnerSelectModal(users) {
  return new Promise((resolve) => {
    // 创建遮罩层
    const overlay = document.createElement('div');
    overlay.className = 'owner-select-overlay';
    overlay.innerHTML = `
      <div class="owner-select-modal">
        <div class="owner-select-header">
          <h3>选择责任人</h3>
          <button class="owner-select-close" title="关闭">&times;</button>
        </div>
        <div class="owner-select-list">
          ${users.map((u, i) => `
            <div class="owner-select-item" data-index="${i}">
              <span class="owner-select-name">${escHtml((u.fullName || '').replace(/\/$/, ''))}</span>
              <span class="owner-select-center">${escHtml(u.centerName || '--')}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // 点击选项
    overlay.querySelectorAll('.owner-select-item').forEach(item => {
      item.addEventListener('click', () => {
        const idx = parseInt(item.getAttribute('data-index'));
        document.body.removeChild(overlay);
        resolve(users[idx]);
      });
    });

    // 点击关闭按钮
    overlay.querySelector('.owner-select-close').addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(null);
    });

    // 点击遮罩层关闭
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        document.body.removeChild(overlay);
        resolve(null);
      }
    });
  });
}

// ── 清单列表弹窗 ──

function updateClCount() {
  const n = _clItems.filter(s => s.trim()).length;
  $('#cl-list-count').textContent = n + ' 条';
}

function updateMonthCount(count) {
  const el = $('#cl-month-count');
  if (!el) return;
  el.textContent = '本月已提交: ' + count;
  // 红（<150）/ 品牌蓝（>=150）
  el.style.background = count < 150 ? '#FEE2E2' : '#E0F2FE';
  el.style.color = count < 150 ? '#EF4444' : '#0284C7';
  el.style.padding = '2px 10px';
  el.style.borderRadius = '4px';
  el.style.fontWeight = '600';
  el.style.fontSize = '12px';
}

async function clSaveInterval() {
  const minVal = parseInt($('#cl-interval-min').value) || 20;
  const maxVal = parseInt($('#cl-interval-max').value) || 30;
  await call('checklist_set_interval', minVal, maxVal);
}

function clOpenListPopup() {
  const modal = $('#cl-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  clRebuildPopupRows();
}

function clCloseListPopup() {
  // 从弹窗同步数据回 _clItems
  clSyncItemsFromPopup();
  const modal = $('#cl-modal');
  if (modal) modal.classList.add('hidden');
  updateClCount();
}

function clSyncItemsFromPopup() {
  const list = $('#cl-popup-list');
  if (!list) return;
  _clItems = [];
  list.querySelectorAll('.cl-popup-row').forEach(row => {
    const ta = row.querySelector('textarea');
    if (ta) _clItems.push(ta.value);
  });
  // 至少保留一行为空
  if (_clItems.length === 0) _clItems = [''];
}

function clRebuildPopupRows() {
  const list = $('#cl-popup-list');
  if (!list) return;
  list.innerHTML = '';
  if (_clItems.length === 0) _clItems = [''];
  _clItems.forEach((text, i) => {
    clAddPopupRow(text, i + 1);
  });
  clUpdatePopupCount();
}

function clAddPopupRow(text, num) {
  const list = $('#cl-popup-list');
  if (!list) return;
  const idx = num || (list.children.length + 1);
  const row = document.createElement('div');
  row.className = 'cl-popup-row';
  row.innerHTML = `
    <span class="cl-popup-num">${idx}.</span>
    <textarea class="textarea cl-popup-ta" rows="2" placeholder="清单内容...">${escHtml(text || '')}</textarea>
    <button class="btn-icon-sm" title="删除" onclick="clRemovePopupRow(this.closest('.cl-popup-row'))">&times;</button>
  `;
  // 绑定输入自动调整高度
  const ta = row.querySelector('textarea');
  if (ta) {
    ta.addEventListener('input', () => clAutoResizeTA(ta));
    // 初始调整
    setTimeout(() => clAutoResizeTA(ta), 50);
  }
  list.appendChild(row);
}

function clAutoResizeTA(ta) {
  ta.style.height = 'auto';
  ta.style.height = Math.max(ta.scrollHeight, 44) + 'px';
}

function clRemovePopupRow(row) {
  const list = $('#cl-popup-list');
  if (!list) return;
  // 至少保留一行
  if (list.children.length <= 1) {
    const ta = list.querySelector('.cl-popup-row textarea');
    if (ta) ta.value = '';
    clUpdatePopupCount();
    return;
  }
  row.remove();
  // 重新编号
  list.querySelectorAll('.cl-popup-row').forEach((r, i) => {
    const span = r.querySelector('span');
    if (span) span.textContent = (i + 1) + '.';
  });
  clUpdatePopupCount();
}

function clPopupAddRow() {
  const list = $('#cl-popup-list');
  if (!list) return;
  clAddPopupRow('', list.children.length + 1);
  clUpdatePopupCount();
}

function clPopupClear() {
  if (!confirm('确定清空全部清单内容？')) return;
  const list = $('#cl-popup-list');
  if (!list) return;
  list.innerHTML = '';
  clAddPopupRow('');
  clUpdatePopupCount();
}

function clUpdatePopupCount() {
  const list = $('#cl-popup-list');
  if (!list) return;
  let n = 0;
  list.querySelectorAll('.cl-popup-row').forEach(row => {
    const ta = row.querySelector('textarea');
    if (ta && ta.value.trim()) n++;
  });
  const el = $('#cl-popup-count');
  if (el) el.textContent = n + ' 条';
}

// ── AI 生成后自动打开弹窗 ──

function clAIFillItems(items) {
  _clItems = items && items.length ? items : [''];
  updateClCount();
  // 如果弹窗已打开，刷新弹窗
  const modal = $('#cl-modal');
  if (modal && !modal.classList.contains('hidden')) {
    clRebuildPopupRows();
  }
}

// ── 提交 ──

async function clPopupSubmitAndClose() {
  clSyncItemsFromPopup();
  // 不关闭弹窗，先提交（进度条会遮住弹窗，完成后统一处理）
  await clSubmit();
}

async function clSubmit(fromPopup) {
  if (!_clLoggedIn) { showToast('请先登录五项清单', false); return; }

  // 同步责任人
  clSyncOwnersFromUI();

  // 过滤有效内容
  const contents = _clItems.filter(s => s.trim());
  if (!contents.length) { showToast('请至少填写一条清单内容，可点击「打开清单列表」编辑', false); return; }

  // 过滤有效责任人
  const validOwners = _clOwners.filter(o => o.name.trim() || o.id);
  if (!validOwners.length) { showToast('请至少填写一个责任人', false); return; }

  const urgency = $('#cl-urgency').value || 'B';
  const finishTime = $('#cl-finish-time').value.trim() || '';

  // 构建提交项：每个内容配一个责任人（轮转分配）
  const items = [];
  const nOwners = validOwners.length;
  for (let i = 0; i < contents.length; i++) {
    const owner = validOwners[i % nOwners];
    items.push({
      content: contents[i],
      owner_name: owner.name || '',
      owner_id: owner.id || '',
      owner_center: owner.center || '',
    });
  }

  // 获取提交间隔区间
  const intervalMin = parseInt($('#cl-interval-min').value) || 20;
  const intervalMax = parseInt($('#cl-interval-max').value) || 30;

  // 启动后台提交
  const r = await call('checklist_submit', JSON.stringify(items), urgency, '', finishTime, intervalMin, intervalMax);

  if (!r || !r.ok || !r.running) {
    showToast('提交失败: ' + ((r && r.error) || '未知'), false);
    return;
  }

  showGlobalProgress('批量提交五项清单', 'checklist_submit_progress', async (p) => {
    if (p.error) {
      showToast('提交失败: ' + p.error, false);
    } else {
      const prefix = p.cancelled ? '已终止 — ' : '';
      showToast(`${prefix}成功 ${p.ok_count} 条，失败 ${p.fail_count} 条`);
      _clItems = [''];
      updateClCount();
      // 关闭弹窗并刷新
      const modal = $('#cl-modal');
      if (modal && !modal.classList.contains('hidden')) {
        modal.classList.add('hidden');
      }
      const mc = await call('checklist_month_count');
      if (mc && mc.ok) updateMonthCount(mc.count);
    }
  });
}

// ── AI 生成 ──

async function clAIGenerate() {
  if (!_clLoggedIn) { showToast('请先登录五项清单', false); return; }
  const cfg = await call('get_ai_settings');
  if (!cfg || !cfg.api_key) { showToast('请先在日报配置中填写 AI API Key', false); return; }
  const prompt = $('#cl-ai-prompt').value.trim();
  const count = parseInt($('#cl-ai-count').value) || 10;

  $('#cl-ai-btn').disabled = true;
  $('#cl-ai-btn').innerHTML = '<span class="spinner"></span> 生成中...';
  $('#cl-ai-status').textContent = 'AI 正在生成...';

  const r = await call('checklist_ai_generate', prompt, count, cfg.api_key, cfg.api_url, '');
  $('#cl-ai-btn').disabled = false;
  $('#cl-ai-btn').textContent = 'AI 一键生成';

  if (r && r.ok && r.items && r.items.length) {
    clAIFillItems(r.items);
    // 自动打开弹窗展示
    clOpenListPopup();
    $('#cl-ai-status').textContent = '生成 ' + r.items.length + ' 条';
    showToast('AI 生成完成，已打开清单列表');
  } else {
    $('#cl-ai-status').textContent = '生成失败';
    showToast('AI 生成失败: ' + ((r && r.error) || '未知'), false);
  }
}

async function clFetchProto() {
  const url = $('#cl-proto-url').value.trim();
  if (!url) { showToast('请输入原型链接', false); return; }
  $('#cl-proto-fetch').disabled = true;
  $('#cl-proto-status').textContent = '抓取中...';
  const r = await call('checklist_fetch_prototype', url);
  $('#cl-proto-fetch').disabled = false;
  if (r && r.ok) {
    $('#cl-proto-content').value = r.content || '';
    $('#cl-proto-status').textContent = '已抓取: ' + (r.page_name || '') + ' (' + (r.content ? r.content.length : 0) + '字)';
  } else {
    $('#cl-proto-status').textContent = '抓取失败';
    showToast('抓取失败: ' + ((r && r.error) || '未知'), false);
  }
}

function clClearProto() {
  $('#cl-proto-content').value = '';
  $('#cl-proto-status').textContent = '';
  $('#cl-proto-url').value = '';
}

async function clProtoAIGenerate() {
  if (!_clLoggedIn) { showToast('请先登录五项清单', false); return; }
  const cfg = await call('get_ai_settings');
  if (!cfg || !cfg.api_key) { showToast('请先在日报配置中填写 AI API Key', false); return; }
  const proto = $('#cl-proto-content').value.trim();
  if (!proto) { showToast('请先抓取原型内容或手动粘贴', false); return; }
  const count = parseInt($('#cl-proto-count').value) || 10;

  $('#cl-proto-ai').disabled = true;
  $('#cl-proto-ai').innerHTML = '<span class="spinner"></span> 生成中...';

  const r = await call('checklist_ai_generate', '', count, cfg.api_key, cfg.api_url, proto);
  $('#cl-proto-ai').disabled = false;
  $('#cl-proto-ai').textContent = 'AI 一键生成';

  if (r && r.ok && r.items && r.items.length) {
    clAIFillItems(r.items);
    // 自动打开弹窗展示
    clOpenListPopup();
    showToast('AI 生成完成，已打开清单列表');
  } else {
    showToast('AI 生成失败: ' + ((r && r.error) || '未知'), false);
  }
}

/* ═══════════════════════════════════════════════════════════
   回复/评价页
   ═══════════════════════════════════════════════════════════ */
let _replyLoaded = false;
let _replyTextAutoSaveBound = false;

async function initReplyPage() {
  // Load tasks count
  const tasks = await call('reply_get_tasks');
  if (tasks && tasks.ok) {
    const replyCount = tasks.reply_count || 0;
    const evalCount = tasks.eval_count || 0;
    $('#reply-count').textContent = '待回复 ' + replyCount + ' 条';
    $('#eval-count').textContent = '待评价 ' + evalCount + ' 条';
    $('#reply-count').classList.toggle('badge-alert', replyCount > 0);
    $('#eval-count').classList.toggle('badge-alert', evalCount > 0);
    const total = tasks.total_pending || 0;
    const badge = $('#reply-badge');
    if (badge) {
      badge.textContent = total || '';
      badge.classList.toggle('hidden', total === 0);
    }
  }

  // Load auto settings
  const auto = await call('reply_auto_settings');
  if (auto && auto.ok && auto.settings) {
    const s = auto.settings;
    $('#auto-reply-sw').checked = !!s.auto_reply_enabled;
    $('#auto-eval-sw').checked = !!s.auto_eval_enabled;
    $('#auto-reply-text').value = s.auto_reply_text || '收到';
    $('#auto-eval-result').value = s.auto_eval_result || '满意';
    // 加载记忆的批量回复内容
    $('#reply-text').value = s.batch_reply_text || '收到';
  }

  _replyLoaded = true;

  // 绑定回复内容变更自动保存（600ms 防抖）
  if (!_replyTextAutoSaveBound) {
    _replyTextAutoSaveBound = true;
    let _rtTimer = null;
    $('#reply-text').addEventListener('input', () => {
      clearTimeout(_rtTimer);
      _rtTimer = setTimeout(() => {
        call('reply_save_batch_text', $('#reply-text').value);
      }, 600);
    });
  }
}

async function replyBatch() {
  const content = $('#reply-text').value.trim();
  if (!content) { showToast('请输入回复内容', false); return; }

  // 启动后台批量回复
  const r = await call('reply_batch_reply', content);
  if (!r || !r.ok || !r.running) {
    showToast('回复失败: ' + ((r && r.error) || '未知'), false);
    return;
  }

  $('#reply-btn').disabled = true;
  $('#reply-btn').textContent = '回复中...';
  $('#reply-status').textContent = '';

  showGlobalProgress('批量回复', 'reply_batch_reply_progress', async (p) => {
    $('#reply-btn').disabled = false;
    $('#reply-btn').textContent = '一键批量回复';
    if (p.error) {
      $('#reply-status').textContent = '回复失败: ' + p.error;
      showToast('回复失败', false);
    } else {
      $('#reply-status').textContent = `完成 ${p.ok_count}/${p.total} 条` + (p.fail_count ? ` (失败${p.fail_count})` : '');
      showToast('批量回复完成');
      initReplyPage();
    }
  });
}

async function evalBatch() {
  const result = $('#eval-result').value;

  const r = await call('reply_batch_evaluate', result);
  if (!r || !r.ok || !r.running) {
    showToast('评价失败: ' + ((r && r.error) || '未知'), false);
    return;
  }

  $('#eval-btn').disabled = true;
  $('#eval-btn').textContent = '评价中...';
  $('#eval-status').textContent = '';

  showGlobalProgress('批量评价', 'reply_batch_evaluate_progress', async (p) => {
    $('#eval-btn').disabled = false;
    $('#eval-btn').textContent = '一键批量评价';
    if (p.error) {
      $('#eval-status').textContent = '评价失败: ' + p.error;
      showToast('评价失败', false);
    } else {
      $('#eval-status').textContent = `完成 ${p.ok_count}/${p.total} 条` + (p.fail_count ? ` (失败${p.fail_count})` : '');
      showToast('批量评价完成');
      initReplyPage();
    }
  });
}

async function autoSettingChanged() {
  const enabled = $('#auto-reply-sw').checked;
  const evalEnabled = $('#auto-eval-sw').checked;
  const text = $('#auto-reply-text').value.trim();
  const result = $('#auto-eval-result').value;
  const r = await call('reply_save_auto_settings', enabled, evalEnabled, text, result);
  if (r && r.ok) {
    $('#auto-status').textContent = '已保存';
    setTimeout(() => { const el = $('#auto-status'); if (el) el.textContent = ''; }, 2000);
  }
}

/* ═══════════════════════════════════════════════════════════
   Utils
   ═══════════════════════════════════════════════════════════ */

/* ── 全局居中进度条 ── */

/**
 * 启动全局居中进度条轮询
 * @param {string} title 标题文本
 * @param {string} progressApiName 轮询进度的 API 方法名
 * @param {function} onDone 完成回调 (result) => {}
 */
function showGlobalProgress(title, progressApiName, onDone) {
  const ov = $('#progress-overlay');
  const fill = $('#progress-fill-global');
  const text = $('#progress-text-global');
  const cdEl = $('#progress-countdown');
  const cancelBtn = $('#progress-cancel-btn');
  $('#progress-title').textContent = title;
  fill.style.width = '0%';
  text.textContent = '0/0';
  if (cdEl) { cdEl.classList.add('hidden'); cdEl.textContent = ''; }
  // 只有五项清单提交才显示终止按钮
  if (cancelBtn) {
    if (progressApiName === 'checklist_submit_progress') {
      cancelBtn.classList.remove('hidden');
      cancelBtn.disabled = false;
      cancelBtn.textContent = '终止提交';
    } else {
      cancelBtn.classList.add('hidden');
    }
  }
  ov.classList.remove('hidden');

  let poll = setInterval(async () => {
    const p = await call(progressApiName);
    if (!p) return;
    const pct = p.total > 0 ? Math.round((p.done / p.total) * 100) : 0;
    fill.style.width = pct + '%';
    text.textContent = `${p.done}/${p.total}`;

    // 倒计时（仅五项清单提交有 last_submit_time 字段）
    if (cdEl && p.running && p.last_submit_time && p.interval_sec && p.done < p.total) {
      const now = Date.now() / 1000;
      const elapsed = now - p.last_submit_time;
      const remaining = Math.max(0, Math.ceil(p.interval_sec - elapsed));
      cdEl.textContent = `下次提交倒计时：${remaining} 秒（间隔 ${p.interval_min}-${p.interval_max} 秒随机）`;
      cdEl.classList.remove('hidden');
    } else if (cdEl) {
      cdEl.classList.add('hidden');
    }

    // 已取消后禁用按钮并更新文案
    if (cancelBtn && p.cancelled) {
      cancelBtn.disabled = true;
      cancelBtn.textContent = '已终止';
    }

    if (!p.running) {
      clearInterval(poll);
      if (cancelBtn) cancelBtn.classList.add('hidden');
      ov.classList.add('hidden');
      if (onDone) onDone(p);
    }
  }, 250);
}

/** 终止五项清单批量提交 */
async function clCancelSubmit() {
  const btn = $('#progress-cancel-btn');
  if (btn) { btn.disabled = true; btn.textContent = '正在终止...'; }
  await call('checklist_submit_cancel');
}

function escAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ═══════════════════════════════════════════════════════════
   神秘工具 — BPE
   ═══════════════════════════════════════════════════════════ */
let _bpeRunning = false;
let _bpeInited = false;

async function initMysteryPage() {
  const seen = await call('mystery_letter_is_seen');
  if (seen && seen.seen) {
    const letterCard = $('#bpe-letter-card');
    if (letterCard) letterCard.remove();
  } else {
    await call('mystery_letter_mark_seen');
  }

  if (_bpeInited) return;
  _bpeInited = true;
  // 默认日期：当月 1 号 ~ 当月最后一天
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const fmt = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  $('#bpe-date-start').value = fmt(firstDay);
  $('#bpe-date-end').value = fmt(lastDay);
  // 自动填充已保存的账号密码
  const cfg = await call('bpe_get_config');
  if (cfg && cfg.ok) {
    if (cfg.username) $('#bpe-username').value = cfg.username;
    if (cfg.password) $('#bpe-password').value = cfg.password;
  }
}

async function bpeStart() {
  if (_bpeRunning) return;
  const username = $('#bpe-username').value.trim();
  const password = $('#bpe-password').value.trim();
  const apiPattern = $('#bpe-api-pattern').value.trim();
  const dateStart = $('#bpe-date-start').value.replace(/-/g, '/');
  const dateEnd = $('#bpe-date-end').value.replace(/-/g, '/');
  const capacity = parseInt($('#bpe-capacity').value) || 400;

  if (!username) { showToast('请输入登录账号', false); return; }
  if (!password) { showToast('请输入登录密码', false); return; }
  if (!apiPattern) { showToast('请输入断点接口匹配', false); return; }

  _bpeRunning = true;
  // 销毁温馨提示卡片，永久不可见
  const letterCard = $('#bpe-letter-card');
  if (letterCard) {
    letterCard.remove();
    call('mystery_letter_mark_seen');
  }
  const btn = $('#bpe-start-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 执行中...';
  $('#bpe-status').textContent = '正在启动浏览器...';

  const r = await call('bpe_start', username, password, apiPattern, dateStart, dateEnd, capacity);
  if (!r || !r.ok) {
    _bpeRunning = false;
    btn.disabled = false;
    btn.innerHTML = '&#x1F680; 开始执行';
    $('#bpe-status').textContent = '';
    showToast((r && r.error) || '启动失败', false);
  } else {
    $('#bpe-status').textContent = '已启动，请查看运行日志';
  }
}

/* ═══════════════════════════════════════════════════════════
   Lightbox 图片放大
   ═══════════════════════════════════════════════════════════ */
function openLightbox(src) {
  const lb = $('#lightbox');
  const img = $('#lightbox-img');
  if (lb && img) {
    img.src = src;
    lb.classList.remove('hidden');
  }
}

function closeLightbox() {
  const lb = $('#lightbox');
  if (lb) lb.classList.add('hidden');
}

/* ═══════════════════════════════════════════════════════════
   清除缓存
   ═══════════════════════════════════════════════════════════ */
async function clearCache() {
  const r = await call('clear_cache');
  if (r && r.ok) {
    // 先显示 Toast
    showToast(r.message || '缓存已清除，已退出登录', true);
    
    // 延迟 500ms 后跳转到登录页面，让用户看到 Toast
    setTimeout(() => {
      showView('login');
      bindLoginEnter();
      // 自动填充用户名（如果有）
      if (r.username) {
        $('#login-username').value = r.username;
      }
      $('#login-password').value = '';
    }, 500);
  } else {
    showToast((r && r.error) || '清除缓存失败', false);
  }
}
