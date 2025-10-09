"""
Shared utility functions for ComfyUI dependency analysis.
"""

import re


def make_filename_safe(query):
    """Convert a query string to a filename-safe version."""
    # Remove &save suffix if present
    query = query.replace('&save', '').strip()
    # Replace asterisks with 'wildcard'
    query = query.replace('*', 'wildcard')
    # Replace non-alphanumeric characters with underscores
    safe_name = re.sub(r'[^\w\-_]', '_', query)
    # Remove multiple underscores
    safe_name = re.sub(r'_+', '_', safe_name)
    # Trim underscores from ends
    return safe_name.strip('_')