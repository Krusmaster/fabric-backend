"""UM2: the weekly usage digest to the founder's webhook (usage_digest.py), and a full deploy run that says it drops the
operator's secrets (metrics-token, usage-salt, founder-webhook) while --update points their variables at them again.
Fake storage, a fake webhook and a faked `az`; nothing here calls Azure, Entra, Fabric or Teams."""
import json
import logging
import threading
from datetime import datetime, timezone

import pytest

from deploy import azure_containerapp as d
from fabric_backend import billing, usage_digest as ud, usage_metrics as um
from tests import test_deploy_from_azure as fa
from tests import test_n159_operator_flags as of

WEBHOOK = "https://prod-00.example.invalid/workflows/abc/triggers/manual/paths/invoke?sig=SIGNATURE-not-real"
TOKEN = "m" * 64
SALT = "salt-" + "y" * 30
TID_A = "aaaaaaaa-0000-0000-0000-00000000000a"
TID_B = "bbbbbbbb-0000-0000-0000-00000000000b"
OID = "11111111-0000-0000-0000-000000000001"


def ts(y, m, day, h=0, mi=0):
    return datetime(y, m, day, h, mi, tzinfo=timezone.utc).timestamp()


MONDAY_0700 = ts(2026, 11, 23, 7, 0)       # Monday of ISO week 48; the digest covers 16-22 Nov (W47) and 9-15 Nov


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class Hook:
    def __init__(self, answers=(True,)):
        self.sent, self.answers = [], list(answers)

    def __call__(self, message):
        self.sent.append(json.loads(json.dumps(message)))
        return self.answers.pop(0) if self.answers else True


def day_row(orgs=(), users=(), sessions=0, tools=None, errors=None, routes=None, clients=None):
    r = um.empty_day()
    r.update(orgs=list(orgs), users=list(users), sessions=sessions, tools=tools or {}, errors=errors or {},
             routes=routes or {}, clients=clients or {})
    return r


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_FOUNDER_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", TOKEN)
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", SALT)
    monkeypatch.delenv("KRUSGRAPH_METRICS", raising=False)
    monkeypatch.delenv("KRUSGRAPH_USAGE_DIGEST", raising=False)


@pytest.fixture
def stored(env):
    """Fixed daily rows in a fake table, as two replicas wrote them."""
    rows = um.MemoryRows()
    a, b = um.hashes(TID_A, OID), um.hashes(TID_B, OID)
    # the week reported (16-22 Nov): two organisations, two replicas on one day
    rows.put("2026-11-16_r1", day_row([a[0]], [a[1]], 3, {"plan_backend": 5, "review_plan": 2},
                                      {"plan_backend:not_found": 1}, {"review": 2}, {"claude-ai": 3}))
    rows.put("2026-11-16_r2", day_row([b[0]], [b[1]], 1, {"plan_backend": 1, "start": 4},
                                      {"start:consent": 2}, {"build": 1}, {"cursor": 1}))
    rows.put("2026-11-22_r1", day_row([a[0]], [a[1]], 2, {"verify_build": 3, "check_source": 1, "explain": 1, "start": 1},
                                      {"verify_build:rate_limited": 1, "explain:not_found": 1, "start:consent": 1}, {},
                                      {"claude-ai": 2}))
    # the week before (9-15 Nov): one organisation
    rows.put("2026-11-09_r1", day_row([a[0]], [a[1]], 1, {"start": 2}, {}, {"review": 1}, {"claude-ai": 1}))
    # outside both weeks: not counted
    rows.put("2026-11-08_r1", day_row([b[0]], [b[1]], 50, {"start": 50}))
    rows.put("2026-11-23_r1", day_row([b[0]], [b[1]], 70, {"start": 70}))
    return rows


def digest(rows, t=MONDAY_0700, answers=(True,), durable=True):
    clock = Clock(t)
    hook = Hook(answers)
    return ud.Digest(um.Counts(rows, durable=durable, clock=clock), post=hook, clock=clock, sleep=lambda s: None), hook, clock


