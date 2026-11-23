"""Team match schedule, ratings and reflections."""
import datetime
import io

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from PIL import Image, UnidentifiedImageError

from league_schedule import FIXTURES
import match_leave


def init_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY, date TEXT NOT NULL, time TEXT NOT NULL, competition TEXT NOT NULL,
        round TEXT NOT NULL DEFAULT '', home TEXT NOT NULL, away TEXT NOT NULL, venue TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','finished','cancelled')),
        home_score INTEGER, away_score INTEGER, report TEXT NOT NULL DEFAULT '', goals TEXT NOT NULL DEFAULT '',
        assists TEXT NOT NULL DEFAULT '', seed_key TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_managers (user_id INTEGER PRIMARY KEY REFERENCES users(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_players (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id),
        user_id INTEGER REFERENCES users(id), name TEXT NOT NULL, lineup TEXT NOT NULL DEFAULT 'substitute',
        UNIQUE(match_id,user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_ratings (player_id INTEGER NOT NULL REFERENCES match_players(id),
        user_id INTEGER NOT NULL REFERENCES users(id), score INTEGER NOT NULL CHECK(score BETWEEN 10 AND 100),
        comment TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL, PRIMARY KEY(player_id,user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_reflections (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id),
        user_id INTEGER NOT NULL REFERENCES users(id), content TEXT NOT NULL, image BLOB, image_type TEXT, created TEXT NOT NULL)''')
    # 记录图片尺寸，模板才能写 width/height，图片加载时不会把页面顶来顶去。
    reflection_columns={row['name'] for row in c.execute('PRAGMA table_info(match_reflections)')}
    if 'image_w' not in reflection_columns: c.execute('ALTER TABLE match_reflections ADD COLUMN image_w INTEGER')
    if 'image_h' not in reflection_columns: c.execute('ALTER TABLE match_reflections ADD COLUMN image_h INTEGER')
    c.execute('''CREATE TABLE IF NOT EXISTS match_reflection_likes (reflection_id INTEGER NOT NULL REFERENCES match_reflections(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id), PRIMARY KEY(reflection_id,user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_reflection_comments (id INTEGER PRIMARY KEY,
        reflection_id INTEGER NOT NULL REFERENCES match_reflections(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id), content TEXT NOT NULL, created TEXT NOT NULL)''')
    # A marker prevents deleted or edited imported fixtures from being recreated.
    seeded=c.execute("SELECT 1 FROM app_settings WHERE key='matches_seeded_v1'").fetchone()
    if not seeded:
        for date,time,round_,home,away in FIXTURES:
            forfeit=date=='2026-11-14' and home=='岭南学院' and away=='中山医光华联队'
            draw=date=='2026-11-22' and home=='岭南学院' and away=='数学学院'
            finished=forfeit or draw
            c.execute('''INSERT INTO matches(date,time,competition,round,home,away,venue,status,home_score,away_score,report,seed_key)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(date,time,'2026–2027 南校联赛',round_,home,away,'西区大球场',
                'finished' if finished else 'scheduled',3 if forfeit else 0 if draw else None,0 if finished else None,
                '对手弃赛，岭南学院 3:0 获胜。' if forfeit else '',date+'|'+home+'|'+away))
        c.execute("INSERT INTO app_settings(key,value) VALUES('matches_seeded_v1','1')")


def upcoming_matches(db, today):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM matches WHERE status='scheduled' AND date>=? ORDER BY date,time,id",(today.isoformat(),))]


def register(app, *, db, current, login_required, now):
    def wants_json():
        # 点赞、评论先走 fetch；失败时前端退回整页提交。
        return request.headers.get('X-Requested-With','').lower()=='fetch'

    def manager(c):
        u=current()
        return u['role']=='admin' or c.execute('SELECT 1 FROM match_managers WHERE user_id=?',(u['id'],)).fetchone() is not None

    def require_manager(c):
        if not manager(c): abort(403)

    def match(c, match_id):
        row=c.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone()
        if not row: abort(404)
        return row

    def back(match_id, anchor=None): return redirect(url_for('matches_detail',match_id=match_id,_anchor=anchor))

    @app.get('/matches')
    @login_required
    def matches_index():
        with db() as c:
            games=c.execute('SELECT * FROM matches ORDER BY date DESC,time DESC,id DESC').fetchall()
            can_manage=manager(c)
        today=now()[:10]
        finished=[game for game in games if game['status']=='finished']
        upcoming=sorted((game for game in games if game['status']=='scheduled' and game['date']>=today),key=lambda game:(game['date'],game['time'],game['id']))
        other=[game for game in games if game['status']=='cancelled' or (game['status']=='scheduled' and game['date']<today)]
        return render_template('matches_index.html',latest=finished[0] if finished else None,history=finished[1:],upcoming=upcoming,other=other,can_manage=can_manage,today=today)

    @app.route('/matches/new',methods=['GET','POST'])
    @app.route('/matches/<int:match_id>/edit',methods=['GET','POST'])
    @login_required
    def matches_edit(match_id=None):
        with db() as c:
            if request.method=='POST': c.execute('BEGIN IMMEDIATE')
            require_manager(c)
            game=match(c,match_id) if match_id is not None else None
            if request.method=='POST':
                fields={k:request.form.get(k,'').strip() for k in ('date','time','competition','round','home','away','venue','status','home_score','away_score','report','goals','assists')}
                try:
                    datetime.date.fromisoformat(fields['date']); datetime.time.fromisoformat(fields['time'])
                    if not all(fields[x] and len(fields[x])<=100 for x in ('competition','home','away')): raise ValueError()
                    if fields['status'] not in ('scheduled','finished','cancelled'): raise ValueError()
                    scores=[int(fields[x]) if fields[x] else None for x in ('home_score','away_score')]
                    if any(x is not None and not 0<=x<=99 for x in scores): raise ValueError()
                    if fields['status']=='finished' and None in scores: raise ValueError()
                    if any(len(fields[x])>5000 for x in ('report','goals','assists')): raise ValueError()
                except ValueError:
                    flash('请检查比赛信息：日期、时间、球队和赛事为必填，已结束比赛需填写比分。','error')
                    return render_template('matches_edit.html',game=fields),400
                values=[fields[x] for x in ('date','time','competition','round','home','away','venue','status')]+scores+[fields[x] for x in ('report','goals','assists')]
                if game:
                    if (fields['date']!=game['date'] or fields['time']!=game['time']) and c.execute("SELECT 1 FROM match_leave_requests WHERE match_id=? AND status='active'",(match_id,)).fetchone():
                        flash('已有队员请假，不能直接修改比赛时间；请取消本场并重新创建。','error'); return back(match_id)
                    c.execute('UPDATE matches SET date=?,time=?,competition=?,round=?,home=?,away=?,venue=?,status=?,home_score=?,away_score=?,report=?,goals=?,assists=? WHERE id=?',values+[match_id])
                else:
                    cur=c.execute('INSERT INTO matches(date,time,competition,round,home,away,venue,status,home_score,away_score,report,goals,assists) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',values); match_id=cur.lastrowid
                flash('比赛信息已保存。'); return back(match_id)
        return render_template('matches_edit.html',game=game)

    @app.get('/matches/<int:match_id>')
    @login_required
    def matches_detail(match_id):
        with db() as c:
            game=match(c,match_id); can_manage=manager(c); uid=current()['id']
            players=c.execute('''SELECT p.*,u.active AS owner_active,u.deleted AS owner_deleted FROM match_players p
                LEFT JOIN users u ON u.id=p.user_id WHERE p.match_id=?
                ORDER BY CASE p.lineup WHEN 'starter' THEN 0 ELSE 1 END,p.id''',(match_id,)).fetchall()
            reflections=c.execute('''SELECT f.*,u.name author,u.active AS author_active,u.deleted AS author_deleted,
                EXISTS(SELECT 1 FROM match_reflection_likes l WHERE l.reflection_id=f.id AND l.user_id=?) liked,
                (SELECT count(*) FROM match_reflection_likes l WHERE l.reflection_id=f.id) likes
                FROM match_reflections f JOIN users u ON u.id=f.user_id WHERE f.match_id=? ORDER BY f.id DESC''',(uid,match_id)).fetchall()
            comments=c.execute('''SELECT x.*,u.name author FROM match_reflection_comments x JOIN users u ON u.id=x.user_id
                JOIN match_reflections f ON f.id=x.reflection_id WHERE f.match_id=? ORDER BY x.id''',(match_id,)).fetchall()
            users=c.execute('SELECT id,name,real_name FROM users WHERE active=1 AND deleted=0 ORDER BY name').fetchall() if can_manage else []
            managers=c.execute('SELECT user_id FROM match_managers').fetchall() if current()['role']=='admin' else []
            own_leave=c.execute("SELECT status FROM match_leave_requests WHERE match_id=? AND user_id=?",(match_id,uid)).fetchone()
            can_leave=game['status']!='cancelled' and match_leave.match_start(game)>=match_leave.enabled_at(c)
        return render_template('matches_detail.html',game=game,players=players,reflections=reflections,comments=comments,
                               can_manage=can_manage,users=users,managers=managers,can_leave=can_leave,
                               own_leave=own_leave['status'] if own_leave else None)

    @app.post('/matches/managers')
    @login_required
    def matches_managers():
        if current()['role']!='admin': abort(403)
        try: uid=int(request.form.get('user_id',''))
        except ValueError: abort(400)
        with db() as c:
            if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1 AND deleted=0',(uid,)).fetchone(): abort(400)
            if request.form.get('action')=='remove': c.execute('DELETE FROM match_managers WHERE user_id=?',(uid,))
            elif request.form.get('action')=='add': c.execute('INSERT OR IGNORE INTO match_managers(user_id) VALUES(?)',(uid,))
            else: abort(400)
        return redirect(url_for('matches_index'))

    @app.post('/matches/<int:match_id>/players')
    @login_required
    def matches_player_add(match_id):
        with db() as c:
            require_manager(c); match(c,match_id)
            value=request.form.get('user_id',''); name=request.form.get('name','').strip(); lineup=request.form.get('lineup')
            if lineup not in ('starter','substitute'): abort(400)
            uid=None
            if value:
                if not value.isdigit(): abort(400)
                user=c.execute('SELECT id,name,real_name FROM users WHERE id=? AND active=1 AND deleted=0',(int(value),)).fetchone()
                if not user: abort(400)
                uid=user['id']; name=user['real_name'] or user['name']
                if c.execute('SELECT 1 FROM match_players WHERE match_id=? AND user_id=?',(match_id,uid)).fetchone():
                    flash('这名队员已在名单中。','error'); return back(match_id)
            if not name or len(name)>100: abort(400)
            c.execute('INSERT INTO match_players(match_id,user_id,name,lineup) VALUES(?,?,?,?)',(match_id,uid,name,lineup))
        return back(match_id)

    @app.post('/matches/<int:match_id>/players/<int:player_id>/manage')
    @login_required
    def matches_player_manage(match_id,player_id):
        with db() as c:
            require_manager(c)
            player=c.execute('SELECT * FROM match_players WHERE id=? AND match_id=?',(player_id,match_id)).fetchone()
            if not player: abort(404)
            action=request.form.get('action')
            if action in ('starter','substitute'):
                c.execute('UPDATE match_players SET lineup=? WHERE id=?',(action,player_id))
            elif action=='remove':
                if c.execute('SELECT 1 FROM match_ratings WHERE player_id=?',(player_id,)).fetchone():
                    flash('该球员有关联的历史记录，暂不能移出名单。','error')
                else: c.execute('DELETE FROM match_players WHERE id=?',(player_id,))
            else: abort(400)
        return back(match_id)

    @app.get('/matches/<int:match_id>/reflections/new')
    @login_required
    def matches_reflection_new(match_id):
        with db() as c:
            game=match(c,match_id)
            if game['status']!='finished': abort(404)
        return render_template('match_reflection_new.html',game=game)

    @app.post('/matches/<int:match_id>/reflections')
    @login_required
    def matches_reflect(match_id):
        content=request.form.get('content','').strip(); upload=request.files.get('image'); raw=None; kind=None; width=height=None
        if not content or len(content)>3000: abort(400)
        if upload and upload.filename:
            raw=upload.stream.read(7*1024*1024+1)
            if len(raw)>7*1024*1024: abort(400)
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    kind={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp','GIF':'image/gif'}.get(im.format)
                    if not kind or im.width*im.height>16000000: raise ValueError()
                    width,height=im.size
                    im.verify()
            except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError): abort(400)
        with db() as c:
            if match(c,match_id)['status']!='finished': abort(400)
            c.execute('INSERT INTO match_reflections(match_id,user_id,content,image,image_type,image_w,image_h,created) VALUES(?,?,?,?,?,?,?,?)',(match_id,current()['id'],content,raw,kind,width,height,now()))
        return back(match_id,'reflections')

    @app.get('/matches/reflections/<int:reflection_id>/image')
    @login_required
    def matches_reflection_image(reflection_id):
        with db() as c: row=c.execute('SELECT image,image_type FROM match_reflections WHERE id=?',(reflection_id,)).fetchone()
        if not row or not row['image']: abort(404)
        if request.args.get('thumb'):
            try:
                with Image.open(io.BytesIO(row['image'])) as im:
                    im.draft('RGB',(640,640)); im.thumbnail((640,640))
                    small=io.BytesIO(); im.convert('RGB').save(small,'JPEG',quality=72); small.seek(0)
            except (OSError,ValueError): abort(404)
            response=send_file(small,mimetype='image/jpeg',max_age=0)
        else: response=send_file(io.BytesIO(row['image']),mimetype=row['image_type'])
        response.headers['Cache-Control']='private, no-store'; response.headers['X-Content-Type-Options']='nosniff'; return response

    @app.post('/matches/<int:match_id>/reflections/<int:reflection_id>/<action>')
    @login_required
    def matches_reflection_action(match_id,reflection_id,action):
        with db() as c:
            row=c.execute('SELECT * FROM match_reflections WHERE id=? AND match_id=?',(reflection_id,match_id)).fetchone()
            if not row: abort(404)
            uid=current()['id']; can_manage=manager(c)
            if action=='like':
                removed=c.execute('DELETE FROM match_reflection_likes WHERE reflection_id=? AND user_id=?',(reflection_id,uid)).rowcount
                if not removed: c.execute('INSERT INTO match_reflection_likes VALUES(?,?)',(reflection_id,uid))
                if wants_json():
                    liked=not removed; likes=c.execute('SELECT count(*) FROM match_reflection_likes WHERE reflection_id=?',(reflection_id,)).fetchone()[0]
                    return jsonify(ok=True,liked=liked,likes=likes,label=('取消赞 · %d' if liked else '点赞 · %d')%likes)
            elif action=='comment':
                content=request.form.get('content','').strip()
                if not content or len(content)>1000: abort(400)
                comment_id=c.execute('INSERT INTO match_reflection_comments(reflection_id,user_id,content,created) VALUES(?,?,?,?)',(reflection_id,uid,content,now())).lastrowid
                if wants_json():
                    comment=c.execute('''SELECT x.*,u.name author FROM match_reflection_comments x
                        JOIN users u ON u.id=x.user_id WHERE x.id=?''',(comment_id,)).fetchone()
                    return jsonify(ok=True,html=render_template('_match_comment.html',comment=comment,game={'id':match_id},can_manage=can_manage))
            elif action=='edit':
                if row['user_id']!=uid: abort(403)
                content=request.form.get('content','').strip()
                if not content or len(content)>3000: abort(400)
                c.execute('UPDATE match_reflections SET content=? WHERE id=?',(content,reflection_id))
            elif action=='delete':
                if row['user_id']!=uid and not manager(c): abort(403)
                c.execute('DELETE FROM match_reflections WHERE id=?',(reflection_id,))
            else: abort(404)
        return back(match_id,'reflections')

    @app.post('/matches/<int:match_id>/comments/<int:comment_id>/delete')
    @login_required
    def matches_comment_delete(match_id,comment_id):
        with db() as c:
            row=c.execute('''SELECT x.user_id FROM match_reflection_comments x JOIN match_reflections f ON f.id=x.reflection_id
                WHERE x.id=? AND f.match_id=?''',(comment_id,match_id)).fetchone()
            if not row: abort(404)
            if row['user_id']!=current()['id'] and not manager(c): abort(403)
            c.execute('DELETE FROM match_reflection_comments WHERE id=?',(comment_id,))
        return back(match_id,'reflections')
