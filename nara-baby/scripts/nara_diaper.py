"""One selected diaper write with stable identity and checked readback."""
import hashlib
import json
import time
from nara_keychain import NaraError

COLORS = ('BLACK','BROWN','GRAY','GREEN','RED','YELLOW')
TEXTURES = {'mucous':'MUCOUS','mushy':'MUSH','pebble':'PEBBLE','runny':'RUN','solid':'SOLID'}

def diaper_fields(contents, color=None, texture=None):
    if contents not in ('wet','dirty','both','dry'):
        raise NaraError('Specify wet, dirty, both, or dry.')
    if contents not in ('dirty','both') and (color or texture):
        raise NaraError('Color and texture require a dirty diaper.')
    fields = {'diaperTypePee':contents in ('wet','both'),
              'diaperTypePoop':contents in ('dirty','both'),
              'diaperTypeDry':contents=='dry'}
    if color:
        if color.upper() not in COLORS: raise NaraError('Unsupported diaper color; clarify rather than guessing.')
        fields['diaperPoopColor']=color.upper()
    if texture:
        if texture.lower() not in TEXTURES: raise NaraError('Unsupported diaper texture; clarify rather than guessing.')
        fields['diaperPoopTexture']=TEXTURES[texture.lower()]
    return fields

def log_diaper(api, *, child, begin, contents, color=None, texture=None, check_only=False):
    fields=diaper_fields(contents,color,texture)
    if isinstance(begin,bool) or not isinstance(begin,int): raise NaraError('Diaper time must be epoch milliseconds.')
    expected=dict(fields,childKey=child,type='DIAPER',beginDt=begin,tz=api.activity_timezone)
    track_id='diaper'+hashlib.sha256(json.dumps([api.family_key,child,begin,'DIAPER']).encode()).hexdigest()[:32]
    def matches(record):
        return isinstance(record,dict) and record.get('familyKey',api.family_key)==api.family_key and all(record.get(k)==v for k,v in expected.items())
    def receipt(record,status):
        return dict(status=status,verified=True,contents=contents,track=record)
    tracks=api.get_data()
    candidates=[r for r in tracks.values() if isinstance(r,dict) and r.get('childKey')==child and r.get('type')=='DIAPER' and r.get('beginDt')==begin]
    if candidates:
        if len(candidates)==1 and matches(candidates[0]): return receipt(candidates[0],'already_recorded')
        raise NaraError('A diaper already exists at that time with different or ambiguous details. Inspect it; do not create another.')
    if track_id in tracks: raise NaraError('Stable diaper identity already exists; do not replace it.')
    if check_only: return dict(status='not_found',verified=False)
    if getattr(api,'_selected_child',None)!=child or not getattr(api,'_allow_writes',False):
        raise NaraError('A selected child and authorized write client are required.')
    try: api.log_activity('DIAPER',begin_dt=begin,track_id=track_id,**fields)
    except Exception: pass
    for attempt in range(3):
        try:
            fresh=api.get_data().get(track_id)
            if matches(fresh): return receipt(fresh,'saved')
        except Exception: break
        if attempt<2: time.sleep(.25)
    raise NaraError('Diaper outcome uncertain. Use the same time with --check-only; do not retry a write.')
