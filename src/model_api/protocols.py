"""Four HTTP envelopes. No business JSON parsing, evidence repair or tools."""
import base64
import json
import mimetypes
from pathlib import Path

from ._json import filehash
from .contracts import ApiFailure, BackendResponse


def request_body(profile, request):
    p=profile.value;protocol=p['protocol']
    images=request.get('images',[])
    if images and not p['vision']:raise ApiFailure('profile does not support images','not_applicable','capability')
    if len(images)>p['max_images']:raise ApiFailure('complete image set exceeds model capacity','paused_capacity','preflight_capacity')
    pictures=[]
    for image in images:
        path=Path(image['path'])
        if not path.is_file() or filehash(path)!=image['sha256']:raise ApiFailure('image identity changed','failed_validation')
        mime=mimetypes.guess_type(path.name)[0]
        if mime not in {'image/png','image/jpeg','image/webp','image/gif'}:raise ApiFailure('unsupported image media type','failed_validation')
        pictures.append((mime,base64.b64encode(path.read_bytes()).decode('ascii')))
    text=json.dumps({'protocol_version':request['protocol_version'],'stage':request['stage'],
                     'payload':request['payload'],'response_schema':request['response_schema']},ensure_ascii=False,separators=(',',':'),allow_nan=False)
    instruction=request['instruction']
    schema=request['response_schema'];mode=p['structured_output'];generation=p['generation']
    if protocol=='responses':
        content=[{'type':'input_text','text':text}]+[{'type':'input_image','image_url':f'data:{mime};base64,{data}'} for mime,data in pictures]
        body={'model':p['model'],'instructions':instruction,'input':[{'role':'user','content':content}],
              'max_output_tokens':p['max_output_tokens'],'stream':False,'store':False,**generation}
        if mode!='none':body['text']={'format':({'type':'json_schema','name':'curation_response','schema':schema,'strict':False} if mode=='json_schema' else {'type':'json_object'})}
    elif protocol=='chat_completions':
        content=[{'type':'text','text':text}]+[{'type':'image_url','image_url':{'url':f'data:{mime};base64,{data}'}} for mime,data in pictures]
        body={'model':p['model'],'messages':[{'role':'system','content':instruction},{'role':'user','content':content}],
              p['output_token_field']:p['max_output_tokens'],'stream':False,**generation}
        if mode!='none':body['response_format']=({'type':'json_schema','json_schema':{'name':'curation_response','schema':schema,'strict':False}} if mode=='json_schema' else {'type':'json_object'})
    elif protocol=='anthropic':
        content=[{'type':'text','text':text}]+[{'type':'image','source':{'type':'base64','media_type':mime,'data':data}} for mime,data in pictures]
        body={'model':p['model'],'system':instruction,'messages':[{'role':'user','content':content}],
              'max_tokens':p['max_output_tokens'],'stream':False,**generation}
        if mode=='json_schema':body['output_config']={'format':{'type':'json_schema','schema':schema}}
    else:
        parts=[{'text':text}]+[{'inlineData':{'mimeType':mime,'data':data}} for mime,data in pictures]
        config={'maxOutputTokens':p['max_output_tokens'],**generation}
        if mode!='none':config['responseMimeType']='application/json'
        if mode=='json_schema':config['responseJsonSchema']=schema
        body={'systemInstruction':{'parts':[{'text':instruction}]},'contents':[{'role':'user','parts':parts}],'generationConfig':config}
    # Count the complete protocol-specific body, including duplicated native schema
    # and JSON escaping. Image bytes use the explicit per-image token reservation.
    size=len(json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))-sum(len(data) for _,data in pictures)
    if size>p['max_input_bytes']:raise ApiFailure('complete request exceeds declared input byte bound; no truncation','paused_capacity','preflight_capacity')
    return body


