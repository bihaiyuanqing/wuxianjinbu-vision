import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv('DATA_DIR', DB_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv('DB_PATH', os.path.join(DATA_DIR, 'badminton.db'))

ADMIN_WECHAT_NAME = '行遇书'
ADMIN_DEFAULT_PASSWORD = 'XingYuShu@2026'


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn, table, column, definition):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id TEXT UNIQUE NOT NULL,
                user_name TEXT,
                task_name TEXT,
                original_filename TEXT,
                safe_filename TEXT,
                upload_url TEXT,
                upload_size INTEGER,
                output_dir TEXT,
                min_duration REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                output_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        _ensure_column(conn, 'tasks', 'wechat_name', 'TEXT')
        _ensure_column(conn, 'tasks', 'progress', 'REAL DEFAULT 0.0')
        _ensure_column(conn, 'tasks', 'progress_message', 'TEXT DEFAULT \'\'')
        _ensure_column(conn, 'tasks', 'error', 'TEXT')
        _ensure_column(conn, 'tasks', 'started_at', 'TEXT')
        _ensure_column(conn, 'tasks', 'total_segments', 'INTEGER DEFAULT 0')
        _ensure_column(conn, 'tasks', 'result_data', 'TEXT')
        _ensure_column(conn, 'tasks', 'is_deleted', 'INTEGER DEFAULT 0')
        _ensure_column(conn, 'tasks', 'deleted_at', 'TEXT')
        _ensure_column(conn, 'tasks', 'is_private', 'INTEGER DEFAULT 0')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user_name ON tasks(user_name)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_task_name ON tasks(task_name)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_wechat_name ON tasks(wechat_name)')

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wechat_name TEXT NOT NULL,
                rating INTEGER NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(conn, 'comments', 'is_deleted', 'INTEGER DEFAULT 0')
        _ensure_column(conn, 'comments', 'deleted_at', 'TEXT')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_wechat_name ON comments(wechat_name)')

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wechat_name TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                wechat_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_wechat ON sessions(wechat_name)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)')

        conn.execute(
            "UPDATE tasks SET task_name = wechat_name WHERE (task_name IS NULL OR task_name = '') AND wechat_name IS NOT NULL AND wechat_name <> ''"
        )
        conn.execute(
            "UPDATE tasks SET user_name = wechat_name WHERE (user_name IS NULL OR user_name = '') AND wechat_name IS NOT NULL AND wechat_name <> ''"
        )
        conn.execute(
            "UPDATE tasks SET is_private = 0 WHERE is_private IS NULL"
        )

        _ensure_admin_exists(conn)

        conn.execute(
            "UPDATE tasks SET status='failed', error='服务重启，任务被中断' WHERE status IN ('processing', 'queued') AND (completed_at IS NULL)"
        )


def _ensure_admin_exists(conn):
    row = conn.execute('SELECT id FROM users WHERE wechat_name = ?', (ADMIN_WECHAT_NAME,)).fetchone()
    if not row:
        now = datetime.utcnow().isoformat() + 'Z'
        conn.execute(
            'INSERT INTO users (wechat_name, password_hash, is_admin, created_at) VALUES (?, ?, 1, ?)',
            (ADMIN_WECHAT_NAME, generate_password_hash(ADMIN_DEFAULT_PASSWORD), now)
        )


def user_exists(wechat_name):
    with get_conn() as conn:
        row = conn.execute('SELECT id FROM users WHERE wechat_name = ?', (wechat_name,)).fetchone()
    return row is not None


def create_user(wechat_name, password):
    if not wechat_name or not password:
        return None
    with get_conn() as conn:
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            is_admin = 1 if wechat_name == ADMIN_WECHAT_NAME else 0
            conn.execute(
                'INSERT INTO users (wechat_name, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)',
                (wechat_name, generate_password_hash(password), is_admin, now)
            )
        except sqlite3.IntegrityError:
            return None
        row = conn.execute('SELECT * FROM users WHERE wechat_name = ?', (wechat_name,)).fetchone()
    return dict(row) if row else None


def verify_user(wechat_name, password):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM users WHERE wechat_name = ?', (wechat_name,)).fetchone()
    if not row:
        return None
    if not check_password_hash(row['password_hash'], password):
        return None
    return dict(row)


def get_user_by_name(wechat_name):
    if not wechat_name:
        return None
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM users WHERE wechat_name = ?', (wechat_name,)).fetchone()
    return dict(row) if row else None


