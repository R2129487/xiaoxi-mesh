import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const XiaoQingApp());
}

class XiaoQingApp extends StatelessWidget {
  const XiaoQingApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '小青',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1A73E8), // 青蓝色
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFEDEDED),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFFEDEDED),
          foregroundColor: Color(0xFF191919),
          elevation: 0,
          centerTitle: true,
          titleTextStyle: TextStyle(
            color: Color(0xFF191919),
            fontSize: 17,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      home: const HomeScreen(),
    );
  }
}
