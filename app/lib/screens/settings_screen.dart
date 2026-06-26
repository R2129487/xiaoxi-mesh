import 'package:flutter/material.dart';
import '../services/dispatcher_api.dart';

/// 设置页面
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final DispatcherApi _api = DispatcherApi();
  final _hostCtrl = TextEditingController(text: '<HOST_IP>');
  final _portCtrl = TextEditingController(text: '8767');
  bool _connected = false;
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    _checkConnection();
  }

  @override
  void dispose() {
    _hostCtrl.dispose();
    _portCtrl.dispose();
    super.dispose();
  }

  Future<void> _checkConnection() async {
    setState(() => _checking = true);
    _connected = await _api.checkConnection();
    if (mounted) setState(() => _checking = false);
  }

  Future<void> _connect() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim()) ?? 8767;
    _api.setServer(host, port);
    await _checkConnection();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 连接状态卡片
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('服务器连接', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Icon(
                        _checking ? Icons.hourglass_empty : (_connected ? Icons.check_circle : Icons.error),
                        color: _checking ? Colors.grey : (_connected ? Colors.green : Colors.red),
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _checking ? '检测中...' : (_connected ? '已连接' : '未连接'),
                        style: TextStyle(color: _checking ? Colors.grey : (_connected ? Colors.green : Colors.red)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        flex: 3,
                        child: TextField(
                          controller: _hostCtrl,
                          decoration: const InputDecoration(
                            labelText: '服务器地址',
                            border: OutlineInputBorder(),
                            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                            isDense: true,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 1,
                        child: TextField(
                          controller: _portCtrl,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: '端口',
                            border: OutlineInputBorder(),
                            contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                            isDense: true,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    children: [
                      actionChip('本机', '<HOST_IP>', '8767'),
                      actionChip('阿里云', '<SERVER_IP>', '8767'),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _connect,
                      icon: const Icon(Icons.link, size: 18),
                      label: const Text('连接'),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          // 关于卡片
          Card(
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: const Color(0xFFe67e22),
                child: const Text('青', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
              ),
              title: const Text('小青'),
              subtitle: const Text('v1.0.0'),
            ),
          ),
        ],
      ),
    );
  }

  Widget actionChip(String label, String host, String port) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontSize: 12)),
      onPressed: () {
        _hostCtrl.text = host;
        _portCtrl.text = port;
      },
    );
  }
}