def create_token(wechat_name):
    token = uuid.uuid4().hex
    now = datetime.utcnow().isoformat() + 'Z'
    with get_conn() as conn:
        conn.execute('DELETE FROM sessions WHERE julianday(?) - julianday(created_at) > 7', (now,))
        conn.execute(
            'INSERT INTO sessions (token, wechat_name, created_at) VALUES (?, ?, ?)',
            (token, wechat_name, now)
        )
    return token


def get_user_by_token(token):
    if not token:
        return None
    with get_conn() as conn:
        row = conn.execute(
            'SELECT u.* FROM sessions s JOIN users u ON s.wechat_name = u.wechat_name WHERE s.token = ? AND julianday(?) - julianday(s.created_at) <= 7',
            (token, datetime.utcnow().isoformat() + 'Z')
        ).fetchone()
    return dict(row) if row else None


def revoke_token(token):
    if not token:
        return
    with get_conn() as conn:
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))


def is_admin(wechat_name):
    user = get_user_by_name(wechat_name)
    return bool(user and user.get('is_admin'))


def create_task(payload):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (upload_id, user_name, task_name, original_filename, safe_filename,
                               upload_url, upload_size, output_dir, min_duration, status,
                               output_count, created_at, wechat_name, is_private)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload['upload_id'],
                payload.get('user_name'),
                payload.get('task_name'),
                payload.get('original_filename'),
                payload.get('safe_filename'),
                payload.get('upload_url'),
                payload.get('upload_size'),
                payload.get('output_dir'),
                payload.get('min_duration'),
                payload.get('status', 'pending'),
                payload.get('output_count', 0),
                datetime.utcnow().isoformat() + 'Z',
                payload.get('wechat_name'),
                1 if payload.get('is_private') else 0,
            ),
        )
        return cur.lastrowid


def get_task(upload_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM tasks WHERE upload_id = ?',
            (upload_id,),
        ).fetchone()
    return dict(row) if row else None


def can_view_task(task, current_user_name):
    if not task:
        return False
    if is_admin(current_user_name):
        return True
    owner = task.get('wechat_name')
    if owner == current_user_name:
        return True
    if task.get('is_deleted'):
        return False
    if task.get('is_private'):
        return False
    return True


def delete_task(upload_id):
    with get_conn() as conn:
        conn.execute('DELETE FROM tasks WHERE upload_id = ?', (upload_id,))


def soft_delete_task(upload_id):
    now = datetime.utcnow().isoformat() + 'Z'
    with get_conn() as conn:
        conn.execute(
            'UPDATE tasks SET is_deleted=1, deleted_at=? WHERE upload_id=?',
            (now, upload_id),
        )


def restore_task(upload_id):
    with get_conn() as conn:
        conn.execute(
            'UPDATE tasks SET is_deleted=0, deleted_at=NULL WHERE upload_id=?',
            (upload_id,),
        )


def update_task_completed(upload_id, status, output_count, completed_at=None, result_data=None, error=None):
    if completed_at is None:
        completed_at = datetime.utcnow().isoformat() + 'Z'
    with get_conn() as conn:
        if result_data is not None:
            import json
            conn.execute(
                'UPDATE tasks SET status=?, output_count=?, completed_at=?, result_data=?, error=? WHERE upload_id=?',
                (status, output_count, completed_at, json.dumps(result_data, ensure_ascii=False), error, upload_id),
            )
        else:
            conn.execute(
                'UPDATE tasks SET status=?, output_count=?, completed_at=?, error=? WHERE upload_id=?',
                (status, output_count, completed_at, error, upload_id),
            )


def update_task_progress(upload_id, progress, message='', status=None, total_segments=None):
    with get_conn() as conn:
        updates = ['progress=?', 'progress_message=?']
        params = [float(progress), message]
        if status is not None:
            updates.append('status=?')
            params.append(status)
        if status == 'processing':
            updates.append('started_at=COALESCE(started_at, ?)')
            params.append(datetime.utcnow().isoformat() + 'Z')
        if total_segments is not None:
            updates.append('total_segments=?')
            params.append(int(total_segments))
        params.append(upload_id)
        conn.execute(
            f'UPDATE tasks SET {", ".join(updates)} WHERE upload_id=?',
            params,
        )


def update_task_started(upload_id, task_name=None, user_name=None):
    started_at = datetime.utcnow().isoformat() + 'Z'
    with get_conn() as conn:
        updates = ['status=?', 'started_at=?', 'progress=?', 'progress_message=?']
        params = ['processing', started_at, 0.01, '正在准备处理视频…']
        if task_name is not None:
            updates.append('task_name=?')
            params.append(task_name)
        if user_name is not None:
            updates.append('user_name=?')
            params.append(user_name)
        params.append(upload_id)
        conn.execute(
            f'UPDATE tasks SET {", ".join(updates)} WHERE upload_id=?',
            params,
        )


