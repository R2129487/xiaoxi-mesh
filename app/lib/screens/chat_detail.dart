import 'package:flutter/material.dart';
import 'dart:convert';
import '../services/dispatcher_api.dart';
import '../models/message.dart';

/// 聊天详情页 — 微信风格消息列表 + 输入框
class ChatDetail extends StatefulWidget {
  final String agentId;
  final String agentName;
  final Color agentColor;
  final String agentAvatar;
  final String sessionId;

  const ChatDetail({
    super.key,
    required this.agentId,
    required this.agentName,
    required this.agentColor,
    required this.agentAvatar,
    required this.sessionId,
  });

  @override
  State<ChatDetail> createState() => _ChatDetailState();
}

class _ChatDetailState extends State<ChatDetail> {
  final DispatcherApi _api = DispatcherApi();
  final TextEditingController _textCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();
  List<Message> _messages = [];
  bool _loading = true;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    final msgs = await _api.getHistory(widget.sessionId);
    if (mounted) {
      setState(() { _messages = msgs; _loading = false; });
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  void _scrollToBottom() {
    if (_scrollCtrl.hasClients) {
      _scrollCtrl.animateTo(
        _scrollCtrl.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _sendMessage() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty || _sending) return;

    _textCtrl.clear();
    setState(() {
      _sending = true;
      _messages.add(Message(
        id: DateTime.now().microsecondsSinceEpoch.toString(),
        content: text,
        fromAgent: 'user',
        toAgent: widget.agentId,
        isMe: true,
      ));
    });
    _scrollToBottom();

    final reply = await _api.sendMessage(text, widget.sessionId, widget.agentId);

    if (mounted) {
      setState(() {
        _sending = false;
        if (reply != null) {
          _messages.add(Message(
            id: DateTime.now().microsecondsSinceEpoch.toString(),
            content: reply,
            fromAgent: widget.agentId,
            toAgent: 'user',
            isMe: false,
          ));
        } else {
          _messages.add(Message(
            id: DateTime.now().microsecondsSinceEpoch.toString(),
            content: '⚠️ 发送失败，请重试',
            fromAgent: 'system',
            toAgent: 'user',
            isMe: false,
          ));
        }
      });
      _scrollToBottom();
    }
  }

  Future<void> _pickFile() async {
    // 文件选择暂不支持，提示用户用网页版
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('文件发送请在网页版操作'), duration: Duration(seconds: 2)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              backgroundColor: widget.agentColor,
              radius: 16,
              child: Text(widget.agentAvatar, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 14)),
            ),
            const SizedBox(width: 8),
            Text(widget.agentName),
          ],
        ),
        backgroundColor: const Color(0xFFEDEDED),
      ),
      body: Column(
        children: [
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _messages.isEmpty
                    ? Center(
                        child: Text('开始和 ${widget.agentName} 对话吧',
                          style: TextStyle(color: Colors.grey[400], fontSize: 14)),
                      )
                    : ListView.builder(
                        controller: _scrollCtrl,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        itemCount: _messages.length,
                        itemBuilder: (_, i) => _buildMessageBubble(_messages[i]),
                      ),
          ),
          _buildInputBar(),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(Message msg) {
    final isUser = msg.isMe || msg.fromAgent == 'user';
    final isSystem = msg.fromAgent == 'system';

    if (isSystem) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.grey[200],
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(msg.content, style: TextStyle(color: Colors.grey[700], fontSize: 12)),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isUser) ...[
            CircleAvatar(
              backgroundColor: widget.agentColor,
              radius: 16,
              child: Text(widget.agentAvatar, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 12)),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.7),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: isUser ? const Color(0xFF1A73E8) : Colors.white,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(12),
                  topRight: const Radius.circular(12),
                  bottomLeft: Radius.circular(isUser ? 12 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 12),
                ),
                boxShadow: [
                  BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 2, offset: const Offset(0, 1)),
                ],
              ),
              child: Text(
                msg.content,
                style: TextStyle(color: isUser ? Colors.white : Colors.black87, fontSize: 15, height: 1.4),
              ),
            ),
          ),
          if (isUser) const SizedBox(width: 8),
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: EdgeInsets.only(
        left: 8, right: 8, top: 8,
        bottom: MediaQuery.of(context).padding.bottom + 8,
      ),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Color(0xFFE0E0E0), width: 0.5)),
      ),
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Icons.add_circle_outline, color: Color(0xFF8E8E93), size: 28),
            onPressed: _pickFile,
          ),
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: const Color(0xFFF0F0F0),
                borderRadius: BorderRadius.circular(6),
              ),
              child: TextField(
                controller: _textCtrl,
                maxLines: 4,
                minLines: 1,
                style: const TextStyle(fontSize: 16),
                decoration: const InputDecoration(
                  hintText: '输入消息...',
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(vertical: 8),
                ),
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
          ),
          const SizedBox(width: 4),
          IconButton(
            icon: Icon(
              Icons.send_rounded,
              color: _textCtrl.text.isNotEmpty ? const Color(0xFF1A73E8) : const Color(0xFF8E8E93),
              size: 28,
            ),
            onPressed: _sendMessage,
          ),
        ],
      ),
    );
  }
}
