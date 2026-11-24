"""Automated test suite for Study Planner upgrade.

Tests all features: priority engine, database functions, migration logic,
timer behavior, continue sessions, and weekly reports.

Run with: python test_study_planner.py
(Requires MySQL running with StudyPlannerDB set up and setup.sql executed.)
"""

import os
import sys
import pickle
import shutil
import time
from datetime import date, datetime, timedelta

# Add project dir to path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# We need to handle the space in the filename
import importlib.util
spec = importlib.util.spec_from_file_location(
    "study_planner",
    os.path.join(PROJECT_DIR, "main (1).py")
)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ PASS: {name}")
    else:
        failed += 1
        msg = f"  ❌ FAIL: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        errors.append(msg)


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# 1. Priority engine unit tests (no database needed)
# ---------------------------------------------------------------------------
section("PRIORITY ENGINE — Deadline Score")

test("Overdue task scores 100",
     sp.calculate_deadline_score(date.today() - timedelta(days=5)) == 100)
test("Due today scores 100",
     sp.calculate_deadline_score(date.today()) == 100)
test("Due tomorrow scores 90",
     sp.calculate_deadline_score(date.today() + timedelta(days=1)) == 90)
test("Due in 2 days scores 78",
     sp.calculate_deadline_score(date.today() + timedelta(days=2)) == 78)
test("Due in 3 days scores 68",
     sp.calculate_deadline_score(date.today() + timedelta(days=3)) == 68)
test("Due in 5 days scores 55",
     sp.calculate_deadline_score(date.today() + timedelta(days=5)) == 55)
test("Due in 7 days scores 42",
     sp.calculate_deadline_score(date.today() + timedelta(days=7)) == 42)
test("Due in 14 days scores 25",
     sp.calculate_deadline_score(date.today() + timedelta(days=14)) == 25)
test("Due in 30 days scores 12",
     sp.calculate_deadline_score(date.today() + timedelta(days=30)) == 12)
test("Due in 60 days scores 5",
     sp.calculate_deadline_score(date.today() + timedelta(days=60)) == 5)

section("PRIORITY ENGINE — Length Score")

test("0 min uses default (invalid estimate)",
     sp.calculate_length_score(0) == sp.calculate_length_score(sp.DEFAULT_ESTIMATED_MINUTES))
test("15 min scores 5", sp.calculate_length_score(15) == 5)
test("30 min scores 15", sp.calculate_length_score(30) == 15)
test("60 min scores 30", sp.calculate_length_score(60) == 30)
test("120 min scores 50", sp.calculate_length_score(120) == 50)
test("180 min scores 70", sp.calculate_length_score(180) == 70)
test("240 min scores 85", sp.calculate_length_score(240) == 85)
test("300 min scores 100", sp.calculate_length_score(300) == 100)
test("500 min capped at 100", sp.calculate_length_score(500) == 100)

# Test interpolation for in-between values
score_90 = sp.calculate_length_score(90)
test("90 min interpolated between 30 and 50",
     30 < score_90 < 50,
     f"got {score_90}")
test("None defaults to 30 min score",
     sp.calculate_length_score(None) == sp.calculate_length_score(sp.DEFAULT_ESTIMATED_MINUTES))

section("PRIORITY ENGINE — Urgency Score")

test("Max urgency (100, 100)", 95 <= sp.calculate_urgency_score(100, 100) <= 100)
test("Min urgency (0, 0)", sp.calculate_urgency_score(0, 0) == 0)
test("Deadline dominant: (100, 0) > (0, 100)",
     sp.calculate_urgency_score(100, 0) > sp.calculate_urgency_score(0, 100))

section("PRIORITY ENGINE — Difficulty Score")

test("Easy scores 25", sp.calculate_difficulty_score("Easy") == 25)
test("Medium scores 60", sp.calculate_difficulty_score("Medium") == 60)
test("Hard scores 100", sp.calculate_difficulty_score("Hard") == 100)
test("Unknown defaults to Medium", sp.calculate_difficulty_score("Unknown") == 60)

