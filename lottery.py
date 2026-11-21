from flask import render_template, request, jsonify
import secrets

# Units are tenths of a percent, per independent ordinary draw.
PRIZES = [('医用绷带',10,'bandage.jpg'),('茉莉绝弦蛋白威化饼干',9,'wafer.jpg'),('弹力带',8,'band.jpg'),('14天Keep会员',8,'keep.jpg'),('2025穗港交流文化衫',7,'shirt.jpg'),('麦当劳三加二随心配',1,'meal.jpg'),('Keep瑜伽垫',3,'mat.jpg')]

def register(app, *, db, current, login_required, now, settle):
    def prizes(c):
        rows = {r['name']:dict(r) for r in c.execute('SELECT id,name,stock FROM rewards WHERE deleted=0')}
        return [dict(rows[name], weight=weight, image=image) for name,weight,image in PRIZES if name in rows]

    @app.get('/lottery')
    @login_required
    def lottery_page():
        settle(); uid=current()['id']
        with db() as c:
            items=prizes(c)
            count=c.execute('SELECT count(*) FROM lottery_draws WHERE user_id=?',(uid,)).fetchone()[0]
            points=c.execute('SELECT coalesce(sum(amount),0) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0]
            preference=c.execute('SELECT wish_reward_id FROM lottery_settings WHERE user_id=?',(uid,)).fetchone()
            history=c.execute('SELECT result,created FROM lottery_draws WHERE user_id=? ORDER BY id DESC LIMIT 10',(uid,)).fetchall()
        return render_template('lottery.html',items=items,count=count,progress=count%50,points=points,history=history,wish_id=preference['wish_reward_id'] if preference else None)

    @app.post('/lottery/wish')
    @login_required
    def lottery_wish():
        uid=current()['id']; value=request.form.get('wish','')
        if not value.isdigit(): return jsonify(error='请选择心仪奖品。'),400
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not any(x['id']==int(value) and x['stock']>0 for x in prizes(c)):
                return jsonify(error='奖品已售罄，请选择其他奖品。'),400
            c.execute('INSERT INTO lottery_settings(user_id,wish_reward_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET wish_reward_id=excluded.wish_reward_id',(uid,int(value)))
        return jsonify(ok=True)

    @app.post('/lottery/draw')
    @login_required
    def lottery_draw():
        uid=current()['id']; token=request.form.get('token',''); chosen=request.form.get('wish','')
        if not token or len(token)>100 or not chosen.isdigit(): return jsonify(error='请选择心仪奖品。'),400
        settle()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT user_id,result,reward_id FROM lottery_draws WHERE token=?',(token,)).fetchone()
            if old:
                if old['user_id']!=uid: return jsonify(error='请求无效。'),400
                balance=c.execute('SELECT coalesce(sum(amount),0) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0]
                count=c.execute('SELECT count(*) FROM lottery_draws WHERE user_id=?',(uid,)).fetchone()[0]
                return jsonify(result=old['result'],points=balance,progress=count%50,duplicate=True)
            balance=c.execute('SELECT coalesce(sum(amount),0) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0]
            items=prizes(c); available=[x for x in items if x['stock']>0]; wish=next((x for x in available if x['id']==int(chosen)),None)
            count=c.execute('SELECT count(*) FROM lottery_draws WHERE user_id=?',(uid,)).fetchone()[0]
            guaranteed=(count+1)%50==0
            if balance<1: return jsonify(error='积分不足，开箱需要 1 积分。'),400
            if not wish: return jsonify(error='心仪奖品已售罄，请重新选择。'),400
            if guaranteed and len(available)<2: return jsonify(error='可选奖品不足两种，暂无法按保底规则开箱，请联系管理员补货。'),400
            c.execute('INSERT INTO lottery_settings(user_id,wish_reward_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET wish_reward_id=excluded.wish_reward_id',(uid,wish['id']))
            picked=None; bonus=0
            if guaranteed:
                if secrets.randbelow(2)==0: picked=wish
                else:
                    others=[x for x in available if x['id']!=wish['id']]; draw=secrets.randbelow(sum(x['weight'] for x in others))
                    for x in others:
                        if draw<x['weight']: picked=x; break
                        draw-=x['weight']
            else:
                draw=secrets.randbelow(1000)
                # Sold-out rewards retain their original probability as no prize.
                for name,weight,_ in PRIZES:
                    if draw<weight:
                        picked=next((x for x in available if x['name']==name),None); break
                    draw-=weight
                else:
                    if draw<200: bonus=.5
                    elif draw<300: bonus=1
            result=picked['name'] if picked else (str(bonus).removesuffix('.0')+'积分奖励' if bonus else '谢谢参与')
            c.execute("INSERT INTO ledger(user_id,amount,note,created,category) VALUES(?,?,?,?,?)",(uid,-1,'开箱消耗',now(),'redemption'))
            if bonus: c.execute("INSERT INTO ledger(user_id,amount,note,created,category) VALUES(?,?,?,?,?)",(uid,bonus,'开箱积分奖励',now(),'redemption'))
            if picked:
                c.execute('UPDATE rewards SET stock=stock-1 WHERE id=?',(picked['id'],))
                c.execute('INSERT INTO redemptions(user_id,reward_id,cost,created) VALUES(?,?,0,?)',(uid,picked['id'],now()))
            c.execute('INSERT INTO lottery_draws(user_id,token,result,reward_id,created) VALUES(?,?,?,?,?)',(uid,token,result,picked['id'] if picked else None,now()))
            return jsonify(result=result,points=balance-1+bonus,progress=(count+1)%50,guaranteed=guaranteed)
