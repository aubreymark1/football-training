"""163 SMTP mail delivery. Credentials come from a restricted environment file."""
import os,smtplib,ssl,time
from email.message import EmailMessage

def configured():
 return bool(os.environ.get('TEAM_SMTP_USER') and os.environ.get('TEAM_SMTP_PASSWORD') and os.environ.get('TEAM_SMTP_FROM'))

def send(to,subject,body):
 if not configured():raise RuntimeError('mail not configured')
 message=EmailMessage();message['From']=os.environ['TEAM_SMTP_FROM'];message['To']=to;message['Subject']=subject;message.set_content(body)
 host=os.environ.get('TEAM_SMTP_HOST','smtp.163.com');port=int(os.environ.get('TEAM_SMTP_PORT','465'))
 if host!='smtp.163.com' or port not in (465,994):raise ValueError('SMTP configuration invalid')
 with smtplib.SMTP_SSL(host,port,timeout=15,context=ssl.create_default_context()) as smtp:
  smtp.login(os.environ['TEAM_SMTP_USER'],os.environ['TEAM_SMTP_PASSWORD']);smtp.send_message(message)

def verification(to,code):
 send(to,'球队训练打卡邮箱验证码',f'你的验证码是：{code}\n\n验证码 10 分钟内有效。若不是你本人操作，请忽略此邮件。')

def reminder(to,name,week_start):
 send(to,'本周训练记录提醒',f'{name}，你好：\n\n截至目前，系统尚未收到你本周（{week_start} 起）的训练记录。请按球队安排完成训练，并在网站提交记录。\n\n如已请假、受伤或有其他情况，请与球队管理员联系。')


def notice_text(name,week_start,required,bonus,link):
 """本周任务通知的标题和正文。"""
 lines=[f'{name}，你好：','',f'本周（{week_start} 起）的训练任务已经发布：']
 if required:
  lines.append('');lines.append('必做：')
  lines.extend('- '+t for t in required)
 if bonus:
  lines.append('');lines.append('附加（每项 1 分，每周最多计 1 次）：')
  lines.extend('- '+t for t in bonus)
 lines+=['','必做任务请在周日 24:00 前提交；未完成且未免除的，那一周扣 10 分。',f'网站：{link}','','如已请假或受伤，请联系管理员标记免除。']
 return '本周训练任务已发布',"\n".join(lines)

def _send_batch(items,delay):
 results=[False]*len(items)
 if not items:return results
 host=os.environ.get('TEAM_SMTP_HOST','smtp.163.com');port=int(os.environ.get('TEAM_SMTP_PORT','465'))
 if host!='smtp.163.com' or port not in (465,994):raise ValueError('SMTP configuration invalid')
 with smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) as smtp:
  smtp.login(os.environ['TEAM_SMTP_USER'],os.environ['TEAM_SMTP_PASSWORD'])
  for index,(to,subject,body) in enumerate(items):
   if index:time.sleep(delay)
   message=EmailMessage();message['From']=os.environ['TEAM_SMTP_FROM'];message['To']=to;message['Subject']=subject;message.set_content(body)
   try:smtp.send_message(message);results[index]=True
   except Exception:pass
 return results

def send_many(items,delay=0.8,chunk=8):
 """分批发信：163 每个连接大约 11 封后就会拒收，所以每 chunk 封换一次连接；失败的再单独补一次。"""
 if not configured():raise RuntimeError('mail not configured')
 results=[]
 for start in range(0,len(items),chunk):
  results.extend(_send_batch(items[start:start+chunk],delay))
  if start+chunk<len(items):time.sleep(2)
 failed=[i for i,ok in enumerate(results) if not ok]
 if failed:
  time.sleep(3)
  retry=_send_batch([items[i] for i in failed],delay)
  for index,ok in zip(failed,retry):results[index]=ok
 return results
