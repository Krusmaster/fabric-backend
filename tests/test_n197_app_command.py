"""Round n197, item 5: the App (Rayfin, preview) is published with one command in Azure Cloud Shell.

Microsoft Learn documents no definition for an App's pages or connector (rayfin_app.py cites the pages read on 10
November 2026), so Krusgraph does not deploy them: the package carries krusgraph-publish.sh, which runs create, login,
connector add, unzip and up in that order, keeps what is done when run again, and stops with a plain message at the
first error. Run here with stub node, npm, npx and unzip on PATH, in a temporary HOME."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from fabric_backend import rayfin_app as R

ARGS = ("shop_conn", "SqlAnalyticsEndpoint", "Demo workspace", "ws-1", "sql-1", "demo_lh_app")


def _stub(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/usr/bin/env bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def shell(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash is not installed")
    home, bins = tmp_path / "home", tmp_path / "bin"
    home.mkdir()
    bins.mkdir()
    log = tmp_path / "log"
    _stub(bins, "node", "exit 0\n")
    _stub(bins, "unzip", f'echo "unzip $*" >> {log}\nexit 0\n')
    _stub(bins, "npm", f'echo "npm $*" >> {log}\nmkdir -p "$4" && echo {{}} > "$4/package.json"\n')
    _stub(bins, "npx", f'echo "npx $*" >> {log}\nif [ "$3" = "connector" ]; then mkdir -p rayfin && echo shop_conn > rayfin/c.json; fi\n'
                       'if [ -n "${FAIL_AT:-}" ] && [ "$3" = "$FAIL_AT" ]; then exit 3; fi\nexit 0\n')
    (home / "demo_lh_app_rayfin_app.zip").write_text("zip")
    script = tmp_path / R.PUBLISH_SCRIPT
    script.write_text(R.publish_script(*ARGS))
    env = {"HOME": str(home), "PATH": f"{bins}:/usr/bin:/bin"}

    def run(**extra):
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True, env={**env, **extra}, cwd=home, timeout=60)
        lines = log.read_text().splitlines() if log.exists() else []
        log.write_text("")
        return r, lines
    return run


def test_the_script_runs_the_five_steps_in_order_and_keeps_what_is_done(shell):
    r, calls = shell()
    assert r.returncode == 0, r.stderr
    assert [c.split()[0] + " " + c.split()[{"npm": 1, "npx": 3, "unzip": 1}[c.split()[0]]] for c in calls] == [
        "npm create", "npx login", "npx connector", "unzip -oq", "npx up"]
    assert "--operations read" in calls[2] and "--workspace-id ws-1 --item-id sql-1 --name shop_conn" in calls[2]
    assert "Done: the App demo_lh_app is published" in r.stdout
    again, calls = shell()                                              # idempotent: the project and connector are kept
    assert again.returncode == 0 and "already there: kept" in again.stdout and "already in the project: kept" in again.stdout
    assert [c.split()[3] for c in calls if c.startswith("npx")] == ["login", "up"] and not any(c.startswith("npm") for c in calls)


def test_the_script_stops_at_the_first_error_with_a_plain_message(shell):
    r, calls = shell(FAIL_AT="login")
    assert r.returncode == 1
    assert "Stopped at step 2: the sign-in did not finish." in r.stderr
    assert not any(" up " in f" {c} " for c in calls)                    # nothing after that step


def test_the_one_command_holds_no_secret_and_the_script_passes_bash_n(tmp_path):
    cmd = R.one_command("demo_lh_app")
    assert cmd == 'bash <(unzip -p "$HOME/demo_lh_app_rayfin_app.zip" krusgraph-publish.sh) "$HOME/demo_lh_app_rayfin_app.zip"'
    text = R.publish_script(*ARGS)
    for word in ("token", "secret", "password", "client_secret", "Bearer"):
        assert word.lower() not in (cmd + text.replace("No secret is stored or passed", "")).lower(), word
    p = tmp_path / "s.sh"
    p.write_text(text)
    assert subprocess.run(["bash", "-n", str(p)]).returncode == 0
    quoted = R.publish_script("c", "T", "Bob's workspace", "w", "s", "a")
    assert "WORKSPACE='Bob'\\''s workspace'" in quoted