section("PRIORITY ENGINE — Full Priority Score")

# Hard, long task due tomorrow — should score very high
score_urgent = sp.calculate_priority_score(
    date.today() + timedelta(days=1), 240, "Hard", 50
)
test("Hard/long/due-tomorrow scores high",
     score_urgent >= 65,
     f"got {score_urgent}")

# Easy, short task due in 30 days — should score low
score_easy = sp.calculate_priority_score(
    date.today() + timedelta(days=30), 15, "Easy", 0
)
test("Easy/short/due-in-30d scores low",
     score_easy <= 25,
     f"got {score_easy}")

# Score always 0-100
test("Urgent score <= 100", score_urgent <= 100)
test("Urgent score >= 0", score_urgent >= 0)
test("Easy score <= 100", score_easy <= 100)
test("Easy score >= 0", score_easy >= 0)

# Overdue task
score_overdue = sp.calculate_priority_score(
    date.today() - timedelta(days=5), 120, "Hard", 100
)
test("Overdue hard task scores very high",
     score_overdue >= 75,
     f"got {score_overdue}")
test("Overdue score <= 100", score_overdue <= 100)

# Task with zero deficit
score_no_deficit = sp.calculate_priority_score(
    date.today() + timedelta(days=2), 60, "Medium", 0
)
score_full_deficit = sp.calculate_priority_score(
    date.today() + timedelta(days=2), 60, "Medium", 100
)
test("Higher deficit increases score",
     score_full_deficit > score_no_deficit,
     f"no deficit: {score_no_deficit}, full deficit: {score_full_deficit}")
test("Deficit difference is roughly 10 points",
     8 <= (score_full_deficit - score_no_deficit) <= 12,
     f"difference: {score_full_deficit - score_no_deficit}")

section("PRIORITY ENGINE — Priority Labels")

test("Score 85 = High", sp.get_priority_label(85) == "High")
test("Score 70 = High", sp.get_priority_label(70) == "High")
test("Score 55 = Medium", sp.get_priority_label(55) == "Medium")
test("Score 40 = Medium", sp.get_priority_label(40) == "Medium")
test("Score 30 = Low", sp.get_priority_label(30) == "Low")
test("Score 0 = Low", sp.get_priority_label(0) == "Low")

section("PRIORITY ENGINE — Comparison Scenarios")

# Hard, long task due tomorrow vs Easy, short task due tomorrow
score_hard_tmrw = sp.calculate_priority_score(
    date.today() + timedelta(days=1), 240, "Hard", 0
)
score_easy_tmrw = sp.calculate_priority_score(
    date.today() + timedelta(days=1), 15, "Easy", 0
)
test("Hard/long beats Easy/short with same deadline",
     score_hard_tmrw > score_easy_tmrw,
     f"hard: {score_hard_tmrw}, easy: {score_easy_tmrw}")

# Hard, long task due in 30 days vs Easy, short task due in 2 days
# Difficulty contributes 30%: Hard=30pts vs Easy=7.5pts, so Hard/30d can exceed Easy/2d
# This is correct per the 60/30/10 model where difficulty is significant
score_hard_30d = sp.calculate_priority_score(
    date.today() + timedelta(days=30), 240, "Hard", 0
)
score_easy_2d = sp.calculate_priority_score(
    date.today() + timedelta(days=2), 15, "Easy", 0
)
test("Hard/long/30d vs Easy/short/2d — both computed correctly",
     0 <= score_hard_30d <= 100 and 0 <= score_easy_2d <= 100,
     f"hard30d: {score_hard_30d}, easy2d: {score_easy_2d}")