def list_tasks(user_name=None, task_name=None, days=None, wechat_name=None, include_deleted=False, show_all=False, current_user=None):
    sql = 'SELECT * FROM tasks'
    where = []
    params = []

    is_admin_user = is_admin(current_user) if current_user else False

    if show_all and is_admin_user:
        pass
    else:
        if not include_deleted:
            where.append('is_deleted = 0')
        if current_user:
            where.append('(wechat_name = ? OR is_private = 0)')
            params.append(current_user)
        else:
            where.append('is_private = 0')

    if user_name:
        where.append('user_name = ?')
        params.append(user_name)
    if task_name:
        where.append('(task_name = ? OR user_name = ? OR wechat_name = ?)')
        params.extend([task_name, task_name, task_name])
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=int(days))).isoformat() + 'Z'
        where.append('created_at >= ?')
        params.append(cutoff)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY created_at DESC LIMIT 500'
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_task_names(include_deleted=False, current_user=None):
    is_admin_user = is_admin(current_user) if current_user else False
    with get_conn() as conn:
        sql = (
            "SELECT DISTINCT COALESCE(NULLIF(task_name, ''), NULLIF(user_name, ''), NULLIF(wechat_name, '')) AS name "
            "FROM tasks WHERE COALESCE(NULLIF(task_name, ''), NULLIF(user_name, ''), NULLIF(wechat_name, '')) IS NOT NULL "
        )
        params = []
        if not is_admin_user:
            if not include_deleted:
                sql += "AND is_deleted = 0 "
            if current_user:
                sql += "AND (wechat_name = ? OR is_private = 0) "
                params.append(current_user)
            else:
                sql += "AND is_private = 0 "
        sql += "ORDER BY name ASC"
        rows = conn.execute(sql, params).fetchall()
    return [r['name'] for r in rows]


def add_comment(wechat_name, rating, content):
    with get_conn() as conn:
        cur = conn.execute(
            'INSERT INTO comments (wechat_name, rating, content, created_at) VALUES (?, ?, ?, ?)',
            (wechat_name, int(rating or 0), content, datetime.utcnow().isoformat() + 'Z'),
        )
        row = conn.execute('SELECT * FROM comments WHERE id = ?', (cur.lastrowid,)).fetchone()
    return dict(row) if row else None


def list_comments(wechat_name=None, include_deleted=False):
    sql = 'SELECT * FROM comments'
    params = []
    where = []
    if not include_deleted:
        where.append('(is_deleted IS NULL OR is_deleted = 0)')
    if wechat_name:
        where.append('wechat_name = ?')
        params.append(wechat_name)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY created_at DESC LIMIT 500'
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def soft_delete_comment(comment_id):
    now = datetime.utcnow().isoformat() + 'Z'
    with get_conn() as conn:
        conn.execute(
            'UPDATE comments SET is_deleted=1, deleted_at=? WHERE id=?',
            (now, comment_id),
        )


def restore_comment(comment_id):
    with get_conn() as conn:
        conn.execute(
            'UPDATE comments SET is_deleted=0, deleted_at=NULL WHERE id=?',
            (comment_id,),
        )


def get_comment(comment_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM comments WHERE id = ?', (comment_id,)).fetchone()
    return dict(row) if row else None


def reset_user_password(wechat_name, new_password):
    if not wechat_name or not new_password:
        return False
    with get_conn() as conn:
        row = conn.execute('SELECT id FROM users WHERE wechat_name = ?', (wechat_name,)).fetchone()
        if not row:
            return False
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE wechat_name = ?',
            (generate_password_hash(new_password), wechat_name),
        )
    return True


def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT wechat_name, is_admin, created_at FROM users ORDER BY created_at DESC LIMIT 500'
        ).fetchall()
    return [dict(r) for r in rows]


def set_user_admin(wechat_name, is_admin):
    with get_conn() as conn:
        conn.execute(
            'UPDATE users SET is_admin = ? WHERE wechat_name = ?',
            (1 if is_admin else 0, wechat_name),
        )


def expire_old_tasks(days=7):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + 'Z'
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT upload_id, safe_filename, output_dir FROM tasks WHERE created_at < ? AND status <> "expired"',
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_task_expired(upload_id):
    with get_conn() as conn:
        conn.execute(
            'UPDATE tasks SET status="expired" WHERE upload_id=?',
            (upload_id,),
        )