# ------------------------------------------------------------------ the content ---------------------------------------

def test_the_digest_is_built_from_the_stored_daily_rows_last_week_against_the_week_before(stored):
    dg, hook, _ = digest(stored)
    assert dg.tick() == "sent" and len(hook.sent) == 1
    s = ud.build(dg.counts.days(21), datetime(2026, 11, 23).date())
    assert (s["week"], s["from"], s["to"]) == ("2026-W47", "2026-11-16", "2026-11-22")
    assert s["this_week"] == {"organisations": 2, "users": 2, "sessions": 6, "tool_calls": 18, "tool_errors": 6,
                              "workload_calls": 3}
    assert s["week_before"] == {"organisations": 1, "users": 1, "sessions": 1, "tool_calls": 2, "tool_errors": 0,
                                "workload_calls": 1}
    assert s["top_tools"] == [["plan_backend", 6], ["start", 5], ["verify_build", 3], ["review_plan", 2], ["check_source", 1]]
    assert s["top_error_kinds"] == [["consent", 3], ["not_found", 2], ["rate_limited", 1]]
    assert s["clients"] == [["claude-ai", 5], ["cursor", 1]]
    assert s["details"] == "https://krusgraph.com/metrics"


def test_the_card_is_the_adaptive_card_message_envelope_the_trial_notices_already_send(stored):
    dg, hook, _ = digest(stored)
    dg.tick()
    msg = hook.sent[0]
    assert msg["type"] == "message" and len(msg["attachments"]) == 1
    att = msg["attachments"][0]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive" and att["contentUrl"] is None
    assert att["content"]["type"] == "AdaptiveCard" and att["content"]["version"] == "1.4"
    trial = billing.founder_card({"event": "trial_started", "tenant": "x"})
    assert {k: v for k, v in msg.items() if k != "attachments"} == {k: v for k, v in trial.items() if k != "attachments"}
    assert set(att) == set(trial["attachments"][0]) and set(att["content"]) == set(trial["attachments"][0]["content"])
    text = json.dumps(msg, ensure_ascii=False)
    assert "Krusgraph vecka 47" in text and "2026-11-16 till 2026-11-22" in text
    facts = {f["title"]: f["value"] for f in att["content"]["body"][2]["facts"]}
    assert facts["Organisationer"] == "2 (veckan före: 1)" and facts["Verktygsfel"] == "6 (veckan före: 0)"
    assert "Mest använda verktyg: plan_backend 6, start 5, verify_build 3, review_plan 2, check_source 1" in text
    assert "Vanligaste fel: consent 3, not_found 2, rate_limited 1" in text
    assert "MCP-klienter: claude-ai 5, cursor 1" in text
    assert "Se /metrics för detaljer: https://krusgraph.com/metrics" in text


def test_no_token_hash_id_salt_or_webhook_address_is_ever_in_the_payload(stored):
    dg, hook, _ = digest(stored)
    dg.tick()
    text = json.dumps(hook.sent, ensure_ascii=False)
    secrets = [TOKEN, SALT, WEBHOOK, "SIGNATURE", TID_A, TID_B, OID]
    for tid in (TID_A, TID_B):
        secrets += [h for h in um.hashes(tid, OID) if h]
    for row in stored.data.values():
        secrets += row.get("orgs", []) + row.get("users", [])
    assert secrets and not [x for x in secrets if x in text]
    assert "metrics?" not in text and "token" not in text.lower() and "Bearer" not in text


def test_an_empty_week_says_inga_and_still_sends_zeros(env):
    dg, hook, _ = digest(um.MemoryRows())
    assert dg.tick() == "sent"
    text = json.dumps(hook.sent[0], ensure_ascii=False)
    assert "Mest använda verktyg: inga" in text and "0 (veckan före: 0)" in text


# ------------------------------------------------------------------ the week --------------------------------------------

