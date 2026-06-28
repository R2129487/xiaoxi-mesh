/// 智能体模型
class Agent {
  final String agentId;
  final String displayName;
  final String avatar;
  final bool online;
  final String capabilities;

  Agent({
    required this.agentId,
    this.displayName = '',
    this.avatar = '?',
    this.online = false,
    this.capabilities = '',
  });
}
