#!/usr/bin/env python3
"""
Shadowsocks compatibility fix for Python 3.10+
This module patches the collections.MutableMapping issue.
"""

import sys
import logging

logger = logging.getLogger(__name__)

def apply_shadowsocks_fix():
    """Apply compatibility fixes for Shadowsocks with Python 3.10+"""
    try:
        # Fix collections.MutableMapping issue
        if sys.version_info >= (3, 10):
            import collections.abc
            import collections
            
            # Patch MutableMapping if it doesn't exist
            if not hasattr(collections, 'MutableMapping'):
                collections.MutableMapping = collections.abc.MutableMapping
                logger.debug("Applied collections.MutableMapping compatibility fix")
            
            # Patch other moved collections if needed
            if not hasattr(collections, 'Mapping'):
                collections.Mapping = collections.abc.Mapping
            if not hasattr(collections, 'Iterable'):
                collections.Iterable = collections.abc.Iterable
            if not hasattr(collections, 'Callable'):
                collections.Callable = collections.abc.Callable
                
        return True
    except Exception as e:
        logger.error(f"Failed to apply Shadowsocks compatibility fix: {e}")
        return False

def test_shadowsocks_import():
    """Test if Shadowsocks can be imported after applying fixes"""
    try:
        apply_shadowsocks_fix()
        import shadowsocks.local
        logger.info("Shadowsocks import successful after compatibility fix")
        return True
    except ImportError as e:
        logger.error(f"Shadowsocks library not available: {e}")
        logger.error("Try installing with: pip install shadowsocks-libev")
        return False
    except Exception as e:
        logger.error(f"Shadowsocks import failed: {e}")
        return False

if __name__ == "__main__":
    # Test the fix
    logging.basicConfig(level=logging.DEBUG)
    success = test_shadowsocks_import()
    if success:
        print("✅ Shadowsocks compatibility fix successful")
    else:
        print("❌ Shadowsocks compatibility fix failed")