@pytest.mark.parametrize("t,expected", [
    (ts(2026, 11, 23, 6, 59), None),                        # Monday before 07:00: not yet
    (ts(2026, 11, 23, 7, 0), "2026-W48"),                   # Monday 07:00
    (ts(2026, 11, 25, 13, 0), "2026-W48"),                  # the first check after that, two days late
    (ts(2026, 11, 29, 23, 59), "2026-W48"),                 # Sunday night: still this week's (already settled by then)
    (ts(2026, 11, 30, 0, 1), None),                         # the next Monday, before 07:00: last week is not sent late
    (ts(2027, 1, 4, 7, 0), "2027-W01"),                     # across the year
])
def test_due_is_monday_0700_utc_or_the_first_check_after_it(t, expected):
    got = ud.due(t)
    assert (got[0] if got else None) == expected


def test_before_monday_0700_nothing_is_sent_or_claimed(stored):
    dg, hook, clock = digest(stored, t=ts(2026, 11, 23, 6, 59))
    assert dg.tick() == "not_due" and not hook.sent and not any(k.startswith("digest-") for k in stored.data)
    clock.t = MONDAY_0700
    assert dg.tick() == "sent" and "digest-2026-W48" in stored.data
    clock.t += 900
    assert dg.tick() == "done" and len(hook.sent) == 1


def test_the_week_across_new_year_reports_iso_week_53_of_2026(env):
    rows = um.MemoryRows()
    rows.put("2027-01-03_r1", day_row(sessions=4, tools={"start": 4}))
    rows.put("2026-12-28_r1", day_row(sessions=1, tools={"start": 1}))
    rows.put("2026-12-27_r1", day_row(sessions=9, tools={"start": 9}))      # the week before
    dg, hook, _ = digest(rows, t=ts(2027, 1, 4, 8, 0))
    assert dg.tick() == "sent" and "digest-2027-W01" in rows.data
    s = ud.build(dg.counts.days(21), datetime(2027, 1, 4).date())
    assert s["week"] == "2026-W53" and s["this_week"]["sessions"] == 5 and s["week_before"]["sessions"] == 9


# ------------------------------------------------------------------ exactly once ----------------------------------------

