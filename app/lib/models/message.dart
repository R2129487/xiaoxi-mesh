/// 消息模型
class Message {
  final String id;
  final String content;
  final String fromAgent;
  final String toAgent;
  final DateTime timestamp;
  final bool isMe;

  Message({
    required this.id,
    required this.content,
    this.fromAgent = 'user',
    this.toAgent = '',
    DateTime? timestamp,
    this.isMe = false,
  }) : timestamp = timestamp ?? DateTime.now();
}
