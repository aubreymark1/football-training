"""Load the team's Q&A as untrusted retrieval data, not system instructions."""
import json,re,math
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher

PATH=Path(__file__).resolve().parent/'knowledge'/'football_qa.json'
def normalize(value): return re.sub(r'[^\w\u4e00-\u9fff]+','',str(value).lower())
def grams(value):
 value=normalize(value)
 return {value[i:i+2] for i in range(len(value)-1)} if len(value)>1 else set()
@lru_cache(maxsize=1)
def load():
 if not PATH.is_file(): return []
 payload=json.loads(PATH.read_text(encoding='utf8'))
 return [r for r in payload['entries'] if not r.get('disabled')]
def retrieve(query,limit=4):
 q=normalize(query)
 if len(q)<2:return []
 qgrams=grams(q); scored=[]
 for row in load():
  if any(normalize(x) in q for x in row.get('negative',[]) if len(normalize(x))>=2):continue
  best=0
  for candidate in [row['question']]+row.get('aliases',[]):
   c=normalize(candidate);g=grams(c)
   if not c or not g:continue
   overlap=len(qgrams & g); dice=2*overlap/(len(qgrams)+len(g))
   contained=min(len(q),len(c))/max(len(q),len(c)) if (q in c or c in q) else 0
   score=max(dice,contained)
   if q==c:score=1.0
   best=max(best,score)
  if best>=0.38:scored.append((best,row))
 scored.sort(key=lambda pair:(-pair[0],pair[1]['id']))
 return [{'问题':r['question'],'参考回答':r['answers'] if r.get('all_answers') else r['answers'][:1],'来源':'球队问答语料','行号':r['id']} for score,r in scored[:limit]]