def test_two_replicas_and_a_restart_send_exactly_once(stored):
    first, hook1, _ = digest(stored)
    second, hook2, _ = digest(stored)
    results = []
    barrier = threading.Barrier(2)

    def run(dg):
        barrier.wait()
        results.append(dg.tick())
    threads = [threading.Thread(target=run, args=(dg,)) for dg in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["sent", "taken"] and len(hook1.sent) + len(hook2.sent) == 1
    restarted, hook3, _ = digest(stored, t=MONDAY_0700 + 3600)
    assert restarted.tick() == "taken" and not hook3.sent
    row = stored.data["digest-2026-W48"]
    assert set(row) == {"week", "claimed"} and row["week"] == "2026-W48"


def test_the_table_insert_refuses_a_second_writer(monkeypatch):
    calls = []

    class R:
        def __init__(self, code):
            self.status_code, self.headers = code, {}

        def json(self):
            return {}
    answers = iter([204, 409, 500])

    def http(method, url, headers=None, data=None, params=None):
        calls.append((method, url, json.loads(data)))
        return R(next(answers))
    rows = um.TableRows("https://acct.table.core.windows.net/registrations", http=http, token=lambda: "t")
    assert rows.add("digest-2026-W48", {"week": "2026-W48"}) is True
    assert rows.add("digest-2026-W48", {"week": "2026-W48"}) is False
    with pytest.raises(Exception):
        rows.add("digest-2026-W48", {"week": "2026-W48"})
    method, url, body = calls[0]
    assert method == "POST" and url == "https://acct.table.core.windows.net/registrations"       # Insert Entity, not upsert
    assert body["PartitionKey"] == "usage" and body["RowKey"] == "digest-2026-W48"


def test_a_failed_insert_or_no_table_sends_nothing(stored, monkeypatch):
    dg, hook, _ = digest(stored, durable=False)
    assert dg.tick() == "no_table" and not hook.sent

    dg, hook, _ = digest(stored)
    monkeypatch.setattr(stored, "add", lambda *a: (_ for _ in ()).throw(RuntimeError("table down")))
    assert dg.tick() == "claim_failed" and not hook.sent


def test_rows_that_cannot_be_read_send_nothing_and_claim_nothing(stored, monkeypatch):
    dg, hook, _ = digest(stored)
    monkeypatch.setattr(stored, "rows", lambda since: (_ for _ in ()).throw(RuntimeError("read failed")))
    assert dg.tick() == "read_failed" and not hook.sent and "digest-2026-W48" not in stored.data


def test_a_failing_webhook_is_tried_twice_at_most_and_never_again_that_week(stored):
    dg, hook, clock = digest(stored, answers=(False, False))
    assert dg.tick() == "send_failed" and len(hook.sent) == 2
    clock.t += 900
    assert dg.tick() == "done" and len(hook.sent) == 2
    dg2, hook2, _ = digest(stored, answers=(False, True))
    assert dg2.tick() == "taken"


def test_the_retry_succeeds_on_the_second_try(env):
    dg, hook, _ = digest(um.MemoryRows(), answers=(False, True))
    assert dg.tick() == "sent" and len(hook.sent) == 2


# ------------------------------------------------------------------ switches and the unset webhook ----------------------

def test_unset_webhook_sends_nothing_claims_nothing_and_says_so_once(stored, monkeypatch, capsys):
    monkeypatch.delenv("KRUSGRAPH_FOUNDER_WEBHOOK_URL")
    dg, hook, _ = digest(stored)
    assert dg.tick() == "no_webhook" and dg.tick() == "no_webhook"
    assert not hook.sent and not any(k.startswith("digest-") for k in stored.data)
    err = capsys.readouterr().err
    assert err.count('"no_webhook"') == 1
    monkeypatch.setattr(ud, "_said_no_webhook", False)
    monkeypatch.setattr(ud, "_thread", None)
    assert ud.start(dg.counts) is False and ud.start(dg.counts) is False and ud._thread is None
    assert capsys.readouterr().err.count('"no_webhook"') == 1


@pytest.mark.parametrize("variable", ["KRUSGRAPH_USAGE_DIGEST", "KRUSGRAPH_METRICS"])
def test_the_off_switches_stop_the_digest(stored, monkeypatch, variable, capsys):
    monkeypatch.setenv(variable, "off")
    dg, hook, _ = digest(stored)
    assert dg.tick() == "off" and not hook.sent and not any(k.startswith("digest-") for k in stored.data)
    monkeypatch.setattr(ud, "_thread", None)
    assert ud.start(dg.counts) is False and ud._thread is None
    assert "usage_digest" not in capsys.readouterr().err


def test_the_sender_logs_failures_by_type_only_and_uses_a_10_second_timeout(monkeypatch, caplog):
    import urllib.error
    import urllib.request
    seen = {}

    def boom(req, timeout):
        seen["timeout"], seen["url"] = timeout, req.full_url
        raise urllib.error.URLError(f"could not reach {req.full_url}")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setenv("KRUSGRAPH_FOUNDER_WEBHOOK_URL", WEBHOOK)
    with caplog.at_level(logging.WARNING):
        assert ud.Digest(um.Counts(um.MemoryRows(), durable=True), sleep=lambda s: None)._post({"type": "message"}) is False
    assert seen == {"timeout": 10, "url": WEBHOOK}
    assert "URLError" in caplog.text and "example.invalid" not in caplog.text and "SIGNATURE" not in caplog.text


def test_the_sender_refuses_an_address_that_is_not_https(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_FOUNDER_WEBHOOK_URL", "http://plain.example.invalid/hook")
    assert billing.founder_webhook_url() == "" and billing.post_founder_card({"type": "message"}) is False


# ------------------------------------------------------------------ /metrics is unchanged ------------------------------

def test_metrics_and_retention_leave_the_digest_rows_alone(stored):
    dg, _, clock = digest(stored)
    dg.tick()
    rep = um.report(dg.counts, 30)
    assert all(r["day"][:4].isdigit() for r in rep["days"])
    assert rep["windows"]["30d"]["sessions"] == 6 + 1 + 50 + 70
    dg.counts.tidy()
    assert "digest-2026-W48" in stored.data


def test_build_app_starts_the_digest():
    from pathlib import Path
    text = Path(um.__file__).with_name("server.py").read_text(encoding="utf-8")
    assert text.count("_usage_digest.start()") == 1


# ------------------------------------------------------------------ deploy: the full run and --update ------------------

def app_with_operator_secrets():
    app = of.existing_app()
    app["properties"]["configuration"]["secrets"] = [{"name": "entra-secret"}, {"name": "usage-salt"},
                                                     {"name": "metrics-token"}, {"name": "founder-webhook"}]
    app["properties"]["template"]["containers"][0]["env"] += [
        {"name": "KRUSGRAPH_USAGE_SALT", "secretRef": "usage-salt"},
        {"name": "KRUSGRAPH_METRICS_TOKEN", "secretRef": "metrics-token"},
        {"name": "KRUSGRAPH_FOUNDER_WEBHOOK_URL", "secretRef": "founder-webhook"}]
    return app


def test_a_full_run_says_it_drops_metrics_token_and_prints_how_to_restore_it(capsys):
    manifest = d.make_manifest(of.BASE, "env", "identity", "registry", "image", "s", app_with_operator_secrets(), build="b")
    assert manifest["properties"]["configuration"]["secrets"] == [{"name": "entra-secret", "value": "s"}]
    env = manifest["properties"]["template"]["containers"][0]["env"]
    refs = {e.get("secretRef") for e in env} - {None}
    assert refs == {"entra-secret"}                          # no variable points at a secret the manifest dropped
    out = capsys.readouterr().out
    assert "usage-salt, metrics-token, founder-webhook" in out
    assert "--secrets metrics-token=\"$(openssl rand -hex 32)\"" in out
    assert "read -rsp" in out and "founder-webhook=\"$FW\" --output none; unset FW" in out
    assert ("--set-env-vars KRUSGRAPH_USAGE_SALT=secretref:usage-salt KRUSGRAPH_METRICS_TOKEN=secretref:metrics-token "
            "KRUSGRAPH_FOUNDER_WEBHOOK_URL=secretref:founder-webhook") in out


def test_a_full_run_without_operator_secrets_says_nothing_about_them(capsys):
    d.make_manifest(of.BASE, "env", "identity", "registry", "image", "s", of.existing_app(), build="b")
    d.make_manifest(of.BASE, "env", "identity", "registry", "image", "s", None, build="b")
    assert "metrics-token" not in capsys.readouterr().out


def test_update_points_metrics_token_and_the_others_at_their_secrets(monkeypatch, tmp_path):
    cloud = of.Cloud()
    cloud.app["properties"]["configuration"]["secrets"] += [{"name": "metrics-token"}, {"name": "founder-webhook"}]
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    update = next(a for a, _ in cloud.calls if a[:2] == ("containerapp", "update"))
    assert "KRUSGRAPH_METRICS_TOKEN=secretref:metrics-token" in update
    assert "KRUSGRAPH_FOUNDER_WEBHOOK_URL=secretref:founder-webhook" in update
    assert "KRUSGRAPH_USAGE_SALT=secretref:usage-salt" in update


def test_update_without_the_secrets_sets_no_reference(monkeypatch, tmp_path):
    cloud = of.Cloud()
    cloud.app["properties"]["configuration"]["secrets"] = [{"name": "entra-secret"}]
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    update = next(a for a, _ in cloud.calls if a[:2] == ("containerapp", "update"))
    assert not [x for x in update if "secretref:" in x]


def test_from_azure_update_never_touches_the_secret_references(monkeypatch, tmp_path):
    cloud = of.Cloud()
    cloud.app["properties"]["configuration"]["secrets"] += [{"name": "metrics-token"}]
    fa.run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--update")
    update = next(a for a, _ in cloud.calls if a[:2] == ("containerapp", "update"))
    assert not [x for x in update if "secretref:" in x]
