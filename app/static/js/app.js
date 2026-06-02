// ===== SocketIO 实时日志 =====
const socket = io();
const logContainer = document.getElementById('logContainer');

socket.on('log', function(data) {
    if (!logContainer) return;
    const empty = logContainer.querySelector('.log-empty');
    if (empty) empty.remove();
    const line = document.createElement('div');
    line.className = 'log-line ' + (data.level || 'info');
    line.innerHTML = '<span class="log-time">' + (data.time || '') + '</span>' + escapeHtml(data.msg);
    logContainer.appendChild(line);
    logContainer.scrollTop = logContainer.scrollHeight;
});

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function clearLogs() {
    if (logContainer) logContainer.innerHTML = '<div class="log-empty">日志已清空</div>';
}

// ===== 保存所有字段 =====
function saveAllFields() {
    const fields = {};
    document.querySelectorAll('.field-input').forEach(function(el) {
        fields[el.dataset.label] = el.value;
    });
    fetch('/api/save_fields', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fields: fields})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) showToast('保存成功！'); });
}

// ===== 清空所有字段 =====
function clearAllFields() {
    if (!confirm('确定清空所有日报内容？')) return;
    document.querySelectorAll('.field-input').forEach(function(el) { el.value = ''; });
    saveAllFields();
}

// ===== AI 生成 =====
function generateAI() {
    var input = document.getElementById('field1Input');
    var btn = document.getElementById('aiBtn');
    if (!input) return;
    var content = input.value.trim();
    if (!content) { alert('请先输入第一项工作内容'); return; }

    btn.disabled = true;
    btn.textContent = '⏳ AI 生成中...';

    fetch('/api/generate_ai', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field1_content: content})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok) {
            // 保存 AI 返回的所有字段
            fetch('/api/save_fields', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({fields: d.fields})
            }).then(function() {
                // 刷新预览
                if (typeof refreshPreview === 'function') refreshPreview(d.fields);
            });
            showToast('AI 生成完成！');
        } else {
            alert('AI 生成失败: ' + (d.error || '未知错误'));
        }
    })
    .catch(function(e) { alert('请求失败: ' + e); })
    .finally(function() {
        btn.disabled = false;
        btn.textContent = '✨ AI 智能生成';
    });
}

// ===== 执行日报填写 =====
function runReport() {
    var btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.textContent = '⏳ 执行中...';

    fetch('/api/run_report', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok) showToast('任务已启动，请查看日志');
        else alert('启动失败');
    })
    .catch(function(e) { alert('请求失败: ' + e); })
    .finally(function() {
        setTimeout(function() {
            btn.disabled = false;
            btn.textContent = '🚀 一键填写日报';
        }, 30000);
    });
}

// ===== 保存配置 =====
function saveConfig() {
    var data = {
        username: document.getElementById('cfgUsername').value,
        password: document.getElementById('cfgPassword').value,
        auto_submit: document.getElementById('cfgAutoSubmit').checked,
        ai: {
            api_key: document.getElementById('cfgApiKey').value,
            api_url: document.getElementById('cfgApiUrl').value,
            model: document.getElementById('cfgModel').value,
            prompt_template: document.getElementById('cfgRole').value
        }
    };
    fetch('/api/save_config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) showToast('配置已保存！'); });
}

// ===== 保存定时任务 =====
function saveSchedule() {
    var data = {
        enabled: document.getElementById('schedEnabled').checked,
        time: document.getElementById('schedTime').value
    };
    fetch('/api/save_schedule', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) showToast('定时任务已保存！'); });
}

// ===== Toast 提示 =====
function showToast(msg) {
    var toast = document.createElement('div');
    toast.style.cssText = 'position:fixed;top:24px;right:24px;background:#16A34A;color:#fff;padding:12px 24px;border-radius:8px;font-size:14px;z-index:99999;box-shadow:0 4px 12px rgba(0,0,0,.15);transition:opacity .3s;';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(function() {
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 300);
    }, 2000);
}
