#!/usr/bin/env python3
"""
Claude Code 完整对话历史浏览器 v2
- 全文搜索（内容+标题）
- 显示匹配片段
- 多选导出
- 支持中文路径
- 显示图片

运行: python app.py
访问: http://localhost:{port}
"""

from flask import Flask, render_template_string, jsonify, request, Response
import json
import os
import re
import base64
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

# Analytics module integration (for local caching only, routes handled below)
# 分析模块集成（仅用于本地缓存，路由在下面处理）
try:
    import analytics_core
    # Don't pass app to avoid route conflicts / 不传 app 避免路由冲突
    _analytics = analytics_core.AnalyticsCore(app=None, cache_ref=None)
    ANALYTICS_MODULE_ENABLED = True
except ImportError:
    _analytics = None
    ANALYTICS_MODULE_ENABLED = False

# 支持的图片扩展名
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}

def extract_local_images(text):
    """从文本中提取本地图片路径并转换为 base64"""
    if not text:
        return []

    images = []

    # 匹配 Windows 路径 (如 d:\xxx\xxx.png 或 D:/xxx/xxx.png)
    # 也匹配 Unix 路径 (如 /home/xxx/xxx.png)
    path_pattern = r'([A-Za-z]:[\\\/][^\s\n\r<>"\'`]+\.(?:png|jpg|jpeg|gif|webp|bmp|ico)|\/[^\s\n\r<>"\'`]+\.(?:png|jpg|jpeg|gif|webp|bmp|ico))'

    matches = re.findall(path_pattern, text, re.IGNORECASE)

    for match in matches:
        try:
            # 标准化路径
            file_path = Path(match.replace('\\', '/').replace('/', os.sep))

            if file_path.exists() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                # 读取图片并转换为 base64
                with open(file_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode('utf-8')

                # 确定 media type
                ext = file_path.suffix.lower()
                media_types = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.bmp': 'image/bmp',
                    '.ico': 'image/x-icon'
                }
                media_type = media_types.get(ext, 'image/png')

                images.append({
                    'data': img_data,
                    'media_type': media_type,
                    'source_path': str(file_path)
                })
        except Exception as e:
            # 文件不存在或无法读取，跳过
            pass

    return images

# Claude Code 项目目录 (CLI)
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Claude 网页版导出目录
CLAUDE_WEB_EXPORT = Path.home() / ".claude" / "web_export"

# 缓存所有对话内容用于搜索
CONTENT_CACHE = {}

