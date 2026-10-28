"""Compatibility entry point; use build_windows_portable.py for both architectures."""
import sys
from build_windows_portable import main

if __name__ == "__main__":
    main(["--arch", "arm64", *sys.argv[1:]])
