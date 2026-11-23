"""Match leave and attendance, separate from team training leave."""
import datetime
from zoneinfo import ZoneInfo
from flask import abort, flash, redirect, render_template, request, url_for
from training_leave import leave_deadline, submitted_on_time

TZ=ZoneInfo('Asia/Shanghai')


def init_schema(c, timestamp):
    c.execute('''CREATE TABLE IF NOT EXISTS match_leave_requests (
        match_id INTEGER NOT NULL REFERENCES matches(id), user_id INTEGER NOT NULL REFERENCES users(id),
        reason TEXT NOT NULL, submitted_at TEXT NOT NULL, deadline_at_submission TEXT NOT NULL,
        timely INTEGER NOT NULL CHECK(timely IN (0,1)), status TEXT NOT NULL CHECK(status IN ('active','cancelled')),
        PRIMARY KEY(match_id,user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_attendance (
        match_id INTEGER NOT NULL REFERENCES matches(id), user_id INTEGER NOT NULL REFERENCES users(id),
        attendance TEXT NOT NULL CHECK(attendance IN ('attended','absent')),
        recorded_by INTEGER NOT NULL REFERENCES users(id), recorded_at TEXT NOT NULL,
        PRIMARY KEY(match_id,user_id))''')
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('match_leave_enabled_at',?)",(timestamp,))


def match_start(game):
    return datetime.datetime.combine(datetime.date.fromisoformat(game['date']),
        datetime.time.fromisoformat(game['time'])).replace(tzinfo=TZ)


def enabled_at(c):
    return datetime.datetime.fromisoformat(c.execute("SELECT value FROM app_settings WHERE key='match_leave_enabled_at'").fetchone()['value'])


def counts(c, uid):
    """有效请假次数，账号页和请假页共用。"""
    training=c.execute('''SELECT count(*) FROM training_leave_requests l JOIN training_sessions s ON s.id=l.session_id
        WHERE l.user_id=? AND l.status='active' AND s.status='open' ''',(uid,)).fetchone()[0]
    match=c.execute('''SELECT count(*) FROM match_leave_requests l JOIN matches m ON m.id=l.match_id
        WHERE l.user_id=? AND l.status='active' AND m.status!='cancelled' ''',(uid,)).fetchone()[0]
    return dict(training=training, match=match)


def account_data(c, uid, stamp):
    instant=datetime.datetime.fromisoformat(stamp)
    summary=counts(c,uid)
    training_count, match_count = summary['training'], summary['match']
    training=c.execute('''SELECT s.id,s.title,s.starts_at,s.location,l.status leave_status,l.reason,l.timely
        FROM training_sessions s LEFT JOIN training_leave_requests l ON l.session_id=s.id AND l.user_id=?
        WHERE s.status='open' ORDER BY CASE WHEN s.starts_at>=? THEN 0 ELSE 1 END,
        CASE WHEN s.starts_at>=? THEN s.starts_at END ASC, CASE WHEN s.starts_at<? THEN s.starts_at END DESC,s.id''',(uid,stamp,stamp,stamp)).fetchall()
    candidates=c.execute('''SELECT m.*,l.status leave_status,l.reason,l.timely FROM matches m
        LEFT JOIN match_leave_requests l ON l.match_id=m.id AND l.user_id=?
        WHERE m.status IN ('scheduled','finished') ORDER BY m.date,m.time,m.id''',(uid,)).fetchall()
    activated=enabled_at(c)
    games=[g for g in candidates if match_start(g)>=activated]
    upcoming=sorted((g for g in games if g['status']=='scheduled' and match_start(g)>=instant),key=match_start)
    past=sorted((g for g in games if not (g['status']=='scheduled' and match_start(g)>=instant)),key=match_start,reverse=True)
    games=upcoming+past
    training_history=c.execute('''SELECT s.title,s.starts_at,l.status,l.reason,l.timely,l.submitted_at,s.status event_status,a.attendance
        FROM training_leave_requests l JOIN training_sessions s ON s.id=l.session_id
        LEFT JOIN training_attendance a ON a.session_id=l.session_id AND a.user_id=l.user_id
        WHERE l.user_id=? ORDER BY s.starts_at DESC,l.session_id DESC LIMIT 50''',(uid,)).fetchall()
    match_history=c.execute('''SELECT m.home,m.away,m.date,m.time,l.status,l.reason,l.timely,l.submitted_at,m.status event_status,a.attendance
        FROM match_leave_requests l JOIN matches m ON m.id=l.match_id
        LEFT JOIN match_attendance a ON a.match_id=l.match_id AND a.user_id=l.user_id
        WHERE l.user_id=? ORDER BY m.date DESC,m.time DESC,m.id DESC LIMIT 50''',(uid,)).fetchall()
    return dict(training_count=training_count,match_count=match_count,training=training,matches=games,now=stamp,
                training_history=training_history,match_history=match_history)


