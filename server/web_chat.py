"""调度员 - Web 智能体面板 HTML 模板"""
from __future__ import annotations

_CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能体面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans SC',sans-serif;background:#f0f2f5;height:100dvh;display:flex;overflow:hidden;color:#333}
/* 左边栏 */
.sidebar{width:320px;min-width:320px;background:#2c3e50;color:#fff;display:flex;flex-direction:column;flex-shrink:0}
.sidebar-header{padding:16px 18px;border-bottom:1px solid rgba(255,255,255,.1)}
.sidebar-header h1{font-size:14px;font-weight:600}
.sidebar-header .subtitle{font-size:11px;opacity:.5;margin-top:1px}
.sidebar-section{padding:12px 16px 6px;font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.5;font-weight:600}
.agent-list{flex:1;overflow-y:auto;padding:0 8px}
.agent-group{margin-bottom:4px}
.agent-group-header{display:flex;align-items:center;gap:6px;padding:8px 10px 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px;opacity:.5}
.agent-group-header.collapsible{cursor:pointer;user-select:none}
.agent-group-header.collapsible:hover{opacity:.8}
.agent-group-header .arrow{font-size:10px;transition:transform .2s;display:inline-block}
.agent-group-header .arrow.collapsed{transform:rotate(-90deg)}
.agent-group-body{overflow:hidden;transition:max-height .25s ease}
.agent-group-body.collapsed{max-height:0!important}
.agent-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;cursor:pointer;transition:background .15s;margin-bottom:2px}
.agent-item:hover{background:rgba(255,255,255,.08)}
.agent-item.active{background:rgba(52,152,219,.3)}
.agent-item .av{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0}
.agent-item .info{flex:1;min-width:0}
.agent-item .info .name{font-size:13px;font-weight:600}
.agent-item .info .desc{font-size:11px;opacity:.6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.agent-item .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.online{background:#2ecc71}
.dot.offline{background:#95a5a6}
.dot.busy{background:#f39c12}
/* 会话列表 */
.session-section{border-top:1px solid rgba(255,255,255,.08)}
.session-list{padding:0 8px;max-height:200px;overflow-y:auto}
.session-item{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:6px;cursor:pointer;font-size:12px;transition:background .15s;margin-bottom:1px}
.session-item:hover{background:rgba(255,255,255,.06)}
.session-item.active{background:rgba(52,152,219,.2)}
.session-item .s-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.session-item .s-time{font-size:10px;opacity:.4;flex-shrink:0}
.session-item .s-del{background:none;border:none;color:#e74c3c;cursor:pointer;font-size:14px;opacity:0;padding:0 4px}
.session-item:hover .s-del{opacity:.6}
.session-item .s-del:hover{opacity:1}
/* 主区域 */
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.chat-header{background:#fff;padding:14px 20px;border-bottom:1px solid #e0e0e0;display:flex;align-items:center;gap:12px;flex-shrink:0;position:sticky;top:0;z-index:10}
.chat-header .av{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;flex-shrink:0}
.chat-header .info{flex:1}
.chat-header .info h2{font-size:15px;font-weight:600}
.chat-header .info .status{font-size:11px;color:#999}
.settings-link{font-size:20px;text-decoration:none;cursor:pointer;padding:4px 8px;border-radius:6px;transition:background .15s}
.settings-link:hover{background:#f0f0f0}
.chat-area{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:10px;background:#f5f6fa;scroll-behavior:smooth}
.msg{max-width:78%;padding:9px 14px;border-radius:12px;font-size:14px;line-height:1.6;word-break:break-word;animation:fadeIn .2s ease}
.msg.user{background:#3498db;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
.msg.assistant{background:#fff;color:#333;align-self:flex-start;border-bottom-left-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.msg.system{background:#fffbe6;color:#8a6d00;align-self:center;font-size:12px;padding:5px 12px;border-radius:8px;max-width:90%}
.msg .time{font-size:10px;opacity:.6;margin-top:3px}
.msg.user .time{text-align:right}
.thinking{display:flex;align-items:center;gap:8px;padding:9px 14px;background:#fff;border-radius:12px;align-self:flex-start;font-size:13px;color:#999;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.thinking .dot{width:6px;height:6px;background:#999;border-radius:50%;animation:bounce 1.4s infinite}
.thinking .dot:nth-child(2){animation-delay:.2s}
.thinking .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-4px)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.input-area{flex-shrink:0;padding:12px 16px;background:#fff;border-top:1px solid #e0e0e0;display:flex;gap:10px;align-items:flex-end}
.input-area textarea{flex:1;border:1px solid #ddd;border-radius:20px;padding:10px 16px;font-size:14px;resize:none;outline:none;max-height:120px;font-family:inherit;line-height:1.4}
.input-area textarea:focus{border-color:#3498db}
.input-area .send-btn{width:40px;height:40px;border-radius:50%;background:#3498db;color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;transition:background .15s}
.input-area .send-btn:hover{background:#2980b9}
.input-area .send-btn:disabled{background:#bbb;cursor:not-allowed}
.attach-btn{background:none;border:1px solid #ddd;border-radius:8px;padding:8px 10px;cursor:pointer;font-size:16px;color:#666;flex-shrink:0;line-height:1;transition:all .15s}
.attach-btn:hover{background:#f0f0f0;border-color:#bbb}
.attach-btn:disabled{opacity:.4;cursor:not-allowed}
.msg .file-preview{display:flex;align-items:center;gap:10px;padding:6px 0}
.msg .file-preview img{max-width:240px;max-height:240px;border-radius:8px;cursor:pointer;display:block}
.msg .file-preview .file-icon{font-size:28px;flex-shrink:0}
.msg .file-preview .file-info{flex:1;min-width:0}
.msg .file-preview .file-info .fn{font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.msg .file-preview .file-info .fs{font-size:11px;opacity:.6;margin-top:1px}
.new-btn{background:rgba(255,255,255,.1);border:1px dashed rgba(255,255,255,.3);color:#fff;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;margin:8px 12px;text-align:center;transition:all .15s}
.new-btn:hover{background:rgba(255,255,255,.2);border-color:rgba(255,255,255,.5)}
@media(max-width:640px){.sidebar{width:60px;min-width:60px}.sidebar .agent-item .info,.sidebar .session-list,.sidebar-section,.sidebar-header .subtitle,.new-btn span{display:none}.sidebar .agent-item{padding:8px;justify-content:center}.sidebar-header h1{font-size:12px;text-align:center}.main .chat-header{padding:10px 12px}.chat-area{padding:10px 12px}.msg{max-width:92%}.input-area textarea{font-size:16px}.agent-item .av{width:28px;height:28px;font-size:12px}}
</style>
</head>
<body>
<div class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h1>聊天</h1>
    <div class="subtitle">多智能体对话</div>
  </div>
  <div class="sidebar-section">智能体</div>
  <div class="agent-list" id="agent-list"></div>
  <div class="new-btn" onclick="newSession()">➕ <span>新对话</span></div>
  <div class="sidebar-section session-section">历史对话</div>
  <div class="session-list" id="session-list"></div>
</div>
<div class="main">
  <div class="chat-header" id="chat-header">
    <div class="av" id="cur-avatar" style="background:#3498db">调</div>
    <div class="info">
      <h2 id="cur-name">调度员</h2>
      <div class="status" id="cur-status">🟢 在线 · 任务调度</div>
    </div>
    <a class="settings-link" href="/config" title="设置">⚙️</a>
  </div>
  <div class="chat-area" id="chat-area">
    <div class="msg system" id="welcome-msg">选择一个智能体开始对话</div>
  </div>
  <div class="input-area">
    <button class="attach-btn" id="attach-btn" onclick="document.getElementById('file-input').click()" disabled>📎</button>
    <input type="file" id="file-input" style="display:none" multiple onchange="onFileSelected(event)" />
    <textarea id="input" rows="1" placeholder="说点什么…" onkeydown="onKeyDown(event)" disabled></textarea>
    <button class="send-btn" id="send-btn" onclick="send()" disabled>➤</button>
  </div>
</div>
<script>
// ==================== 状态 ====================
let currentAgent = null;
let currentSession = 'default';
let agents = [];
let sessions = [];
let loadingHistory = false;
const chatArea = document.getElementById('chat-area');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');

// 每个智能体绑定独立会话
function agentSessionId(agentId) { return 'session_agent_' + agentId; }

// ==================== 工具 ====================
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

function onKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}

function ts() {
  return new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
}

// ==================== 智能体列表加载 ====================
async function loadAgents() {
  try {
    const r = await fetch('/api/chat/agents');
    const data = await r.json();
    if (data.code !== 0) return;
    agents = data.data || [];
    renderAgentList();
  } catch(e) { console.error('load agents fail:', e); }
}

function renderAgentList() {
  const el = document.getElementById('agent-list');
  
  // 按group分组
  const groups = {};
  agents.forEach(a => {
    const g = a.group || 'member';
    if (!groups[g]) groups[g] = [];
    groups[g].push(a);
  });

  const groupLabels = {
    system: '调度',
    member: '成员',
  };
  const groupOrder = ['system', 'member'];

  // 折叠状态（仅成员组可折叠）
  const collapsedKey = 'chat_agent_groups_collapsed';
  let collapsed = {};
  try { collapsed = JSON.parse(localStorage.getItem(collapsedKey) || '{}'); } catch(e) {}

  el.innerHTML = groupOrder.map(gid => {
    const items = groups[gid];
    if (!items || items.length === 0) return '';
    const label = groupLabels[gid] || gid;
    const isCollapsible = gid !== 'system';
    const isCollapsed = isCollapsible && collapsed[gid];
    return `<div class="agent-group">
      <div class="agent-group-header${isCollapsible ? ' collapsible' : ''}" ${isCollapsible ? `onclick="toggleGroup('${gid}')"` : ''}>
        ${isCollapsible ? `<span class="arrow ${isCollapsed ? 'collapsed' : ''}">▼</span>` : ''}
        ${label} (${items.length})
      </div>
      <div class="agent-group-body${isCollapsed ? ' collapsed' : ''}">
        ${items.map(a => {
          const active = currentAgent && currentAgent.id === a.id ? 'active' : '';
          return `<div class="agent-item ${active}" data-agent-id="${a.id}" onclick="selectAgent('${a.id}')">
            <div class="av" style="background:${a.color}">${a.avatar}</div>
            <div class="info">
              <div class="name">${escHtml(a.name)}</div>
              <div class="desc">${escHtml(a.description || a.capabilities || '')}</div>
            </div>
            <span class="dot ${a.status}"></span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }).join('');
}

function toggleGroup(gid) {
  // 仅成员组可折叠，调度组忽略
  if (gid === 'system') return;
  const key = 'chat_agent_groups_collapsed';
  let collapsed = {};
  try { collapsed = JSON.parse(localStorage.getItem(key) || '{}'); } catch(e) {}
  collapsed[gid] = !collapsed[gid];
  localStorage.setItem(key, JSON.stringify(collapsed));
  renderAgentList();
}

// ==================== 智能体切换 ====================
function selectAgent(agentId) {
  const agent = agents.find(a => a.id === agentId);
  if (!agent) return;
  currentAgent = agent;
  // 切到该智能体的独立会话
  currentSession = agentSessionId(agentId);

  // 更新头像
  document.getElementById('cur-avatar').textContent = agent.avatar;
  document.getElementById('cur-avatar').style.background = agent.color;
  document.getElementById('cur-name').textContent = agent.name;
  const statusMap = {online:'🟢', offline:'🔴', busy:'🟡'};
  document.getElementById('cur-status').textContent = (statusMap[agent.status]||'🟢') + ' ' + (agent.description || '');

  // 启用输入框
  input.disabled = false;
  sendBtn.disabled = false;
  document.getElementById('attach-btn').disabled = false;
  input.placeholder = '对 ' + agent.name + ' 说…';
  input.focus();

  // 高亮
  document.querySelectorAll('.agent-item').forEach(el => el.classList.remove('active'));
  const activeEl = document.querySelector(`.agent-item[data-agent-id="${agentId}"]`);
  if (activeEl) activeEl.classList.add('active');

  // 如果当前会话没有消息，或者没有智能体的历史，重置会话
  loadHistory();
}

// ==================== 会话管理 ====================
async function loadSessions() {
  try {
    const r = await fetch('/api/chat/sessions');
    const data = await r.json();
    if (data.code !== 0) return;
    sessions = data.data || [];
    renderSessionList();
  } catch(e) { console.error('load sessions fail:', e); }
}

function renderSessionList() {
  const el = document.getElementById('session-list');
  if (!sessions.length) {
    el.innerHTML = '<div style="padding:12px;font-size:11px;opacity:.4;text-align:center">暂无历史对话</div>';
    return;
  }
  el.innerHTML = sessions.map(s => {
    const active = s.session_id === currentSession ? 'active' : '';
    return `<div class="session-item ${active}" onclick="switchSession('${s.session_id}')">
      <span class="s-title">${escHtml(s.title)}</span>
      <span class="s-time">${(s.last_time||'').slice(5,16)}</span>
      <button class="s-del" onclick="event.stopPropagation();deleteSession('${s.session_id}')">✕</button>
    </div>`;
  }).join('');
}

function escHtml(s) { return String(s).replace(/[<>&"]/g,function(m){return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[m];}); }

async function switchSession(sessionId) {
  currentSession = sessionId;
  renderSessionList();
  loadHistory();
}

function newSession() {
  const base = currentAgent ? agentSessionId(currentAgent.id) : 'session';
  currentSession = base + '_new_' + Date.now();
  chatArea.innerHTML = '<div class="msg system">新对话已创建</div>';
  loadSessions();
  if (currentAgent) {
    input.disabled = false;
    sendBtn.disabled = false;
    document.getElementById('attach-btn').disabled = false;
    input.focus();
  }
}

async function deleteSession(sessionId) {
  if (!confirm('确定删除此对话？')) return;
  try {
    await fetch('/api/chat/session/' + sessionId, {method:'DELETE'});
    if (currentSession === sessionId) {
      currentSession = currentAgent ? agentSessionId(currentAgent.id) : 'default';
      chatArea.innerHTML = '<div class="msg system">对话已删除，选择智能体开始新对话</div>';
    }
    loadSessions();
  } catch(e) { alert('删除失败'); }
}

// ==================== 聊天 ====================
async function loadHistory() {
  if (loadingHistory) return;
  loadingHistory = true;
  try {
    const r = await fetch('/api/chat/history/' + encodeURIComponent(currentSession));
    const data = await r.json();
    if (data.code !== 0) return;
    const messages = data.data.messages || [];
    chatArea.innerHTML = '';
    if (messages.length === 0) {
      chatArea.innerHTML = '<div class="msg system">开始和 ' + (currentAgent ? currentAgent.name : '智能体') + ' 对话吧</div>';
    } else {
      messages.forEach(m => addMessage(m.role, m.content, false));
    }
    chatArea.scrollTop = chatArea.scrollHeight;
  } catch(e) { console.error('load history fail:', e); }
  loadingHistory = false;
}

function addMessage(role, content, save) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;

  // 检查是否是文件消息（JSON格式）
  let hasFile = false;
  if (typeof content === 'string' && content.startsWith('[FILE]')) {
    try {
      const fileData = JSON.parse(content.slice(6));
      hasFile = true;
      const isImage = fileData.type && fileData.type.startsWith('image/');
      const sizeStr = fileData.size > 1024*1024 ? (fileData.size/1024/1024).toFixed(1)+'MB' : (fileData.size/1024).toFixed(1)+'KB';
      const preview = document.createElement('div');
      preview.className = 'file-preview';
      if (isImage) {
        preview.innerHTML = `<img src="${fileData.url}" alt="${escHtml(fileData.name)}" onclick="window.open(this.src)" />`;
      } else {
        preview.innerHTML = `<div class="file-icon">📄</div><div class="file-info"><div class="fn">${escHtml(fileData.name)}</div><div class="fs">${sizeStr} · <a href="${fileData.url}" target="_blank" style="color:inherit">下载</a></div></div>`;
      }
      div.appendChild(preview);
    } catch(e) {
      div.textContent = content;
    }
  } else {
    div.textContent = content;
  }

  if (!hasFile) {
    const time = document.createElement('div');
    time.className = 'time';
    time.textContent = ts();
    div.appendChild(time);
  } else {
    // 文件消息也显示时间
    const time = document.createElement('div');
    time.className = 'time';
    time.textContent = ts();
    div.appendChild(time);
  }
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function showThinking() {
  hideThinking();
  const div = document.createElement('div');
  div.className = 'thinking';
  div.id = 'thinking-indicator';
  div.innerHTML = '<span>思考中</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function hideThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.remove();
}

async function send() {
  const msg = input.value.trim();
  if (!msg || !currentAgent) return;

  input.value = '';
  input.style.height = 'auto';
  addMessage('user', msg);
  showThinking();
  sendBtn.disabled = true;

  try {
    const r = await fetch('/api/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        message: msg,
        session_id: currentSession,
        agent_id: currentAgent.id
      })
    });
    const data = await r.json();
    hideThinking();
    if (data.code === 0 && data.data && data.data.reply) {
      addMessage('assistant', data.data.reply);
    } else {
      addMessage('system', '出错了：' + (data.message || '未知错误'));
    }
  } catch(e) {
    hideThinking();
    addMessage('system', '网络错误，请重试');
  }
  sendBtn.disabled = false;
  input.focus();
  // 刷新会话列表（可能有新会话标题）
  setTimeout(loadSessions, 500);
}

async function onFileSelected(event) {
  const files = event.target.files;
  if (!files || files.length === 0 || !currentAgent) return;
  event.target.value = '';
  for (const file of files) {
    addMessage('user', '[FILE]' + JSON.stringify({name: file.name, size: file.size, type: file.type, url: 'uploading...'}));
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch('/api/chat/upload', {method:'POST', body: form});
      const d = await r.json();
      if (d.code !== 0) throw new Error(d.message);
      const fileData = d.data;
      // 发消息给智能体，带上文件
      const fileMsg = '[FILE]' + JSON.stringify({name: fileData.name, size: fileData.size, type: file.type, url: fileData.url});
      sendBtn.disabled = true;
      showThinking();
      const res = await fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message: fileMsg, session_id: currentSession, agent_id: currentAgent.id})
      });
      hideThinking();
      const resData = await res.json();
      if (resData.code === 0 && resData.data && resData.data.reply) {
        addMessage('assistant', resData.data.reply);
      }
      sendBtn.disabled = false;
    } catch(e) {
      hideThinking();
      addMessage('system', '文件上传失败: ' + e.message);
      sendBtn.disabled = false;
    }
  }
}

// ==================== 初始化 ====================
async function init() {
  await loadAgents();
  await loadSessions();
  // 默认选中调度员
  const dispatcher = agents.find(a => a.id === 'dispatcher');
  if (dispatcher) selectAgent('dispatcher');
}
init();
</script>
</body>
</html>"""


def get_chat_html() -> str:
    return _CHAT_HTML
