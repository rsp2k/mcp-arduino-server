#!/usr/bin/env python3
"""Test dependency checker directly"""

import json
import subprocess

def test_deps(library_name):
    """Test dependency checking logic"""

    # Run Arduino CLI command
    cmd = ["arduino-cli", "lib", "deps", library_name, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    # Parse JSON
    data = json.loads(result.stdout)
    print(f"Raw data: {json.dumps(data, indent=2)}")

    # Process dependencies
    deps_info = {
        "library": library_name,
        "dependencies": [],
        "missing": [],
        "installed": [],
    }

    # Extract dependency information
    all_deps = data.get("dependencies", [])
    print(f"\nProcessing {len(all_deps)} dependencies for {library_name}")

    for dep in all_deps:
        dep_name = dep.get("name", "")
        print(f"  Checking: {dep_name}")

        # Skip self-reference (library listing itself)
        if dep_name == library_name:
            print(f"    -> Skipping self-reference")
            continue

        # Determine if installed based on presence of version_installed
        is_installed = bool(dep.get("version_installed"))

        dep_info = {
            "name": dep_name,
            "version_required": dep.get("version_required"),
            "version_installed": dep.get("version_installed"),
            "installed": is_installed
        }

        print(f"    -> Adding as dependency: installed={is_installed}")
        deps_info["dependencies"].append(dep_info)

        if is_installed:
            deps_info["installed"].append(dep_name)
        else:
            deps_info["missing"].append(dep_name)

    print(f"\nFinal result:")
    print(f"  Dependencies: {deps_info['dependencies']}")
    print(f"  Installed: {deps_info['installed']}")
    print(f"  Missing: {deps_info['missing']}")

    return deps_info

if __name__ == "__main__":
    print("Testing ArduinoJson:")
    test_deps("ArduinoJson")

    print("\n" + "="*50 + "\n")

    print("Testing PubSubClient:")
    test_deps("PubSubClient")