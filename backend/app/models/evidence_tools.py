"""Bounded read-only tool selection over a persisted case evidence snapshot."""
from datetime import datetime, timezone
from app.domain import visible_to
from app.providers.base import ModelOutputInvalid


def event(actor, kind, summary, ids=(), provider=None, reason_codes=None):
    item = {'at': datetime.now(timezone.utc).isoformat(), 'actor': actor,
            'event': kind, 'summary': summary, 'evidence_ids': list(ids), 'provider': provider}
    if reason_codes is not None:
        item['reason_codes'] = list(reason_codes)
    return item


def collect(provider, party, evidence, dispute, trace):
    available = [e for e in evidence if visible_to(e.visibility, party)]
    kinds = sorted({e.class_.value for e in available})
    selected = []
    if not kinds:
        trace.append(event(party+'_advocate','evidence_requested','No visible source records available'))
        return []
    schema = {'type':'object', 'required':['evidence_classes','done'], 'additionalProperties':False,
              'properties':{'evidence_classes':{'type':'array','items':{'type':'string','enum':kinds}},
                            'done':{'type':'boolean'}}}
    for round_no in range(3):
        request = provider.complete({
            'role': party+'_evidence_request', 'dispute':dispute,
            'instruction':'Choose read-only evidence classes needed to represent your party. Return evidence_classes and done. Request fare and telemetry for financial disputes, communications and events for disputed timing; request relevant profiles without treating history as fault. Three rounds maximum.',
            'available_tools':kinds, 'round':round_no+1,
            'retrieved_records':[e.to_api() for e in selected],
        }, schema).data
        requested = request.get('evidence_classes')
        if not isinstance(requested,list) or not isinstance(request.get('done'),bool) or any(k not in kinds for k in requested):
            raise ModelOutputInvalid('invalid read-only evidence request')
        returned = [e for e in available if e.class_.value in requested]
        known = {e.evidence_id for e in selected}
        selected.extend(e for e in returned if e.evidence_id not in known)
        trace.append(event(party+'_advocate','evidence_requested',
                           'Read-only request: '+(', '.join(requested) or 'no further records'),
                           [e.evidence_id for e in returned], provider.meta.display_name))
        if request['done']:
            break
    return selected
