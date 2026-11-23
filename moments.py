"""Team-only activity feed, attached to newly submitted training records."""
import io

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from PIL import Image


def init_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS moment_posts (
        record_id INTEGER PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
        hidden INTEGER NOT NULL DEFAULT 0 CHECK(hidden IN (0,1)))''')
    connection.execute('''CREATE TABLE IF NOT EXISTS moment_likes (
        record_id INTEGER NOT NULL REFERENCES moment_posts(record_id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id), created TEXT NOT NULL,
        PRIMARY KEY(record_id,user_id))''')
    connection.execute('''CREATE TABLE IF NOT EXISTS moment_comments (
        id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL REFERENCES moment_posts(record_id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id), content TEXT NOT NULL, created TEXT NOT NULL)''')
    connection.execute('CREATE INDEX IF NOT EXISTS moment_comments_record ON moment_comments(record_id,id)')


def record_post(connection, record_id):
    connection.execute('INSERT INTO moment_posts(record_id) VALUES(?)', (record_id,))


def register(app, *, db, current, login_required, now, data):
    def visible_post(connection, rid):
        return connection.execute('''SELECT r.user_id, r.image FROM moment_posts p
            JOIN records r ON r.id=p.record_id JOIN users u ON u.id=r.user_id
            WHERE p.record_id=? AND p.hidden=0 AND u.active=1 AND u.deleted=0''', (rid,)).fetchone()

    def wants_json():
        # 页面里的点赞、评论先用 fetch 局部更新；失败时前端会退回整页提交。
        return request.headers.get('X-Requested-With', '').lower() == 'fetch'

    def interactions(c, rid):
        like_names=[row['author'] for row in c.execute('''SELECT u.name AS author FROM moment_likes l
            JOIN users u ON u.id=l.user_id WHERE l.record_id=? AND u.active=1 AND u.deleted=0 ORDER BY l.created''',(rid,))]
        comments=c.execute('''SELECT mc.id,mc.record_id,mc.user_id,mc.content,u.name AS author
            FROM moment_comments mc JOIN users u ON u.id=mc.user_id
            WHERE mc.record_id=? AND u.deleted=0 AND u.active=1 ORDER BY mc.id''',(rid,)).fetchall()
        return render_template('_moment_interactions.html',post={'id':rid},like_names=like_names,
            comments=comments,before=request.form.get('before',''))

    def return_to(rid=None):
        before=request.form.get('before', '')
        options={}
        if len(before)<20 and before.isascii() and before.isdigit() and 0<int(before)<2**63:
            options['before']=before
        if rid is not None:
            options['_anchor']='moment-'+str(rid)
        return redirect(url_for('moments_feed', **options))

    @app.get('/moments')
    @login_required
    def moments_feed():
        before=request.args.get('before', '')
        if before and (len(before)>19 or not before.isascii() or not before.isdigit() or not 0<int(before)<2**63):
            abort(400)
        user=current()
        with db() as c:
            posts=c.execute('''SELECT r.id,r.user_id,r.sport,r.minutes,r.note,r.created,
                COALESCE(t.title,'自主训练') AS title,
                u.name AS author,
                EXISTS(SELECT 1 FROM moment_likes l WHERE l.record_id=r.id AND l.user_id=?) AS liked
                FROM moment_posts p JOIN records r ON r.id=p.record_id
                JOIN users u ON u.id=r.user_id LEFT JOIN tasks t ON t.id=r.task_id
                WHERE p.hidden=0 AND u.active=1 AND u.deleted=0 AND (?=0 OR r.id<?)
                ORDER BY r.id DESC LIMIT 21''', (user['id'], int(before or 0), int(before or 0))).fetchall()
            more=len(posts)>20; posts=posts[:20]
            comments={row['id']:[] for row in posts}
            like_names={row['id']:[] for row in posts}
            if posts:
                marks=','.join('?' for _ in posts)
                for row in c.execute('''SELECT ml.record_id,u.name AS author
                    FROM moment_likes ml JOIN users u ON u.id=ml.user_id
                    WHERE u.deleted=0 AND u.active=1 AND ml.record_id IN ('''+marks+''') ORDER BY ml.created''', tuple(comments)):
                    like_names[row['record_id']].append(row['author'])
                for row in c.execute('''SELECT mc.id,mc.record_id,mc.user_id,mc.content,mc.created,
                    u.name AS author
                    FROM moment_comments mc JOIN users u ON u.id=mc.user_id
                    WHERE u.deleted=0 AND u.active=1 AND mc.record_id IN ('''+marks+''') ORDER BY mc.id''', tuple(comments)):
                    comments[row['record_id']].append(row)
        return render_template('moments.html', posts=posts, comments=comments, like_names=like_names, before=before,
                               next_before=posts[-1]['id'] if more else None)

    @app.get('/moments/<int:rid>/image')
    @login_required
    def moments_image(rid):
        with db() as c:
            post=visible_post(c,rid)
        if not post:
            abort(404)
        path=data()/'uploads'/post['image']
        if not path.is_file():
            abort(404)
        if request.args.get('thumb'):
            try:
                with Image.open(path) as im:
                    im.draft('RGB',(640,640));im.thumbnail((640,640))
                    small=io.BytesIO();im.convert('RGB').save(small,'JPEG',quality=72);small.seek(0)
            except (OSError, ValueError):
                abort(404)
            response=send_file(small,mimetype='image/jpeg',max_age=0)
        else:
            response=send_file(path,mimetype='image/jpeg',max_age=0)
        response.headers['Cache-Control']='private, no-store'
        return response

    @app.post('/moments/<int:rid>/like')
    @login_required
    def moments_like(rid):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not visible_post(c,rid): abort(404)
            removed=c.execute('DELETE FROM moment_likes WHERE record_id=? AND user_id=?',(rid,current()['id'])).rowcount
            if not removed:
                c.execute('INSERT INTO moment_likes(record_id,user_id,created) VALUES(?,?,?)',(rid,current()['id'],now()))
            if wants_json():
                liked=not removed
                return jsonify(ok=True,liked=liked,label='♥ 取消' if liked else '♡ 赞',html=interactions(c,rid))
        return return_to(rid)

    @app.post('/moments/<int:rid>/comment')
    @login_required
    def moments_comment(rid):
        content=request.form.get('content','').strip()
        if not content or len(content)>300:
            flash('评论请填写 1–300 字。','error')
            return return_to(rid)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not visible_post(c,rid): abort(404)
            c.execute('INSERT INTO moment_comments(record_id,user_id,content,created) VALUES(?,?,?,?)',(rid,current()['id'],content,now()))
            if wants_json(): return jsonify(ok=True,html=interactions(c,rid))
        return return_to(rid)

    @app.post('/moments/<int:rid>/comment/<int:comment_id>/delete')
    @login_required
    def moments_comment_delete(rid,comment_id):
        user=current()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not visible_post(c,rid): abort(404)
            comment=c.execute('SELECT user_id FROM moment_comments WHERE id=? AND record_id=?',(comment_id,rid)).fetchone()
            if not comment: abort(404)
            if comment['user_id']!=user['id'] and user['role']!='admin': abort(403)
            c.execute('DELETE FROM moment_comments WHERE id=?',(comment_id,))
        return return_to(rid)

    @app.post('/moments/<int:rid>/hide')
    @login_required
    def moments_hide(rid):
        user=current()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            post=visible_post(c,rid)
            if not post: abort(404)
            if post['user_id']!=user['id'] and user['role']!='admin': abort(403)
            c.execute('UPDATE moment_posts SET hidden=1 WHERE record_id=?',(rid,))
        flash('已从动态隐藏，训练记录仍然保留。')
        return return_to()
