#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude History Viewer - Launcher
Run: python run.py
"""
import sys
sys.dont_write_bytecode = True
from app import app, build_content_cache

if __name__ == '__main__':
    print("\n" + "="*50)
    print("  Claude History Viewer v1.0.0")
    print("  http://localhost:5000")
    print("="*50)
    print("\n[*] Building search index...")
    build_content_cache()
    print("[OK] Index complete\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
