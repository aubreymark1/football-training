"""Conservative search planning and source filtering for the team assistant."""
import re
from urllib.parse import urlsplit, parse_qs

FOOTBALL=re.compile(r'足球|足坛|足协|世界杯|欧冠|英超|西甲|中超|亚冠|法甲|德甲|意甲|球员|门将|前锋|后卫|中场|射门|传球|控球|盘带|越位|定位球|阵型|战术|逼抢|角球|梅西|C罗|皇马|巴萨|曼城|曼联|拜仁|利物浦|阿森纳|国足|女足|football|soccer|premier league|champions league',re.I)
EXCLUDE=re.compile(r'人工智能|机器学习|大模型|训练模型|模型训练|python|编程|代码|股票|基金|期货|汇率|电子游戏|游戏攻略',re.I)
NEWS=re.compile(r'新闻|最新|今天|今日|昨天|昨晚|近期|近况|赛程|赛果|比分|战况|转会|伤停|排名|积分榜|什么时候比赛|news|latest|transfer|fixture|score',re.I)
TRAINING=re.compile(r'训练|热身|拉伸|体能|力量|耐力|心肺|跑步|冲刺|加速|爆发力|灵敏|敏捷|有氧|无氧|射门|传球|接球|控球|盘带|带球|头球|防守|进攻|跑位|战术|阵型|逼抢|体测|training|warm.?up|fitness|tactics|drill',re.I)
ADVICE=re.compile(r'怎么|如何|怎样|建议|计划|方案|安排|提高|提升|改善|练习|视频|教学|教程|动作|示范|训练方法|练什么|战术|阵型|training plan|how to|drill|tutorial|video',re.I)
VIDEO=re.compile(r'视频|教学|教程|怎么练|如何练|怎样练|练习|训练|热身|拉伸|体能|力量|耐力|心肺|跑步|冲刺|加速|爆发力|灵敏|敏捷|有氧|无氧|射门|传球|接球|控球|盘带|带球|头球|防守|进攻|跑位|战术|阵型|逼抢|training|drill|tutorial|video',re.I)
TEAM_TERMS=('世界杯','欧冠','英超','西甲','中超','亚冠','法甲','德甲','意甲','女足','国足','梅西','C罗','皇马','巴萨','曼城','曼联','拜仁','利物浦','阿森纳')
TRAIN_TERMS=('热身','拉伸','体能','力量','耐力','心肺','跑步','冲刺','加速','爆发力','灵敏','敏捷','有氧','无氧','射门','传球','接球','控球','盘带','带球','头球','防守','进攻','跑位','战术','阵型','逼抢','体测')
NEWS_SITES=('fifa.com','uefa.com','the-afc.com','theifab.com','premierleague.com','dongqiudi.com','zhibo8.com')
TRAINING_SITES=('fifa.com','uefa.com','theifab.com','englandfootball.com','ussoccer.com','thecoachesvoice.com')

def plan(message):
 if EXCLUDE.search(message):return []
 football=bool(FOOTBALL.search(message));training=bool(TRAINING.search(message));news=bool(NEWS.search(message))
 plans=[]
 if news and football:
  terms=[x for x in TEAM_TERMS if x.lower() in message.lower()]
  q='足球 新闻 最新 '+' '.join(terms[:3])
  plans.append({'kind':'news','query':q.strip()})
 elif training and ADVICE.search(message):
  terms=[x for x in TRAIN_TERMS if x in message]
  topic=' '.join(terms[:3]) or '训练'
  # Query contains only selected topic words, never the player's personal details.
  plans.append({'kind':'training','query':'足球 '+topic+' 战术 训练'})
  if VIDEO.search(message):plans.append({'kind':'video','query':'足球 '+topic+' 训练 教学 视频'})
 return plans

def is_host(host,domain):return host==domain or host.endswith('.'+domain)
def filter_results(items,kind,limit=4):
 result=[];seen=set()
 for item in items:
  try:
   url=str(item.get('url',''))[:2048];p=urlsplit(url);host=(p.hostname or '').lower().rstrip('.')
   if p.scheme not in ('http','https') or not host or p.username or p.password:continue
   if kind=='video':
    valid=(is_host(host,'bilibili.com') and bool(re.match(r'^/video/(?:BV[a-zA-Z0-9]+|av[0-9]+)',p.path,re.I))) or (is_host(host,'youtube.com') and p.path=='/watch' and bool(parse_qs(p.query).get('v'))) or (host=='youtu.be' and len(p.path.strip('/'))>3)
    if not valid:continue
   else:
    sites=NEWS_SITES if kind=='news' else TRAINING_SITES
    if not any(is_host(host,site) for site in sites):continue
   if p.scheme=='http':
    # Approved sources are rewritten to HTTPS so chat links do not open plaintext pages.
    url='https://'+url[len('http://'):]
   text=(str(item.get('title',''))+' '+str(item.get('summary') or item.get('snippet') or ''))
   if kind=='video' and (not re.search(r'足球|球员|球场|射门|传球|带球|控球|盘带|球技|足球队|football|soccer',text,re.I) or re.search(r'篮球|羽毛球|乒乓|网球|排球|basketball|tennis',text,re.I)):continue
   if kind!='video' and not re.search(r'足球|球员|球场|射门|传球|守门|比赛|战术|football|soccer|fifa|uefa|coachesvoice|englandfootball',text+' '+url,re.I):continue
   if url in seen:continue
   seen.add(url);result.append({'title':str(item.get('title','来源'))[:200],'url':url,'summary':str(item.get('summary') or item.get('snippet') or '')[:900],'kind':kind})
   if len(result)>=limit:break
  except (ValueError,TypeError):continue
 return result
