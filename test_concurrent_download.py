#!/usr/bin/env python
"""
Test script to compare sequential vs concurrent registry downloads.
"""
import time
from analysis import get_registry_nodes, get_registry_nodes_concurrent

def test_sequential():
    """Test sequential download."""
    print("\n" + "="*60)
    print("Testing SEQUENTIAL download:")
    print("="*60)
    start = time.perf_counter()
    result = get_registry_nodes(print_time=True)
    end = time.perf_counter()
    print(f"Sequential total time: {end - start:.2f} seconds")
    print(f"Nodes fetched: {len(result['nodes'])}")
    return result

def test_concurrent(max_workers=10):
    """Test concurrent download."""
    print("\n" + "="*60)
    print(f"Testing CONCURRENT download (max_workers={max_workers}):")
    print("="*60)
    start = time.perf_counter()
    result = get_registry_nodes_concurrent(print_time=True, max_workers=max_workers)
    end = time.perf_counter()
    print(f"Concurrent total time: {end - start:.2f} seconds")
    print(f"Nodes fetched: {len(result['nodes'])}")
    return result

def main():
    print("Registry Download Performance Comparison")
    print("=========================================")

    # Test concurrent with different worker counts
    print("\n### Testing different worker counts ###")

    # Test with 5 workers
    result_5 = test_concurrent(max_workers=5)

    # Test with 10 workers
    result_10 = test_concurrent(max_workers=10)

    # Test with 20 workers
    result_20 = test_concurrent(max_workers=20)

    # Test sequential for comparison
    result_seq = test_sequential()

    # Verify all methods got the same data
    print("\n" + "="*60)
    print("Verification:")
    print("="*60)
    print(f"Sequential nodes: {len(result_seq['nodes'])}")
    print(f"Concurrent (5 workers) nodes: {len(result_5['nodes'])}")
    print(f"Concurrent (10 workers) nodes: {len(result_10['nodes'])}")
    print(f"Concurrent (20 workers) nodes: {len(result_20['nodes'])}")

    # Check if all results match
    if (len(result_seq['nodes']) == len(result_5['nodes']) ==
        len(result_10['nodes']) == len(result_20['nodes'])):
        print("OK: All methods fetched the same number of nodes")
    else:
        print("WARNING: Different node counts between methods!")
        print("  This may be due to transient network errors or timing issues")

        # Show which ones differ
        counts = {
            'Sequential': len(result_seq['nodes']),
            '5 workers': len(result_5['nodes']),
            '10 workers': len(result_10['nodes']),
            '20 workers': len(result_20['nodes'])
        }
        max_count = max(counts.values())
        for method, count in counts.items():
            if count < max_count:
                print(f"    {method}: Missing {max_count - count} nodes")

if __name__ == "__main__":
    main()