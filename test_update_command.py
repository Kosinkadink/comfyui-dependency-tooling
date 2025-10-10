#!/usr/bin/env python
"""Test /update command in interactive mode."""
import subprocess
import time

# Test the /update command via stdin
process = subprocess.Popen(
    ['python', 'analysis.py'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Send /update command and then /quit
commands = "/update\n/quit\n"
start_time = time.perf_counter()
stdout, stderr = process.communicate(input=commands)
end_time = time.perf_counter()

print("Output from /update command:")
print(stdout)

if stderr:
    print("Errors:")
    print(stderr)

print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")

# Check if concurrent download was used
if "concurrent" in stdout:
    print("Concurrent download was used")
else:
    print("Concurrent download was NOT used")

# Check for successful completion
if "Successfully updated" in stdout or "Total nodes fetched" in stdout:
    print("Update completed successfully")
else:
    print("Update may have failed")