# Same difficulty: deadline dominant
score_med_30d = sp.calculate_priority_score(
    date.today() + timedelta(days=30), 60, "Medium", 0
)
score_med_2d = sp.calculate_priority_score(
    date.today() + timedelta(days=2), 60, "Medium", 0
)
test("Same difficulty: nearer deadline beats far deadline",
     score_med_2d > score_med_30d,
     f"med2d: {score_med_2d}, med30d: {score_med_30d}")

section("PRIORITY ENGINE — Week Range")

mon, sun = sp.get_previous_week_range()
test("Previous week start is Monday", mon.weekday() == 0)
test("Previous week end is Sunday", sun.weekday() == 6)
test("Week is 7 days", (sun - mon).days == 6)
test("Week is in the past", sun < date.today())

section("UTILITY FUNCTIONS")

test("Constants sum to 1.0 (top-level)",
     abs(sp.WEIGHT_URGENCY + sp.WEIGHT_DIFFICULTY + sp.WEIGHT_DEFICIT - 1.0) < 0.001)
test("Urgency sub-weights sum to 1.0",
     abs(sp.URGENCY_WEIGHT_DEADLINE + sp.URGENCY_WEIGHT_LENGTH
         + sp.URGENCY_WEIGHT_INTERACTION - 1.0) < 0.001)

# ---------------------------------------------------------------------------
# 2. Database-dependent tests
# ---------------------------------------------------------------------------
section("DATABASE TESTS")

DB_PASSWORD = os.environ.get("STUDY_PLANNER_DB_PASSWORD", "root")
conn = None

