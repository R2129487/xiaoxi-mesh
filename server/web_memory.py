"""调度员 - 记忆管理页面 HTML 模板"""

_MEMORY_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>记忆管理</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans SC',sans-serif;background:#f0f2f5;color:#333;padding:20px}
.container{max-width:860px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}
.subtitle{color:#999;font-size:13px;margin-bottom:16px}
.link-bar{text-align:right;margin-bottom:16px}
.link-bar a{color:#3498db;text-decoration:none;font-size:13px}
.link-bar a:hover{text-decoration:underline}
.card{background:#fff;border-radius:10px;padding:20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card h2{font-size:15px;font-weight:600;margin-bottom:12px}
.filter-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.filter-bar input,.filter-bar select{flex:1;min-width:160px;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none}
.filter-bar input:focus,.filter-bar select:focus{border-color:#3498db}
.filter-bar button{padding:8px 16px;background:#3498db;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}
.filter-bar button:hover{background:#2980b9}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 10px;border-bottom:2px solid #eee;font-size:11px;text-transform:uppercase;color:#888;font-weight:600}
td{padding:8px 10px;border-bottom:1px solid #f0f0f0;vertical-align:top;line-height:1.5}
td.val{max-width:400px;word-break:break-word;white-space:pre-wrap}
.cat-tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500}
.cat-tag.agent{background:#e8f4fd;color:#2980b9}
.cat-tag.rule{background:#fef3e2;color:#d68910}
.cat-tag.general{background:#e8f8f0;color:#27ae60}
.tag{display:inline-block;padding:1px 6px;border-radius:4px;background:#f0f0f0;color:#666;font-size:10px;margin:1px}
.btn-sm{padding:4px 10px;border:none;border-radius:4px;cursor:pointer;font-size:11px}
.btn-edit{background:#3498db;color:#fff}
.btn-del{background:#e74c3c;color:#fff}
.btn-edit:hover{background:#2980b9}
.btn-del:hover{background:#c0392b}
.action-cell{white-space:nowrap;display:flex;gap:4px}
.empty{text-align:center;padding:40px;color:#999;font-size:14px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.4);z-index:999;align-items:center;justify-content:center}
.modal.show{display:flex}
.modal-content{background:#fff;border-radius:12px;padding:24px;width:90%;max-width:520px;max-height:80vh;overflow-y:auto}
.modal-content h2{font-size:16px;margin-bottom:16px}
.modal-content .form-group{margin-bottom:12px}
.modal-content label{display:block;font-size:12px;font-weight:600;color:#555;margin-bottom:3px}
.modal-content input,.modal-content textarea,.modal-content select{width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;font-family:inherit}
.modal-content textarea{min-height:80px;resize:vertical}
.modal-content input:focus,.modal-content textarea:focus,.modal-content select:focus{border-color:#3498db}
.modal-btns{display:flex;gap:8px;margin-top:16px;justify-content:flex-end}
.modal-btns button{padding:8px 20px;border-radius:6px;border:none;cursor:pointer;font-size:13px}
.modal-btns .btn-primary{background:#3498db;color:#fff}
.modal-btns .btn-cancel{background:#eee;color:#666}
.toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;color:#fff;font-size:13px;z-index:9999;animation:fadeIn .3s}
.toast.success{background:#27ae60}
.toast.error{background:#e74c3c}
@keyframes fadeIn{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>
<div class="container">
  <div class="link-bar">
    <a href="/config">⚙️ 配置</a>
  </div>
  <h1>📝 记忆管理</h1>
  <div class="subtitle">调度员的记忆系统，记录各智能体职责和任务分配规则</div>

  <div class="card">
    <div class="filter-bar">
      <select id="cat-filter">
        <option value="">全部分类</option>
        <option value="agent">🤖 智能体档案</option>
        <option value="rule">📋 分配规则</option>
        <option value="general">📌 通用</option>
      </select>
      <input id="search-input" placeholder="搜索关键词…" />
      <button onclick="loadMemories()">🔍 搜索</button>
      <button onclick="showAddModal()" style="background:#27ae60">➕ 新增</button>
    </div>
    <table>
      <thead><tr>
        <th style="width:40px">#</th>
        <th>Key</th>
        <th>分类</th>
        <th>内容</th>
        <th>标签</th>
        <th style="width:80px">操作</th>
      </tr></thead>
      <tbody id="mem-table"></tbody>
    </table>
    <div class="empty" id="empty-msg" style="display:none">暂无记忆，点击「新增」添加</div>
  </div>
</div>

<div class="modal" id="modal">
  <div class="modal-content">
    <h2 id="modal-title">新增记忆</h2>
    <div class="form-group">
      <label>Key（唯一标识）</label>
      <input id="edit-key" placeholder="如 agent:xiaolan:role" />
    </div>
    <div class="form-group">
      <label>分类</label>
      <select id="edit-category">
        <option value="agent">🤖 智能体档案</option>
        <option value="rule">📋 分配规则</option>
        <option value="general">📌 通用</option>
      </select>
    </div>
    <div class="form-group">
      <label>内容</label>
      <textarea id="edit-value" rows="4" placeholder="描述该智能体的职责或分配规则"></textarea>
    </div>
    <div class="form-group">
      <label>标签（逗号分隔）</label>
      <input id="edit-tags" placeholder="如 新云,下载,GitHub" />
    </div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeModal()">取消</button>
      <button class="btn-primary" onclick="saveMemory()">保存</button>
    </div>
  </div>
</div>

<script>
let editingKey = null;

async function loadMemories() {
  const cat = document.getElementById('cat-filter').value;
  const search = document.getElementById('search-input').value.trim();
  let url = '/api/memory?';
  if (search) url += 'search=' + encodeURIComponent(search);
  else if (cat) url += 'category=' + encodeURIComponent(cat);

  try {
    const r = await fetch(url);
    const d = await r.json();
    const items = d.data || [];
    const tbody = document.getElementById('mem-table');
    const empty = document.getElementById('empty-msg');

    if (items.length === 0) {
      tbody.innerHTML = '';
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';
    tbody.innerHTML = items.map((m, i) => {
      const catClass = m.category || 'general';
      const catLabel = {'agent':'智能体','rule':'规则','general':'通用'}[catClass] || catClass;
      const tags = (m.tags || '').split(',').filter(Boolean).map(t => `<span class="tag">${esc(t)}</span>`).join('');
      return `<tr>
        <td>${i+1}</td>
        <td style="font-family:monospace;font-size:12px">${esc(m.key)}</td>
        <td><span class="cat-tag ${catClass}">${catLabel}</span></td>
        <td class="val">${esc(m.value)}</td>
        <td>${tags}</td>
        <td class="action-cell">
          <button class="btn-sm btn-edit" onclick="editMemory('${esc(m.key)}')">编辑</button>
          <button class="btn-sm btn-del" onclick="deleteMemory('${esc(m.key)}')">删除</button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) {
    showToast('加载失败: ' + e.message, 'error');
  }
}

function showAddModal() {
  editingKey = null;
  document.getElementById('modal-title').textContent = '新增记忆';
  document.getElementById('edit-key').value = '';
  document.getElementById('edit-key').disabled = false;
  document.getElementById('edit-category').value = 'agent';
  document.getElementById('edit-value').value = '';
  document.getElementById('edit-tags').value = '';
  document.getElementById('modal').classList.add('show');
}

async function editMemory(key) {
  try {
    const r = await fetch('/api/memory?key=' + encodeURIComponent(key));
    const d = await r.json();
    const items = d.data || [];
    if (items.length === 0) { showToast('未找到', 'error'); return; }
    const m = items[0];
    editingKey = key;
    document.getElementById('modal-title').textContent = '编辑记忆';
    document.getElementById('edit-key').value = m.key;
    document.getElementById('edit-key').disabled = true;
    document.getElementById('edit-category').value = m.category || 'general';
    document.getElementById('edit-value').value = m.value;
    document.getElementById('edit-tags').value = m.tags || '';
    document.getElementById('modal').classList.add('show');
  } catch(e) {
    showToast('加载失败: ' + e.message, 'error');
  }
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
}

async function saveMemory() {
  const key = document.getElementById('edit-key').value.trim();
  const category = document.getElementById('edit-category').value;
  const value = document.getElementById('edit-value').value.trim();
  const tags = document.getElementById('edit-tags').value.trim();

  if (!key || !value) { showToast('Key和内容不能为空', 'error'); return; }

  try {
    const r = await fetch('/api/memory', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({key, category, value, tags}),
    });
    const d = await r.json();
    if (d.code !== 0) throw new Error(d.message);
    showToast('✅ 记忆已保存', 'success');
    closeModal();
    loadMemories();
  } catch(e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function deleteMemory(key) {
  if (!confirm('确定删除「' + key + '」？')) return;
  try {
    const r = await fetch('/api/memory?key=' + encodeURIComponent(key), {method:'DELETE'});
    const d = await r.json();
    if (d.code !== 0) throw new Error(d.message);
    showToast('✅ 已删除', 'success');
    loadMemories();
  } catch(e) {
    showToast('删除失败: ' + e.message, 'error');
  }
}

function esc(s) {
  return String(s).replace(/[<>&"]/g, function(m) {
    return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[m];
  });
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// 回车搜索
document.getElementById('search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') loadMemories();
});

loadMemories();
</script>
</body>
</html>"""


def get_memory_html() -> str:
    return _MEMORY_HTML
