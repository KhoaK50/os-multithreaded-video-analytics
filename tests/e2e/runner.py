"""
Master E2E Test Suite Runner.
Executes 4 tiers of tests covering all 19 features of OS Multithreaded Video Analytics.
Academic Module: Operating Systems (Hệ Điều Hành)

Usage:
    python tests/e2e/runner.py
    python tests/e2e/runner.py --tier 1
    python tests/e2e/runner.py --tier 2
    python tests/e2e/runner.py --tier 3
    python tests/e2e/runner.py --tier 4
    python tests/e2e/runner.py --report summary.json
"""

import os
import sys
import time
import json
import argparse
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 stdout on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


E2E_DIR = PROJECT_ROOT / "tests" / "e2e"

TIER_FILES = {
    1: E2E_DIR / "test_tier1_feature_coverage.py",
    2: E2E_DIR / "test_tier2_boundary_corner_cases.py",
    3: E2E_DIR / "test_tier3_cross_feature_interactions.py",
    4: E2E_DIR / "test_tier4_real_world_scenarios.py",
}

TIER_NAMES = {
    1: "Tier 1: Feature Coverage (F01 - F19)",
    2: "Tier 2: Boundary & Corner Cases",
    3: "Tier 3: Cross-Feature Interactions",
    4: "Tier 4: Real-World Scenarios",
}


def run_tier_with_pytest(tier: int, verbose: bool = False) -> dict:
    """Runs a single test tier via pytest."""
    test_file = TIER_FILES.get(tier)
    if not test_file or not test_file.exists():
        return {
            "tier": tier,
            "name": TIER_NAMES.get(tier, f"Tier {tier}"),
            "status": "ERROR",
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration": 0.0,
            "output": f"Test file not found: {test_file}"
        }

    cmd = [sys.executable, "-m", "pytest", str(test_file), "-q"]
    if verbose:
        cmd.append("-v")

    start_time = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    duration = time.time() - start_time

    output = res.stdout + "\n" + res.stderr
    passed = 0
    failed = 0
    skipped = 0

    # Parse pytest output summary (e.g. "5 passed, 2 failed, 1 skipped in 1.23s")
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "skipped" in line:
            import re
            m_pass = re.search(r"(\d+)\s+passed", line)
            m_fail = re.search(r"(\d+)\s+failed", line)
            m_skip = re.search(r"(\d+)\s+skipped", line)
            if m_pass:
                passed = int(m_pass.group(1))
            if m_fail:
                failed = int(m_fail.group(1))
            if m_skip:
                skipped = int(m_skip.group(1))

    status = "PASS" if res.returncode == 0 else "FAIL"

    return {
        "tier": tier,
        "name": TIER_NAMES.get(tier, f"Tier {tier}"),
        "file": str(test_file.relative_to(PROJECT_ROOT)),
        "status": status,
        "returncode": res.returncode,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration": round(duration, 2),
        "output": output
    }


def main():
    parser = argparse.ArgumentParser(description="OS Multithreaded Video Analytics E2E Test Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run specific tier (1, 2, 3, or 4)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution output")
    parser.add_argument("--report", type=str, default="", help="Path to write JSON test execution report")
    args = parser.parse_args()

    print("=" * 80)
    print("  OS MULTITHREADED VIDEO ANALYTICS - E2E TEST SUITE RUNNER")
    print("  Academic Standard: Operating Systems | Multithreaded Architecture")
    print("=" * 80)
    print(f"  Python Version: {sys.version.split()[0]}")
    print(f"  Project Root:   {PROJECT_ROOT}")
    print(f"  Timestamp:      {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 80)

    selected_tiers = [args.tier] if args.tier else [1, 2, 3, 4]
    results = []

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_start = time.time()

    for t in selected_tiers:
        print(f"\n>> Executing {TIER_NAMES[t]}...")
        tier_res = run_tier_with_pytest(t, verbose=args.verbose)
        results.append(tier_res)

        total_passed += tier_res["passed"]
        total_failed += tier_res["failed"]
        total_skipped += tier_res["skipped"]

        badge = "[PASS]" if tier_res["status"] == "PASS" else "[FAIL]"
        print(f"  Status:   {badge}")
        print(f"  Metrics:  {tier_res['passed']} passed, {tier_res['failed']} failed, {tier_res['skipped']} skipped ({tier_res['duration']}s)")

        if tier_res["status"] != "PASS" and not args.verbose:
            # Print brief failure summary
            lines = tier_res["output"].strip().splitlines()
            failure_lines = [l for l in lines if "FAIL" in l or "Error" in l or "Defect" in l]
            for fl in failure_lines[:6]:
                print(f"    * {fl}")


    total_duration = round(time.time() - total_start, 2)

    print("\n" + "=" * 80)
    print("  E2E TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f"  Total Tiers Executed: {len(results)}")
    print(f"  Passed Tests:         {total_passed}")
    print(f"  Failed Tests:         {total_failed}")
    print(f"  Skipped Tests:        {total_skipped}")
    print(f"  Total Wall Duration:  {total_duration}s")
    print("=" * 80)

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "total_duration": total_duration,
        "overall_status": "PASS" if total_failed == 0 else "FAIL",
        "tiers": results
    }

    if args.report:
        report_path = Path(args.report).resolve()
        report_path.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Summary report saved to: {report_path}")

    # Return exit code matching test results
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