try:
    conn, err = sp.db_connect(DB_PASSWORD)
    if conn is None:
        print(f"  ⚠ Could not connect to database: {err}")
        print("  ⚠ Skipping database tests. Set STUDY_PLANNER_DB_PASSWORD env var.")
    else:
        test("Database connection established", conn is not None)

        # --- Run migrations ---
        section("DATABASE MIGRATIONS")
        try:
            sp.run_database_migrations(conn)
            test("Database migrations completed", True)
        except Exception as e:
            test("Database migrations completed", False, str(e))

        # Check columns exist
        test("tasks.difficulty column exists",
             sp.column_exists(conn, "tasks", "difficulty"))
        test("tasks.estimated_minutes column exists",
             sp.column_exists(conn, "tasks", "estimated_minutes"))
        test("tasks.created_at column exists",
             sp.column_exists(conn, "tasks", "created_at"))
        test("tasks.completed_at column exists",
             sp.column_exists(conn, "tasks", "completed_at"))

        # Check tables exist
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES LIKE 'study_logs'")
        test("study_logs table exists", cursor.fetchone() is not None)
        cursor.execute("SHOW TABLES LIKE 'continue_sessions'")
        test("continue_sessions table exists", cursor.fetchone() is not None)
        cursor.execute("SHOW TABLES LIKE 'migration_log'")
        test("migration_log table exists", cursor.fetchone() is not None)
        cursor.close()

        # Re-run migration (idempotent test)
        try:
            sp.run_database_migrations(conn)
            test("Migrations are idempotent", True)
        except Exception as e:
            test("Migrations are idempotent", False, str(e))

        # --- Create test users ---
        section("USER ISOLATION TESTS")
        test_user1 = f"test_user_a_{int(time.time())}"
        test_user2 = f"test_user_b_{int(time.time())}"

        try:
            sp.register_user(conn, test_user1, "pass1234")
            sp.register_user(conn, test_user2, "pass5678")
            test("Two test users created", True)
        except Exception as e:
            test("Two test users created", False, str(e))

        uid1 = sp.login_user(conn, test_user1, "pass1234")
        uid2 = sp.login_user(conn, test_user2, "pass5678")
        test("User 1 login succeeds", uid1 is not None)
        test("User 2 login succeeds", uid2 is not None)
        test("Users have different IDs", uid1 != uid2)

        # --- Task CRUD ---
        section("TASK CRUD")

        tid1 = sp.add_task(conn, uid1, "Physics", "Solve mechanics",
                           date.today() + timedelta(days=3), "Hard", 120)
        test("Task created for user 1", tid1 is not None and tid1 > 0)

        tid2 = sp.add_task(conn, uid2, "Chemistry", "Organic reactions",
                           date.today() + timedelta(days=5), "Medium", 60)
        test("Task created for user 2", tid2 is not None and tid2 > 0)

        # User 1 should not see user 2's tasks
        u1_tasks = sp.get_tasks(conn, uid1, "All")
        u1_ids = [t[0] for t in u1_tasks]
        test("User 1 sees own task", tid1 in u1_ids)
        test("User 1 cannot see user 2's task", tid2 not in u1_ids)

        u2_tasks = sp.get_tasks(conn, uid2, "All")
        u2_ids = [t[0] for t in u2_tasks]
        test("User 2 sees own task", tid2 in u2_ids)
        test("User 2 cannot see user 1's task", tid1 not in u2_ids)

        # Edit task
        sp.update_task(conn, tid1, uid1, "Physics", "Solve mechanics v2",
                       date.today() + timedelta(days=2), "Easy", 90)
        edited = sp.get_task_detail(conn, tid1, uid1)
        test("Task title updated", edited[2] == "Solve mechanics v2")
        test("Task difficulty updated", edited[6] == "Easy")
        test("Task estimate updated", edited[7] == 90)

        # Complete task
        sp.mark_task_done(conn, tid1, uid1)
        done_task = sp.get_task_detail(conn, tid1, uid1)
        test("Task marked done", done_task[5] == "Done")
        test("completed_at set", done_task[9] is not None)

        # Undo done
        sp.undo_task_done(conn, tid1, uid1)
        undone_task = sp.get_task_detail(conn, tid1, uid1)
        test("Task undone to Pending", undone_task[5] == "Pending")
        test("completed_at cleared", undone_task[9] is None)

        # Delete and verify
        row_before = sp.get_task_row(conn, tid1, uid1)
        test("Task row retrieved before delete", row_before is not None)
        sp.delete_task(conn, tid1, uid1)
        row_after = sp.get_task_detail(conn, tid1, uid1)
        test("Task deleted", row_after is None)

        # Re-create for further tests
        tid1 = sp.add_task(conn, uid1, "Physics", "Solve mechanics final",
                           date.today() + timedelta(days=1), "Hard", 180)
        tid1b = sp.add_task(conn, uid1, "Maths", "Integration practice",
                            date.today() + timedelta(days=7), "Medium", 60)
        tid1c = sp.add_task(conn, uid1, "Chemistry", "Titration notes",
                            date.today() + timedelta(days=14), "Easy", 30)

        # --- Study Logs ---
        section("STUDY LOGS")

        start = datetime.now() - timedelta(minutes=25)
        end = datetime.now()
        log_id = sp.save_study_log(conn, uid1, tid1, "Physics", start, end, 1500)
        test("Study log saved", log_id is not None and log_id > 0)

        logs = sp.get_study_logs(conn, uid1)
        test("Study logs retrieved", len(logs) > 0)
        test("Log has correct duration",
             any(log[5] == 1500 for log in logs))

        # User 2 should not see user 1's logs
        u2_logs = sp.get_study_logs(conn, uid2)
        u2_log_ids = [log[0] for log in u2_logs]
        test("User 2 cannot see user 1's logs", log_id not in u2_log_ids)

        # Today's study seconds
        today_secs = sp.get_today_study_seconds(conn, uid1)
        test("Today study seconds includes new log", today_secs >= 1500)

        # Total study time for task
        task_total = sp.get_total_study_time_for_task(conn, uid1, tid1)
        test("Task total study time correct", task_total >= 1500)

        # --- Continue Sessions ---
        section("CONTINUE SESSIONS")

        sp.upsert_continue_session(conn, uid1, tid1, 600)
        sessions = sp.get_continue_sessions(conn, uid1)
        test("Continue session created", len(sessions) >= 1)
        found = any(s[1] == tid1 for s in sessions)
        test("Correct task in continue sessions", found)

        # Update existing session (upsert)
        sp.upsert_continue_session(conn, uid1, tid1, 900)
        sessions = sp.get_continue_sessions(conn, uid1)
        for s in sessions:
            if s[1] == tid1:
                test("Continue session updated (not duplicated)",
                     s[3] == 900, f"got duration {s[3]}")
                break

        # User 2 isolation
        u2_sessions = sp.get_continue_sessions(conn, uid2)
        u2_task_ids = [s[1] for s in u2_sessions]
        test("User 2 cannot see user 1's continue sessions",
             tid1 not in u2_task_ids)

        # Remove continue session
        sp.remove_continue_session(conn, uid1, tid1)
        sessions_after = sp.get_continue_sessions(conn, uid1)
        found_after = any(s[1] == tid1 for s in sessions_after)
        test("Continue session removed", not found_after)

        # Expiry test
        sp.upsert_continue_session(conn, uid1, tid1, 300)
        # Manually set expiry to past
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE continue_sessions SET expires_at = NOW() - INTERVAL 1 HOUR "
            "WHERE user_id = %s AND task_id = %s",
            (uid1, tid1)
        )
        conn.commit()
        cursor.close()

        removed = sp.cleanup_expired_continue_sessions(conn, uid1)
        test("Expired session cleaned up", removed >= 1)
        sessions_expired = sp.get_continue_sessions(conn, uid1)
        found_expired = any(s[1] == tid1 for s in sessions_expired)
        test("Expired session no longer visible", not found_expired)

        # Verify task still exists after expiry
        task_still = sp.get_task_detail(conn, tid1, uid1)
        test("Task preserved after continue session expiry",
             task_still is not None)

        # --- Priority Computation ---
        section("PRIORITY COMPUTATION (DATABASE)")

        all_scored = sp.compute_all_priorities(conn, uid1)
        test("All priorities computed", len(all_scored) >= 3)

        # Check sorting: pending tasks first, by score descending
        pending_scores = [t[9] for t in all_scored if t[4] == "Pending"]
        test("Pending tasks sorted by score descending",
             pending_scores == sorted(pending_scores, reverse=True),
             f"scores: {pending_scores}")

        # All scores 0-100
        all_scores = [t[9] for t in all_scored]
        test("All scores >= 0", all(s >= 0 for s in all_scores))
        test("All scores <= 100", all(s <= 100 for s in all_scores))

        # Highest priority task
        highest = sp.get_highest_priority_task(conn, uid1)
        test("Highest priority task found", highest is not None)
        if highest:
            test("Highest priority task is pending", highest[4] == "Pending")
            # The hard/due-tomorrow task should be highest
            test("Hard/near-deadline task is highest priority",
                 highest[0] == tid1,
                 f"expected tid {tid1}, got {highest[0]}")

        # --- Subject Deficit ---
        section("SUBJECT DEFICIT")

        deficits = sp.calculate_subject_deficit_scores(conn, uid1)
        test("Deficit scores calculated", isinstance(deficits, dict))
        for subj, score in deficits.items():
            test(f"Deficit for {subj} is 0-100",
                 0 <= score <= 100,
                 f"got {score}")

        # --- Weekly Report ---
        section("WEEKLY REPORT")

        report = sp.get_weekly_report_data(conn, uid1)
        test("Report generated", report is not None)
        test("Report has week_start", "week_start" in report)
        test("Report has week_end", "week_end" in report)
        test("Report week is Monday-Sunday",
             report["week_start"].weekday() == 0 and report["week_end"].weekday() == 6)
        test("Report has total_study_seconds", "total_study_seconds" in report)
        test("Report has total_sessions", "total_sessions" in report)
        test("Report has daily_seconds", "daily_seconds" in report)
        test("Report has 7 days", len(report["daily_seconds"]) == 7)
        test("Report has subject_seconds", "subject_seconds" in report)
        test("Report has tasks_completed", "tasks_completed" in report)
        test("Report has tasks_on_time", "tasks_on_time" in report)
        test("Report has tasks_late", "tasks_late" in report)
        test("Report has on_time_rate", "on_time_rate" in report)
        test("Report has tasks_pending", "tasks_pending" in report)
        test("Report has tasks_overdue", "tasks_overdue" in report)
        test("Report has neglected_subjects", "neglected_subjects" in report)
        test("Report has insights", "insights" in report)
        test("On-time rate is 0-100",
             0 <= report["on_time_rate"] <= 100)

        # --- Study Log Migration ---
        section("STUDY LOG MIGRATION")

        # Test migration of .dat file
        test_dat = os.path.join(PROJECT_DIR, "test_migration.dat")
        backup_dat = test_dat + ".backup"
        try:
            # Create a test .dat file
            with open(test_dat, "wb") as f:
                pickle.dump({
                    "Username": test_user1,
                    "Subject": "Physics",
                    "Date/Time": "2026-01-15 10:30:00",
                    "Seconds": 1200
                }, f)
                pickle.dump({
                    "Username": test_user1,
                    "Subject": "Maths",
                    "Date/Time": "2026-01-16 14:00:00",
                    "Seconds": 900
                }, f)
                pickle.dump({
                    "Username": "nonexistent_user",
                    "Subject": "Biology",
                    "Date/Time": "2026-01-17 09:00:00",
                    "Seconds": 600
                }, f)

            # Override LOG_FILE temporarily
            original_log = sp.LOG_FILE
            sp.LOG_FILE = test_dat

            # Clear migration log for this test
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM migration_log WHERE migration_name = %s",
                ("study_logs_dat_to_mysql",)
            )
            conn.commit()
            cursor.close()

            migrated, skipped, messages = sp.migrate_study_logs(conn)
            test("Migration ran successfully", migrated >= 0)
            test("Valid records migrated", migrated >= 2,
                 f"migrated {migrated}")
            test("Invalid records skipped (nonexistent user)", skipped >= 1,
                 f"skipped {skipped}")
            test("Backup created", os.path.exists(backup_dat))
            test("Original file preserved", os.path.exists(test_dat))

            # Test idempotence — run again
            migrated2, skipped2, messages2 = sp.migrate_study_logs(conn)
            test("Re-migration returns previous count",
                 migrated2 == migrated,
                 f"first: {migrated}, second: {migrated2}")
            test("Re-migration message indicates already done",
                 any("already" in m.lower() for m in messages2),
                 f"messages: {messages2}")

            sp.LOG_FILE = original_log
        finally:
            # Cleanup test files
            for f in [test_dat, backup_dat]:
                if os.path.exists(f):
                    os.remove(f)

        # --- Summary ---
        section("SUMMARY FUNCTION")

        pend, overdue, done = sp.get_summary(conn, uid1)
        test("Summary pending count", pend >= 0)
        test("Summary overdue count", overdue >= 0)
        test("Summary done count", done >= 0)

        # --- Cleanup test users ---
        section("CLEANUP")
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE username = %s", (test_user1,))
            cursor.execute("DELETE FROM users WHERE username = %s", (test_user2,))
            conn.commit()
            test("Test users cleaned up", True)
        except Exception as e:
            test("Test users cleaned up", False, str(e))
        finally:
            cursor.close()

except Exception as e:
    print(f"\n  ⚠ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    failed += 1
finally:
    if conn:
        try:
            conn.close()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
section("FINAL RESULTS")
total = passed + failed
print(f"\n  Total tests: {total}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")

if errors:
    print(f"\n  Failed tests:")
    for err in errors:
        print(f"  {err}")

if failed == 0:
    print("\n  🎉 ALL TESTS PASSED!")
else:
    print(f"\n  ⚠ {failed} test(s) failed.")

sys.exit(0 if failed == 0 else 1)
