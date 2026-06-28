import 'package:flutter/material.dart';
import '../services/dispatcher_api.dart';
import '../models/agent.dart';
import 'chat_detail.dart';

/// 对话列表 — 微信首页风格，显示所有对话
class ConversationList extends StatefulWidget {
  const ConversationList({super.key});

  @override
  State<ConversationList> createState() => _ConversationListState();
}

class _ConversationListState extends State<ConversationList> {
  final DispatcherApi _api = DispatcherApi();
  List<Agent> _agents = [];
  List<Map<String, dynamic>> _sessions = [];
  Map<String, String> _lastMessages = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _loading = true);
    final agents = await _api.getAgents();
    final sessions = await _api.getSessions();
    // 获取每个会话的最后一条消息
    final lastMsgs = <String, String>{};
    for (final s in sessions) {
      final sid = s['session_id'] as String;
      final history = await _api.getHistory(sid);
      if (history.isNotEmpty) {
        lastMsgs[sid] = history.last.content;
      }
    }
    if (mounted) {
      setState(() {
        _agents = agents;
        _sessions = sessions;
        _lastMessages = lastMsgs;
        _loading = false;
      });
    }
  }

  String _agentName(String id) {
    for (final a in _agents) {
      if (a.agentId == id) return a.displayName;
    }
    switch (id) {
      case 'dispatcher': return '调度员';
      case 'xiao-qing': return '小青';
      case 'xiao-lan': return '小蓝';
      case 'xiao-bai': return '小白';
      case 'xiao-hei': return '小黑';
      default: return id;
    }
  }

  String _agentIdFromSession(String sessionId) {
    // session_agent_dispatcher → dispatcher
    for (final prefix in ['session_agent_', 'session_']) {
      if (sessionId.startsWith(prefix)) {
        return sessionId.substring(prefix.length);
      }
    }
    return 'dispatcher';
  }

  Color _agentColor(String id) {
    switch (id) {
      case 'dispatcher': return const Color(0xFF3498db);
      case 'xiao-qing': return const Color(0xFFe67e22);
      case 'xiao-lan': return const Color(0xFF3498db);
      case 'xiao-bai': return const Color(0xFF95a5a6);
      case 'xiao-hei': return const Color(0xFFe74c3c);
      default: return Colors.grey;
    }
  }

  String _agentAvatar(String id) {
    switch (id) {
      case 'dispatcher': return '调';
      case 'xiao-qing': return '青';
      case 'xiao-lan': return '蓝';
      case 'xiao-bai': return '白';
      case 'xiao-hei': return '黑';
      default: return '?';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('小青'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            onPressed: () => _showNewChat(context),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadData,
              child: _sessions.isEmpty
                  ? ListView(
                      children: [
                        const SizedBox(height: 80),
                        Center(
                          child: Column(
                            children: [
                              Icon(Icons.chat_bubble_outline, size: 64, color: Colors.grey[300]),
                              const SizedBox(height: 16),
                              Text('暂无对话', style: TextStyle(color: Colors.grey[500], fontSize: 14)),
                              const SizedBox(height: 24),
                              TextButton.icon(
                                onPressed: () => _showNewChat(context),
                                icon: const Icon(Icons.add),
                                label: const Text('开始新对话'),
                              ),
                            ],
                          ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.only(top: 4),
                      itemCount: _sessions.length,
                      itemBuilder: (_, i) {
                        final s = _sessions[i];
                        final sid = s['session_id'] as String;
                        final agentId = _agentIdFromSession(sid);
                        final lastMsg = _lastMessages[sid] ?? '';
                        final time = s['last_time'] as String? ?? '';
                        final displayTime = time.length >= 16 ? time.substring(5, 16) : time.substring(0, 10);

                        return Column(
                          children: [
                            ListTile(
                              leading: CircleAvatar(
                                backgroundColor: _agentColor(agentId),
                                child: Text(_agentAvatar(agentId), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 18)),
                              ),
                              title: Text(_agentName(agentId), style: const TextStyle(fontWeight: FontWeight.w500)),
                              subtitle: Text(
                                lastMsg.length > 30 ? '${lastMsg.substring(0, 30)}...' : lastMsg,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(color: Colors.grey[600], fontSize: 13),
                              ),
                              trailing: Text(displayTime, style: TextStyle(color: Colors.grey[400], fontSize: 11)),
                              onTap: () {
                                Navigator.push(context, MaterialPageRoute(
                                  builder: (_) => ChatDetail(
                                    agentId: agentId,
                                    agentName: _agentName(agentId),
                                    agentColor: _agentColor(agentId),
                                    agentAvatar: _agentAvatar(agentId),
                                    sessionId: sid,
                                  ),
                                )).then((_) => _loadData());
                              },
                              onLongPress: () => _deleteSession(sid),
                            ),
                            const Divider(height: 1, indent: 72),
                          ],
                        );
                      },
                    ),
            ),
    );
  }

  void _showNewChat(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(width: 40, height: 4, margin: const EdgeInsets.only(top: 12),
              decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(2)),
            ),
            const Padding(padding: EdgeInsets.all(16), child: Text('选择聊天对象', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
            const Divider(height: 1),
            ..._agents.map((a) => ListTile(
              leading: CircleAvatar(
                backgroundColor: _agentColor(a.agentId),
                child: Text(_agentAvatar(a.agentId), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
              ),
              title: Text(a.displayName),
              subtitle: Text(a.online ? '在线' : '离线', style: TextStyle(fontSize: 12, color: a.online ? Colors.green : Colors.grey)),
              onTap: () {
                Navigator.pop(ctx);
                final sessionId = 'session_agent_${a.agentId}';
                Navigator.push(context, MaterialPageRoute(
                  builder: (_) => ChatDetail(
                    agentId: a.agentId,
                    agentName: a.displayName,
                    agentColor: _agentColor(a.agentId),
                    agentAvatar: _agentAvatar(a.agentId),
                    sessionId: sessionId,
                  ),
                )).then((_) => _loadData());
              },
            )),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  void _deleteSession(String sessionId) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除对话'),
        content: const Text('确定删除此对话？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (confirm == true) {
      try {
        await _api.deleteSession(sessionId);
        _loadData();
      } catch (_) {}
    }
  }
}