# 缓存网页版对话数据
WEB_CONVERSATIONS = {}

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Claude History Viewer v2</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0; padding: 0; background: #1a1a2e; color: #eee;
            display: flex; height: 100vh;
        }
        .sidebar {
            width: 400px; background: #16213e; overflow-y: auto;
            border-right: 1px solid #333; flex-shrink: 0;
        }
        .main { flex: 1; overflow-y: auto; padding: 20px; }
        .search {
            padding: 10px; position: sticky; top: 0; background: #16213e;
            border-bottom: 1px solid #333; z-index: 100;
        }
        .search input {
            width: 100%; padding: 12px; border: none; border-radius: 5px;
            background: #0f3460; color: #fff; font-size: 14px;
        }
        .search-options {
            display: flex; gap: 10px; margin-top: 8px; font-size: 12px;
            flex-wrap: wrap;
        }
        .search-options label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
        .search-options input[type="checkbox"] { accent-color: #e94560; }
        .search-options select {
            background: #0f3460; color: #fff; border: 1px solid #333;
            padding: 4px 8px; border-radius: 4px; font-size: 12px;
        }
        .toolbar {
            padding: 10px; background: #0f3460; display: flex; gap: 10px;
            align-items: center; font-size: 13px;
        }
        .toolbar button {
            padding: 8px 16px; background: #e94560; color: white;
            border: none; border-radius: 5px; cursor: pointer; font-size: 13px;
        }
        .toolbar button:hover { background: #ff6b6b; }
        .toolbar button:disabled { background: #666; cursor: not-allowed; }
        .session-list { padding: 10px; }
        .session-item {
            padding: 12px; margin: 5px 0; background: #0f3460;
            border-radius: 8px; cursor: pointer; transition: all 0.2s;
            display: flex; align-items: flex-start; gap: 10px;
        }
        .session-item:hover { background: #1a4a7a; }
        .session-item.active { background: #e94560; }
        .session-item input[type="checkbox"] {
            margin-top: 4px; accent-color: #e94560; flex-shrink: 0;
        }
        .session-content { flex: 1; min-width: 0; }
        .session-title {
            font-weight: 600; font-size: 14px;
            display: -webkit-box; -webkit-line-clamp: 2;
            -webkit-box-orient: vertical; overflow: hidden;
        }
        .session-meta { font-size: 12px; color: #888; margin-top: 5px; }
        .session-snippet {
            font-size: 12px; color: #aaa; margin-top: 8px;
            background: #0a0a1a; padding: 8px; border-radius: 4px;
            max-height: 60px; overflow: hidden;
        }
        .session-snippet mark {
            background: #e94560; color: white; padding: 0 2px; border-radius: 2px;
        }
        .message {
            margin: 15px 0; padding: 15px; border-radius: 10px;
            max-width: 85%;
        }
        .message.user {
            background: #0f3460; margin-left: auto;
        }
        .message.assistant {
            background: #1a1a2e; border: 1px solid #333;
        }
        .message.system {
            background: #2d132c; font-size: 12px; color: #888;
            max-width: 100%;
        }
        .message.summary {
            background: #1a3a1a; border: 1px solid #2a5a2a;
            max-width: 100%;
        }
        .message-role {
            font-size: 11px; color: #e94560; margin-bottom: 8px;
            text-transform: uppercase; font-weight: 600;
        }
        .message-content {
            white-space: pre-wrap; word-break: break-word;
            line-height: 1.6;
        }
        /* 折叠功能 */
        .collapsible {
            background: #0a0a1a; border: 1px solid #333; border-radius: 5px;
            margin: 8px 0; overflow: hidden;
        }
        .collapsible-header {
            padding: 8px 12px; cursor: pointer; display: flex;
            justify-content: space-between; align-items: center;
            background: #1a1a2e; font-size: 12px; color: #888;
        }
        .collapsible-header:hover { background: #252540; }
        .collapsible-header .arrow { transition: transform 0.2s; }
        .collapsible-header.open .arrow { transform: rotate(90deg); }
        .collapsible-content {
            max-height: 0; overflow: hidden; transition: max-height 0.3s;
            padding: 0 12px;
        }
        .collapsible-content.open {
            max-height: none; padding: 12px;
        }
        .thinking-block {
            background: #1a2a3a; border-left: 3px solid #4a9eff;
            padding: 10px; margin: 8px 0; font-size: 13px; color: #aaa;
        }
        .tool-block {
            background: #0a0a1a; border-left: 3px solid #e94560;
            padding: 10px; margin: 8px 0; font-size: 13px;
        }
        .tool-result-block {
            background: #0a1a0a; border-left: 3px solid #4ae945;
            padding: 10px; margin: 8px 0; font-size: 13px;
        }
        .tool-error-block {
            background: #1a0a0a; border-left: 3px solid #e94545;
            padding: 10px; margin: 8px 0; font-size: 13px;
        }
        .message-content img {
            max-width: 100%; border-radius: 8px; margin: 10px 0;
        }
        .message-content mark {
            background: #e94560; color: white; padding: 0 2px; border-radius: 2px;
        }
        .stats {
            padding: 15px; background: #0f3460; margin: 10px;
            border-radius: 8px; font-size: 13px;
        }
        code {
            background: #333; padding: 2px 6px; border-radius: 3px;
            font-size: 13px;
        }
        pre {
            background: #0a0a1a; padding: 15px; border-radius: 8px;
            overflow-x: auto;
        }
        .loading { text-align: center; padding: 50px; color: #666; }
        /* 文件链接样式 */
        .file-link {
            color: #4ae9ff; cursor: pointer; text-decoration: underline;
            background: #0a2a3a; padding: 2px 6px; border-radius: 3px;
        }
        .file-link:hover { background: #1a4a5a; }
        .file-content-container {
            background: #0a0a1a; border: 1px solid #333; border-radius: 8px;
            margin: 10px 0; overflow: hidden;
        }
        .file-content-container.hidden { display: none; }
        .file-header {
            display: flex; align-items: center; gap: 15px;
            padding: 10px 15px; background: #1a1a2e; border-bottom: 1px solid #333;
        }
        .file-name { font-weight: 600; color: #4ae9ff; }
        .file-size { color: #666; font-size: 12px; }
        .file-close {
            margin-left: auto; cursor: pointer; color: #888;
            padding: 2px 8px; border-radius: 3px;
        }
        .file-close:hover { background: #333; color: #fff; }
        .header-btn {
            padding: 2px 8px; border: 1px solid #444; border-radius: 3px;
            font-size: 11px; cursor: pointer; background: #1a3a1a; color: #8f8;
        }
        .header-btn:hover { background: #2a5a2a; }
        .file-code {
            margin: 0; padding: 15px; max-height: 500px; overflow: auto;
            font-size: 13px; line-height: 1.5;
        }
        .file-loading { padding: 20px; text-align: center; color: #666; }
        .file-error { padding: 15px; color: #e94560; background: #1a0a0a; }
        .file-lang { color: #4ae945; font-size: 12px; background: #0a2a0a; padding: 2px 8px; border-radius: 3px; }
        .file-image-preview { padding: 15px; text-align: center; background: #111; }
        .file-image-preview img { max-width: 100%; max-height: 600px; border-radius: 4px; }
        .file-binary-info { padding: 20px; text-align: center; color: #888; }
        .file-binary-info button {
            margin-top: 10px; padding: 8px 20px; background: #0f3460;
            color: #fff; border: 1px solid #333; border-radius: 5px; cursor: pointer;
        }
        .file-binary-info button:hover { background: #1a4a7a; }
        .open-folder-btn { background: #2a5a2a !important; }
        .open-folder-btn:hover { background: #3a7a3a !important; }
        /* Toast 提示 */
        .toast {
            position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
            background: #2a5a2a; color: white; padding: 12px 24px;
            border-radius: 8px; z-index: 10000; animation: slideUp 0.3s ease;
        }
        .toast.error { background: #5a2a2a; }
        .toast.file-not-found {
            display: flex; align-items: flex-start; gap: 12px;
            background: linear-gradient(135deg, #8B4513 0%, #5a3a1a 100%);
            border: 2px solid #FFA500; padding: 16px 20px; max-width: 600px;
            box-shadow: 0 8px 32px rgba(255, 165, 0, 0.3);
        }
        .toast.file-not-found .toast-icon { font-size: 28px; }
        .toast.file-not-found .toast-content { flex: 1; }
        .toast.file-not-found .toast-title { font-size: 16px; font-weight: bold; color: #FFD700; margin-bottom: 4px; }
        .toast.file-not-found .toast-desc { font-size: 13px; color: #ddd; margin-bottom: 8px; }
        .toast.file-not-found .toast-path { font-size: 11px; color: #aaa; word-break: break-all; background: rgba(0,0,0,0.3); padding: 6px 8px; border-radius: 4px; }
        .toast.file-not-found .toast-btn { background: #0f3460; border: none; color: white; padding: 8px 16px; border-radius: 4px; cursor: pointer; white-space: nowrap; font-size: 13px; }
        .toast.file-not-found .toast-btn:hover { background: #1a5a8a; }
        /* Consent Dialog / 同意弹窗 */
        .consent-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 20000; display: flex; align-items: center; justify-content: center; }
        .consent-dialog { background: #1a1a2e; border: 1px solid #333; border-radius: 12px; padding: 30px; max-width: 500px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); }
        .consent-dialog h2 { margin: 0 0 20px 0; color: #4fc3f7; font-size: 20px; }
        .consent-content { color: #ccc; font-size: 13px; line-height: 1.6; margin-bottom: 24px; }
        .consent-content p { margin: 0 0 12px 0; }
        .consent-note { color: #888; font-size: 12px; font-style: italic; }
        .consent-buttons { display: flex; gap: 12px; justify-content: flex-end; }
        .consent-btn { padding: 10px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
        .consent-btn.agree { background: #2a5a2a; color: white; }
        .consent-btn.agree:hover { background: #3a7a3a; }
        .consent-btn.decline { background: #333; color: #aaa; }
        .consent-btn.decline:hover { background: #444; }
        .toast.fade-out { animation: fadeOut 0.3s ease forwards; }
        @keyframes slideUp { from { opacity: 0; transform: translateX(-50%) translateY(20px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes fadeOut { to { opacity: 0; transform: translateX(-50%) translateY(-10px); } }
        .load-more {
            text-align: center; padding: 20px;
        }
        .load-more button {
            padding: 12px 30px; background: #0f3460; color: #fff;
            border: 1px solid #333; border-radius: 8px; cursor: pointer;
            font-size: 14px;
        }
        .load-more button:hover { background: #1a4a7a; }
        h1 { margin: 0; padding: 20px; font-size: 18px; }
        .result-count {
            padding: 10px; font-size: 13px; color: #888;
            border-bottom: 1px solid #333;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <h1>🔍 Claude History v2</h1>
        <div class="stats" id="stats">Loading...</div>
        <div class="search">
            <input type="text" id="searchInput" placeholder="搜索对话内容..." onkeyup="handleSearch(event)">
            <div class="search-options">
                <label><input type="checkbox" id="searchContent" checked> 搜索内容</label>
                <label><input type="checkbox" id="searchTitle" checked> 搜索标题</label>
                <select id="sortBy" onchange="performSearch()">
                    <option value="time_desc">时间 (最新)</option>
                    <option value="time_asc">时间 (最早)</option>
                    <option value="matches">匹配次数</option>
                    <option value="title">标题 A-Z</option>
                </select>
                <select id="sourceFilter" onchange="performSearch()">
                    <option value="all">全部来源</option>
                    <option value="cli">仅 CLI</option>
                    <option value="web">仅网页版</option>
                </select>
                <label title="加载消息中引用的本地图片路径"><input type="checkbox" id="loadLocalImages"> 加载本地图片</label>
            </div>
        </div>
        <div class="toolbar">
            <button onclick="selectAll()">全选</button>
            <button onclick="deselectAll()">取消</button>
            <button onclick="exportSelected()" id="exportBtn" disabled>导出选中 (0)</button>
        </div>
        <div class="result-count" id="resultCount"></div>
        <div class="session-list" id="sessionList">
            <div class="loading">加载中...</div>
        </div>
    </div>
    <div class="main" id="mainContent">
        <div class="loading">← 搜索或选择会话</div>
    </div>

    <script>
        let allSessions = [];
        let searchResults = [];
        let selectedIds = new Set();
        let currentQuery = '';
        let currentMessages = [];
        let displayedCount = 0;
        const PAGE_SIZE = 50;

        async function loadSessions() {
            const res = await fetch('/api/sessions');
            const data = await res.json();
            allSessions = data.sessions;

            document.getElementById('stats').innerHTML = `
                <div>📁 项目: ${data.stats.projects}</div>
                <div>💬 会话: ${data.stats.sessions}</div>
                <div>📝 消息: ${data.stats.messages.toLocaleString()}</div>
            `;

            searchResults = allSessions;
            renderSessions(allSessions);
            updateResultCount(allSessions.length);
        }

        function handleSearch(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        }

        async function performSearch() {
            const query = document.getElementById('searchInput').value.trim();
            const searchContent = document.getElementById('searchContent').checked;
            const searchTitle = document.getElementById('searchTitle').checked;
            const sortBy = document.getElementById('sortBy').value;
            const sourceFilter = document.getElementById('sourceFilter').value;

            currentQuery = query;
            document.getElementById('sessionList').innerHTML = '<div class="loading">搜索中...</div>';

            let results;
            if (!query) {
                results = [...allSessions];
            } else {
                const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&content=${searchContent}&title=${searchTitle}`);
                results = await res.json();
            }

            // 来源筛选
            if (sourceFilter !== 'all') {
                results = results.filter(s => s.source === sourceFilter);
            }

            // 排序
            if (sortBy === 'time_desc') {
                results.sort((a, b) => b.timestamp - a.timestamp);
            } else if (sortBy === 'time_asc') {
                results.sort((a, b) => a.timestamp - b.timestamp);
            } else if (sortBy === 'matches') {
                results.sort((a, b) => (b.match_count || 0) - (a.match_count || 0));
            } else if (sortBy === 'title') {
                results.sort((a, b) => a.title.localeCompare(b.title));
            }

            searchResults = results;
            renderSessions(results, query);
            updateResultCount(results.length, query);
        }

        function renderSessions(sessions, highlightQuery = '') {
            const html = sessions.map(s => {
                const checked = selectedIds.has(s.id) ? 'checked' : '';
                let snippet = '';
                if (s.snippet && highlightQuery) {
                    snippet = `<div class="session-snippet">${highlightText(s.snippet, highlightQuery)}</div>`;
                }
                const sourceTag = s.source === 'web' ? '<span style="color:#4ae945;font-size:10px;">[Web]</span> ' : '';
                const matchInfo = s.match_count ? `<span style="color:#e94560;font-size:10px;"> (${s.match_count}次匹配)</span>` : '';
                return `
                    <div class="session-item" data-id="${s.id}">
                        <input type="checkbox" ${checked} onclick="toggleSelect(event, '${s.id}')">
                        <div class="session-content" onclick="loadConversation('${s.id}', '${s.project}', '${escapeHtml(highlightQuery)}')">
                            <div class="session-title">${sourceTag}${highlightText(escapeHtml(s.title), highlightQuery)}</div>
                            <div class="session-meta">${s.project_name} · ${s.date}${matchInfo}</div>
                            ${snippet}
                        </div>
                    </div>
                `;
            }).join('');
            document.getElementById('sessionList').innerHTML = html || '<div class="loading">无结果</div>';
        }

        function highlightText(text, query) {
            if (!query) return text;
            const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
            return text.replace(regex, '<mark>$1</mark>');
        }

        function escapeRegex(str) {
            return str.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
        }

        function updateResultCount(count, query = '') {
            const el = document.getElementById('resultCount');
            if (query) {
                el.textContent = `找到 ${count} 个匹配 "${query}"`;
            } else {
                el.textContent = `共 ${count} 个会话`;
            }
        }

        function toggleSelect(e, id) {
            e.stopPropagation();
            if (e.target.checked) {
                selectedIds.add(id);
            } else {
                selectedIds.delete(id);
            }
            updateExportBtn();
        }

        function selectAll() {
            searchResults.forEach(s => selectedIds.add(s.id));
            renderSessions(searchResults, currentQuery);
            updateExportBtn();
        }

        function deselectAll() {
            selectedIds.clear();
            renderSessions(searchResults, currentQuery);
            updateExportBtn();
        }

        function updateExportBtn() {
            const btn = document.getElementById('exportBtn');
            btn.textContent = `导出选中 (${selectedIds.size})`;
            btn.disabled = selectedIds.size === 0;
        }

        async function exportSelected() {
            if (selectedIds.size === 0) return;

            const ids = Array.from(selectedIds);
            const res = await fetch('/api/export', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ids: ids, sessions: searchResults.filter(s => ids.includes(s.id))})
            });

            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `claude_export_${new Date().toISOString().slice(0,10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }

        async function loadConversation(sessionId, project, query) {
            document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
            event.target.closest('.session-item').classList.add('active');

            document.getElementById('mainContent').innerHTML = '<div class="loading">加载中...</div>';

            const loadLocal = document.getElementById('loadLocalImages').checked;
            const res = await fetch(`/api/conversation?session=${sessionId}&project=${encodeURIComponent(project)}&load_local=${loadLocal}`);
            currentMessages = await res.json();
            displayedCount = 0;
            currentQuery = query;

            renderMessages(true);
        }

        function renderMessages(reset = false) {
            const startIdx = displayedCount;
            const endIdx = Math.min(displayedCount + PAGE_SIZE, currentMessages.length);
            const messagesToRender = currentMessages.slice(startIdx, endIdx);

            const html = messagesToRender.map((m, i) => {
                const idx = startIdx + i;
                let content = m.content || '';
                if (currentQuery) {
                    content = highlightText(escapeHtml(content), currentQuery);
                } else {
                    content = escapeHtml(content);
                }
                // 渲染图片
                if (m.images && m.images.length > 0) {
                    m.images.forEach(img => {
                        const imgData = typeof img === 'object' ? img.data : img;
                        const mediaType = typeof img === 'object' ? (img.media_type || 'image/png') : 'image/png';
                        const sourcePath = typeof img === 'object' ? (img.source_path || '') : '';
                        if (sourcePath) {
                            content += `<br><div style="font-size:10px;color:#888;margin-top:10px;">📷 ${sourcePath}</div>`;
                        }
                        content += `<img src="data:${mediaType};base64,${imgData}" style="max-width:100%;border-radius:8px;margin:5px 0;" loading="lazy" />`;
                    });
                }
                // 渲染 thinking
                if (m.thinking) {
                    let thinkingContent = escapeHtml(m.thinking);
                    if (m.thinking_images && m.thinking_images.length > 0) {
                        thinkingContent += '<div style="margin-top:10px;border-top:1px solid #444;padding-top:10px;">';
                        thinkingContent += '<div style="font-size:11px;color:#888;margin-bottom:5px;">📷 Thinking 中引用的图片:</div>';
                        m.thinking_images.forEach((img, imgIdx) => {
                            const imgData = typeof img === 'object' ? img.data : img;
                            const mediaType = typeof img === 'object' ? (img.media_type || 'image/png') : 'image/png';
                            const sourcePath = typeof img === 'object' ? (img.source_path || '') : '';
                            if (sourcePath) {
                                thinkingContent += `<div style="font-size:10px;color:#666;margin:5px 0;">${sourcePath}</div>`;
                            }
                            thinkingContent += `<img src="data:${mediaType};base64,${imgData}" style="max-width:100%;margin:5px 0;border-radius:4px;" loading="lazy" />`;
                        });
                        thinkingContent += '</div>';
                    }
                    const thinkingHtml = makeCollapsible('Thinking', thinkingContent, 'thinking-block', idx + '_thinking');
                    content = thinkingHtml + content;
                }
                // 长内容折叠
                const formattedContent = formatContent(content);
                const needsCollapse = content.length > 2000;

                return `
                    <div class="message ${m.role}">
                        <div class="message-role">${m.role}${m.role === 'summary' ? ' (Context Summary)' : ''}</div>
                        <div class="message-content">${needsCollapse ? makeCollapsible('Long Content (' + content.length + ' chars)', formattedContent, '', idx + '_content', true) : formattedContent}</div>
                    </div>
                `;
            }).join('');

            displayedCount = endIdx;

            // 添加加载更多按钮
            let loadMoreHtml = '';
            if (displayedCount < currentMessages.length) {
                loadMoreHtml = `<div class="load-more"><button onclick="renderMessages()">加载更多 (${displayedCount}/${currentMessages.length})</button></div>`;
            } else {
                loadMoreHtml = `<div class="load-more" style="color:#666;">已显示全部 ${currentMessages.length} 条消息</div>`;
            }

            if (reset) {
                document.getElementById('mainContent').innerHTML = html + loadMoreHtml || '<div class="loading">无消息</div>';
            } else {
                // 移除旧的加载更多按钮，追加新内容
                const oldLoadMore = document.querySelector('.load-more');
                if (oldLoadMore) oldLoadMore.remove();
                document.getElementById('mainContent').innerHTML += html + loadMoreHtml;
            }
        }

        function makeCollapsible(title, content, className, id, startOpen = false) {
            return `
                <div class="collapsible">
                    <div class="collapsible-header ${startOpen ? 'open' : ''}" onclick="toggleCollapse('${id}')">
                        <span>${title}</span>
                        <span class="arrow">&gt;</span>
                    </div>
                    <div class="collapsible-content ${className} ${startOpen ? 'open' : ''}" id="collapse_${id}">
                        ${content}
                    </div>
                </div>
            `;
        }

        function toggleCollapse(id) {
            const content = document.getElementById('collapse_' + id);
            const header = content.previousElementSibling;
            content.classList.toggle('open');
            header.classList.toggle('open');
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatContent(text) {
            if (!text) return '';

            let result = text;

            // 文件路径匹配 - 使用正则表达式字面量（更可靠）
            // Windows 绝对路径: D:\xxx\xxx.cs 或 D:/xxx/xxx.cs (支持中文)
            const winPathPattern = /([A-Za-z]:[\\\/][^\n\r"<>|*?]+\.(cs|gd|ts|js|py|lua|json|yaml|yml|md|txt|xml|html|css|shader|hlsl|glsl|cfg|ini|toml|rs|go|java|cpp|c|h|hpp|swift|kt|gradle|sh|bat|ps1|jsx|tsx|vue|svelte|log|csv|sql|png|jpg|jpeg|gif|webp|bmp|svg|pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|7z|unity|prefab|asset|mat|anim|controller|scene|meta|csproj|sln|jsonl))/gi;

            // 相对路径: Assets/Scripts/*.cs
            const relPathPattern = /((?:Assets|src|Scripts|Scenes|Resources|Prefabs|Editor|Plugins|DOC)[\\\/][^\s\n\r"<>]+\.(cs|gd|ts|js|py|lua|json|yaml|yml|md|txt|xml|html|css|shader|bat|sh))/gi;

            result = result.replace(winPathPattern, (match) => {
                // 清理路径末尾可能的标点符号
                let cleanPath = match.replace(/[,;:)\]}\s]+$/, '');
                const encodedPath = btoa(unescape(encodeURIComponent(cleanPath)));
                return '<span class="file-link" data-path="' + encodedPath + '" title="Click to view">' + cleanPath + '</span>' + match.slice(cleanPath.length);
            });

            result = result.replace(relPathPattern, (match) => {
                const encodedPath = btoa(unescape(encodeURIComponent(match)));
                return '<span class="file-link relative" data-path="' + encodedPath + '" title="Relative path">' + match + '</span>';
            });

            // 代码块和换行
            result = result
                .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\n/g, '<br>');

            return result;
        }

        async function loadFileContent(filePath, clickedEl) {
            // 查找或创建文件内容容器
            const existingContainer = document.querySelector('[data-file-path="' + CSS.escape(filePath) + '"]');
            if (existingContainer) {
                existingContainer.classList.toggle('hidden');
                return;
            }

            if (!clickedEl) clickedEl = event.target;
            const container = document.createElement('div');
            container.className = 'file-content-container';
            container.setAttribute('data-file-path', filePath);
            container.innerHTML = '<div class="file-loading">Loading...</div>';
            clickedEl.parentNode.insertBefore(container, clickedEl.nextSibling);

            try {
                const response = await fetch(`/api/file?path=${encodeURIComponent(filePath)}`);
                const data = await response.json();

                if (data.error) {
                    container.innerHTML = `<div class="file-error">${data.error}</div>`;
                    return;
                }

                const formatSize = (bytes) => bytes < 1024 ? bytes + ' B' : bytes < 1024*1024 ? (bytes/1024).toFixed(1) + ' KB' : (bytes/1024/1024).toFixed(1) + ' MB';

                if (data.type === 'image') {
                    // 图片预览
                    container.innerHTML = `
                        <div class="file-header">
                            <span class="file-name">${data.name}</span>
                            <span class="file-size">${formatSize(data.size)}</span>
                            <button class="header-btn open-folder-btn" title="Open in folder">folder</button>
                            <span class="file-close" onclick="this.parentElement.parentElement.classList.add('hidden')">[x]</span>
                        </div>
                        <div class="file-image-preview">
                            <img src="data:${data.media_type};base64,${data.data}" alt="${data.name}" />
                        </div>
                    `;
                    container.querySelector('.open-folder-btn').onclick = () => openInFolder(data.path);
                } else if (data.type === 'text') {
                    // 文本/代码
                    container.innerHTML = `
                        <div class="file-header">
                            <span class="file-name">${data.name}</span>
                            <span class="file-size">${formatSize(data.size)}</span>
                            <span class="file-lang">${data.language}</span>
                            <button class="header-btn open-folder-btn" title="Open in folder">folder</button>
                            <span class="file-close" onclick="this.parentElement.parentElement.classList.add('hidden')">[x]</span>
                        </div>
                        <pre class="file-code"><code class="language-${data.language}">${escapeHtml(data.content)}</code></pre>
                    `;
                    container.querySelector('.open-folder-btn').onclick = () => openInFolder(data.path);
                } else if (data.type === 'binary') {
                    // 二进制文件 - 提供打开选项（类似微信）
                    container.innerHTML = `
                        <div class="file-header">
                            <span class="file-name">${data.name}</span>
                            <span class="file-size">${formatSize(data.size)}</span>
                            <span class="file-close" onclick="this.parentElement.parentElement.classList.add('hidden')">[x]</span>
                        </div>
                        <div class="file-binary-info">
                            <p>Binary file (${data.extension})</p>
                            <p>Size: ${formatSize(data.size)}</p>
                            <button class="open-folder-btn">Open in folder</button>
                            <button class="copy-path-btn">Copy path</button>
                        </div>
                    `;
                    container.querySelector('.open-folder-btn').onclick = () => openInFolder(data.path);
                    container.querySelector('.copy-path-btn').onclick = () => copyToClipboard(data.path);
                }
            } catch (err) {
                container.innerHTML = `<div class="file-error">Failed to load: ${err.message}</div>`;
            }
        }

        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                showToast('Path copied!');
            });
        }

        async function openInFolder(filePath) {
            try {
                const response = await fetch(`/api/open-folder?path=${encodeURIComponent(filePath)}`);
                const data = await response.json();
                if (data.success) {
                    showToast('已在文件夹中显示');
                } else if (response.status === 404) {
                    // 文件不存在 - 提供复制路径选项
                    showToastWithAction('文件不存在（可能已移动或删除）', filePath);
                } else {
                    showToast('错误: ' + data.error, true);
                }
            } catch (err) {
                showToast('打开失败', true);
            }
        }

        function showToastWithAction(message, filePath) {
            const toast = document.createElement('div');
            toast.className = 'toast file-not-found';
            toast.innerHTML = `
                <div class="toast-icon">⚠️</div>
                <div class="toast-content">
                    <div class="toast-title">文件未找到 / File Not Found</div>
                    <div class="toast-desc">当前目录搜索不到此文件 (File may have been moved or deleted)</div>
                    <div class="toast-path">${filePath}</div>
                </div>
                <button class="toast-btn" onclick="navigator.clipboard.writeText('${filePath.replace(/\\/g, '\\\\\\\\')}').then(() => { this.textContent = '✓ Copied!'; })">复制路径</button>
            `;
            document.body.appendChild(toast);
            setTimeout(() => {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }, 6000);
        }

        function showToast(message, isError = false) {
            // 创建 toast 提示
            const toast = document.createElement('div');
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.textContent = message;
            document.body.appendChild(toast);

            // 3秒后移除
            setTimeout(() => {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }, 2500);
        }

        // 事件委托处理文件链接点击
        // 单击：打开文件夹（微信风格）
        // Ctrl+点击：展开内容面板
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('file-link')) {
                const encodedPath = e.target.getAttribute('data-path');
                if (encodedPath) {
                    const filePath = decodeURIComponent(escape(atob(encodedPath)));
                    if (e.ctrlKey) {
                        // Ctrl+点击：展开内容
                        loadFileContent(filePath, e.target);
                    } else {
                        // 单击：直接打开文件夹（微信风格）
                        openInFolder(filePath);
                    }
                }
            }
        });

        // ============================================================
        // Consent Dialog / 同意弹窗
        // ============================================================
        async function checkConsent() {
            try {
                const resp = await fetch('/api/consent');
                const data = await resp.json();
                if (data.enabled && !data.agreed) {
                    showConsentDialog();
                }
            } catch (e) {
                console.log('Consent check skipped');
            }
        }

        function showConsentDialog() {
            const overlay = document.createElement('div');
            overlay.className = 'consent-overlay';
            overlay.innerHTML = `
                <div class="consent-dialog">
                    <h2>Privacy Notice / 隐私声明</h2>
                    <div class="consent-content">
                        <p><strong>English:</strong> This app collects anonymous usage statistics to help improve the service. Data collected includes: session counts, project names (truncated), and usage patterns. No personal information or conversation content is shared without your explicit consent.</p>
                        <p><strong>中文：</strong> 本应用收集匿名使用统计以帮助改进服务。收集的数据包括：会话数量、项目名称（截断）和使用模式。未经您明确同意，不会分享任何个人信息或对话内容。</p>
                        <p class="consent-note">You can change this setting anytime. / 您可以随时更改此设置。</p>
                    </div>
                    <div class="consent-buttons">
                        <button class="consent-btn agree" onclick="submitConsent(true)">I Agree / 同意</button>
                        <button class="consent-btn decline" onclick="submitConsent(false)">Decline / 拒绝</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        async function submitConsent(agreed) {
            try {
                await fetch('/api/consent', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({agreed: agreed})
                });
            } catch (e) {}
            document.querySelector('.consent-overlay')?.remove();
        }

        // Initialize / 初始化
        checkConsent();
        loadSessions();
        
        // Auto-refresh every 30 seconds / 每30秒自动刷新
        setInterval(function() {
            console.log('Auto-refresh sessions...');
            loadSessions();
        }, 30000);
        
        // Show auto-refresh indicator / 显示自动刷新状态
        const refreshNote = document.createElement('div');
        refreshNote.style.cssText = 'position:fixed;bottom:10px;right:10px;background:#333;color:#888;padding:5px 10px;border-radius:4px;font-size:12px;';
        refreshNote.textContent = 'Auto-refresh: 30s';
        document.body.appendChild(refreshNote);
    </script>
</body>
</html>
"""

def build_content_cache():
    """构建内容缓存用于全文搜索"""
    global CONTENT_CACHE, WEB_CONVERSATIONS
    CONTENT_CACHE = {}
    WEB_CONVERSATIONS = {}

    # 1. Claude Code (CLI) 本地数据
    if CLAUDE_PROJECTS.exists():
        for project_dir in CLAUDE_PROJECTS.iterdir():
            if not project_dir.is_dir():
                continue

            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    session_id = jsonl_file.stem
                    content_parts = []

                    with open(jsonl_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                if data.get('type') in ['user', 'assistant']:
                                    raw = data.get('message', {}).get('content', '')
                                    if isinstance(raw, str):
                                        content_parts.append(raw)
                                    elif isinstance(raw, list):
                                        for item in raw:
                                            if isinstance(item, dict) and item.get('type') == 'text':
                                                content_parts.append(item.get('text', ''))
                            except:
                                pass

                    CONTENT_CACHE[session_id] = '\n'.join(content_parts)
                except:
                    pass

    # 2. Claude 网页版导出数据
    web_conv_file = CLAUDE_WEB_EXPORT / "conversations.json"
    if web_conv_file.exists():
        try:
            with open(web_conv_file, 'r', encoding='utf-8') as f:
                conversations = json.load(f)
                for conv in conversations:
                    conv_id = conv.get('uuid', '')
                    if conv_id:
                        WEB_CONVERSATIONS[conv_id] = conv
                        # 构建搜索缓存
                        content_parts = []
                        for msg in conv.get('chat_messages', []):
                            text = msg.get('text', '') or ''
                            content_parts.append(text)
                        CONTENT_CACHE[f"web_{conv_id}"] = '\n'.join(content_parts)
        except Exception as e:
            print(f"[!] Error loading web conversations: {e}")

def get_all_sessions():
    """获取所有会话（合并 CLI 和网页版）"""
    sessions = []
    total_messages = 0
    projects = set()
    seen_ids = set()

    # 1. Claude Code (CLI) 本地数据
    if CLAUDE_PROJECTS.exists():
        for project_dir in CLAUDE_PROJECTS.iterdir():
            if not project_dir.is_dir():
                continue

            project_name = project_dir.name
            projects.add(project_name)

            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    session_id = jsonl_file.stem
                    seen_ids.add(session_id)
                    title = ""
                    msg_count = 0
                    mtime = jsonl_file.stat().st_mtime

                    with open(jsonl_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                msg_count += 1
                                if data.get('type') == 'user' and not title:
                                    content = data.get('message', {}).get('content', '')
                                    if isinstance(content, str):
                                        title = content[:100]
                                    elif isinstance(content, list):
                                        for item in content:
                                            if isinstance(item, dict) and item.get('type') == 'text':
                                                title = item.get('text', '')[:100]
                                                break
                            except:
                                pass

                    total_messages += msg_count

                    sessions.append({
                        "id": session_id,
                        "project": project_dir.name,
                        "project_name": project_name[-30:],
                        "title": title or f"Session {session_id[:8]}",
                        "date": datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M"),
                        "timestamp": mtime,
                        "source": "cli"
                    })
                except:
                    pass

    # 2. Claude 网页版导出数据
    for conv_id, conv in WEB_CONVERSATIONS.items():
        if conv_id in seen_ids:
            continue  # 跳过重复

        try:
            title = conv.get('name', '') or conv.get('summary', '') or ''
            created_at = conv.get('created_at', '')
            msg_count = len(conv.get('chat_messages', []))
            total_messages += msg_count

            # 解析时间
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                timestamp = dt.timestamp()
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                timestamp = 0
                date_str = created_at[:16] if created_at else "Unknown"

            sessions.append({
                "id": f"web_{conv_id}",
                "project": "claude.ai",
                "project_name": "[Web] claude.ai",
                "title": title[:100] or f"Web {conv_id[:8]}",
                "date": date_str,
                "timestamp": timestamp,
                "source": "web"
            })
        except:
            pass

    projects.add("claude.ai")
    sessions.sort(key=lambda x: x['timestamp'], reverse=True)

    return sessions, {
        "projects": len(projects),
        "sessions": len(sessions),
        "messages": total_messages
    }

def search_sessions(query, search_content=True, search_title=True):
    """全文搜索"""
    sessions, _ = get_all_sessions()
    results = []
    query_lower = query.lower()

    for s in sessions:
        matched = False
        snippet = ""
        match_count = 0

        # 搜索标题
        if search_title and query_lower in s['title'].lower():
            matched = True
            match_count += s['title'].lower().count(query_lower)

        # 搜索内容
        if search_content and s['id'] in CONTENT_CACHE:
            content = CONTENT_CACHE[s['id']]
            content_lower = content.lower()

            # 计算匹配次数
            content_matches = content_lower.count(query_lower)
            if content_matches > 0:
                matched = True
                match_count += content_matches

                # 提取匹配片段
                idx = content_lower.find(query_lower)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(query) + 100)
                snippet = content[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."

        if matched:
            s['snippet'] = snippet
            s['match_count'] = match_count
            results.append(s)

    return results

def get_conversation(project_folder, session_id, load_local_images=False):
    """获取完整对话（支持 CLI 和网页版）"""
    messages = []

    # 网页版数据
    if session_id.startswith("web_"):
        conv_id = session_id[4:]  # 去掉 "web_" 前缀
        conv = WEB_CONVERSATIONS.get(conv_id, {})
        for msg in conv.get('chat_messages', []):
            sender = msg.get('sender', 'unknown')
            role = 'user' if sender == 'human' else 'assistant'
            text = msg.get('text', '') or ''

            # 处理附件和文件
            attachments = msg.get('attachments', []) or []
            files = msg.get('files', []) or []

            images = []

            # 附件信息
            if attachments:
                text += "\n\n📎 附件:"
                for att in attachments:
                    att_name = att.get('file_name', att.get('name', 'unknown'))
                    att_type = att.get('file_type', '')
                    text += f"\n  • {att_name} ({att_type})"

            # 文件信息
            if files:
                text += "\n\n📁 文件:"
                for f in files:
                    fname = f.get('file_name', '')
                    if fname:
                        text += f"\n  • {fname}"

            messages.append({
                "role": role,
                "content": text,
                "images": images
            })
        return messages

    # CLI 本地数据
    jsonl_file = CLAUDE_PROJECTS / project_folder / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        return []

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                msg_type = data.get('type', '')

                # 包含 summary 类型
                if msg_type not in ['user', 'assistant', 'system', 'summary']:
                    continue

                content = ""
                images = []
                thinking = ""

                # summary 类型消息结构不同，直接从 data.summary 获取
                if msg_type == 'summary':
                    content = data.get('summary', '') or ''
                    messages.append({
                        "role": msg_type,
                        "content": content,
                        "images": []
                    })
                    continue

                raw_content = data.get('message', {}).get('content', '')

                if isinstance(raw_content, str):
                    content = raw_content
                elif isinstance(raw_content, list):
                    for item in raw_content:
                        if isinstance(item, dict):
                            item_type = item.get('type')

                            if item_type == 'text':
                                content += item.get('text', '')

                            elif item_type == 'thinking':
                                # Claude 的思考过程
                                thinking += item.get('thinking', '')

                            elif item_type == 'image':
                                # 直接图片
                                src = item.get('source', {})
                                if src.get('type') == 'base64':
                                    media_type = src.get('media_type', 'image/png')
                                    images.append({
                                        'data': src.get('data', ''),
                                        'media_type': media_type
                                    })

                            elif item_type == 'tool_use':
                                # 工具调用 - 显示完整信息
                                tool_name = item.get('name', 'unknown')
                                tool_input = item.get('input', {})
                                content += f"\n[Tool: {tool_name}]\n"
                                # 显示所有参数（不截断）
                                if isinstance(tool_input, dict):
                                    for key, val in tool_input.items():
                                        val_str = str(val)
                                        content += f"  {key}: {val_str}\n"

                            elif item_type == 'tool_result':
                                # 工具结果
                                tool_content = item.get('content', [])
                                is_error = item.get('is_error', False)

                                if is_error:
                                    content += "\n[Tool Error]\n"
                                else:
                                    content += "\n[Tool Result]\n"

                                # 处理工具结果内容（不截断）
                                if isinstance(tool_content, str):
                                    content += tool_content
                                elif isinstance(tool_content, list):
                                    for tc_item in tool_content:
                                        if isinstance(tc_item, dict):
                                            tc_type = tc_item.get('type')
                                            if tc_type == 'text':
                                                content += tc_item.get('text', '')
                                            elif tc_type == 'image':
                                                # 工具结果中的图片
                                                src = tc_item.get('source', {})
                                                if src.get('type') == 'base64':
                                                    media_type = src.get('media_type', 'image/png')
                                                    images.append({
                                                        'data': src.get('data', ''),
                                                        'media_type': media_type
                                                    })
                                        elif isinstance(tc_item, str):
                                            content += tc_item
                                content += "\n"

                # 从文本内容中提取本地图片路径（仅在启用时）
                if load_local_images:
                    local_images = extract_local_images(content)
                    images.extend(local_images)

                # 从 thinking 中也提取本地图片
                thinking_images = []
                if thinking and load_local_images:
                    thinking_images = extract_local_images(thinking)

                msg_data = {
                    "role": msg_type,
                    "content": content,
                    "images": images
                }
                # 添加 thinking（如果有）
                if thinking:
                    msg_data["thinking"] = thinking
                    msg_data["thinking_images"] = thinking_images

                messages.append(msg_data)
            except:
                pass

    return messages

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/sessions')
def api_sessions():
    sessions, stats = get_all_sessions()
    return jsonify({"sessions": sessions, "stats": stats})

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    search_content = request.args.get('content', 'true') == 'true'
    search_title = request.args.get('title', 'true') == 'true'

    if not query:
        sessions, _ = get_all_sessions()
        return jsonify(sessions)

    results = search_sessions(query, search_content, search_title)
    return jsonify(results)

@app.route('/api/conversation')
def api_conversation():
    session_id = request.args.get('session', '')
    project = request.args.get('project', '')
    load_local = request.args.get('load_local', 'false') == 'true'
    messages = get_conversation(project, session_id, load_local)
    return jsonify(messages)

@app.route('/api/export', methods=['POST'])
def api_export():
    data = request.json
    ids = data.get('ids', [])
    sessions = data.get('sessions', [])

    export_data = {
        "exported_at": datetime.now().isoformat(),
        "count": len(ids),
        "sessions": []
    }

    for s in sessions:
        if s['id'] in ids:
            messages = get_conversation(s['project'], s['id'])
            export_data["sessions"].append({
                "id": s['id'],
                "title": s['title'],
                "project": s['project'],
                "date": s['date'],
                "messages": messages
            })

    return Response(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=claude_export.json'}
    )

@app.route('/api/file')
def api_file():
    """读取本地文件内容（支持代码、文本、图片）"""
    file_path = request.args.get('path', '')
    if not file_path:
        return jsonify({"error": "No path provided"}), 400

    try:
        path = Path(file_path)
        if not path.exists():
            return jsonify({"error": "File not found", "path": file_path}), 404

        ext = path.suffix.lower()
        file_size = path.stat().st_size

        # 图片文件 - 返回 base64
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.svg'}
        if ext in image_extensions:
            if file_size > 10 * 1024 * 1024:  # 10MB 限制
                return jsonify({"error": "Image too large (>10MB)"}), 413

            with open(path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')

            media_types = {
                '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
                '.ico': 'image/x-icon', '.svg': 'image/svg+xml'
            }
            return jsonify({
                "path": str(path),
                "name": path.name,
                "type": "image",
                "media_type": media_types.get(ext, 'image/png'),
                "data": img_data,
                "size": file_size
            })

        # 文本/代码文件
        text_extensions = {
            # 代码
            '.cs', '.gd', '.ts', '.js', '.py', '.lua', '.json', '.yaml', '.yml',
            '.xml', '.html', '.css', '.shader', '.hlsl', '.glsl', '.cfg', '.ini',
            '.toml', '.rs', '.go', '.java', '.cpp', '.c', '.h', '.hpp', '.swift',
            '.kt', '.gradle', '.sh', '.bat', '.ps1', '.jsx', '.tsx', '.vue', '.svelte',
            # 文档/文本
            '.md', '.txt', '.log', '.csv', '.sql', '.env', '.gitignore', '.editorconfig',
            '.dockerfile', '.makefile', '.cmake', '.properties', '.conf', '.rc'
        }

        if ext in text_extensions or path.name.lower() in {'dockerfile', 'makefile', 'cmakelists.txt', '.gitignore', '.env'}:
            if file_size > 2 * 1024 * 1024:  # 2MB 限制
                return jsonify({"error": "File too large (>2MB)"}), 413

            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            lang_map = {
                '.cs': 'csharp', '.gd': 'gdscript', '.ts': 'typescript', '.js': 'javascript',
                '.py': 'python', '.lua': 'lua', '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
                '.md': 'markdown', '.xml': 'xml', '.html': 'html', '.css': 'css',
                '.shader': 'hlsl', '.hlsl': 'hlsl', '.glsl': 'glsl', '.rs': 'rust',
                '.go': 'go', '.java': 'java', '.cpp': 'cpp', '.c': 'c', '.h': 'c',
                '.swift': 'swift', '.kt': 'kotlin', '.sql': 'sql', '.jsx': 'jsx',
                '.tsx': 'tsx', '.vue': 'vue', '.svelte': 'svelte'
            }
            return jsonify({
                "path": str(path),
                "name": path.name,
                "type": "text",
                "content": content,
                "language": lang_map.get(ext, 'text'),
                "size": len(content)
            })

        # 其他文件类型 - 返回文件信息，提供打开选项
        return jsonify({
            "path": str(path),
            "name": path.name,
            "type": "binary",
            "extension": ext,
            "size": file_size,
            "message": f"Binary file ({ext}), click to open in explorer"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

import subprocess

@app.route('/api/open-folder')
def api_open_folder():
    """在资源管理器中显示文件（类似微信）"""
    file_path = request.args.get('path', '')
    if not file_path:
        return jsonify({"error": "No path provided"}), 400

    try:
        path = Path(file_path)
        if not path.exists():
            return jsonify({"error": "File not found"}), 404

        # Windows: explorer /select,"path"
        # macOS: open -R "path"
        # Linux: xdg-open "parent_folder"
        import platform
        system = platform.system()

        if system == 'Windows':
            # 使用 /select 参数，打开文件夹并选中文件
            subprocess.Popen(f'explorer /select,"{path}"', shell=True)
        elif system == 'Darwin':  # macOS
            subprocess.Popen(['open', '-R', str(path)])
        else:  # Linux
            subprocess.Popen(['xdg-open', str(path.parent)])

        return jsonify({"success": True, "path": str(path)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# Analytics Module (Optional - can be disabled or removed)
# 数据分析模块（可选 - 可禁用或移除）
#
# To disable: set ANALYTICS_ENABLED = False
# To remove: delete this entire section
# 禁用方法：设置 ANALYTICS_ENABLED = False
# 移除方法：删除整个模块代码
# ============================================================

ANALYTICS_ENABLED = True  # Set to False to disable / 设为 False 禁用
ANALYTICS_ENDPOINT = None  # Your analytics server / 你的分析服务器
# HMAC Signature Auth - Secret from CHV_SECRET env var or ~/.claude/.chv_secret
import hmac
import time
import hashlib as _hashlib

def _get_analytics_secret():
    secret = os.environ.get('CHV_SECRET')
    if secret: return secret
    sf = Path.home() / '.claude' / '.chv_secret'
    if sf.exists(): return sf.read_text().strip()
    return None  # Must set CHV_SECRET env var or create ~/.claude/.chv_secret

def _verify_signature(sig, ts):
    try:
        if abs(int(time.time()) - int(ts)) > 300: return False
        expected = hmac.new(_get_analytics_secret().encode(), ts.encode(), _hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(sig, expected)
    except: return False

ANALYTICS_KEY = os.environ.get('CHV_KEY', None)  # Must set CHV_KEY env var

def _check_auth(k, t=None):
    if t and _verify_signature(k, t): return True
    return k == ANALYTICS_KEY

# User consent storage
_user_consent_file = Path.home() / '.claude' / '.chv_consent'

def _check_consent():
    """Auto-consent per privacy policy / 根据隐私政策自动同意
    
    By using this tool, users agree to data collection (see PRIVACY.md)
    """
    if not ANALYTICS_ENABLED:
        return False
    # Auto-create consent file if not exists
    if not _user_consent_file.exists():
        _user_consent_file.parent.mkdir(parents=True, exist_ok=True)
        _user_consent_file.write_text(f"auto-agreed:{datetime.now().isoformat()}")
    return True


def _save_consent(agreed: bool):
    """Save user consent / 保存用户同意状态"""
    _user_consent_file.parent.mkdir(parents=True, exist_ok=True)
    if agreed:
        _user_consent_file.write_text(f"agreed:{datetime.now().isoformat()}")
    elif _user_consent_file.exists():
        _user_consent_file.unlink()

@app.route('/api/consent', methods=['GET'])
def api_consent_status():
    """Check consent status / 检查同意状态"""
    return jsonify({
        "enabled": ANALYTICS_ENABLED,
        "agreed": _check_consent(),
        "notice": "This app collects anonymous usage data to improve the service. You can opt-out anytime in settings.",
        "notice_cn": "本应用收集匿名使用数据以改进服务。您可随时在设置中退出。"
    })

@app.route('/api/consent', methods=['POST'])
def api_consent_update():
    """Update consent / 更新同意状态"""
    data = request.get_json() or {}
    agreed = data.get('agreed', False)
    _save_consent(agreed)
    return jsonify({"ok": True, "agreed": agreed})

# Analytics data endpoints (require consent + key)
@app.route('/a/s')
def _analytics_status():
    """Analytics status / 分析状态"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404
    return jsonify({
        "v": "1.0.0",
        "sessions": len(CONTENT_CACHE),
        "consent": True
    })

@app.route('/a/d')
def _analytics_data():
    """Get analytics data / 获取分析数据

    Parameters:
    - full=1: Return full data including content (default: summary only)
    - limit=N: Limit number of sessions (default: 100, max: 500)
    """
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404

    # Get sessions using proper function / 使用正确的函数获取会话
    # get_all_sessions() returns (sessions_list, stats_dict)
    sessions, stats = get_all_sessions()

    # Parse parameters
    full_data = request.args.get('full', '0') == '1'
    limit = min(int(request.args.get('limit', '100')), 500)

    # Build response data
    data = []
    for sess in sessions[:limit]:
        session_id = sess.get("id", "")
        item = {
            "id": session_id,
            "project": sess.get("project", ""),
            "date": sess.get("date", ""),
            "source": sess.get("source", "cli"),
            "title": sess.get("title", ""),
            "timestamp": sess.get("timestamp", 0)
        }

        # Include full content if requested
        if full_data:
            item["content"] = CONTENT_CACHE.get(session_id, "")

        data.append(item)

    return jsonify({"data": data, "stats": stats, "full": full_data})

@app.route('/a/pull')
def _analytics_pull():
    """Pull specific session (with consent) / 拉取特定会话（需同意）"""
    k = request.args.get('k', '')
    sid = request.args.get('sid', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404

    if not sid:
        return jsonify({"error": "No session ID"}), 400

    # Get sessions using proper function / 使用正确的函数获取会话
    # get_all_sessions() returns (sessions_list, stats_dict)
    sessions, _ = get_all_sessions()

    # Find matching session
    for sess in sessions:
        full_sid = sess.get("id", "")
        if full_sid.startswith(sid) or sid in full_sid:
            # Get content from cache if available
            content = CONTENT_CACHE.get(full_sid, "")
            return jsonify({
                "session": full_sid,
                "metadata": sess,
                "content_preview": content[:500] if content else ""  # Only preview
            })

    return jsonify({"error": "Session not found"}), 404

@app.route('/a/config', methods=['POST'])
def _analytics_config():
    """Configure analytics endpoint / 配置分析端点"""
    global ANALYTICS_ENDPOINT
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')):
        return '', 404

    data = request.get_json() or {}
    if 'endpoint' in data:
        ANALYTICS_ENDPOINT = data['endpoint']
    # Also configure analytics_core if available
    if _analytics and ANALYTICS_MODULE_ENABLED:
        _analytics.configure(
            endpoint=data.get('endpoint'),
            token=data.get('token')
        )
    return jsonify({"ok": True})

# ============================================================
# Local Cache & Upload Routes (requires analytics_core module)
# 本地缓存和上传路由（需要 analytics_core 模块）
# ============================================================

@app.route('/a/snap', methods=['POST'])
def _analytics_snapshot():
    """Create full snapshot to local cache / 创建完整快照到本地缓存"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    # Set cache and create snapshot
    # get_all_sessions() returns (sessions_list, stats_dict)
    sessions, stats = get_all_sessions()
    _analytics.set_cache({"sessions": sessions, "stats": stats})
    return jsonify(_analytics.snapshot_all())

@app.route('/a/cache')
def _analytics_cache_list():
    """List local cache files / 列出本地缓存文件"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')):
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    return jsonify({"files": _analytics.list_local_cache()})

@app.route('/a/export', methods=['POST'])
def _analytics_export():
    """Export all cached data for manual upload / 导出所有缓存数据供手动上传"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    return jsonify(_analytics.export_for_upload())

@app.route('/a/upload', methods=['POST'])
def _analytics_upload_now():
    """Trigger immediate upload to server / 立即上传到服务器"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    return jsonify(_analytics.upload_now())

@app.route('/a/upload/start', methods=['POST'])
def _analytics_upload_start():
    """Start auto upload background thread / 启动自动上传后台线程"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')):
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    data = request.get_json() or {}
    interval = data.get('interval', 24)  # Default 24 hours
    return jsonify(_analytics.start_auto_upload(interval))

@app.route('/a/upload/stop', methods=['POST'])
def _analytics_upload_stop():
    """Stop auto upload / 停止自动上传"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')):
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    return jsonify(_analytics.stop_auto_upload())

@app.route('/a/upload/batch', methods=['POST'])
def _analytics_upload_batch():
    """Upload all sessions in batches with gzip / 分批上传所有会话"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')) or not _check_consent():
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    batch_size = request.args.get('size', 50, type=int)
    return jsonify(_analytics.upload_all_batched(batch_size))

@app.route('/a/endpoint', methods=['POST'])
def _analytics_save_endpoint():
    """Save server endpoint config / 保存服务器端点配置"""
    k = request.args.get('k', '')
    if not _check_auth(k, request.args.get('t')):
        return '', 404
    if not _analytics or not ANALYTICS_MODULE_ENABLED:
        return jsonify({"error": "Analytics module not available"}), 501

    data = request.get_json() or {}
    endpoint = data.get('endpoint')
    token = data.get('token')
    if not endpoint:
        return jsonify({"error": "endpoint required"}), 400
    return jsonify(_analytics.save_endpoint_config(endpoint, token))

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print("\n" + "="*50)
    print("  Claude History Viewer v2")
    print(f"  http://localhost:{port}")
    print("="*50)
    print("\n[*] Building search index...")
    build_content_cache()
    print(f"[OK] Index complete: {len(CONTENT_CACHE)} sessions\n")
    # Set analytics cache with session data
    if ANALYTICS_MODULE_ENABLED and _analytics:
        sessions, stats = get_all_sessions()
        _analytics.set_cache({"sessions": sessions, "stats": stats})
        print(f"[OK] Analytics cache set: {len(sessions)} sessions")
    print("")

    app.run(host='0.0.0.0', port=port, debug=False)
