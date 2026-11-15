"""Cross-platform test runner (Windows PowerShell, macOS, Linux):   python tests/run_all.py
Runs the score / pipeline / engine tests, rebuilds the static site and prints the dataset health table."""
import os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
failed = []


def run(title, cmd):
    print(f"\n=== {title}")
    if subprocess.run(cmd).returncode != 0:
        failed.append(title)


run("score tests (JS and Python pick the same notes, masks, audio)", [sys.executable, "tests/test_score.py"])
run("pipeline tests (colour ramp, dates, voices, importer fallback)", [sys.executable, "tests/test_pipeline.py"])
if shutil.which("node"):
    run("audio engine against a mock Web Audio", ["node", "tests/engine_mock.mjs"])
    run("guided tour of a single picture", ["node", "tests/tour_still.mjs"])
else:
    print("\n(skipped: Node.js not installed, so the JS/Python agreement test above also needs it)")
run("static website build", [sys.executable, "-m", "pipeline.build", "static"])
run("dataset health check", [sys.executable, "-m", "pipeline.check"])
print("\nALL AUTOMATED CHECKS PASSED. Now do the listening tests in SETUP_AND_TEST.md." if not failed else f"\nFAILED: {failed}")
sys.exit(1 if failed else 0)
