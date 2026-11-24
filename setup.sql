CREATE DATABASE IF NOT EXISTS StudyPlannerDB;

USE StudyPlannerDB;

CREATE TABLE IF NOT EXISTS users (
    user_id  INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50)  NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL
);

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
);

-- Study logs table
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
);

-- Continue-later sessions table
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
);
