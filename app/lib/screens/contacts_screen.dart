import 'package:flutter/material.dart';
import '../services/dispatcher_api.dart';
import '../models/agent.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

/// 联系人页面 — 显示所有智能体
class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen> {
  final DispatcherApi _api = DispatcherApi();
  List<Agent> _agents = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadAgents();
  }

  Future<void> _loadAgents() async {
    setState(() => _loading = true);
    final agents = await _api.getAgents();
    if (mounted) setState(() { _agents = agents; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('联系人')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadAgents,
              child: ListView.builder(
                padding: const EdgeInsets.only(top: 8),
                itemCount: _agents.length,
                itemBuilder: (_, i) {
                  final a = _agents[i];
                  return ListTile(
                    leading: CircleAvatar(
                      backgroundColor: _agentColor(a.agentId),
                      child: Text(a.avatar, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 16)),
                    ),
                    title: Text(a.displayName, style: const TextStyle(fontWeight: FontWeight.w500)),
                    subtitle: Text(
                      a.online ? '在线' : '离线',
                      style: TextStyle(color: a.online ? Colors.green : Colors.grey, fontSize: 12),
                    ),
                    trailing: Container(
                      width: 8, height: 8,
                      decoration: BoxDecoration(
                        color: a.online ? Colors.green : Colors.grey,
                        shape: BoxShape.circle,
                      ),
                    ),
                  );
                },
              ),
            ),
    );
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
}