def register(app, *, db, current, login_required, now):
    def manager():
        u=current();return u['role']=='admin' or bool(u['is_captain'])

    def get_game(c,mid):
        game=c.execute('SELECT * FROM matches WHERE id=?',(mid,)).fetchone()
        if game is None:abort(404)
        return game

    def back_to(mid):
        return redirect(url_for('leave',_anchor='match-%d'%mid))

    @app.get('/leave')
    @login_required
    def leave():
        with db() as c: state=account_data(c,current()['id'],now())
        return render_template('leave.html',leave=state)

    @app.post('/account/match-leave/<int:match_id>')
    @login_required
    def account_match_leave(match_id):
        uid=current()['id'];reason=request.form.get('reason','').strip();stamp=datetime.datetime.fromisoformat(now())
        if not reason or len(reason)>500:abort(400)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');game=get_game(c,match_id);start=match_start(game)
            if game['status']=='cancelled' or start<enabled_at(c):abort(400)
            previous=c.execute('SELECT * FROM match_leave_requests WHERE match_id=? AND user_id=?',(match_id,uid)).fetchone()
            if previous and previous['status']=='active':
                c.execute('UPDATE match_leave_requests SET reason=? WHERE match_id=? AND user_id=?',(reason,match_id,uid))
            else:
                deadline=leave_deadline(start)
                c.execute('''INSERT INTO match_leave_requests(match_id,user_id,reason,submitted_at,deadline_at_submission,timely,status)
                    VALUES(?,?,?,?,?,?,'active') ON CONFLICT(match_id,user_id) DO UPDATE SET reason=excluded.reason,
                    submitted_at=excluded.submitted_at,deadline_at_submission=excluded.deadline_at_submission,timely=excluded.timely,status='active' ''',
                    (match_id,uid,reason,stamp.isoformat(timespec='seconds'),deadline.isoformat(timespec='seconds'),int(submitted_on_time(start,stamp))))
        flash('比赛请假已保存。');return back_to(match_id)

    @app.post('/account/match-leave/<int:match_id>/cancel')
    @login_required
    def account_match_leave_cancel(match_id):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');game=get_game(c,match_id)
            if game['status']!='scheduled' or datetime.datetime.fromisoformat(now())>=match_start(game):abort(400)
            c.execute("UPDATE match_leave_requests SET status='cancelled' WHERE match_id=? AND user_id=? AND status='active'",(match_id,current()['id']))
        flash('已取消比赛请假。');return back_to(match_id)

    @app.get('/matches/<int:match_id>/attendance')
    @login_required
    def match_attendance_view(match_id):
        if not manager():abort(403)
        with db() as c:
            game=get_game(c,match_id)
            roster=c.execute('''SELECT u.id,u.name,u.real_name,l.reason,l.timely,l.status leave_status,a.attendance
                FROM users u LEFT JOIN match_leave_requests l ON l.user_id=u.id AND l.match_id=?
                LEFT JOIN match_attendance a ON a.user_id=u.id AND a.match_id=?
                WHERE u.active=1 AND u.deleted=0 ORDER BY u.name''',(match_id,match_id)).fetchall()
            eligible=match_start(game)>=enabled_at(c)
            can_record=eligible and game['status']=='finished' and datetime.datetime.fromisoformat(now())>=match_start(game)
        return render_template('match_attendance.html',game=game,roster=roster,eligible=eligible,can_record=can_record)

    @app.post('/matches/<int:match_id>/attendance/<int:user_id>')
    @login_required
    def match_attendance_record(match_id,user_id):
        if not manager():abort(403)
        value=request.form.get('attendance','')
        if value not in ('attended','absent','clear'):abort(400)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');game=get_game(c,match_id)
            if game['status']!='finished' or match_start(game)<enabled_at(c) or datetime.datetime.fromisoformat(now())<match_start(game):abort(400)
            if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1 AND deleted=0',(user_id,)).fetchone():abort(404)
            if value=='clear':c.execute('DELETE FROM match_attendance WHERE match_id=? AND user_id=?',(match_id,user_id))
            else:c.execute('''INSERT INTO match_attendance(match_id,user_id,attendance,recorded_by,recorded_at) VALUES(?,?,?,?,?)
                ON CONFLICT(match_id,user_id) DO UPDATE SET attendance=excluded.attendance,recorded_by=excluded.recorded_by,recorded_at=excluded.recorded_at''',
                (match_id,user_id,value,current()['id'],now()))
        return redirect(url_for('match_attendance_view',match_id=match_id))
