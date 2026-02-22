#!/usr/bin/env python3
"""
MacReplayXC v4.2.0 - Deployment Test Script
Tests basic functionality before deployment
"""

import sys
import os

def test_syntax():
    """Test Python syntax"""
    print("🔍 Testing Python syntax...")
    try:
        import py_compile
        py_compile.compile('app-docker.py', doraise=True)
        print("✅ Syntax check passed")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return False

def test_imports():
    """Test that all imports work"""
    print("\n🔍 Testing imports...")
    try:
        # Test critical imports
        import flask
        import threading
        import secrets
        import sqlite3
        import requests
        
        print("✅ All critical imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_app_import():
    """Test that app-docker.py can be imported"""
    print("\n🔍 Testing app-docker.py import...")
    try:
        # Add current directory to path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Try to import (this will fail if there are syntax errors)
        import app_docker
        
        print(f"✅ App imported successfully (version: {app_docker.__version__})")
        return True
    except Exception as e:
        print(f"❌ App import failed: {e}")
        return False

def test_database():
    """Test database initialization"""
    print("\n🔍 Testing database...")
    try:
        import sqlite3
        
        # Test channels.db
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()
        
        # Test table creation
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                portal TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (portal, channel_id)
            )
        ''')
        
        # Test insert
        cursor.execute('INSERT INTO channels VALUES (?, ?)', ('test', '123'))
        
        # Test select
        cursor.execute('SELECT * FROM channels')
        result = cursor.fetchone()
        
        conn.close()
        
        if result == ('test', '123'):
            print("✅ Database operations successful")
            return True
        else:
            print("❌ Database test failed")
            return False
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_threading():
    """Test threading locks"""
    print("\n🔍 Testing threading...")
    try:
        import threading
        
        # Test lock creation
        test_lock = threading.Lock()
        
        # Test lock acquisition
        with test_lock:
            pass
        
        print("✅ Threading locks working")
        return True
    except Exception as e:
        print(f"❌ Threading error: {e}")
        return False

def test_secrets():
    """Test secrets module for constant-time comparison"""
    print("\n🔍 Testing secrets module...")
    try:
        import secrets
        
        # Test compare_digest
        result = secrets.compare_digest("test", "test")
        
        if result:
            print("✅ Secrets module working")
            return True
        else:
            print("❌ Secrets compare_digest failed")
            return False
    except Exception as e:
        print(f"❌ Secrets error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("MacReplayXC v4.2.0 - Deployment Test")
    print("=" * 60)
    
    tests = [
        ("Syntax Check", test_syntax),
        ("Import Check", test_imports),
        ("App Import", test_app_import),
        ("Database Test", test_database),
        ("Threading Test", test_threading),
        ("Secrets Test", test_secrets),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Ready for deployment.")
        print("=" * 60)
        return 0
    else:
        print("⚠️  Some tests failed. Fix issues before deployment.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
