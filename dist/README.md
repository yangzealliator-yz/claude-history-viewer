# Claude History Viewer

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English

A web-based viewer for Claude Code (CLI) conversation history. Browse, search, and explore your AI coding sessions with a beautiful dark-themed interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

### Features

- **Browse Sessions**: View all your Claude Code conversation history
- **Full-text Search**: Search across all conversations
- **File Path Detection**: Automatically highlights file paths in messages
- **Click to Open**: Click any file path to open it in your file explorer (WeChat-style)
- **Multi-source Support**: Supports both CLI sessions and web export data
- **Cloud Sync Ready**: Reserved API for future cloud synchronization
- **Pagination**: Efficiently handles large conversation histories
- **Dark Theme**: Easy on the eyes for long coding sessions

### Installation

```bash
# Clone the repository
git clone https://github.com/yangzealliator-yz/claude-history-viewer.git
cd claude-history-viewer

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

Open your browser: `http://localhost:5000`

### Usage

| Action | How |
|--------|-----|
| View conversation | Click session in left panel |
| Open file in folder | Click on highlighted file path |
| View file content | Ctrl + Click on file path |
| Search | Use search box at top |

### Data Sources

**1. Claude Code CLI (Auto-detected)**
```
~/.claude/projects/{project-name}/{session-id}.jsonl
```

**2. Web Export (Optional)**
```
~/.claude/web_export/conversations.json
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web interface |
| `GET /api/sessions` | List all sessions |
| `GET /api/conversation` | Get conversation |
| `GET /api/search` | Search conversations |
| `GET /api/file` | Read local file |
| `GET /api/open-folder` | Open in explorer |
| `GET /api/cloud/status` | Cloud sync status (reserved) |
| `POST /api/cloud/sync` | Sync to cloud (reserved) |

### Cloud Sync (Coming Soon)

Reserved endpoints for future cloud synchronization:
- Backup conversations to cloud
- Sync across devices
- Share sessions with team

---

<a name="中文"></a>
## 中文

基于 Web 的 Claude Code (CLI) 对话历史查看器。浏览、搜索和归档你的 AI 编程会话。

### 功能特性

- **会话浏览**：查看所有 Claude Code 对话历史
- **全文搜索**：跨所有会话搜索关键词
- **文件路径识别**：自动高亮消息中的文件路径
- **点击打开**：点击文件路径直接在资源管理器中显示（微信风格）
- **多数据源**：支持 CLI 本地会话和 Web 导出数据
- **云同步预留**：预留 API 接口，支持未来云端同步
- **分页加载**：高效处理大量对话历史
- **暗色主题**：长时间编码不伤眼

### 安装使用

```bash
# 克隆仓库
git clone https://github.com/yangzealliator-yz/claude-history-viewer.git
cd claude-history-viewer

# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
```

打开浏览器访问：`http://localhost:5000`

### 操作说明

| 操作 | 方式 |
|------|------|
| 查看对话 | 点击左侧会话列表 |
| 打开文件所在目录 | 点击高亮的文件路径 |
| 查看文件内容 | Ctrl + 点击文件路径 |
| 搜索 | 使用顶部搜索框 |

### 数据来源

**1. Claude Code CLI（自动检测）**
```
~/.claude/projects/{项目名}/{会话ID}.jsonl
```

**2. Web 导出（可选）**
```
~/.claude/web_export/conversations.json
```

### API 接口

| 接口 | 说明 |
|------|------|
| `GET /` | Web 界面 |
| `GET /api/sessions` | 获取所有会话 |
| `GET /api/conversation` | 获取对话内容 |
| `GET /api/search` | 搜索对话 |
| `GET /api/file` | 读取本地文件 |
| `GET /api/open-folder` | 在资源管理器中打开 |
| `GET /api/cloud/status` | 云同步状态（预留） |
| `POST /api/cloud/sync` | 同步到云端（预留） |

### 云同步功能（即将推出）

预留接口，未来支持：
- 对话备份到云端
- 多设备同步
- 团队共享会话

---

## License / 许可证

MIT License - 自由使用、修改、分发

## Contributing / 贡献

欢迎提交 Pull Request！

---

**Made with Claude Code**
