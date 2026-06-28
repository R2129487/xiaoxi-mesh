# 小青 App

直连 MESH 系统的跨平台即时通讯客户端，替代微信/QQ 作为与智能体团队的通信入口。

## 架构

```
手机 App (Flutter) → WebSocket → MESH 服务器 (小蓝) → Agent Runners → Hermes
```

App 注册为 MESH 的特殊节点 `user`，不参与任务委派，只负责收发消息和查看任务状态。

## 核心功能

- **聊天** — 文字消息，支持 Markdown 渲染
- **任务创建** — 以 `#` 开头输入，自动创建 MESH 任务并分派
- **多 Agent 切换** — 横向滑动切换与小青/小蓝/小白的对话
- **文件传输** — 图片、文件上传与接收
- **任务状态跟踪** — 任务创建、执行、完成全流程可见

## 开发环境

```bash
# 安装 Flutter SDK
# 参考: https://flutter.dev/docs/get-started/install/linux

# 初始化（如果已有 pubspec.yaml 不需要 init）
cd ~/xiaoxi-project/xiaoqing-app
flutter pub get

# 运行
flutter run

# 构建 APK
flutter build apk
```

## 项目结构

```
lib/
  config/       — 配置
  models/       — 数据模型
  services/     — 服务层（MESH WebSocket 连接）
  screens/      — 页面
  widgets/      — 组件
  main.dart     — 入口

MESH 服务器（xiaoqing_app 在 MESH 中以 user 身份注册）:
  小蓝 IP: <SERVER_IP>:8765
```

## 部署（后续）

1. 备案为正式互联网应用
2. 打包 APK / IPA
3. 下载安装即可使用
