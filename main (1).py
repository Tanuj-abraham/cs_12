import os
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

import mysql.connector

PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__))

DB_HOST = "localhost"
DB_USER = "root"
DB_NAME = "StudyPlannerDB"

SUBJECTS = ["Physics", "Chemistry", "Maths", "English",
            "Computer Science", "Biology", "Other"]

DIFFICULTIES = ["Easy", "Medium", "Hard"]

PRIORITIES = ["High", "Medium", "Low"]

CONTINUE_EXPIRY_HOURS = 48

WEIGHT_URGENCY = 0.60
WEIGHT_DIFFICULTY = 0.30
WEIGHT_DEFICIT = 0.10

URGENCY_WEIGHT_DEADLINE = 0.60
URGENCY_WEIGHT_LENGTH = 0.30
URGENCY_WEIGHT_INTERACTION = 0.10

DEADLINE_SCORE_MAP = [
    (0, 100),
    (1, 90),
    (2, 78),
    (3, 68),
    (5, 55),
    (7, 42),
    (14, 25),
    (30, 12),
]
DEADLINE_SCORE_DEFAULT = 5

LENGTH_SCORE_ANCHORS = [
    (0, 0),
    (15, 5),
    (30, 15),
    (60, 30),
    (120, 50),
    (180, 70),
    (240, 85),
    (300, 100),
]

DIFFICULTY_SCORES = {
    "Easy": 25,
    "Medium": 60,
    "Hard": 100,
}

PRIORITY_LABEL_THRESHOLDS = [
    (70, "High"),
    (40, "Medium"),
    (0, "Low"),
]

DEFAULT_ESTIMATED_MINUTES = 30

WORKLOAD_WEIGHT_ESTIMATE = 0.80
WORKLOAD_WEIGHT_COUNT = 0.20
WORKLOAD_COUNT_MINUTES = 60


def db_connect(password):
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=password, database=DB_NAME
        )
        return connection, None
    except mysql.connector.Error as error:
        return None, error


def register_user(connection, username, password):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        connection.commit()
    finally:
        cursor.close()


def login_user(connection, username, password):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT user_id, password FROM users WHERE username = %s",
            (username,)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if row is None:
        return None
    user_id, stored_password = row
    if password == stored_password:
        return user_id
    return None


def get_user_id_by_username(connection, username):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT user_id FROM users WHERE username = %s", (username,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def ensure_table_exists(connection, table_name, create_sql):
    cursor = connection.cursor()
    try:
        cursor.execute(create_sql)
        connection.commit()
    finally:
        cursor.close()


def column_exists(connection, table_name, column_name):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (DB_NAME, table_name, column_name)
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()


def add_column_if_missing(connection, table_name, column_name, column_def):
    if not column_exists(connection, table_name, column_name):
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
            )
            connection.commit()
        finally:
            cursor.close()
        return True
    return False


