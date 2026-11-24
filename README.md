# Study Planner

A CBSE Class 12 Computer Science project using Python, Tkinter and MySQL.

Users register and log in, plan their tasks per subject, run a task-linked study
timer, see weekly reports, and track study progress with automatic priority scoring.

## Files

| File | Purpose |
|---|---|
| `main (1).py` | The complete application: MySQL functions, priority engine, Tkinter screens |
| `setup.sql` | Creates the `StudyPlannerDB` database with all tables (`users`, `tasks`, `study_logs`, `continue_sessions`) |
| `requirements.txt` | Python packages to install (`mysql-connector-python`) |
| `test_study_planner.py` | Automated test suite |

## Setup

1. Start the MySQL server.
2. Run `setup.sql` in MySQL Workbench or the MySQL command line:
   ```sql
   SOURCE setup.sql;
   ```
3. Install the package: `pip install -r requirements.txt`
   (Tkinter comes pre-installed with Python. On Linux: `sudo apt install python3-tk`.)
4. Run: `python "main (1).py"`
5. Type your MySQL root password, then register and log in.

If MySQL uses a different host or user, change `DB_HOST` and `DB_USER` at the top of `main (1).py`.

## Features

### Core
- **User Authentication**: Simple and direct username/password registration and login with user-isolated data
- **Task Management**: Add, edit, delete, complete, and undo tasks with subject, deadline, difficulty, and estimated duration
- **Automatic Priority Scoring**: 60/30/10 weighted model using deadline urgency, task difficulty, and subject study deficit
- **Task-Based Study Timer**: Every study session is linked to a specific task
- **Session Completion Options**: Choose "Finished Task" or "Continue Later" after each session
- **Continue Previous Sessions**: Dashboard showing paused tasks with 48-hour auto-expiry
- **Start Highest Priority Task**: One-click shortcut to study the most urgent task
- **Weekly Study Report**: Comprehensive dashboard with daily/subject breakdowns, Tkinter Canvas bar charts, and insights
- **MySQL Native Storage**: All data (users, tasks, study logs, continue sessions) is stored directly in MySQL

### Priority Engine (60/30/10 Model)
- **60% Deadline × Length Urgency**: Proximity score mapped from days remaining + length score interpolated from minutes + interaction boost
- **30% Difficulty**: Easy (25), Medium (60), Hard (100) scoring
- **10% Subject Deficit**: Workload-aware neglect detection based on task count and estimated minutes

### Database
- Direct MySQL storage with foreign keys and CASCADE deletes
- Parameterized SQL queries (`%s`) throughout to prevent SQL injection
- Strict user isolation across all tables and queries

## Class 12 topics covered

- Python functions, loops, dictionaries, lists, exception handling
- Python-MySQL connectivity: `connect`, `cursor`, `execute`, `fetchone`, `fetchall`, `commit`, parameterised queries (`%s`)
- SQL: CREATE, INSERT, SELECT, UPDATE, DELETE, WHERE, ORDER BY, SUM, JOIN, GROUP BY, primary key, foreign key, UNIQUE, INDEX, ENUM, ALTER TABLE
- Stack: the Undo Delete list uses `append` (push) and `pop` (LIFO)
- Event-driven GUI programming with Tkinter / ttk and Canvas graphics

## Viva questions you can expect

1. Why use `%s` placeholders instead of putting inputs directly in the query text?
   To prevent SQL injection attacks by ensuring the database engine treats input strictly as data rather than executable SQL commands.
2. How does the priority engine work?
   It uses a 60/30/10 weighted formula: 60% from urgency (deadline proximity combined with estimated task duration), 30% from task difficulty, and 10% from the subject study deficit.
3. Why use `time.monotonic()` for the timer instead of `time.time()`?
   Unlike `time.time()`, `time.monotonic()` cannot go backwards and is unaffected by system clock adjustments, providing exact and reliable elapsed-time calculation.
4. How does the subject deficit model work?
   It calculates each subject's expected study share based on task count and estimated workload, then compares actual study time from MySQL logs to find neglected subjects.
5. Why are study logs stored in MySQL?
   Storing logs in MySQL allows relational queries, aggregation (SUM, AVG), filtering by date range, and strict user isolation via `user_id` foreign keys.
6. How does the Continue Later feature work?
   When a user pauses a study session, an entry is created in `continue_sessions` with an `expires_at` timestamp set 48 hours in the future. The user can resume from the Continue Sessions tab.
7. Where is the Stack data structure used?
   In the Undo Delete feature: deleted tasks are pushed onto a Python list (`append`), and pressing Undo Delete pops the most recently deleted task (`pop`) to restore it (LIFO order).
8. How does the timer keep running without freezing the window?
   Tkinter's non-blocking `after()` method schedules `tick()` calls every 500ms rather than using a blocking `sleep()` loop.
