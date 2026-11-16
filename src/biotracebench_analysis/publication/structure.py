"""Format, type, key and declared-reference checks."""
import json
from collections import Counter
import collections

def pairs_no_duplicates(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate_json_key:'+k)
  d[k]=v
 return d

def parse(raw):
 def invalid(v):raise ValueError('nonfinite_json_number:'+v)
 return json.loads(raw,object_pairs_hook=pairs_no_duplicates,parse_constant=invalid)

def jsontype(x):
 return 'null' if x is None else 'boolean' if type(x) is bool else 'integer' if type(x) is int else 'number' if type(x) is float else 'string' if type(x) is str else 'array' if type(x) is list else 'object' if type(x) is dict else 'unknown'

def structural(db,schema,dictionary):
 errors=[]
 def walk(x,rule,path):
  typ=jsontype(x);allowed=rule.get('type',[]);allowed=[allowed] if isinstance(allowed,str) else allowed
  if allowed and typ not in allowed and not (typ=='integer' and 'number' in allowed):
   errors.append((path,'type'));return
  if isinstance(x,str) and len(x)<rule.get('minLength',0):errors.append((path,'minLength'))
  if isinstance(x,dict):
   for k in rule.get('required',[]):
    if k not in x:errors.append((path+'.'+k,'required'))
   for k,v in x.items():
    child=rule.get('properties',{}).get(k)
    if child is None and rule.get('additionalProperties') is False:errors.append((path+'.'+k,'additionalProperty'))
    elif child is not None:walk(v,child,path+'.'+k)
  elif isinstance(x,list):
   if len(x)<rule.get('minItems',0):errors.append((path,'minItems'))
   if rule.get('uniqueItems') and len({json.dumps(v,sort_keys=True,ensure_ascii=False) for v in x})!=len(x):errors.append((path,'uniqueItems'))
   for i,v in enumerate(x):walk(v,rule.get('items',{}),path+f'[{i}]')
 walk(db,schema,'$')
 if not isinstance(db,dict):return errors,0,0
 ids={}; nonempty=0; fk_count=0
 for table,spec in dictionary.items():
  table_rows=db.get(table); table_rows=table_rows if isinstance(table_rows,list) else []
  nonempty+=len(table_rows)
  vals=[];key=spec.get('identifier')
  for i,row in enumerate(table_rows):
   if isinstance(row,dict) and key and isinstance(row.get(key),str) and row[key]:vals.append(row[key])
  if len(vals)!=len(set(vals)):errors.append(('$.%s.%s'%(table,key),'duplicate_primary_key'))
  ids[table]=set(vals)
 for table,spec in dictionary.items():
  table_rows=db.get(table);table_rows=table_rows if isinstance(table_rows,list) else []
  for i,row in enumerate(table_rows):
   if not isinstance(row,dict):continue
   for field,target in spec.get('references',{}).items():
    v=row.get(field); values=v if isinstance(v,list) else [v]
    for ref in values:
     if ref is None:continue
     fk_count+=1
     if not isinstance(ref,str) or ref not in ids[target]:errors.append((f'$.{table}[{i}].{field}','dangling_foreign_key'))
 return sorted(set(errors)),nonempty,fk_count

def validate_tests():
 schema={'type':'object','required':['a','b'],'additionalProperties':False,'properties':{'a':{'type':'array','items':{'type':'object','required':['id'],'additionalProperties':False,'properties':{'id':{'type':'string','minLength':1}}}},'b':{'type':'array','items':{'type':'object','required':['id','a_id'],'additionalProperties':False,'properties':{'id':{'type':'string','minLength':1},'a_id':{'type':'string','minLength':1}}}}}}
 dic={'a':{'identifier':'id'},'b':{'identifier':'id','references':{'a_id':'a'}}}
 good={'a':[{'id':'a'}],'b':[{'id':'b','a_id':'a'}]}
 assert structural(good,schema,dic)[0]==[]
 bad={'a':[{'id':'a'},{'id':'a'}],'b':[{'id':'b','a_id':'no'}]}
 assert {e[1] for e in structural(bad,schema,dic)[0]}=={'duplicate_primary_key','dangling_foreign_key'}
 assert 'type' in {e[1] for e in structural({'a':1,'b':[]},schema,dic)[0]}
 assert 'required' in {e[1] for e in structural({'a':[]},schema,dic)[0]}
 for s in ('{"a": 1, "a": 2}','{"a": NaN}'):
  try:parse(s)
  except ValueError:pass
  else:raise AssertionError('strict parse failed')