def init_database(connection):
    ensure_table_exists(connection, "users", """
        CREATE TABLE IF NOT EXISTS users (
            user_id  INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password VARCHAR(100) NOT NULL
        )
    """)
    add_column_if_missing(
        connection, "users", "password", "VARCHAR(100) NOT NULL DEFAULT ''"
    )

    ensure_table_exists(connection, "tasks", """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id  INT AUTO_INCREMENT PRIMARY KEY,
            user_id  INT          NOT NULL,
            subject  VARCHAR(50)  NOT NULL,
            title    VARCHAR(100) NOT NULL,
            due_date DATE         NOT NULL,
            priority ENUM('High', 'Medium', 'Low') NOT NULL DEFAULT 'Medium',
            status   ENUM('Pending', 'Done')       NOT NULL DEFAULT 'Pending',
            difficulty ENUM('Easy', 'Medium', 'Hard') NOT NULL DEFAULT 'Medium',
            estimated_minutes INT DEFAULT 30,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    add_column_if_missing(
        connection, "tasks", "difficulty",
        "ENUM('Easy', 'Medium', 'Hard') NOT NULL DEFAULT 'Medium'"
    )
    add_column_if_missing(
        connection, "tasks", "estimated_minutes",
        "INT DEFAULT 30"
    )
    add_column_if_missing(
        connection, "tasks", "created_at",
        "DATETIME DEFAULT CURRENT_TIMESTAMP"
    )
    add_column_if_missing(
        connection, "tasks", "completed_at",
        "DATETIME DEFAULT NULL"
    )

    ensure_table_exists(connection, "study_logs", """
        CREATE TABLE IF NOT EXISTS study_logs (
            log_id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id         INT          NOT NULL,
            task_id         INT          DEFAULT NULL,
            subject         VARCHAR(50)  NOT NULL,
            start_time      DATETIME     NOT NULL,
            end_time        DATETIME     NOT NULL,
            duration_seconds INT         NOT NULL,
            session_date    DATE         NOT NULL,
            created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE SET NULL,
            INDEX idx_study_logs_user (user_id),
            INDEX idx_study_logs_date (session_date),
            INDEX idx_study_logs_subject (subject)
        )
    """)

    ensure_table_exists(connection, "continue_sessions", """
        CREATE TABLE IF NOT EXISTS continue_sessions (
            continue_id     INT AUTO_INCREMENT PRIMARY KEY,
            user_id         INT          NOT NULL,
            task_id         INT          NOT NULL,
            last_session_end DATETIME    NOT NULL,
            last_duration_seconds INT    NOT NULL DEFAULT 0,
            expires_at      DATETIME     NOT NULL,
            created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
            UNIQUE KEY uq_continue_user_task (user_id, task_id),
            INDEX idx_continue_expires (expires_at)
        )
    """)


run_database_migrations = init_database


def add_task(connection, user_id, subject, title, due_date,
             difficulty="Medium", estimated_minutes=30, status="Pending"):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO tasks (user_id, subject, title, due_date, priority, "
            "status, difficulty, estimated_minutes, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
            (user_id, subject, title, due_date, "Medium", status,
             difficulty, estimated_minutes)
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def get_tasks(connection, user_id, status_filter="All"):
    sql = ("SELECT task_id, subject, title, due_date, priority, status, "
           "difficulty, estimated_minutes, created_at, completed_at "
           "FROM tasks WHERE user_id = %s")
    params = [user_id]
    if status_filter in ("Pending", "Done"):
        sql += " AND status = %s"
        params.append(status_filter)
    sql += " ORDER BY (status = 'Done'), due_date"

    cursor = connection.cursor()
    try:
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()


def get_task_row(connection, task_id, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT subject, title, due_date, priority, status, "
            "difficulty, estimated_minutes "
            "FROM tasks WHERE task_id = %s AND user_id = %s",
            (task_id, user_id)
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def get_task_detail(connection, task_id, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT task_id, subject, title, due_date, priority, status, "
            "difficulty, estimated_minutes, created_at, completed_at "
            "FROM tasks WHERE task_id = %s AND user_id = %s",
            (task_id, user_id)
        )
        return cursor.fetchone()
    finally:
        cursor.close()


def update_task(connection, task_id, user_id, subject, title, due_date,
                difficulty, estimated_minutes):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE tasks SET subject = %s, title = %s, due_date = %s, "
            "difficulty = %s, estimated_minutes = %s "
            "WHERE task_id = %s AND user_id = %s",
            (subject, title, due_date, difficulty, estimated_minutes,
             task_id, user_id)
        )
        connection.commit()
    finally:
        cursor.close()


def mark_task_done(connection, task_id, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE tasks SET status = 'Done', completed_at = NOW() "
            "WHERE task_id = %s AND user_id = %s",
            (task_id, user_id)
        )
        connection.commit()
    finally:
        cursor.close()


def undo_task_done(connection, task_id, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE tasks SET status = 'Pending', completed_at = NULL "
            "WHERE task_id = %s AND user_id = %s",
            (task_id, user_id)
        )
        connection.commit()
    finally:
        cursor.close()


def delete_task(connection, task_id, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "DELETE FROM tasks WHERE task_id = %s AND user_id = %s",
            (task_id, user_id)
        )
        connection.commit()
    finally:
        cursor.close()


def get_summary(connection, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT SUM(status = 'Pending'), "
            "SUM(status = 'Pending' AND due_date < CURDATE()), "
            "SUM(status = 'Done') FROM tasks WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)


def save_study_log(connection, user_id, task_id, subject, start_time,
                   end_time, duration_seconds):
    session_date = end_time.date() if isinstance(end_time, datetime) else date.today()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO study_logs "
            "(user_id, task_id, subject, start_time, end_time, "
            "duration_seconds, session_date) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, task_id, subject, start_time, end_time,
             duration_seconds, session_date)
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def get_study_logs(connection, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT log_id, task_id, subject, start_time, end_time, "
            "duration_seconds, session_date "
            "FROM study_logs WHERE user_id = %s "
            "ORDER BY end_time DESC",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def get_study_logs_for_week(connection, user_id, week_start, week_end):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT log_id, task_id, subject, start_time, end_time, "
            "duration_seconds, session_date "
            "FROM study_logs "
            "WHERE user_id = %s AND session_date >= %s AND session_date <= %s "
            "ORDER BY end_time DESC",
            (user_id, week_start, week_end)
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def get_today_study_seconds(connection, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM study_logs "
            "WHERE user_id = %s AND session_date = CURDATE()",
            (user_id,)
        )
        return cursor.fetchone()[0]
    finally:
        cursor.close()


def get_total_study_time_for_task(connection, user_id, task_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM study_logs "
            "WHERE user_id = %s AND task_id = %s",
            (user_id, task_id)
        )
        return cursor.fetchone()[0]
    finally:
        cursor.close()


def upsert_continue_session(connection, user_id, task_id, duration_seconds):
    expires_at = datetime.now() + timedelta(hours=CONTINUE_EXPIRY_HOURS)
    now = datetime.now()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE continue_sessions SET last_session_end = %s, "
            "last_duration_seconds = %s, expires_at = %s "
            "WHERE user_id = %s AND task_id = %s",
            (now, duration_seconds, expires_at, user_id, task_id)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO continue_sessions "
                "(user_id, task_id, last_session_end, last_duration_seconds, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, task_id, now, duration_seconds, expires_at)
            )
        connection.commit()
    finally:
        cursor.close()


def remove_continue_session(connection, user_id, task_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "DELETE FROM continue_sessions WHERE user_id = %s AND task_id = %s",
            (user_id, task_id)
        )
        connection.commit()
    finally:
        cursor.close()


def cleanup_expired_continue_sessions(connection, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "DELETE FROM continue_sessions WHERE user_id = %s AND expires_at < NOW()",
            (user_id,)
        )
        connection.commit()
        return cursor.rowcount
    finally:
        cursor.close()


def get_continue_sessions(connection, user_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT cs.continue_id, cs.task_id, cs.last_session_end, "
            "cs.last_duration_seconds, cs.expires_at, "
            "t.subject, t.title, t.due_date, t.difficulty, "
            "t.estimated_minutes, t.status "
            "FROM continue_sessions cs "
            "JOIN tasks t ON cs.task_id = t.task_id "
            "WHERE cs.user_id = %s AND cs.expires_at >= NOW() "
            "AND t.status = 'Pending' "
            "ORDER BY cs.last_session_end DESC",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()


def calculate_deadline_score(due_date):
    today = date.today()
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    days_remaining = (due_date - today).days

    if days_remaining <= 0:
        return 100

    for max_days, score in DEADLINE_SCORE_MAP:
        if max_days == 0:
            continue
        if days_remaining <= max_days:
            return score

    return DEADLINE_SCORE_DEFAULT


def calculate_length_score(estimated_minutes):
    if estimated_minutes is None or estimated_minutes <= 0:
        estimated_minutes = DEFAULT_ESTIMATED_MINUTES

    if estimated_minutes >= LENGTH_SCORE_ANCHORS[-1][0]:
        return LENGTH_SCORE_ANCHORS[-1][1]

    for i in range(len(LENGTH_SCORE_ANCHORS) - 1):
        mins_lo, score_lo = LENGTH_SCORE_ANCHORS[i]
        mins_hi, score_hi = LENGTH_SCORE_ANCHORS[i + 1]
        if mins_lo <= estimated_minutes <= mins_hi:
            if mins_hi == mins_lo:
                return score_lo
            fraction = (estimated_minutes - mins_lo) / (mins_hi - mins_lo)
            return score_lo + fraction * (score_hi - score_lo)

    return 0


def calculate_urgency_score(deadline_score, length_score):
    interaction = (deadline_score * length_score) / 100.0
    urgency = (URGENCY_WEIGHT_DEADLINE * deadline_score
               + URGENCY_WEIGHT_LENGTH * length_score
               + URGENCY_WEIGHT_INTERACTION * interaction)
    return max(0, min(100, urgency))


def calculate_difficulty_score(difficulty):
    return DIFFICULTY_SCORES.get(difficulty, DIFFICULTY_SCORES["Medium"])


def get_previous_week_range():
    today = date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    prev_monday = this_monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def calculate_subject_deficit_scores(connection, user_id):
    prev_monday, prev_sunday = get_previous_week_range()

    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT subject, estimated_minutes, created_at, completed_at "
            "FROM tasks WHERE user_id = %s "
            "AND (created_at IS NULL OR created_at <= %s) "
            "AND (completed_at IS NULL OR completed_at >= %s)",
            (user_id, prev_sunday, prev_monday)
        )
        eligible_tasks = cursor.fetchall()
    finally:
        cursor.close()

    if not eligible_tasks:
        return {}

    subject_workload = {}
    subject_task_count = {}
    for subject, est_mins, created_at, completed_at in eligible_tasks:
        est = est_mins if est_mins and est_mins > 0 else DEFAULT_ESTIMATED_MINUTES
        subject_workload[subject] = subject_workload.get(subject, 0) + est
        subject_task_count[subject] = subject_task_count.get(subject, 0) + 1

    if not subject_workload:
        return {}

    workload_weights = {}
    for subject in subject_workload:
        est_total = subject_workload[subject]
        count = subject_task_count[subject]
        weight = (WORKLOAD_WEIGHT_ESTIMATE * est_total
                  + WORKLOAD_WEIGHT_COUNT * (WORKLOAD_COUNT_MINUTES * count))
        workload_weights[subject] = max(weight, 0.01)

    total_workload = sum(workload_weights.values())
    if total_workload <= 0:
        return {}

    target_shares = {
        s: w / total_workload for s, w in workload_weights.items()
    }

    study_logs = get_study_logs_for_week(connection, user_id, prev_monday, prev_sunday)

    subject_study_time = {}
    for log in study_logs:
        subject = log[2]
        if subject in target_shares:
            subject_study_time[subject] = (
                subject_study_time.get(subject, 0) + log[5]
            )

    total_study = sum(subject_study_time.values())

    deficit_scores = {}
    for subject in target_shares:
        target = target_shares[subject]
        if total_study > 0:
            actual = subject_study_time.get(subject, 0) / total_study
        else:
            actual = 0

        if target > 0:
            deficit = max(0, (target - actual) / target)
        else:
            deficit = 0

        deficit = min(1.0, deficit)
        deficit_scores[subject] = deficit * 100

    return deficit_scores


def calculate_priority_score(due_date, estimated_minutes, difficulty,
                             subject_deficit_score):
    deadline_score = calculate_deadline_score(due_date)
    length_score = calculate_length_score(estimated_minutes)
    urgency_score = calculate_urgency_score(deadline_score, length_score)

    difficulty_score = calculate_difficulty_score(difficulty)

    final = (WEIGHT_URGENCY * urgency_score
             + WEIGHT_DIFFICULTY * difficulty_score
             + WEIGHT_DEFICIT * subject_deficit_score)

    return max(0, min(100, round(final, 1)))


def get_priority_label(score):
    for threshold, label in PRIORITY_LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


def compute_all_priorities(connection, user_id):
    tasks = get_tasks(connection, user_id, "All")
    if not tasks:
        return []

    deficit_scores = calculate_subject_deficit_scores(connection, user_id)

    scored_tasks = []
    for task in tasks:
        (task_id, subject, title, due_date, priority, status,
         difficulty, estimated_minutes, created_at, completed_at) = task

        est = estimated_minutes if estimated_minutes else DEFAULT_ESTIMATED_MINUTES
        diff = difficulty if difficulty else "Medium"

        if status == "Pending":
            subject_deficit = deficit_scores.get(subject, 0)
            score = calculate_priority_score(
                due_date, est, diff, subject_deficit
            )
        else:
            score = 0

        label = get_priority_label(score)
        scored_tasks.append((
            task_id, subject, title, due_date, status,
            diff, est, created_at, completed_at,
            score, label
        ))

    def sort_key(item):
        is_done = 0 if item[4] == "Pending" else 1
        score = -item[9]
        due = item[3]
        est = -(item[6] or 0)
        return (is_done, score, due, est)

    scored_tasks.sort(key=sort_key)
    return scored_tasks


def get_highest_priority_task(connection, user_id):
    tasks = compute_all_priorities(connection, user_id)
    for task in tasks:
        if task[4] == "Pending":
            return task
    return None


def get_weekly_report_data(connection, user_id):
    prev_monday, prev_sunday = get_previous_week_range()
    report = {
        "week_start": prev_monday,
        "week_end": prev_sunday,
    }

    logs = get_study_logs_for_week(connection, user_id, prev_monday, prev_sunday)

    total_seconds = sum(log[5] for log in logs)
    total_sessions = len(logs)
    avg_session = total_seconds / total_sessions if total_sessions > 0 else 0

    report["total_study_seconds"] = total_seconds
    report["total_sessions"] = total_sessions
    report["avg_session_seconds"] = avg_session

    daily_seconds = {}
    for i in range(7):
        day = prev_monday + timedelta(days=i)
        daily_seconds[day] = 0
    for log in logs:
        day = log[6]
        if day in daily_seconds:
            daily_seconds[day] += log[5]
    report["daily_seconds"] = daily_seconds

    subject_seconds = {}
    for log in logs:
        subject = log[2]
        subject_seconds[subject] = subject_seconds.get(subject, 0) + log[5]
    report["subject_seconds"] = subject_seconds
    report["subjects_studied"] = len(subject_seconds)

    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT task_id, subject, title, due_date, status, difficulty, "
            "estimated_minutes, completed_at "
            "FROM tasks WHERE user_id = %s "
            "AND completed_at >= %s AND completed_at <= %s",
            (user_id,
             datetime.combine(prev_monday, datetime.min.time()),
             datetime.combine(prev_sunday, datetime.max.time()))
        )
        completed_tasks = cursor.fetchall()
    finally:
        cursor.close()

    tasks_completed = len(completed_tasks)
    tasks_on_time = 0
    tasks_late = 0
    for task in completed_tasks:
        due = task[3]
        completed = task[7]
        if completed and due:
            completed_date = completed.date() if isinstance(completed, datetime) else completed
            if completed_date <= due:
                tasks_on_time += 1
            else:
                tasks_late += 1

    report["tasks_completed"] = tasks_completed
    report["tasks_on_time"] = tasks_on_time
    report["tasks_late"] = tasks_late
    report["on_time_rate"] = (
        (tasks_on_time / tasks_completed * 100) if tasks_completed > 0 else 0
    )

    subject_completed = {}
    subject_estimated = {}
    for task in completed_tasks:
        subject = task[1]
        est = task[6] or DEFAULT_ESTIMATED_MINUTES
        subject_completed[subject] = subject_completed.get(subject, 0) + 1
        subject_estimated[subject] = subject_estimated.get(subject, 0) + est
    report["subject_completed"] = subject_completed
    report["subject_estimated_minutes"] = subject_estimated

    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = %s AND status = 'Pending'",
            (user_id,)
        )
        report["tasks_pending"] = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = %s "
            "AND status = 'Pending' AND due_date < CURDATE()",
            (user_id,)
        )
        report["tasks_overdue"] = cursor.fetchone()[0]
    finally:
        cursor.close()

    deficit_scores = calculate_subject_deficit_scores(connection, user_id)
    neglected = sorted(deficit_scores.items(), key=lambda x: -x[1])
    report["neglected_subjects"] = neglected

    insights = []
    if subject_seconds:
        most_studied = max(subject_seconds, key=subject_seconds.get)
        insights.append(
            f"Most studied subject: {most_studied} "
            f"({subject_seconds[most_studied] // 60} min)"
        )
    if neglected:
        worst = neglected[0]
        if worst[1] > 50:
            insights.append(
                f"Most neglected subject: {worst[0]} "
                f"(deficit score: {worst[1]:.0f}/100)"
            )

    if daily_seconds:
        days_list = list(daily_seconds.items())
        if any(v > 0 for _, v in days_list):
            best_day = max(days_list, key=lambda x: x[1])
            worst_day = min(days_list, key=lambda x: x[1])
            insights.append(
                f"Best study day: {best_day[0].strftime('%A')} "
                f"({best_day[1] // 60} min)"
            )
            insights.append(
                f"Least study day: {worst_day[0].strftime('%A')} "
                f"({worst_day[1] // 60} min)"
            )

    if tasks_completed > 0:
        insights.append(
            f"Task completion rate: {report['on_time_rate']:.0f}% on time"
        )

    if report["tasks_overdue"] > 0:
        insights.append(
            f"⚠ You have {report['tasks_overdue']} overdue task(s)"
        )

    if total_sessions == 0:
        insights.append("No study sessions recorded last week.")

    report["insights"] = insights
    return report


class StudyPlannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Study Planner")
        self.geometry("960x650")
        self.minsize(860, 600)

        self.connection = None
        self.user_id = None
        self.username = None
        self.undo_stack = []

        self.timer_running = False
        self.timer_job = None
        self.timer_task_id = None
        self.timer_subject = "Other"
        self.timer_task_title = ""
        self.start_time = 0
        self.start_datetime = None
        self.total_seconds = 0
        self.timer_session_saved = False

        self._priority_cache = None
        self._priority_cache_time = 0

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_connect()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_db_error(self, error):
        messagebox.showerror("Database error", str(error))

    def invalidate_priority_cache(self):
        self._priority_cache = None
        self._priority_cache_time = 0

    def get_cached_priorities(self):
        now = time.time()
        if (self._priority_cache is not None
                and now - self._priority_cache_time < 2):
            return self._priority_cache
        try:
            self._priority_cache = compute_all_priorities(
                self.connection, self.user_id
            )
            self._priority_cache_time = now
        except mysql.connector.Error as error:
            self.show_db_error(error)
            self._priority_cache = []
        return self._priority_cache

    def format_minutes(self, total_seconds):
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes} min"
        hours = minutes // 60
        mins = minutes % 60
        if mins:
            return f"{hours}h {mins}m"
        return f"{hours}h"

    def show_connect(self):
        self.clear_window()
        frame = ttk.Frame(self, padding=30)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(frame, text="Study Planner",
                  font=("Helvetica", 24, "bold")).grid(row=0, column=0, columnspan=2)
        ttk.Label(frame, text="Connect to your MySQL server to begin"
                  ).grid(row=1, column=0, columnspan=2, pady=(0, 15))

        ttk.Label(frame, text="MySQL root password:").grid(row=2, column=0, padx=5, pady=5)
        self.db_password_entry = ttk.Entry(frame, show="*", width=25)
        self.db_password_entry.grid(row=2, column=1, pady=5)
        self.db_password_entry.focus()
        self.db_password_entry.bind("<Return>", lambda event: self.connect_database())

        ttk.Button(frame, text="Connect", command=self.connect_database
                   ).grid(row=3, column=0, columnspan=2, pady=15)

    def connect_database(self):
        password = self.db_password_entry.get()
        connection, error = db_connect(password)
        if connection is None:
            messagebox.showerror(
                "Could not connect",
                f"{error}\n\nCheck that MySQL is running and setup.sql has been run."
            )
            return
        self.connection = connection

        try:
            init_database(connection)
        except mysql.connector.Error as error:
            messagebox.showerror(
                "Database error",
                f"Could not initialize database tables:\n{error}"
            )
            return

        self.show_login()

    def show_login(self):
        self.clear_window()
        frame = ttk.Frame(self, padding=30)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(frame, text="Welcome", font=("Helvetica", 22, "bold")
                  ).grid(row=0, column=0, columnspan=2, pady=(0, 15))

        ttk.Label(frame, text="Username:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.username_entry = ttk.Entry(frame, width=25)
        self.username_entry.grid(row=1, column=1, pady=5)

        ttk.Label(frame, text="Password:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.password_entry = ttk.Entry(frame, show="*", width=25)
        self.password_entry.grid(row=2, column=1, pady=5)
        self.password_entry.bind("<Return>", lambda event: self.do_login())

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(buttons, text="Login", command=self.do_login).pack(side="left", padx=5)
        ttk.Button(buttons, text="Register", command=self.do_register).pack(side="left", padx=5)

        self.username_entry.focus()

    def do_register(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if len(username) < 3 or len(username) > 50:
            messagebox.showwarning("Check username", "Username must be 3 to 50 characters.")
            return
        if len(password) < 4:
            messagebox.showwarning("Check password", "Password must be at least 4 characters.")
            return

        try:
            register_user(self.connection, username, password)
            messagebox.showinfo("Registered", "Account created. You can log in now.")
        except mysql.connector.errors.IntegrityError:
            messagebox.showerror("Registration failed", "That username is already taken.")
        except mysql.connector.Error as error:
            self.show_db_error(error)

    def do_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if username == "" or password == "":
            messagebox.showwarning("Missing details", "Enter both username and password.")
            return

        try:
            user_id = login_user(self.connection, username, password)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        if user_id is None:
            messagebox.showerror("Login failed", "Incorrect username or password.")
            return

        self.user_id = user_id
        self.username = username

        try:
            cleanup_expired_continue_sessions(self.connection, self.user_id)
        except mysql.connector.Error:
            pass

        self.show_main()

    def show_main(self):
        self.clear_window()
        self.undo_stack = []

        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text=f"Welcome, {self.username}!",
                  font=("Helvetica", 15, "bold")).pack(side="left")
        ttk.Button(top, text="Logout", command=self.logout).pack(side="right")

        self.summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self.summary_var, padding=(12, 0, 12, 8)
                  ).pack(fill="x")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tasks_tab = ttk.Frame(notebook, padding=10)
        timer_tab = ttk.Frame(notebook, padding=10)
        continue_tab = ttk.Frame(notebook, padding=10)
        history_tab = ttk.Frame(notebook, padding=10)
        report_tab = ttk.Frame(notebook, padding=10)
        notebook.add(tasks_tab, text="Tasks")
        notebook.add(timer_tab, text="Study Timer")
        notebook.add(continue_tab, text="Continue Sessions")
        notebook.add(history_tab, text="History")
        notebook.add(report_tab, text="Weekly Report")

        self.notebook = notebook

        self.build_tasks_tab(tasks_tab)
        self.build_timer_tab(timer_tab)
        self.build_continue_tab(continue_tab)
        self.build_history_tab(history_tab)
        self.build_report_tab(report_tab)
        self.refresh_all()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event=None):
        if not hasattr(self, 'notebook'):
            return
        try:
            tab_idx = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if tab_idx == 0:
            self.refresh_tasks()
            self.refresh_summary()
        elif tab_idx == 1:
            self.refresh_timer_tasks_dropdown(force_fresh=True)
        elif tab_idx == 2:
            self.refresh_continue_tab()
        elif tab_idx == 3:
            self.refresh_history()

    def logout(self):
        if self.timer_running:
            self.finish_timer(action="continue", quiet=True)
        self.user_id = None
        self.username = None
        self.invalidate_priority_cache()
        self.show_login()

    def on_close(self):
        if self.timer_running:
            self.finish_timer(action="continue", quiet=True)
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.destroy()

    def refresh_all(self):
        self.invalidate_priority_cache()
        self.refresh_tasks()
        self.refresh_history()
        self.refresh_summary()
        self.refresh_continue_tab()
        self.refresh_timer_tasks_dropdown()

    def refresh_summary(self):
        try:
            pending, overdue, done = get_summary(self.connection, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        try:
            seconds_today = get_today_study_seconds(self.connection, self.user_id)
        except mysql.connector.Error:
            seconds_today = 0

        self.summary_var.set(
            f"Pending: {pending}     Overdue: {overdue}     Done: {done}"
            f"     Studied today: {seconds_today // 60} min"
        )

    def build_tasks_tab(self, parent):
        form = ttk.LabelFrame(parent, text="Add a task", padding=8)
        form.pack(fill="x")

        ttk.Label(form, text="Subject").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Task").grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Due (YYYY-MM-DD)").grid(row=0, column=2, sticky="w")
        ttk.Label(form, text="Difficulty").grid(row=0, column=3, sticky="w")
        ttk.Label(form, text="Est. min").grid(row=0, column=4, sticky="w")

        self.subject_box = ttk.Combobox(form, values=SUBJECTS, width=15)
        self.subject_box.set(SUBJECTS[0])
        self.title_entry = ttk.Entry(form, width=25)
        self.due_entry = ttk.Entry(form, width=12)
        self.due_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        self.difficulty_box = ttk.Combobox(
            form, values=DIFFICULTIES, width=8, state="readonly"
        )
        self.difficulty_box.set("Medium")
        self.est_minutes_entry = ttk.Spinbox(form, from_=5, to=600, width=6)
        self.est_minutes_entry.set(30)

        self.subject_box.grid(row=1, column=0, padx=(0, 5), pady=3)
        self.title_entry.grid(row=1, column=1, padx=(0, 5), pady=3)
        self.due_entry.grid(row=1, column=2, padx=(0, 5), pady=3)
        self.difficulty_box.grid(row=1, column=3, padx=(0, 5), pady=3)
        self.est_minutes_entry.grid(row=1, column=4, padx=(0, 5), pady=3)
        ttk.Button(form, text="Add Task", command=self.on_add_task
                   ).grid(row=1, column=5, pady=3)
        self.title_entry.bind("<Return>", lambda event: self.on_add_task())

        filter_row = ttk.Frame(parent)
        filter_row.pack(fill="x", pady=(10, 4))
        ttk.Label(filter_row, text="Show:").pack(side="left")
        self.filter_box = ttk.Combobox(filter_row, values=["All", "Pending", "Done"],
                                       width=10, state="readonly")
        self.filter_box.set("Pending")
        self.filter_box.pack(side="left", padx=5)
        self.filter_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_tasks())
        ttk.Label(filter_row, text="(red = overdue, grey = done)"
                  ).pack(side="left", padx=10)

        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        columns = ("subject", "title", "due", "difficulty", "est_min",
                   "priority", "score", "status")
        self.task_tree = ttk.Treeview(table, columns=columns, show="headings",
                                      selectmode="browse")
        col_defs = [
            ("subject", "Subject", 110),
            ("title", "Task", 200),
            ("due", "Due date", 90),
            ("difficulty", "Difficulty", 70),
            ("est_min", "Est. min", 60),
            ("priority", "Priority", 65),
            ("score", "Score", 50),
            ("status", "Status", 60),
        ]
        for name, text, width in col_defs:
            self.task_tree.heading(name, text=text)
            self.task_tree.column(name, width=width, minwidth=40)
        self.task_tree.tag_configure("overdue", foreground="red")
        self.task_tree.tag_configure("done", foreground="grey")
        self.task_tree.tag_configure("high_priority", foreground="#CC0000")

        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        self.task_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Mark as Done", command=self.on_mark_done).pack(
            side="left")
        ttk.Button(buttons, text="Undo Done", command=self.on_undo_done).pack(
            side="left", padx=6)
        ttk.Button(buttons, text="Edit Task", command=self.on_edit_task).pack(
            side="left", padx=6)
        ttk.Button(buttons, text="Delete", command=self.on_delete).pack(
            side="left", padx=6)
        ttk.Button(buttons, text="Undo Delete", command=self.on_undo_delete).pack(
            side="left")
        ttk.Button(buttons, text="▶ Study This Task", command=self.on_study_task).pack(
            side="right", padx=6)

    def refresh_tasks(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        try:
            scored = self.get_cached_priorities()
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        today = date.today()
        status_filter = self.filter_box.get()
        for (task_id, subject, title, due_date, status,
             difficulty, est_min, created_at, completed_at,
             score, label) in scored:
            if status_filter == "Pending" and status != "Pending":
                continue
            if status_filter == "Done" and status != "Done":
                continue

            if status == "Done":
                tags = ("done",)
            elif due_date < today:
                tags = ("overdue",)
            elif label == "High" and status == "Pending":
                tags = ("high_priority",)
            else:
                tags = ()

            self.task_tree.insert("", "end", iid=str(task_id),
                                  values=(subject, title, str(due_date),
                                          difficulty, est_min or "",
                                          label, f"{score:.0f}", status),
                                  tags=tags)

    def selected_task_id(self):
        selection = self.task_tree.selection()
        if not selection:
            messagebox.showinfo("Select a task", "Click a task in the list first.")
            return None
        return int(selection[0])

    def on_add_task(self):
        subject = self.subject_box.get().strip()
        title = self.title_entry.get().strip()
        due_text = self.due_entry.get().strip()
        difficulty = self.difficulty_box.get()

        if subject == "" or title == "":
            messagebox.showwarning("Missing details", "Subject and task cannot be blank.")
            return
        if len(subject) > 50 or len(title) > 100:
            messagebox.showwarning("Too long", "Subject: max 50 characters. Task: max 100.")
            return
        try:
            due_date = datetime.strptime(due_text, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showwarning("Check date", "Write the date like 2026-12-31.")
            return

        try:
            est_min = int(self.est_minutes_entry.get())
            if est_min <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Check estimate",
                                   "Estimated minutes must be a positive number.")
            return

        try:
            add_task(self.connection, self.user_id, subject, title, due_date,
                     difficulty, est_min)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        self.title_entry.delete(0, "end")
        self.refresh_all()

    def on_mark_done(self):
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            mark_task_done(self.connection, task_id, self.user_id)
            remove_continue_session(self.connection, self.user_id, task_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        self.refresh_all()

    def on_undo_done(self):
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            undo_task_done(self.connection, task_id, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        self.refresh_all()

    def on_delete(self):
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            row = get_task_row(self.connection, task_id, self.user_id)
            if row is not None:
                self.undo_stack.append(row)
                remove_continue_session(self.connection, self.user_id, task_id)
                delete_task(self.connection, task_id, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        self.refresh_all()

    def on_undo_delete(self):
        if not self.undo_stack:
            messagebox.showinfo("Nothing to undo", "No deleted tasks to bring back.")
            return
        row = self.undo_stack.pop()
        subject, title, due = row[0], row[1], row[2]
        status = row[4] if len(row) > 4 else "Pending"
        difficulty = row[5] if len(row) > 5 else "Medium"
        est_min = row[6] if len(row) > 6 else DEFAULT_ESTIMATED_MINUTES

        try:
            add_task(self.connection, self.user_id, subject, title, due,
                     difficulty, est_min, status)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        self.refresh_all()

    def on_edit_task(self):
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            task = get_task_detail(self.connection, task_id, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        if task is None:
            messagebox.showwarning("Not found", "Task not found.")
            return

        (tid, subject, title, due_date, priority, status,
         difficulty, estimated_minutes, created_at, completed_at) = task

        dialog = tk.Toplevel(self)
        dialog.title("Edit Task")
        dialog.geometry("400x320")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Subject:").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        subj_var = ttk.Combobox(frame, values=SUBJECTS, width=20)
        subj_var.set(subject)
        subj_var.grid(row=0, column=1, pady=4)

        ttk.Label(frame, text="Task:").grid(row=1, column=0, sticky="e", padx=5, pady=4)
        title_var = ttk.Entry(frame, width=23)
        title_var.insert(0, title)
        title_var.grid(row=1, column=1, pady=4)

        ttk.Label(frame, text="Due date:").grid(row=2, column=0, sticky="e", padx=5, pady=4)
        due_var = ttk.Entry(frame, width=23)
        due_var.insert(0, str(due_date))
        due_var.grid(row=2, column=1, pady=4)

        ttk.Label(frame, text="Difficulty:").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        diff_var = ttk.Combobox(frame, values=DIFFICULTIES, width=20, state="readonly")
        diff_var.set(difficulty or "Medium")
        diff_var.grid(row=3, column=1, pady=4)

        ttk.Label(frame, text="Est. minutes:").grid(row=4, column=0, sticky="e", padx=5, pady=4)
        est_var = ttk.Spinbox(frame, from_=5, to=600, width=20)
        est_var.set(estimated_minutes or DEFAULT_ESTIMATED_MINUTES)
        est_var.grid(row=4, column=1, pady=4)

        def save_edit():
            new_subj = subj_var.get().strip()
            new_title = title_var.get().strip()
            new_due_text = due_var.get().strip()
            new_diff = diff_var.get()
            try:
                new_est = int(est_var.get())
                if new_est <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Check estimate",
                                       "Estimated minutes must be a positive number.",
                                       parent=dialog)
                return

            if not new_subj or not new_title:
                messagebox.showwarning("Missing", "Subject and task cannot be blank.",
                                       parent=dialog)
                return

            try:
                new_due = datetime.strptime(new_due_text, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showwarning("Check date", "Write the date like 2026-12-31.",
                                       parent=dialog)
                return

            try:
                update_task(self.connection, task_id, self.user_id,
                            new_subj, new_title, new_due, new_diff, new_est)
            except mysql.connector.Error as error:
                self.show_db_error(error)
                return

            self.refresh_all()
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Save", command=save_edit).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

    def on_study_task(self):
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            task = get_task_detail(self.connection, task_id, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return
        if task is None:
            messagebox.showwarning("Not found", "Task not found.")
            return
        if task[5] == "Done":
            messagebox.showinfo("Already done", "This task is already completed.")
            return

        self._load_task_into_timer(task)
        self.notebook.select(1)

    def build_timer_tab(self, parent):
        choose_frame = ttk.LabelFrame(parent, text="Choose Task", padding=10)
        choose_frame.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(choose_frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Select Task:").pack(side="left", padx=(0, 6))
        self.timer_task_combo = ttk.Combobox(
            row1, state="readonly", width=50,
            postcommand=lambda: self.refresh_timer_tasks_dropdown(force_fresh=True)
        )
        self.timer_task_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.timer_task_combo.bind("<<ComboboxSelected>>", self.on_task_dropdown_selected)

        ttk.Button(row1, text="⚡ Start Highest Priority Task",
                   command=self.on_start_highest_priority
                   ).pack(side="right")

        self.timer_task_info = tk.StringVar(value="No task selected")
        ttk.Label(choose_frame, textvariable=self.timer_task_info,
                  wraplength=800, justify="left", font=("Helvetica", 10, "bold")
                  ).pack(fill="x", pady=(6, 2))

        box = ttk.Frame(parent)
        box.pack(expand=True)

        row = ttk.Frame(box)
        row.pack(pady=5)
        ttk.Label(row, text="Session duration (minutes):").pack(side="left", padx=5)
        self.minutes_box = ttk.Spinbox(row, from_=1, to=300, width=6)
        self.minutes_box.set(25)
        self.minutes_box.pack(side="left", padx=5)

        preset_row = ttk.Frame(box)
        preset_row.pack(pady=3)
        for mins in [25, 45, 60, 90]:
            ttk.Button(preset_row, text=f"{mins} min",
                       command=lambda m=mins: self.minutes_box.set(m)
                       ).pack(side="left", padx=3)

        self.timer_text = tk.StringVar(value="25:00")
        ttk.Label(box, textvariable=self.timer_text,
                  font=("Helvetica", 64, "bold")).pack(pady=15)

        self.timer_status = tk.StringVar(value="Select a task and press Start.")
        ttk.Label(box, textvariable=self.timer_status).pack()

        buttons = ttk.Frame(box)
        buttons.pack(pady=15)
        ttk.Button(buttons, text="▶ Start", command=self.start_timer).pack(
            side="left", padx=6)
        ttk.Button(buttons, text="⏹ Stop",
                   command=self.on_stop_timer).pack(side="left", padx=6)

    def refresh_timer_tasks_dropdown(self, force_fresh=False):
        if not hasattr(self, 'timer_task_combo'):
            return

        if force_fresh:
            self.invalidate_priority_cache()

        try:
            scored = self.get_cached_priorities()
        except Exception:
            scored = []

        self.timer_task_list = [t for t in scored if t[4] == "Pending"]

        if not self.timer_task_list:
            self.timer_task_combo['values'] = ["(No pending tasks)"]
            self.timer_task_combo.set("(No pending tasks)")
            self.timer_task_id = None
            self.timer_task_info.set("No task selected")
            return

        values = [
            f"Task: {t[2]}  |  Subject: {t[1]}  |  Score: {t[9]:.0f}"
            for t in self.timer_task_list
        ]
        self.timer_task_combo['values'] = values

        if self.timer_task_id is not None:
            found = False
            for idx, t in enumerate(self.timer_task_list):
                if t[0] == self.timer_task_id:
                    self.timer_task_combo.current(idx)
                    found = True
                    break
            if not found:
                self.timer_task_id = None
                self.timer_task_combo.set("Select a task from dropdown")
                self.timer_task_info.set("No task selected")
        else:
            self.timer_task_combo.set("Select a task from dropdown")

    def on_task_dropdown_selected(self, event=None):
        if self.timer_running:
            messagebox.showinfo(
                "Timer active",
                "Stop the current timer before selecting a different task."
            )
            self.refresh_timer_tasks_dropdown()
            return

        idx = self.timer_task_combo.current()
        if idx < 0 or idx >= len(getattr(self, 'timer_task_list', [])):
            return

        task = self.timer_task_list[idx]
        task_tuple = (task[0], task[1], task[2], task[3], "Medium", task[4],
                      task[5], task[6], task[7], task[8])
        self._load_task_into_timer(task_tuple, score=task[9])

    def _load_task_into_timer(self, task, score=None):
        (task_id, subject, title, due_date, priority, status,
         difficulty, estimated_minutes, created_at, completed_at) = task

        self.timer_task_id = task_id
        self.timer_subject = subject
        self.timer_task_title = title

        if score is None:
            deficit_scores = calculate_subject_deficit_scores(self.connection, self.user_id)
            deficit = deficit_scores.get(subject, 0)
            est = estimated_minutes or DEFAULT_ESTIMATED_MINUTES
            diff = difficulty or "Medium"
            score = calculate_priority_score(due_date, est, diff, deficit)

        info = f"Task: {title}  |  Subject: {subject}  |  Score: {score:.0f}"
        self.timer_task_info.set(info)

        if hasattr(self, 'timer_task_combo') and hasattr(self, 'timer_task_list'):
            for idx, t in enumerate(self.timer_task_list):
                if t[0] == task_id:
                    self.timer_task_combo.current(idx)
                    break

    def on_start_highest_priority(self):
        if self.timer_running:
            messagebox.showinfo("Timer active",
                                "Stop the current timer before starting a new task.")
            return

        try:
            task = get_highest_priority_task(self.connection, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        if task is None:
            messagebox.showinfo("No tasks", "No pending tasks found.")
            return

        (task_id, subject, title, due_date, status,
         difficulty, est_min, created_at, completed_at,
         score, label) = task

        task_tuple = (task_id, subject, title, due_date, "Medium", status,
                      difficulty, est_min, created_at, completed_at)
        self._load_task_into_timer(task_tuple, score=score)

    def start_timer(self):
        if self.timer_running:
            return

        if self.timer_task_id is None:
            messagebox.showwarning(
                "No task selected",
                "Please select a task from the Tasks tab or use "
                "'Start Highest Priority Task'."
            )
            return

        try:
            task = get_task_detail(
                self.connection, self.timer_task_id, self.user_id
            )
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        if task is None:
            messagebox.showwarning("Task not found",
                                   "The selected task no longer exists.")
            self.timer_task_id = None
            self.timer_task_info.set("No task selected")
            return

        if task[5] == "Done":
            messagebox.showinfo("Task completed",
                                "This task has already been completed.")
            self.timer_task_id = None
            self.timer_task_info.set("No task selected")
            return

        try:
            minutes = int(self.minutes_box.get())
        except ValueError:
            minutes = 0
        if not 1 <= minutes <= 300:
            messagebox.showwarning("Invalid time", "Enter minutes between 1 and 300.")
            return

        self.total_seconds = minutes * 60
        self.start_time = time.monotonic()
        self.start_datetime = datetime.now()
        self.timer_running = True
        self.timer_session_saved = False
        self.timer_status.set(f"Studying '{self.timer_task_title}'... stay focused!")
        self.tick()

    def tick(self):
        if not self.timer_running:
            return
        elapsed = int(time.monotonic() - self.start_time)
        remaining = max(0, self.total_seconds - elapsed)
        self.timer_text.set(f"{remaining // 60:02d}:{remaining % 60:02d}")

        if remaining == 0:
            self.on_timer_complete()
        else:
            self.timer_job = self.after(500, self.tick)

    def on_timer_complete(self):
        self.bell()
        self._stop_timer_and_choose()

    def on_stop_timer(self):
        if not self.timer_running:
            return
        self._stop_timer_and_choose()

    def _stop_timer_and_choose(self):
        if not self.timer_running:
            return
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
            self.timer_job = None
        self.timer_running = False

        elapsed = min(self.total_seconds,
                      int(time.monotonic() - self.start_time))

        if elapsed < 1:
            self.timer_status.set("Session too short to save.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Session Complete")
        dialog.geometry("420x220")
        dialog.transient(self)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        mins = elapsed // 60
        secs = elapsed % 60
        ttk.Label(frame,
                  text=f"You studied '{self.timer_task_title}' for {mins}m {secs}s",
                  font=("Helvetica", 11), wraplength=380
                  ).pack(pady=(0, 15))

        ttk.Label(frame, text="What would you like to do?",
                  font=("Helvetica", 10, "bold")).pack(pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)

        def on_finished():
            dialog.destroy()
            self.finish_timer(action="finished", elapsed=elapsed)

        def on_continue():
            dialog.destroy()
            self.finish_timer(action="continue", elapsed=elapsed)

        ttk.Button(btn_frame, text="✅ Finished Task",
                   command=on_finished).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="⏸ Continue Later",
                   command=on_continue).pack(side="left", padx=10)

    def finish_timer(self, action="continue", elapsed=None, quiet=False):
        if self.timer_session_saved:
            return
        self.timer_session_saved = True

        if self.timer_running:
            if self.timer_job is not None:
                self.after_cancel(self.timer_job)
                self.timer_job = None
            self.timer_running = False

        if elapsed is None:
            elapsed = min(self.total_seconds,
                          int(time.monotonic() - self.start_time))

        if elapsed < 1:
            return

        end_datetime = datetime.now()
        if self.start_datetime:
            start_dt = self.start_datetime
        else:
            start_dt = end_datetime - timedelta(seconds=elapsed)

        try:
            save_study_log(
                self.connection, self.user_id, self.timer_task_id,
                self.timer_subject, start_dt, end_datetime, elapsed
            )
        except mysql.connector.Error as error:
            if not quiet:
                self.show_db_error(error)

        task_id = self.timer_task_id

        if action == "finished" and task_id is not None:
            try:
                mark_task_done(self.connection, task_id, self.user_id)
                remove_continue_session(self.connection, self.user_id, task_id)
            except mysql.connector.Error as error:
                if not quiet:
                    self.show_db_error(error)
        elif action == "continue" and task_id is not None:
            try:
                upsert_continue_session(
                    self.connection, self.user_id, task_id, elapsed
                )
            except mysql.connector.Error as error:
                if not quiet:
                    self.show_db_error(error)

        self.timer_text.set(f"{self.total_seconds // 60:02d}:00")
        if action == "finished":
            self.timer_status.set("Task completed! Select a new task to study.")
            self.timer_task_id = None
            self.timer_task_info.set("No task selected")
        else:
            self.timer_status.set("Session saved. You can continue this task later.")

        self.invalidate_priority_cache()

        if not quiet:
            if action == "finished":
                messagebox.showinfo(
                    "Task Completed! 🎉",
                    f"Great job! '{self.timer_task_title}' is done.\n"
                    f"Session: {elapsed // 60} min {elapsed % 60} sec."
                )
            else:
                messagebox.showinfo(
                    "Session Saved",
                    f"Saved {elapsed // 60} min {elapsed % 60} sec "
                    f"of '{self.timer_task_title}'.\n"
                    f"You can continue this task later."
                )
            self.refresh_all()

    def build_continue_tab(self, parent):
        ttk.Label(parent, text="Tasks you paused — resume within 48 hours",
                  font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 8))

        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)

        columns = ("title", "subject", "due", "difficulty", "priority",
                   "last_studied", "last_duration", "total_time", "expires_in")
        self.continue_tree = ttk.Treeview(table, columns=columns,
                                          show="headings", selectmode="browse")
        col_defs = [
            ("title", "Task", 180),
            ("subject", "Subject", 100),
            ("due", "Due", 85),
            ("difficulty", "Diff.", 55),
            ("priority", "Priority", 65),
            ("last_studied", "Last Studied", 130),
            ("last_duration", "Last Session", 80),
            ("total_time", "Total Time", 75),
            ("expires_in", "Expires In", 80),
        ]
        for name, text, width in col_defs:
            self.continue_tree.heading(name, text=text)
            self.continue_tree.column(name, width=width, minwidth=40)

        scrollbar = ttk.Scrollbar(table, orient="vertical",
                                  command=self.continue_tree.yview)
        self.continue_tree.configure(yscrollcommand=scrollbar.set)
        self.continue_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_frame, text="▶ Continue Studying",
                   command=self.on_continue_studying).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🔄 Refresh",
                   command=self.refresh_continue_tab).pack(side="left", padx=5)

    def refresh_continue_tab(self):
        if not hasattr(self, 'continue_tree'):
            return
        for item in self.continue_tree.get_children():
            self.continue_tree.delete(item)

        try:
            cleanup_expired_continue_sessions(self.connection, self.user_id)
            sessions = get_continue_sessions(self.connection, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        deficit_scores = calculate_subject_deficit_scores(self.connection, self.user_id)

        now = datetime.now()
        for session in sessions:
            (continue_id, task_id, last_session_end, last_duration,
             expires_at, subject, title, due_date, difficulty,
             estimated_minutes, status) = session

            est = estimated_minutes or DEFAULT_ESTIMATED_MINUTES
            diff = difficulty or "Medium"
            deficit = deficit_scores.get(subject, 0)
            score = calculate_priority_score(due_date, est, diff, deficit)
            label = get_priority_label(score)

            try:
                total_secs = get_total_study_time_for_task(
                    self.connection, self.user_id, task_id
                )
            except mysql.connector.Error:
                total_secs = 0

            if expires_at > now:
                remaining = expires_at - now
                hours_left = remaining.total_seconds() / 3600
                if hours_left >= 1:
                    expires_str = f"{hours_left:.0f}h"
                else:
                    expires_str = f"{int(remaining.total_seconds() / 60)}m"
            else:
                expires_str = "Expired"

            last_studied_str = last_session_end.strftime("%Y-%m-%d %H:%M")

            self.continue_tree.insert(
                "", "end", iid=str(task_id),
                values=(title, subject, str(due_date), diff, label,
                        last_studied_str,
                        self.format_minutes(last_duration),
                        self.format_minutes(total_secs),
                        expires_str)
            )

    def on_continue_studying(self):
        selection = self.continue_tree.selection()
        if not selection:
            messagebox.showinfo("Select a task",
                                "Click a task in the list first.")
            return

        task_id = int(selection[0])

        try:
            task = get_task_detail(self.connection, task_id, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        if task is None:
            messagebox.showwarning("Not found", "Task not found.")
            return

        if task[5] == "Done":
            messagebox.showinfo("Already done", "This task is already completed.")
            return

        self._load_task_into_timer(task)
        self.notebook.select(1)

    def build_history_tab(self, parent):
        self.totals_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.totals_var, wraplength=800,
                  justify="left").pack(fill="x", pady=(0, 8))

        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        columns = ("when", "subject", "task", "minutes")
        self.history_tree = ttk.Treeview(table, columns=columns, show="headings")
        for name, text, width in [("when", "Date and time", 160),
                                  ("subject", "Subject", 130),
                                  ("task", "Task", 220),
                                  ("minutes", "Duration", 100)]:
            self.history_tree.heading(name, text=text)
            self.history_tree.column(name, width=width)

        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def refresh_history(self):
        if not hasattr(self, 'history_tree'):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        try:
            logs = get_study_logs(self.connection, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        totals = {}
        for log in logs:
            subject = log[2]
            seconds = log[5]
            end_time = log[4]
            task_id = log[1]

            totals[subject] = totals.get(subject, 0) + seconds

            task_name = ""
            if task_id:
                try:
                    task = get_task_detail(self.connection, task_id, self.user_id)
                    if task:
                        task_name = task[2]
                except mysql.connector.Error:
                    pass

            when_str = end_time.strftime("%Y-%m-%d %H:%M") if isinstance(
                end_time, datetime) else str(end_time)
            self.history_tree.insert("", "end", values=(
                when_str, subject, task_name,
                self.format_minutes(seconds)))

        if not logs:
            self.totals_var.set("No study sessions yet. Use the Study Timer tab.")
            return
        overall = sum(totals.values()) // 60
        per_subject = "   |   ".join(f"{name}: {secs // 60} min"
                                     for name, secs in sorted(totals.items()))
        self.totals_var.set(f"Total: {overall} min     {per_subject}")

    def build_report_tab(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.report_frame = ttk.Frame(canvas)

        self.report_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.report_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        btn_frame = ttk.Frame(self.report_frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_frame, text="📊 Generate Weekly Report",
                   command=self.generate_weekly_report).pack(side="left", padx=5)

        self.report_content_frame = ttk.Frame(self.report_frame)
        self.report_content_frame.pack(fill="both", expand=True)

    def generate_weekly_report(self):
        for widget in self.report_content_frame.winfo_children():
            widget.destroy()

        try:
            report = get_weekly_report_data(self.connection, self.user_id)
        except mysql.connector.Error as error:
            self.show_db_error(error)
            return

        frame = self.report_content_frame

        week_start = report["week_start"]
        week_end = report["week_end"]
        ttk.Label(frame,
                  text=f"Weekly Study Report: {week_start.strftime('%b %d')} – "
                       f"{week_end.strftime('%b %d, %Y')}",
                  font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 10))

        stats_frame = ttk.LabelFrame(frame, text="Overall Statistics", padding=10)
        stats_frame.pack(fill="x", pady=(0, 10))

        total_min = report["total_study_seconds"] // 60
        avg_min = report["avg_session_seconds"] // 60
        stats_text = (
            f"Total study time: {self.format_minutes(report['total_study_seconds'])}    "
            f"Sessions: {report['total_sessions']}    "
            f"Avg session: {self.format_minutes(int(report['avg_session_seconds']))}\n"
            f"Tasks completed: {report['tasks_completed']}    "
            f"On time: {report['tasks_on_time']}    "
            f"Late: {report['tasks_late']}    "
            f"On-time rate: {report['on_time_rate']:.0f}%    "
            f"Subjects studied: {report['subjects_studied']}"
        )
        ttk.Label(stats_frame, text=stats_text, wraplength=800,
                  justify="left").pack(anchor="w")

        daily_frame = ttk.LabelFrame(frame, text="Daily Breakdown", padding=10)
        daily_frame.pack(fill="x", pady=(0, 10))

        daily = report["daily_seconds"]
        days_ordered = sorted(daily.keys())
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        if any(v > 0 for v in daily.values()):
            max_val = max(daily.values())
            chart_canvas = tk.Canvas(daily_frame, width=700, height=180,
                                     bg="white", highlightthickness=1,
                                     highlightbackground="#ccc")
            chart_canvas.pack(pady=5)

            chart_w = 700
            chart_h = 160
            bar_width = 60
            gap = 25
            left_margin = 50
            bottom = chart_h - 10
            max_bar_h = 120

            for i, day in enumerate(days_ordered):
                x = left_margin + i * (bar_width + gap)
                secs = daily[day]
                mins = secs // 60

                if max_val > 0:
                    bar_h = int((secs / max_val) * max_bar_h)
                else:
                    bar_h = 0

                if bar_h > 0:
                    chart_canvas.create_rectangle(
                        x, bottom - bar_h, x + bar_width, bottom,
                        fill="#4682B4", outline="#2c5f8a"
                    )
                    chart_canvas.create_text(
                        x + bar_width // 2, bottom - bar_h - 8,
                        text=f"{mins}m", font=("Helvetica", 8)
                    )

                day_name = day_names[i] if i < len(day_names) else str(day)
                chart_canvas.create_text(
                    x + bar_width // 2, bottom + 10,
                    text=day_name, font=("Helvetica", 9)
                )
        else:
            ttk.Label(daily_frame, text="No study sessions during this week."
                      ).pack(anchor="w")

        subj_frame = ttk.LabelFrame(frame, text="Subject Breakdown", padding=10)
        subj_frame.pack(fill="x", pady=(0, 10))

        subject_seconds = report["subject_seconds"]
        total_secs = report["total_study_seconds"]

        if subject_seconds:
            subj_tree = ttk.Treeview(
                subj_frame,
                columns=("subject", "time", "pct", "completed", "workload"),
                show="headings", height=min(len(subject_seconds), 8)
            )
            subj_tree.heading("subject", text="Subject")
            subj_tree.heading("time", text="Study Time")
            subj_tree.heading("pct", text="% of Total")
            subj_tree.heading("completed", text="Tasks Done")
            subj_tree.heading("workload", text="Est. Workload")
            subj_tree.column("subject", width=150)
            subj_tree.column("time", width=100)
            subj_tree.column("pct", width=80)
            subj_tree.column("completed", width=80)
            subj_tree.column("workload", width=100)

            all_subjects = set(subject_seconds.keys()) | set(
                report.get("subject_completed", {}).keys()
            )
            for subj in sorted(all_subjects):
                secs = subject_seconds.get(subj, 0)
                pct = (secs / total_secs * 100) if total_secs > 0 else 0
                completed = report.get("subject_completed", {}).get(subj, 0)
                est_wl = report.get("subject_estimated_minutes", {}).get(subj, 0)
                subj_tree.insert("", "end", values=(
                    subj, self.format_minutes(secs), f"{pct:.1f}%",
                    completed, f"{est_wl} min" if est_wl else "-"
                ))
            subj_tree.pack(fill="x")
        else:
            ttk.Label(subj_frame, text="No subjects studied this week."
                      ).pack(anchor="w")

        neglect_frame = ttk.LabelFrame(frame, text="Subject Attention Needed",
                                       padding=10)
        neglect_frame.pack(fill="x", pady=(0, 10))

        neglected = report["neglected_subjects"]
        high_deficit = [(s, d) for s, d in neglected if d > 30]
        if high_deficit:
            for subj, deficit in high_deficit:
                color = "red" if deficit > 70 else ("orange" if deficit > 50 else "black")
                lbl = ttk.Label(
                    neglect_frame,
                    text=f"⚠ {subj}: deficit score {deficit:.0f}/100 — "
                         f"needs more study time",
                )
                lbl.pack(anchor="w", pady=1)
        else:
            ttk.Label(neglect_frame,
                      text="✅ No subjects significantly neglected."
                      ).pack(anchor="w")

        task_frame = ttk.LabelFrame(frame, text="Task Status", padding=10)
        task_frame.pack(fill="x", pady=(0, 10))

        task_text = (
            f"Pending tasks: {report['tasks_pending']}    "
            f"Overdue tasks: {report['tasks_overdue']}"
        )
        ttk.Label(task_frame, text=task_text).pack(anchor="w")

        insights_frame = ttk.LabelFrame(frame, text="Weekly Insights", padding=10)
        insights_frame.pack(fill="x", pady=(0, 10))

        insights = report["insights"]
        if insights:
            for insight in insights:
                ttk.Label(insights_frame, text=f"• {insight}",
                          wraplength=750).pack(anchor="w", pady=1)
        else:
            ttk.Label(insights_frame, text="Not enough data for insights."
                      ).pack(anchor="w")


if __name__ == "__main__":
    app = StudyPlannerApp()
    app.mainloop()
