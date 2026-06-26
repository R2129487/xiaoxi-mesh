import 'package:flutter_test/flutter_test.dart';
import 'package:xiaoqing_app/models/agent.dart';

void main() {
  test('Agent 模型创建', () {
    final agent = Agent(agentId: 'xiaoqing', name: '小青', online: true, status: 'online');
    expect(agent.displayName, '小青');
    expect(agent.statusLabel, '在线');
  });
}
