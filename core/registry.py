"""Registry API interaction: fetching and saving node data from api.comfy.org."""

import time
import threading
import concurrent.futures

import requests

BASE_URL = "https://api.comfy.org"


def get_registry_nodes_concurrent(print_time=True, max_workers=10, log_callback=None, progress_callback=None):
    """
    Fetch all nodes from registry using concurrent requests for faster performance.

    Args:
        print_time: Whether to print the fetch time
        max_workers: Maximum number of concurrent threads
        log_callback: Optional callable(msg: str) for log output
        progress_callback: Optional callable(completed: int, total: int) for progress

    Returns:
        Dictionary with 'nodes' key containing all nodes
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    def _progress(completed, total):
        if progress_callback:
            progress_callback(completed, total)

    nodes_dict = {}
    lock = threading.Lock()

    def fetch_page(page_num, retries=3):
        """Fetch a single page of nodes with retry logic."""
        sub_uri = f'{BASE_URL}/nodes?page={page_num}&limit=30'

        for attempt in range(retries):
            try:
                response = requests.get(sub_uri, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    _log(f"Timeout on page {page_num}, attempt {attempt + 1}/{retries}, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                else:
                    _log(f"Failed to fetch page {page_num} after {retries} attempts (timeout)")
                    return None
            except Exception as e:
                if attempt < retries - 1:
                    _log(f"Error on page {page_num}, attempt {attempt + 1}/{retries}: {e}, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                else:
                    _log(f"Failed to fetch page {page_num} after {retries} attempts: {e}")
                    return None

        return None

    def process_page_results(json_obj):
        """Process the results from a page fetch."""
        if json_obj and 'nodes' in json_obj:
            with lock:
                for node in json_obj['nodes']:
                    if 'id' in node:
                        nodes_dict[node['id']] = node
                    else:
                        _log(f"Warning: Node without ID found: {node}")

    start_time = time.perf_counter()

    # First, fetch page 1 to get total pages
    _log("Fetching first page to determine total pages...")
    first_page = fetch_page(1)
    if not first_page:
        _log("Failed to fetch first page")
        return {'nodes': []}

    total_pages = first_page.get('totalPages', 1)
    _log(f"Total pages to fetch: {total_pages}")

    # Process first page
    process_page_results(first_page)
    _progress(1, total_pages)

    if total_pages > 1:
        _log(f"Fetching remaining {total_pages - 1} pages with {max_workers} workers...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {
                executor.submit(fetch_page, page): page
                for page in range(2, total_pages + 1)
            }

            completed = 1  # page 1 already done
            failed_pages = []
            for future in concurrent.futures.as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    json_obj = future.result()
                    if json_obj:
                        process_page_results(json_obj)
                    else:
                        failed_pages.append(page)
                    completed += 1
                    _progress(completed, total_pages)
                    if completed % 10 == 0:
                        _log(f"  Processed {completed}/{total_pages} pages...")
                except Exception as e:
                    _log(f"Error processing page {page}: {e}")
                    failed_pages.append(page)

            if failed_pages:
                _log(f"Warning: Failed to fetch {len(failed_pages)} pages: {failed_pages}")
                _log("Attempting sequential retry for failed pages...")
                for page in failed_pages:
                    json_obj = fetch_page(page, retries=5)
                    if json_obj:
                        process_page_results(json_obj)
                        _log(f"  Successfully recovered page {page}")
                    else:
                        _log(f"  Could not recover page {page}")

    end_time = time.perf_counter()
    if print_time:
        _log(f"Time taken to fetch all nodes (concurrent): {end_time - start_time:.2f} seconds")
        _log(f"Total nodes fetched: {len(nodes_dict)}")

    # Add default latest_version for nodes without it
    for v in nodes_dict.values():
        if 'latest_version' not in v:
            v['latest_version'] = dict(version='nightly')

    return {'nodes': list(nodes_dict.values())}


def get_registry_nodes(print_time=True, log_callback=None, progress_callback=None):
    """Fetch all nodes from registry."""
    return get_registry_nodes_concurrent(
        print_time=print_time,
        log_callback=log_callback,
        progress_callback=progress_callback,
    )


def save_nodes_json(registry_data, log_callback=None):
    """
    Save registry data to cache.

    Returns:
        True if successful, False otherwise
    """
    from .cache import save_nodes_cache

    def _log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    try:
        save_nodes_cache(registry_data)
        _log(f"Total nodes saved: {len(registry_data['nodes'])}")
        return True
    except Exception as e:
        _log(f"Error saving nodes cache: {e}")
        return False


def fetch_and_save_extension_node_map(log_callback=None):
    """
    Fetch extension-node-map.json from ComfyUI-Manager repository and save to cache.

    Returns:
        True if successful, False otherwise
    """
    from .cache import save_ext_map_cache

    def _log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    url = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"

    try:
        _log(f"Fetching extension-node-map.json...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        node_map_data = response.json()

        save_ext_map_cache(node_map_data)

        _log(f"Total extensions mapped: {len(node_map_data)}")
        return True
    except requests.exceptions.RequestException as e:
        _log(f"Error fetching extension-node-map.json: {e}")
        return False
    except Exception as e:
        _log(f"Error saving extension-node-map.json: {e}")
        return False
