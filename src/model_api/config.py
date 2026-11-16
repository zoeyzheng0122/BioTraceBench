"""Explicit, non-secret profiles; no environment reads until HTTP submission."""
import copy
import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit,unquote

from ._json import digest
from ._json import loads
from .contracts import BackendDescription

PROTOCOLS = {'responses', 'chat_completions', 'anthropic', 'gemini'}
FIELDS = {'profile_version','name','provider','protocol','endpoint','model','key_env','vision',
          'structured_output','context_tokens','max_output_tokens','max_input_bytes','max_images',
          'image_token_reserve','output_token_field','generation','timeout','api_version'}
GENERATIONS = {
    'responses': {'temperature','top_p','reasoning'},
    'chat_completions': {'temperature','top_p','seed','presence_penalty','frequency_penalty','reasoning_effort','enable_thinking','thinking'},
    'anthropic': {'temperature','top_p','top_k','thinking'},
    'gemini': {'temperature','topP','topK','seed','thinkingConfig'},
}


@dataclass(frozen=True)
class Profile:
    value: dict

    def describe(self):
        return copy.deepcopy(self.value)

    def identity(self):
        p = self.value
        return BackendDescription(p['provider'],p['model'],p['protocol'],self.describe(),digest(p))


def load_profile(value):
    if isinstance(value,Profile):
        value=value.describe()
    if isinstance(value,(str,Path)):
        path=Path(value).expanduser().resolve()
        value=loads(path.read_text(encoding='utf-8'))
        if isinstance(value,dict) and 'vendor_template' in value:
            value=copy.deepcopy(value)
            template=(path.parent/value.pop('vendor_template')).resolve()
            base=loads(template.read_text(encoding='utf-8'));base.pop('template_notes',None)
            value={**base,**value}
    if not isinstance(value,dict):raise ValueError('model profile must be a JSON object')
    p=copy.deepcopy(value)
    if set(p)-FIELDS:raise ValueError('unknown model profile fields: '+','.join(sorted(set(p)-FIELDS)))
    required=FIELDS-{'api_version'}
    if required-set(p):raise ValueError('missing model profile fields: '+','.join(sorted(required-set(p))))
    if type(p['profile_version']) is not int or p['profile_version']!=1:raise ValueError('unsupported profile version')
    for field in ('name','provider','model','key_env','endpoint','output_token_field'):
        if not isinstance(p[field],str) or not p[field].strip():raise ValueError('invalid profile field: '+field)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',p['name']):raise ValueError('profile name must be a safe identifier')
    if not re.fullmatch(r'[A-Z_][A-Z0-9_]*',p['key_env']):raise ValueError('key_env must name an environment variable')
    if any(x in p['model'] for x in ('<','>','REPLACE','YOUR_')):raise ValueError('select an actual model ID')
    if p['protocol'] not in PROTOCOLS:raise ValueError('unknown API protocol')
    url=urlsplit(p['endpoint'])
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or '{' in p['endpoint']:
        raise ValueError('endpoint must be a complete credential-free HTTPS URL without query or placeholders')
    if p['protocol']=='gemini' and not unquote(url.path).endswith('/models/'+p['model']+':generateContent'):
        raise ValueError('Gemini endpoint model must match the declared model ID')
    if type(p['vision']) is not bool:raise ValueError('vision must be boolean')
    if p['structured_output'] not in {'none','json_object','json_schema'}:raise ValueError('unsupported structured output mode')
    if p['protocol']=='anthropic' and p['structured_output']=='json_object':raise ValueError('Anthropic supports none or json_schema')
    for field in ('context_tokens','max_output_tokens','max_input_bytes','timeout','max_images','image_token_reserve'):
        minimum=0 if field in {'max_images','image_token_reserve'} else 1
        if type(p[field]) is not int or p[field]<minimum:raise ValueError('invalid profile field: '+field)
    if p['timeout']>900:raise ValueError('API timeout cannot exceed 900 seconds')
    if p['max_output_tokens']>=p['context_tokens']:raise ValueError('output must fit context')
    if p['max_input_bytes']+p['max_output_tokens']+p['max_images']*p['image_token_reserve']>p['context_tokens']:
        raise ValueError('conservative input byte/token bound plus image/output reserves exceeds context')
    if not p['vision'] and (p['max_images'] or p['image_token_reserve']):raise ValueError('text profile cannot reserve images')
    if p['vision'] and (not p['max_images'] or not p['image_token_reserve']):raise ValueError('vision needs explicit image count and token reserve')
    if p['output_token_field'] not in {'max_tokens','max_completion_tokens','max_output_tokens','maxOutputTokens'}:raise ValueError('unsupported output token field')
    expected={'responses':{'max_output_tokens'},'chat_completions':{'max_tokens','max_completion_tokens'},'anthropic':{'max_tokens'},'gemini':{'maxOutputTokens'}}
    if p['output_token_field'] not in expected[p['protocol']]:raise ValueError('output token field does not match protocol')
    if not isinstance(p['generation'],dict) or set(p['generation'])-GENERATIONS[p['protocol']]:raise ValueError('unsupported generation parameters for protocol')
    if p['protocol']=='chat_completions' and 'thinking' in p['generation'] and p['provider']!='deepseek':
        raise ValueError('Chat Completions thinking is supported only for the explicit DeepSeek provider')
    for key,v in p['generation'].items():
        if key in {'reasoning','thinking','thinkingConfig'}:
            allowed={'reasoning':{'effort'},'thinking':{'type','budget_tokens'},'thinkingConfig':{'thinkingBudget','thinkingLevel','includeThoughts'}}[key]
            if not isinstance(v,dict) or set(v)-allowed:raise ValueError('unsupported nested generation parameter')
            if key=='thinking' and (v.get('type') not in {'enabled','disabled','adaptive'} or 'budget_tokens' in v and (type(v['budget_tokens']) is not int or v['budget_tokens']<1)):raise ValueError('invalid thinking configuration')
        elif key=='enable_thinking':
            if type(v) is not bool:raise ValueError('enable_thinking must be boolean')
        elif key=='reasoning_effort':
            if v not in {'none','minimal','low','medium','high','xhigh'}:raise ValueError('invalid reasoning effort')
        elif type(v) not in (int,float) or not math.isfinite(v):raise ValueError('generation parameter must be finite numeric')
        if key in {'temperature','top_p','topP'} and not 0<=v<=(2 if key=='temperature' else 1):raise ValueError('generation parameter outside supported range')
        if key in {'seed','top_k','topK'} and type(v) is not int:raise ValueError('integer generation parameter required')
    if 'api_version' in p and (not isinstance(p['api_version'],str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',p['api_version'])):raise ValueError('invalid API version')
    return Profile(p)
