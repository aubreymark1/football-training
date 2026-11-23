"""Rules for leave from an in-person team training session."""
import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, render_template, request, url_for

TZ = ZoneInfo('Asia/Shanghai')


def leave_deadline(starts_at):
    """Return the inclusive 72-hour deadline for an aware training start."""
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError('训练开始时间必须包含时区')
    return starts_at - datetime.timedelta(hours=72)


def submitted_on_time(starts_at, submitted_at):
    if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
        raise ValueError('请假提交时间必须包含时区')
    return submitted_at <= leave_deadline(starts_at)


def init_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS training_sessions (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','cancelled')),
        created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS training_leave_requests (
        session_id INTEGER NOT NULL REFERENCES training_sessions(id), user_id INTEGER NOT NULL REFERENCES users(id),
        reason TEXT NOT NULL, submitted_at TEXT NOT NULL, deadline_at_submission TEXT NOT NULL,
        timely INTEGER NOT NULL CHECK(timely IN (0,1)), status TEXT NOT NULL CHECK(status IN ('active','cancelled')),
        PRIMARY KEY(session_id,user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS training_attendance (
        session_id INTEGER NOT NULL REFERENCES training_sessions(id), user_id INTEGER NOT NULL REFERENCES users(id),
        attendance TEXT NOT NULL CHECK(attendance IN ('attended','absent')),
        recorded_by INTEGER NOT NULL REFERENCES users(id), recorded_at TEXT NOT NULL,
        PRIMARY KEY(session_id,user_id))''')


def register(app, *, db, current, login_required, now):
    def is_manager(user):
        return user['role']=='admin' or bool(user['is_captain'])

    def require_manager():
        if not is_manager(current()): abort(403)

    def get_session(c, session_id):
        row=c.execute('SELECT * FROM training_sessions WHERE id=?',(session_id,)).fetchone()
        if row is None: abort(404)
        return row

    def back(session_id):
        return redirect(url_for('training_session_detail',session_id=session_id))

    @app.get('/training-sessions')
    @login_required
    def training_sessions():
        with db() as c:
            sessions=c.execute('''SELECT s.*,
                (SELECT count(*) FROM users u WHERE u.active=1 AND u.deleted=0) members,
                (SELECT count(*) FROM training_leave_requests l JOIN users u ON u.id=l.user_id
                 WHERE l.session_id=s.id AND l.status='active' AND u.active=1 AND u.deleted=0) leave_count,
                (SELECT status FROM training_leave_requests l WHERE l.session_id=s.id AND l.user_id=?) my_leave
                FROM training_sessions s ORDER BY CASE WHEN s.status='open' AND s.starts_at>=? THEN 0 ELSE 1 END,
                CASE WHEN s.status='open' AND s.starts_at>=? THEN s.starts_at END ASC,
                CASE WHEN s.status!='open' OR s.starts_at<? THEN s.starts_at END DESC,s.id DESC''',
                (current()['id'],now(),now(),now())).fetchall()
        return render_template('training_sessions.html',sessions=sessions,can_manage=is_manager(current()),current_time=now())

    @app.route('/training-sessions/new',methods=['GET','POST'])
    @app.route('/training-sessions/<int:session_id>/edit',methods=['GET','POST'])
    @login_required
    def training_session_edit(session_id=None):
        require_manager()
        with db() as c:
            if request.method=='POST': c.execute('BEGIN IMMEDIATE')
            session=get_session(c,session_id) if session_id is not None else None
            if request.method=='POST':
                title=request.form.get('title','').strip(); location=request.form.get('location','').strip()
                try:
                    if not title or len(title)>100 or len(location)>200: raise ValueError()
                    parsed=datetime.datetime.fromisoformat(request.form.get('starts_at',''))
                    parsed_end=datetime.datetime.fromisoformat(request.form.get('ends_at',''))
                    if parsed.tzinfo is not None or parsed_end.tzinfo is not None: raise ValueError()
                    start=parsed.replace(tzinfo=TZ,second=0,microsecond=0)
                    end=parsed_end.replace(tzinfo=TZ,second=0,microsecond=0)
                    if start<=datetime.datetime.fromisoformat(now()) or end<=start: raise ValueError()
                except ValueError:
                    flash('请填写训练名称、未来的开始时间和晚于开始时间的结束时间。','error')
                    return render_template('training_session_edit.html',session=session),400
                if session:
                    if session['status']!='open' or datetime.datetime.fromisoformat(session['starts_at'])<=datetime.datetime.fromisoformat(now()): abort(400)
                    changed=start.isoformat(timespec='seconds')!=session['starts_at']
                    if changed and c.execute("SELECT 1 FROM training_leave_requests WHERE session_id=? AND status='active'",(session_id,)).fetchone():
                        flash('已有队员请假，不能直接修改训练时间；请取消本场后重新创建。','error');return back(session_id)
                    c.execute('UPDATE training_sessions SET title=?,starts_at=?,ends_at=?,location=? WHERE id=?',(title,start.isoformat(timespec='seconds'),end.isoformat(timespec='seconds'),location,session_id))
                else:
                    session_id=c.execute('INSERT INTO training_sessions(title,starts_at,ends_at,location,created_by,created_at) VALUES(?,?,?,?,?,?)',
                        (title,start.isoformat(timespec='seconds'),end.isoformat(timespec='seconds'),location,current()['id'],now())).lastrowid
                flash('训练安排已保存。');return back(session_id)
        return render_template('training_session_edit.html',session=session)

    @app.get('/training-sessions/<int:session_id>')
    @login_required
    def training_session_detail(session_id):
        uid=current()['id']; can_manage=is_manager(current()); stamp=datetime.datetime.fromisoformat(now())
        with db() as c:
            session=get_session(c,session_id)
            own=c.execute('SELECT * FROM training_leave_requests WHERE session_id=? AND user_id=?',(session_id,uid)).fetchone()
            count=c.execute('SELECT count(*) FROM users WHERE active=1 AND deleted=0').fetchone()[0]
            leave_count=c.execute('''SELECT count(*) FROM training_leave_requests l JOIN users u ON u.id=l.user_id
                WHERE l.session_id=? AND l.status='active' AND u.active=1 AND u.deleted=0''',(session_id,)).fetchone()[0]
            my_attendance=c.execute('SELECT attendance FROM training_attendance WHERE session_id=? AND user_id=?',(session_id,uid)).fetchone()
            roster=c.execute('''SELECT u.id,u.name,u.real_name,l.reason,l.timely,l.status leave_status,l.submitted_at,
                a.attendance FROM users u LEFT JOIN training_leave_requests l ON l.user_id=u.id AND l.session_id=?
                LEFT JOIN training_attendance a ON a.user_id=u.id AND a.session_id=?
                WHERE u.active=1 AND u.deleted=0 ORDER BY u.name''',(session_id,session_id)).fetchall() if can_manage else []
        start=datetime.datetime.fromisoformat(session['starts_at'])
        return render_template('training_session_detail.html',training=session,own=own,can_manage=can_manage,
            roster=roster,deadline=leave_deadline(start),started=stamp>=start,ended=stamp>=datetime.datetime.fromisoformat(session['ends_at']),expected=count-leave_count,leave_count=leave_count,
            my_attendance=my_attendance)

    @app.post('/training-sessions/<int:session_id>/cancel')
    @login_required
    def training_session_cancel(session_id):
        require_manager()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            session=get_session(c,session_id)
            if session['status']!='open': abort(400)
            c.execute("UPDATE training_sessions SET status='cancelled' WHERE id=?",(session_id,))
        flash('本场训练已取消。');return back(session_id)

    @app.post('/training-sessions/<int:session_id>/leave')
    @login_required
    def training_leave_submit(session_id):
        uid=current()['id'];reason=request.form.get('reason','').strip()
        if not reason or len(reason)>500: abort(400)
        stamp=datetime.datetime.fromisoformat(now())
        with db() as c:
            c.execute('BEGIN IMMEDIATE'); session=get_session(c,session_id)
            if session['status']!='open': abort(400)
            previous=c.execute('SELECT * FROM training_leave_requests WHERE session_id=? AND user_id=?',(session_id,uid)).fetchone()
            if previous and previous['status']=='active':
                c.execute('UPDATE training_leave_requests SET reason=? WHERE session_id=? AND user_id=?',(reason,session_id,uid))
            else:
                start=datetime.datetime.fromisoformat(session['starts_at']);deadline=leave_deadline(start)
                c.execute('''INSERT INTO training_leave_requests(session_id,user_id,reason,submitted_at,deadline_at_submission,timely,status)
                    VALUES(?,?,?,?,?,?,'active') ON CONFLICT(session_id,user_id) DO UPDATE SET reason=excluded.reason,
                    submitted_at=excluded.submitted_at,deadline_at_submission=excluded.deadline_at_submission,timely=excluded.timely,status='active' ''',
                    (session_id,uid,reason,stamp.isoformat(timespec='seconds'),deadline.isoformat(timespec='seconds'),int(submitted_on_time(start,stamp))))
        flash('训练请假已保存。');return redirect(url_for('leave',_anchor='training-%d'%session_id))

    @app.post('/training-sessions/<int:session_id>/leave/cancel')
    @login_required
    def training_leave_cancel(session_id):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            session=get_session(c,session_id)
            if session['status']!='open' or datetime.datetime.fromisoformat(now())>=datetime.datetime.fromisoformat(session['starts_at']): abort(400)
            c.execute("UPDATE training_leave_requests SET status='cancelled' WHERE session_id=? AND user_id=? AND status='active'",(session_id,current()['id']))
        flash('已取消训练请假。');return redirect(url_for('leave',_anchor='training-%d'%session_id))

    @app.post('/training-sessions/<int:session_id>/attendance/<int:user_id>')
    @login_required
    def training_attendance_record(session_id,user_id):
        require_manager();value=request.form.get('attendance','')
        if value not in ('attended','absent','clear'): abort(400)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            session=get_session(c,session_id)
            if session['status']!='open' or datetime.datetime.fromisoformat(now())<datetime.datetime.fromisoformat(session['ends_at']): abort(400)
            if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1 AND deleted=0',(user_id,)).fetchone(): abort(404)
            if value=='clear':c.execute('DELETE FROM training_attendance WHERE session_id=? AND user_id=?',(session_id,user_id))
            else:c.execute('''INSERT INTO training_attendance(session_id,user_id,attendance,recorded_by,recorded_at) VALUES(?,?,?,?,?)
                ON CONFLICT(session_id,user_id) DO UPDATE SET attendance=excluded.attendance,recorded_by=excluded.recorded_by,recorded_at=excluded.recorded_at''',
                (session_id,user_id,value,current()['id'],now()))
        return back(session_id)
