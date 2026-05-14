#!/usr/bin/env python3
"""
CLI entry point for readmap.
"""

import sys
from readmap.pipeline import main as pipeline_main


def main():
    pipeline_main()


if __name__ == "__main__":
    main()
