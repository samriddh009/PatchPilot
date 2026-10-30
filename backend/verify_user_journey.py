"""End-to-End User Journey Verification Script for PatchPilot Phase 2.1.
Verifies all 12 sequence steps against live local backend and frontend.
"""
import sys
import time
import json
import urllib.request
import urllib.error

BACKEND_URL = "http://127.0.0.1:8000/api/v1"
FRONTEND_URL = "http://127.0.0.1:5173"

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if "json" in resp.headers.get("Content-Type", "") else data
    except urllib.error.HTTPError as e:
        data = e.read().decode("utf-8")
        try:
            return e.code, json.loads(data)
        except Exception:
            return e.code, data

def http_post(url, payload=None, headers=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if "json" in resp.headers.get("Content-Type", "") else data
    except urllib.error.HTTPError as e:
        data = e.read().decode("utf-8")
        try:
            return e.code, json.loads(data)
        except Exception:
            return e.code, data

def main():
    print("=" * 70)
    print("PatchPilot End-to-End User Journey Verification")
    print("=" * 70)
    results = {}

    # Step 1 & 2: Start & Confirm Frontend and Backend load
    print("\n[Step 1 & 2] Verifying Backend and Frontend HTTP responsiveness...")
    try:
        code, content = http_get(FRONTEND_URL)
        assert code == 200 and "PatchPilot" in content
        print(f"  [PASS] Frontend loaded successfully at {FRONTEND_URL} (HTTP {code})")
        results["step_1_2"] = True
    except Exception as e:
        print(f"  [FAIL] Frontend check failed: {e}")
        results["step_1_2"] = False

    # Step 3: Health and Provider Status
    print("\n[Step 3] Verifying Health and Provider status endpoints...")
    try:
        h_code, h_data = http_get(f"{BACKEND_URL}/health")
        assert h_code == 200 and h_data["status"] == "healthy"
        print(f"  [PASS] GET /health: status={h_data['status']}, version={h_data.get('version')}")

        p_code, p_data = http_get(f"{BACKEND_URL}/provider/status")
        assert p_code == 200 and "configured" in p_data
        print(f"  [PASS] GET /provider/status: model={p_data['model']}, configured={p_data['configured']}, source={p_data['source']}")

        # Test session key header handling
        dummy_test_key = "AIza" + "SyDummyKeyForVerification12345"
        ps_code, ps_data = http_get(f"{BACKEND_URL}/provider/status", headers={"X-Session-Gemini-Key": dummy_test_key})
        assert ps_code == 200 and ps_data["configured"] is True
        print(f"  [PASS] GET /provider/status with X-Session-Gemini-Key: configured={ps_data['configured']}, source={ps_data.get('source')}")
        results["step_3"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Health/Provider check failed: {e}\n{traceback.format_exc()}")
        results["step_3"] = False

    # Step 4: Repository Selection and File listing
    print("\n[Step 4] Verifying Repository listing and metadata...")
    try:
        r_code, r_data = http_get(f"{BACKEND_URL}/repositories")
        assert r_code == 200 and "items" in r_data and len(r_data["items"]) > 0
        repo_ids = [r["id"] for r in r_data["items"]]
        print(f"  [PASS] GET /repositories: found {len(r_data['items'])} fixtures: {repo_ids}")
        assert "repo_py_calc_01" in repo_ids

        # Check repository files
        f_code, f_data = http_get(f"{BACKEND_URL}/repositories/repo_py_calc_01/files")
        assert f_code == 200 and "files" in f_data
        print(f"  [PASS] GET /repositories/repo_py_calc_01/files: {len(f_data['files'])} files found")
        results["step_4"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Repository listing check failed: {e}\n{traceback.format_exc()}")
        results["step_4"] = False

    # Step 5 & 6: Submit Repair & Poll Status
    print("\n[Step 5 & 6] Submitting repair job for repo_py_calc_01 and polling status...")
    repair_id = None
    try:
        payload = {
            "repository_id": "repo_py_calc_01",
            "bug_report": "Boundary error in discount calculation: cart total of exactly $100 receives 10% instead of 15%",
            "test_target": "tests/test_calculator.py::test_discount_boundary"
        }
        s_code, s_data = http_post(f"{BACKEND_URL}/repairs", payload)
        assert s_code == 201
        repair_id = s_data["id"]
        print(f"  [PASS] POST /repairs created job: id={repair_id}, initial_status={s_data['status']}")
        
        # Poll status until terminal state
        terminal_states = {"verified", "unresolved", "failed", "cancelled"}
        final_status = s_data["status"]
        attempts = 0
        while final_status not in terminal_states and attempts < 60:
            time.sleep(0.5)
            attempts += 1
            p_code, p_data = http_get(f"{BACKEND_URL}/repairs/{repair_id}")
            assert p_code == 200
            final_status = p_data["status"]
            print(f"    [Poll #{attempts}] status={final_status}, diff={p_data['has_diff']}")
            if final_status in terminal_states:
                break

        assert final_status == "verified"
        print(f"  [PASS] Repair successfully reached terminal state: {final_status} (after {attempts} polls)")
        results["step_5_6"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Repair lifecycle failed: {e}\n{traceback.format_exc()}")
        results["step_5_6"] = False

    # Step 7: Confirm Events, Diff, and Test Output
    print("\n[Step 7] Checking Events, Diff, and Test logs...")
    try:
        # Check Events
        ev_code, ev_data = http_get(f"{BACKEND_URL}/repairs/{repair_id}/events")
        assert ev_code == 200 and len(ev_data.get("events", [])) > 0
        events_list = [ev["event_type"] for ev in ev_data["events"]]
        print(f"  [PASS] GET /repairs/{repair_id}/events: {len(events_list)} audit events recorded: {set(events_list)}")

        # Check Diff
        d_code, d_data = http_get(f"{BACKEND_URL}/repairs/{repair_id}/diff")
        assert d_code == 200 and d_data["has_diff"] is True and len(d_data["raw_diff"]) > 0
        print(f"  [PASS] GET /repairs/{repair_id}/diff: has_diff={d_data['has_diff']}, total_insertions={d_data['total_insertions']}, total_deletions={d_data['total_deletions']}")
        print(f"    Files changed: {[fc['path'] for fc in d_data['files_changed']]}")
        results["step_7"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Events and diff check failed: {e}\n{traceback.format_exc()}")
        results["step_7"] = False

    # Step 8 & 9: Terminal State Report Retrieval & Verification
    print("\n[Step 8 & 9] Opening final report and confirming verification evidence...")
    try:
        rep_code, rep_data = http_get(f"{BACKEND_URL}/repairs/{repair_id}/report")
        assert rep_code == 200
        assert rep_data["status"] == "verified"
        assert rep_data["verification"]["baseline_reproduced"] is True
        assert rep_data["verification"]["targeted_pass"] is True
        assert rep_data["verification"]["regression_pass"] is True
        assert len(rep_data["markdown_summary"]) > 0
        assert len(rep_data["diff"]["raw_diff"]) > 0
        print(f"  [PASS] GET /repairs/{repair_id}/report returned full dossier:")
        print(f"    - Status: {rep_data['status']}")
        print(f"    - Baseline exit code: {rep_data['verification']['baseline_exit_code']} (reproduced: {rep_data['verification']['baseline_reproduced']})")
        print(f"    - Targeted exit code: {rep_data['verification']['targeted_exit_code']} (passed: {rep_data['verification']['targeted_pass']})")
        print(f"    - Regression exit code: {rep_data['verification']['regression_exit_code']} (passed: {rep_data['verification']['regression_pass']})")
        print(f"    - Total tests run: {rep_data['verification']['total_tests_run']}, passed: {rep_data['verification']['total_tests_passed']}")
        print(f"    - Duration: {rep_data['duration_seconds']}s")
        print(f"    - Files modified: {rep_data['diff']['files_changed']}")
        results["step_8_9"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Report verification failed: {e}\n{traceback.format_exc()}")
        results["step_8_9"] = False

    # Step 10: Unresolved & Failed repairs do NOT appear successful
    print("\n[Step 10] Verifying unresolved / failed repairs do NOT appear successful...")
    try:
        # Submit a repair with impossible bug report that fails reproduction or verification
        fail_payload = {
            "repository_id": "repo_py_calc_01",
            "bug_report": "UNREPRODUCIBLE_BUG: Nonexistent assertion error in unknown module",
            "test_target": "tests/test_calculator.py::nonexistent_test_function"
        }
        f_code, f_data = http_post(f"{BACKEND_URL}/repairs", fail_payload)
        f_id = f_data["id"]
        # Poll to completion
        f_status = f_data["status"]
        for _ in range(40):
            time.sleep(0.5)
            _, chk = http_get(f"{BACKEND_URL}/repairs/{f_id}")
            f_status = chk["status"]
            if f_status in {"unresolved", "failed"}:
                break

        assert f_status in {"unresolved", "failed"}, f"Expected unresolved or failed, got {f_status}"
        assert f_status != "verified"
        print(f"  [PASS] Non-reproducible bug correctly reached non-successful status: {f_status}")

        # Check that report accurately reflects non-verified status
        fr_code, fr_data = http_get(f"{BACKEND_URL}/repairs/{f_id}/report")
        assert fr_code == 200
        assert fr_data["status"] == f_status
        assert fr_data["verification"]["targeted_pass"] is False or fr_data["verification"]["baseline_reproduced"] is False
        print(f"  [PASS] Non-verified report displays: status={fr_data['status']}, outcome={fr_data['verification']['outcome']}")
        results["step_10"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Failed/unresolved verification failed: {e}\n{traceback.format_exc()}")
        results["step_10"] = False

    # Step 11: Restricted mode warnings
    print("\n[Step 11] Verifying restricted-mode flag and unauthorized path refusal...")
    try:
        p_code, p_data = http_get(f"{BACKEND_URL}/repairs/{repair_id}")
        assert p_code == 200
        print(f"  [PASS] Repair payload restricted_mode flag: {p_data.get('restricted_mode')}")
        assert p_data.get("restricted_mode") is True, "restricted_mode must be True when Docker is unavailable"

        # Attempt to submit an unauthorized arbitrary repository path
        unauth_payload = {
            "repository_id": "c:/windows/system32",
            "bug_report": "Arbitrary repository path escape attempt"
        }
        u_code, u_data = http_post(f"{BACKEND_URL}/repairs", unauth_payload)
        assert u_code in {400, 403, 404, 422}
        print(f"  [PASS] Arbitrary repository rejected with HTTP {u_code}: {u_data.get('detail', {}).get('code', u_data)}")
        results["step_11"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Restricted mode check failed: {e}\n{traceback.format_exc()}")
        results["step_11"] = False

    # Step 12: Cancellation and Error states remain functional
    print("\n[Step 12] Verifying Cancellation lifecycle and Conflict states...")
    try:
        # Start a repair and cancel it
        c_payload = {
            "repository_id": "repo_py_calc_01",
            "bug_report": "Cancelling this test repair"
        }
        cs_code, cs_data = http_post(f"{BACKEND_URL}/repairs", c_payload)
        c_id = cs_data["id"]
        # Cancel immediately
        cancel_code, cancel_data = http_post(f"{BACKEND_URL}/repairs/{c_id}/cancel")
        assert cancel_code == 200 and cancel_data["status"] == "cancelled"
        print(f"  [PASS] POST /repairs/{c_id}/cancel succeeded: status={cancel_data['status']}")

        # Attempt to cancel an already terminal repair -> should return 409 CONFLICT
        term_cancel_code, term_cancel_data = http_post(f"{BACKEND_URL}/repairs/{repair_id}/cancel")
        assert term_cancel_code == 409
        print(f"  [PASS] Cancelling already terminal repair correctly returned HTTP 409 CONFLICT: {term_cancel_data.get('detail', {}).get('code')}")

        # Nonexistent repair cancel -> 404
        bad_cancel_code, _ = http_post(f"{BACKEND_URL}/repairs/nonexistent_repair_xyz/cancel")
        assert bad_cancel_code == 404
        print(f"  [PASS] Cancelling nonexistent repair correctly returned HTTP 404")
        results["step_12"] = True
    except Exception as e:
        import traceback
        print(f"  [FAIL] Cancellation check failed: {e}\n{traceback.format_exc()}")
        results["step_12"] = False

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY:")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    all_passed = all(results.values())
    print(f"\nOVERALL RESULT: {'ALL 12 STEPS PASSED' if all_passed else 'SOME STEPS FAILED'}")
    print("=" * 70)
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
