"""
pytest configuration — sets up sys.path so tests can import ecom_toon.
"""
import sys, os
# Add project root to path so 'from ecom_toon.toon_parser import ...' works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# For running tests directly without installing the package,
# also support 'from toon_parser import ...' style
sys.path.insert(0, '/tmp')  # for CI/sandbox environments