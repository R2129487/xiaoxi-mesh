import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/message.dart';
import '../models/agent.dart';

/// 调度器 HTTP API 客户端
/// 替代原来的 MESH WebSocket 连接
class DispatcherApi {
  String _host = '<HOST_IP>';
  int _port = 8767;

  String get baseUrl => 'http://$_host:$_port';

  void setServer(String host, int port) {
    _host = host;
    _port = port;
  }

  /// 获取可用智能体列表
  Future<List<Agent>> getAgents() async {
    try {
      final r = await http.get(Uri.parse('$baseUrl/api/chat/agents'))
          .timeout(const Duration(seconds: 5));
      if (r.statusCode != 200) return [];
      final data = json.decode(r.body);
      if (data['code'] != 0) return [];
      final list = data['data'] as List;
      return list.map((a) => Agent(
        agentId: a['id'],
        displayName: a['name'],
        avatar: a['avatar'] ?? a['name'][0],
        online: a['status'] == 'online',
        capabilities: a['capabilities'] ?? '',
      )).toList();
    } catch (_) {
      return [];
    }
  }

  /// 获取会话列表
  Future<List<Map<String, dynamic>>> getSessions() async {
    try {
      final r = await http.get(Uri.parse('$baseUrl/api/chat/sessions'))
          .timeout(const Duration(seconds: 5));
      if (r.statusCode != 200) return [];
      final data = json.decode(r.body);
      if (data['code'] != 0) return [];
      return List<Map<String, dynamic>>.from(data['data']);
    } catch (_) {
      return [];
    }
  }

  /// 获取聊天历史
  Future<List<Message>> getHistory(String sessionId) async {
    try {
      final r = await http.get(
        Uri.parse('$baseUrl/api/chat/history/${Uri.encodeComponent(sessionId)}'),
      ).timeout(const Duration(seconds: 5));
      if (r.statusCode != 200) return [];
      final data = json.decode(r.body);
      if (data['code'] != 0) return [];
      final msgs = data['data']['messages'] as List;
      return msgs.map((m) {
        final isUser = m['role'] == 'user';
        return Message(
          id: DateTime.now().microsecondsSinceEpoch.toString(),
          content: m['content'] ?? '',
          fromAgent: isUser ? 'user' : 'assistant',
          toAgent: isUser ? 'assistant' : 'user',
          timestamp: DateTime.tryParse(m['timestamp'] ?? '') ?? DateTime.now(),
          isMe: isUser,
        );
      }).toList();
    } catch (_) {
      return [];
    }
  }

  /// 发送消息
  Future<String?> sendMessage(String text, String sessionId, String agentId) async {
    try {
      final r = await http.post(
        Uri.parse('$baseUrl/api/chat'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'message': text,
          'session_id': sessionId,
          'agent_id': agentId,
        }),
      ).timeout(const Duration(seconds: 30));
      if (r.statusCode != 200) return null;
      final data = json.decode(r.body);
      if (data['code'] != 0) return null;
      return data['data']['reply'];
    } catch (_) {
      return null;
    }
  }

  /// 上传文件
  Future<Map<String, dynamic>?> uploadFile(List<int> bytes, String filename) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/chat/upload'),
      );
      request.files.add(http.MultipartFile.fromBytes(
        'file', bytes, filename: filename,
      ));
      final streamed = await request.send().timeout(const Duration(seconds: 30));
      final r = await http.Response.fromStream(streamed);
      if (r.statusCode != 200) return null;
      final data = json.decode(r.body);
      if (data['code'] != 0) return null;
      return data['data'];
    } catch (_) {
      return null;
    }
  }

  /// 检测连接状态
  Future<bool> checkConnection() async {
    try {
      final r = await http.get(Uri.parse('$baseUrl/api/status'))
          .timeout(const Duration(seconds: 3));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// 删除会话
  Future<bool> deleteSession(String sessionId) async {
    try {
      final r = await http.delete(
        Uri.parse('$baseUrl/api/chat/session/${Uri.encodeComponent(sessionId)}'),
      ).timeout(const Duration(seconds: 5));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
