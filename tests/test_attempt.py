"""Sabotage suite for scripts/reef-attempt: the cap must be reachable, the
signature guard must fire on the same failure (not on byte-identical text), and
every ambiguous input must fail CLOSED (exit 2), never silently pass."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")


def make_task(d, name="007-demo.md", fm="id: 7\nstatus: pending\neffort: medium\nattempts: 0\n", body="# demo\n\n## Log\n"):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(f"---\n{fm}---\n{body}")
    return p


def run(*args):
    return subprocess.run([sys.executable, ATTEMPT, *args], capture_output=True, text=True)


class Attempt(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reef-attempt-test.")

    def test_dispatch_names_the_hand_back_file_and_whose_it_is(self):
        p = make_task(self.dir)
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("\nhand-back: .reef/ci-local/handback-7.md in the task worktree — the implementer writes it", r.stdout)

    def test_clean_dispatch_prints_header(self):
        p = make_task(self.dir)
        r = run(p)
        self.assertEqual(r.returncode, 0)
        self.assertIn("dispatch: model=opus effort=medium attempt=1/3", r.stdout)
        header = [l for l in r.stdout.splitlines() if l.startswith("REEF-TASK: ")]
        self.assertTrue(header and os.path.isabs(header[0].split(": ", 1)[1]),
                        "REEF-TASK must be absolute — the guard resolves it against the SESSION cwd")

    def test_effort_base_from_task_then_escalates(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: low\nattempts: 0\n")
        self.assertIn("effort=low", run(p).stdout)
        run(p, "AssertionError: boom")
        self.assertIn("effort=high", run(p).stdout)

    def test_cap_blocks_on_third_fail(self):
        p = make_task(self.dir)
        self.assertEqual(run(p, "fail one").returncode, 0)
        self.assertEqual(run(p, "fail two").returncode, 0)
        r = run(p, "fail three")
        self.assertEqual(r.returncode, 2)
        self.assertIn("retry cap 3", r.stderr)
        self.assertIn("status: blocked", open(p).read())

    def test_same_failure_twice_blocks(self):
        p = make_task(self.dir)
        run(p, "AssertionError: expected 401 got 200")
        r = run(p, "AssertionError: expected 401 got 200")
        self.assertEqual(r.returncode, 2)
        self.assertIn("same failure signature twice", r.stderr)

    def test_signature_normalized_across_noise(self):
        # same failure, different line number / timing / whitespace -> still "twice"
        p = make_task(self.dir)
        run(p, "tests/test_x.py:17: AssertionError: expected 401 got 200  (0.42s)")
        r = run(p, "tests/test_x.py:19:  AssertionError: Expected 401 got 200 (0.57s)")
        self.assertEqual(r.returncode, 2, f"normalization failed: {r.stdout} {r.stderr}")

    def test_different_failure_not_repeated(self):
        p = make_task(self.dir)
        run(p, "AssertionError: expected 401 got 200")
        r = run(p, "TypeError: cannot unpack None")
        self.assertEqual(r.returncode, 0)

    def test_human_reset_not_burned_by_stale_sig(self):
        # the round-2 scenario: block, human resets attempts/status but the Log keeps
        # history; the FIRST fail of the fresh round must not be "same failure twice"
        p = make_task(self.dir)
        run(p, "AssertionError: boom")
        run(p, "AssertionError: boom")           # blocked (repeated)
        text = open(p).read().replace("status: blocked", "status: pending").replace("attempts: 2", "attempts: 0")
        open(p, "w").write(text)                 # human resets, but leaves last_failure_sig stale
        r = run(p, "AssertionError: boom")
        self.assertEqual(r.returncode, 0, f"stale sig burned the fresh round: {r.stderr}")

    def test_body_keys_never_touched(self):
        # K5: a 'last_failure_sig:' line inside ## Log is history, not state
        body = "# demo\n\n## Log\nlast_failure_sig: deadbeefdead\nstatus: was blocked once\n"
        p = make_task(self.dir, body=body)
        r = run(p, "some new failure")
        self.assertEqual(r.returncode, 0)
        text = open(p).read()
        self.assertIn("last_failure_sig: deadbeefdead", text)   # body line untouched
        fm = text.split("---\n")[1]
        self.assertIn("last_failure_sig: ", fm)                  # state landed in frontmatter

    def test_no_frontmatter_fails_closed(self):
        p = os.path.join(self.dir, "no-fm.md")
        open(p, "w").write("# just a doc\n")
        r = run(p, "failure")
        self.assertEqual(r.returncode, 2)
        self.assertIn("frontmatter", r.stderr)

    def test_empty_failure_arg_fails_closed(self):
        p = make_task(self.dir)
        r = run(p, "")
        self.assertEqual(r.returncode, 2, "an empty failure arg must not be laundered into a dispatch")

    def test_missing_file_fails_closed(self):
        r = run(os.path.join(self.dir, "ghost.md"))
        self.assertEqual(r.returncode, 2)

    def test_non_integer_attempts_fails_closed(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: banana\n")
        self.assertEqual(run(p).returncode, 2)

    def test_negative_attempts_fails_closed(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: -5\n")
        self.assertEqual(run(p).returncode, 2)

    def test_dispatch_path_enforces_cap_too(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: 3\n")
        r = run(p)
        self.assertEqual(r.returncode, 2, "attempts>=cap with status!=blocked must still refuse dispatch")

    def test_cap_flag_and_config_cap(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: 4\n")
        self.assertEqual(run(p).returncode, 2)
        self.assertEqual(run("--cap", "5", p).returncode, 0)
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write('{"caps": {"attempts": 6}}')
        self.assertEqual(run(p).returncode, 0)   # config raises the cap

    def test_blocked_status_refuses_dispatch(self):
        p = make_task(self.dir, fm="id: 7\nstatus: blocked\nattempts: 1\n")
        self.assertEqual(run(p).returncode, 2)

    # ---- round-2 findings ----

    def test_blocked_task_never_mutated_by_further_fails(self):
        p = make_task(self.dir, fm="id: 7\nstatus: blocked\nattempts: 2\nlast_failure_sig: \"cafecafecafe\"\n")
        r = run(p, "another failure while blocked")
        self.assertEqual(r.returncode, 2)
        text = open(p).read()
        self.assertIn("attempts: 2", text)                # counter not burned past the block
        self.assertIn("cafecafecafe", text)               # diagnostic signature preserved

    def test_crlf_file_preserved_byte_for_byte_outside_edited_lines(self):
        p = os.path.join(self.dir, "007-crlf.md")
        with open(p, "wb") as f:
            f.write(b"---\r\nid: 7\r\nstatus: pending\r\nattempts: 0\r\n---\r\n# demo\r\n\r\n## Log\r\n")
        r = run(p, "some failure")
        self.assertEqual(r.returncode, 0, r.stderr)
        raw = open(p, "rb").read()
        self.assertIn(b"# demo\r\n", raw)                 # body EOLs untouched
        self.assertIn(b"id: 7\r\n", raw)                  # unedited frontmatter EOLs untouched

    def test_ports_are_not_line_numbers(self):
        # two genuinely different failures must NOT collide into one signature
        p = make_task(self.dir)
        run(p, "connect to localhost:5432 refused")
        r = run(p, "connect to localhost:6379 refused")
        self.assertEqual(r.returncode, 0, "different ports collided into 'same failure twice'")

    def test_file_line_numbers_still_normalized(self):
        p = make_task(self.dir)
        run(p, "tests/test_x.py:17: AssertionError: boom")
        r = run(p, "tests/test_x.py:19: AssertionError: boom")
        self.assertEqual(r.returncode, 2, "same failure at a drifted line must still count as repeated")

    def test_tld_ports_are_not_extensions(self):
        # round-3: '.co'/'.io' looked like file extensions to the old rule
        p = make_task(self.dir)
        run(p, "connect to db.example.co:5432 refused")
        r = run(p, "connect to db.example.co:6379 refused")
        self.assertEqual(r.returncode, 0, "two ports on a .co host collided into one signature")

    def test_line_and_column_both_normalized(self):
        p = make_task(self.dir)
        run(p, "src/main.rs:10:5 error[E0308]: mismatched types")
        r = run(p, "src/main.rs:12:9 error[E0308]: mismatched types")
        self.assertEqual(r.returncode, 2, "line:col drift must still count as the same failure")

    def test_extensionless_build_files_normalized(self):
        p = make_task(self.dir)
        run(p, "Makefile:23: recipe for target 'all' failed")
        r = run(p, "Makefile:25: recipe for target 'all' failed")
        self.assertEqual(r.returncode, 2, "Makefile line drift must still count as the same failure")

    # ---- 0.4.0 ----

    def test_verifier_model_printed_for_judge_tasks_from_config(self):
        # roles.verifier is read at dispatch, exactly like roles.author
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write(
            '{"roles": {"author": "opus", "verifier": "sonnet"}}')
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\nattempts: 0\n")
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("verifier: model=sonnet", r.stdout)

    def test_report_budget_is_printed_for_the_judges(self):
        # first contact (2026-10-16): the verifier never learned the 900-word cap and wrote 1693 words for 15 criteria;
        # the dispatch printout now names the budget (RULE lines free, +40 per criterion past 8) and the hunter's
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write('{"writing": {"report_words": 900}}')
        acs = "".join(f"- AC-{i}: holds.\n" for i in range(1, 16)) + "- HUMAN AC: looks right on a phone.\n"
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\ntier: design\nattempts: 0\n",
                      body="# demo\n\n## Acceptance Criteria\n" + acs + "\n## Log\n")
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("report: budget=1180 words, RULE lines free (15 criteria)", r.stdout)
        self.assertIn("hunter-report: budget=900 words", r.stdout)
        p = make_task(self.dir, name="008-small.md", fm="id: 8\nstatus: pending\neffort: medium\nverify: judge\nattempts: 0\n",
                      body="# small\n\n## Acceptance Criteria\n- AC-1: holds.\n\n## Log\n")
        self.assertIn("report: budget=900 words, RULE lines free (1 criteria)", run(p).stdout)

    def test_guard_pass_feature_prints_no_adversary_line(self):
        # 0.7 hunter.guard_pass = feature (2026-10-18: two judges, 96k, 20 lines): graph-run and the task skill read the
        # `adversary:` line as "dispatch a hunter"; under feature mode the line is replaced, never printed
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write('{"hunter": {"guard_pass": "feature"}}')
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\ntier: critical\nattempts: 0\n")
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotRegex(r.stdout, r"(?m)^adversary:", "an adversary: line would dispatch a hunter per task")
        self.assertNotIn("hunter-report:", r.stdout)
        self.assertIn("guard-pass: feature", r.stdout)
        self.assertIn("verifier: model=", r.stdout, "the verifier stays per task")
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write('{"hunter": {"guard_pass": "task"}}')
        self.assertRegex(run(p).stdout, r"(?m)^adversary: model=", "the default is the 0.6 behaviour")

    def test_guard_pass_is_read_from_the_main_checkout_not_the_worktree(self):
        # 2026-10-18: the owner set hunter.guard_pass feature on develop; the feature worktree's config predated it and
        # the fix round's reef-attempt printed `adversary:` — a hunter per task again. Loop policy has one home.
        main = tempfile.mkdtemp(prefix="reef-attempt-main.")
        g = ["git", "-C", main, "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", "-b", "develop", main], check=True)
        os.makedirs(os.path.join(main, ".reef"))
        open(os.path.join(main, ".reef", "config.json"), "w").write('{"hunter": {"plan_rounds": 2}}')
        subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-qm", "config without the key"], check=True, capture_output=True)
        wt = os.path.join(main, ".reef", "worktrees", "feat")
        subprocess.run(g + ["worktree", "add", "-q", "-b", "feat/x", wt], check=True, capture_output=True)
        open(os.path.join(main, ".reef", "config.json"), "w").write('{"hunter": {"plan_rounds": 2, "guard_pass": "feature"}}')   # the owner's edit, on develop
        p = make_task(wt, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\ntier: critical\nattempts: 0\n")
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("guard-pass: feature", r.stdout, "the worktree's stale copy of the config must not decide")
        self.assertNotRegex(r.stdout, r"(?m)^adversary:")

    def test_fix_round_prints_rejudge_from_the_logged_failure_and_non_test_proofs(self):
        # 2026-10-18: 202's one-test fix round re-verified all 23 criteria (31 turns, 71k)
        body = ("# demo\n\n## Acceptance Criteria\n- AC-1: a\n- AC-2: b\n- AC-3: c\n- AC-4: d\n\n## Proof\n| AC | Proof |\n|---|---|\n"
                "| AC-1 | `test_a_holds` |\n| AC-2 | `it(\"b holds\")` |\n| AC-3 | `! git grep -n 'as Foo' -- src` |\n| AC-4 | `[mechanic] npm run build` |\n\n## Log\n")
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\nattempts: 0\n", body=body)
        self.assertNotIn("rejudge:", run(p).stdout, "round 1 judges everything")
        r = run(p, "verifier FAIL: AC-2 the proof test does not exist; hunter BLOCKER on AC-2")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(p) as f:
            t = f.read()
        self.assertIn("- attempt 1 FAIL: verifier FAIL: AC-2 the proof test does not exist", t, "the failure's words live in ## Log")
        self.assertIn("rejudge: AC-2, AC-3, AC-4 (round 2: the criteria the failure named plus the ones whose Proof is not a test: AC-3, AC-4;", r.stdout)
        self.assertIn("CARRIED", r.stdout)
        r = run(p, "the gate went red, no criterion named")
        self.assertIn("rejudge: all (round 3: the recorded failure names no criterion)", r.stdout)

    def test_verifier_model_defaults_to_agent_default(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: judge\nattempts: 0\n")
        self.assertIn("verifier: model=opus", run(p).stdout)

    def test_no_verifier_line_for_gate_only_tasks(self):
        # mech tasks have no judge; printing a verifier model would invite one
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: medium\nverify: gate-only\nattempts: 0\n")
        self.assertNotIn("verifier:", run(p).stdout)

    def test_second_rollup_for_same_feature_refused(self):
        # acceptance, diff and CI rounds share ONE rollup file per feature, so attempts:
        # counts across them; a second file would reset the counter and launder the cap
        tasks = os.path.join(self.dir, "tasks")
        os.makedirs(os.path.join(tasks, "done"))
        make_task(os.path.join(tasks, "done"), name="R01-fixups.md",
                  fm="id: R1\nfeature: demo\nstatus: done\neffort: medium\nattempts: 1\n")
        p = make_task(tasks, name="R02-ci-fixups.md",
                      fm="id: R2\nfeature: demo\nstatus: pending\neffort: medium\nattempts: 0\n")
        r = run(p, "CI red: test_x failed")
        self.assertEqual(r.returncode, 2, "a second rollup for one feature must be refused")
        self.assertIn("R01-fixups.md", r.stderr)
        self.assertIn("attempts: 0", open(p).read(), "a refused rollup must not be mutated")

    def test_rollups_of_different_features_coexist(self):
        tasks = os.path.join(self.dir, "tasks")
        os.makedirs(tasks)
        make_task(tasks, name="R01-a.md", fm="id: R1\nfeature: alpha\nstatus: pending\nattempts: 0\n")
        p = make_task(tasks, name="R02-b.md", fm="id: R2\nfeature: beta\nstatus: pending\nattempts: 0\n")
        self.assertEqual(run(p).returncode, 0)

    def test_typoed_parent_dir_exits_2_not_traceback(self):
        r = run(os.path.join(self.dir, "no-such-dir", "007-x.md"), "failure")
        self.assertEqual(r.returncode, 2)
        self.assertIn("USER ACTION REQUIRED", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
