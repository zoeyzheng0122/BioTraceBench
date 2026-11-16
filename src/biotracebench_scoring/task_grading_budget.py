"""Qwen total-completion limits and usage details; no credentials or network."""
from model_api import load_profile

VERSION = 'biotracebench-qwen-total-output-1'
TOKEN_MARGIN = 10
SOURCE = 'https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions'
SOURCE_CHECKED_AT = '2026-10-29'


def output_control(profile):
    """One total-output cap drives the wire, context check and cost reserve."""
    p=load_profile(profile).describe()
    if p['provider']=='deepseek':
        if p['protocol']!='chat_completions' or p['output_token_field']!='max_tokens':
            raise ValueError('DeepSeek grading requires Chat Completions max_tokens for total output')
        if p['max_input_bytes']+p['max_output_tokens']>p['context_tokens']:
            raise ValueError('Complete DeepSeek input and total-output bounds exceed context; no truncation')
        return {'version':'biotracebench-deepseek-total-output-1','output_token_field':'max_tokens',
            'output_scope':'reasoning_plus_final','requested_output_tokens':p['max_output_tokens'],
            'provider_margin_tokens':0,'reserved_output_tokens':p['max_output_tokens'],
            'input_token_upper_bound':p['context_tokens'],
            'input_reservation_basis':'full declared context at uncached peak rate; deliberately conservative',
            'context_input_bound_bytes':p['max_input_bytes'],'context_tokens':p['context_tokens'],
            'source':'https://api-docs.deepseek.com/api/create-chat-completion/',
            'source_checked_at':'2026-10-31','capacity_validation':'requires archived API usage verification'}
    if p['provider']!='qwen' or p['protocol']!='chat_completions':
        raise ValueError('Whole-task Qwen grading requires the Chat Completions profile')
    if p['output_token_field']!='max_completion_tokens':
        raise ValueError('Qwen grading requires max_completion_tokens for reasoning plus final output; max_tokens is not a total-output bound')
    reserved=p['max_output_tokens']+TOKEN_MARGIN
    # Reuse the API's conservative full-request byte/token bound, with provider margin.
    if p['max_input_bytes']+reserved>p['context_tokens']:
        raise ValueError('Complete input bound plus total output and provider token margin exceeds context; no truncation')
    return {'version':VERSION,'output_token_field':'max_completion_tokens',
        'output_scope':'reasoning_plus_final','requested_output_tokens':p['max_output_tokens'],
        'provider_margin_tokens':TOKEN_MARGIN,'reserved_output_tokens':reserved,
        'input_token_upper_bound':p['context_tokens'],
        'input_reservation_basis':'full declared context at uncached rate; deliberately conservative',
        'context_input_bound_bytes':p['max_input_bytes'],'context_tokens':p['context_tokens'],
        'source':SOURCE,'source_checked_at':SOURCE_CHECKED_AT,
        'capacity_validation':'not established by local configuration checks'}


def usage_breakdown(usage, raw_usage):
    """Reasoning is a subset of output, never an additional billable total."""
    integer=lambda v:type(v) is int and v>=0
    ni,no=usage.get('input_tokens'),usage.get('output_tokens')
    details=(raw_usage or {}).get('completion_tokens_details')
    diagnostics=[]
    if details is not None and not isinstance(details,dict):
        diagnostics.append('Invalid completion detail preserved in raw_usage; not used for billing')
    details=details if isinstance(details,dict) else {}
    reasoning,text=details.get('reasoning_tokens'),details.get('text_tokens')
    if reasoning is not None and (not integer(reasoning) or integer(no) and reasoning>no):
        diagnostics.append('Invalid reasoning detail preserved in raw_usage; not used for billing')
        reasoning=None
    if text is not None and (not integer(text) or integer(no) and text>no
                             or integer(reasoning) and text<reasoning):
        diagnostics.append('Invalid text detail preserved in raw_usage; no final-text count inferred')
        text=None
    return {'input_tokens':ni if integer(ni) else None,
        'output_tokens_total':no if integer(no) else None,
        'reasoning_tokens':reasoning,
        'final_text_tokens':text-reasoning if integer(text) and integer(reasoning) else None,
        'reasoning_included_in_output_total':True,
        'billing_basis':'input_tokens and output_tokens_total only; never add reasoning_tokens again',
        'detail_status':'invalid_preserved' if diagnostics else 'reported' if reasoning is not None else 'not_reported',
        'diagnostics':diagnostics}
