# Study Planner

A CBSE Class 12 Computer Science project using Python, Tkinter and MySQL.

Users register and log in, plan their tasks per subject, run a task-linked study
timer, see weekly reports, and track study progress with automatic priority scoring.

## Files

| File | Purpose |
|---|---|
| `main (1).py` | The whole program: MySQL functions, priority engine, Tkinter screens |
| `setup.sql` | Creates the `StudyPlannerDB` database with all tables |
| `requirements.txt` | Python packages to install |
| `study_logs.dat` | Legacy study session file (migrated to MySQL on first run) |
| `test_study_planner.py` | Automated test suite |

## Setup

1. Start the MySQL server.
2. Run `setup.sql` in MySQL Workbench or the MySQL command line.
3. Install the package: `pip install -r requirements.txt`
   (Tkinter comes with Python. On Linux you may need `sudo apt install python3-tk`.)
4. Run: `python "main (1).py"`
5. Type your MySQL root password, then register and log in.

If MySQL uses a different host or user, change `DB_HOST` and `DB_USER` at the top of `main (1).py`.

## Features

### Core
- **Task management**: Add, edit, delete, complete, and undo tasks with subject, deadline, difficulty, and estimated duration
- **Automatic priority scoring**: 60/30/10 weighted model using deadline urgency, task difficulty, and subject study deficit
- **Task-based study timer**: Every study session is linked to a specific task
- **Session completion options**: Choose "Finished Task" or "Continue Later" after each session
- **Continue Previous Sessions**: Dashboard showing paused tasks with 48-hour expiry
- **Start Highest Priority Task**: One-click shortcut to study the most urgent task
- **Weekly Study Report**: Comprehensive dashboard with daily/subject breakdowns, charts, and insights
- **Study log migration**: Legacy `.dat` file records safely migrated to MySQL

### Priority Engine (60/30/10 Model)
- **60% Deadline × Length Urgency**: Considers both deadline proximity and estimated task duration
- **30% Difficulty**: Easy (25), Medium (60), Hard (100) scoring
- **10% Subject Deficit**: Workload-aware neglect detection based on task count and estimated hours

### Database
- Users, tasks, study logs, continue sessions, and migration tracking all in MySQL
- Parameterized queries throughout
- User isolation in every query
- Safe schema migration with column existence checks

## Class 12 topics covered

- Python functions, loops, dictionaries, lists, exception handling
- Python-MySQL connectivity: `connect`, `cursor`, `execute`, `fetchone`, `fetchall`, `commit`, parameterised queries (`%s`)
- SQL: CREATE, INSERT, SELECT, UPDATE, DELETE, WHERE, ORDER BY, SUM, JOIN, GROUP BY, primary key, foreign key, UNIQUE, INDEX, ENUM, ALTER TABLE
- Binary file handling: `pickle.dump` (mode `ab`) and `pickle.load` until `EOFError` (legacy migration)
- Stack: the Undo Delete list uses `append` (push) and `pop`
- File handling: backup creation with `shutil.copy2`

## Viva questions you can expect

1. Why `%s` placeholders instead of putting the username in the query text? To prevent SQL injection.
2. Why is the password hashed? So the database never holds the real password. A random salt is added so two users with the same password get different hashes.
3. How does the priority engine work? It uses a 60/30/10 weighted model: 60% from deadline urgency combined with task length, 30% from difficulty, and 10% from subject study deficit.
4. Why use `time.monotonic()` for the timer? Unlike `time.time()`, monotonic time is not affected by system clock changes, making elapsed-time calculations reliable.
5. How does the subject deficit model work? It calculates each subject's expected study share based on task count and estimated workload, then compares actual study time to find neglected subjects.
6. Why are study logs now in MySQL? For better querying, aggregation, user isolation, and integration with the priority engine and weekly reports.
7. How does the Continue Later feature work? When a user pauses a study session, an entry is created with a 48-hour expiry timestamp. The user can resume from the Continue Sessions tab.
8. Where is the stack? In the Undo Delete feature: last deleted, first restored (LIFO).
9. How does the timer keep running without freezing the window? `after()` schedules `tick()` again every half second instead of using a blocking loop.
10. How is the legacy .dat file migrated? On first connection, the app checks for study_logs.dat, backs it up, reads pickle records, maps them to MySQL rows, and records the migration to prevent re-runs.