def response_value(profile, value, headers, elapsed, archive):
    p=profile.value;protocol=p['protocol'];finish=None;model=value.get('model');rid=value.get('id') or headers.get('x-request-id') or headers.get('request-id')
    usage=value.get('usage');text='';refused=False
    if protocol=='responses':
        finish=value.get('status');parts=[c for item in value.get('output',[]) if item.get('type')=='message' for c in item.get('content',[])]
        refused=any(c.get('type')=='refusal' for c in parts)
        text=''.join(c.get('text','') for c in parts if c.get('type')=='output_text')
        truncated=finish=='incomplete';complete=finish=='completed'
        if any(i.get('type') not in {'message','reasoning'} for i in value.get('output',[])):raise ApiFailure('unexpected model action','failed_validation')
    elif protocol=='chat_completions':
        choices=value.get('choices',[])
        if len(choices)!=1:raise ApiFailure('expected exactly one completion','failed_validation')
        choice=choices[0];message=choice.get('message',{});finish=choice.get('finish_reason')
        refused=bool(message.get('refusal')) or finish=='content_filter'
        if message.get('tool_calls') or message.get('function_call'):raise ApiFailure('model tool response is not allowed','failed_validation')
        content=message.get('content');text=content if isinstance(content,str) else ''
        truncated=finish=='length';complete=finish=='stop'
    elif protocol=='anthropic':
        finish=value.get('stop_reason');parts=value.get('content',[])
        refused=finish=='refusal'
        text=''.join(c.get('text','') for c in parts if c.get('type')=='text')
        if any(c.get('type') not in {'text','thinking','redacted_thinking'} for c in parts):raise ApiFailure('unexpected model action','failed_validation')
        truncated=finish in {'max_tokens','model_context_window_exceeded'};complete=finish=='end_turn'
    else:
        model=value.get('modelVersion');rid=value.get('responseId') or rid;usage=value.get('usageMetadata')
        candidates=value.get('candidates',[])
        refused=bool(value.get('promptFeedback',{}).get('blockReason'))
        if len(candidates)!=1:
            raise ApiFailure('model refused input' if refused else 'expected exactly one candidate','paused_refusal' if refused else 'failed_validation')
        candidate=candidates[0];finish=candidate.get('finishReason');parts=candidate.get('content',{}).get('parts',[])
        text=''.join(c.get('text','') for c in parts if not c.get('thought'))
        if any('functionCall' in c or 'executableCode' in c or 'codeExecutionResult' in c for c in parts):raise ApiFailure('unexpected model action','failed_validation')
        refused=refused or finish in {'SAFETY','RECITATION','BLOCKLIST','PROHIBITED_CONTENT','SPII'}
        truncated=finish=='MAX_TOKENS';complete=finish=='STOP'
    usage=usage if isinstance(usage,dict) else None
    keys=({'input_tokens':'prompt_tokens','output_tokens':'completion_tokens','total_tokens':'total_tokens'} if protocol=='chat_completions' else
          {'input_tokens':'promptTokenCount','output_tokens':'candidatesTokenCount','total_tokens':'totalTokenCount'} if protocol=='gemini' else
          {'input_tokens':'input_tokens','output_tokens':'output_tokens','total_tokens':'total_tokens'})
    normalized={key:(usage or {}).get(v) for key,v in keys.items()}
    for key,v in normalized.items():
        if type(v) is not int or v<0:normalized[key]=None
    result=BackendResponse(text,finish,model,rid,normalized,usage,elapsed,str(archive))
    acknowledged_limit=truncated and (protocol!='responses' or (value.get('incomplete_details') or {}).get('reason')=='max_output_tokens')
    failure=(ApiFailure('model refused input; original response archived','paused_refusal') if refused else
             ApiFailure('model output truncated; original response archived','paused_truncated','output_limit' if acknowledged_limit else 'paused_truncated') if truncated else
             ApiFailure('incomplete or empty model response; original response archived','paused_unknown') if not complete or not text else None)
    if failure:
        failure.response=result
        raise failure
    return result
