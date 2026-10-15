import json
import random
from collections import Counter
import pytest
from ryde_training.generate import generate,case,outside_repository
from ryde_training.review import export
from ryde_training.review_packet import apply_review_data


def test_generation_and_split_integrity(tmp_path):
    root=generate(tmp_path/'data')
    rows=[json.loads(line) for line in (root/'corpus.jsonl').read_text().splitlines()]
    assert len(rows)==1000
    assert Counter(r['filing']['category'] for r in rows)['route_deviation']==400
    assert all('ruling_type' not in json.dumps(r['records']) for r in rows)
    review=[json.loads(line) for line in (root/'review-queue.jsonl').read_text().splitlines()]
    assert Counter(r['split'] for r in review)=={'train':40,'validation':10,'test':10}
    assert {r['sample']['policy_version'] for r in review}=={'ryde-policy-1.1.0'}
    assert {tuple(sorted(r['role_targets'])) for r in review}=={('driver_advocate','judge','rider_advocate')}
    assert all(r['ruling_review']['decision']=='pending' and not r['approved_ruling'] for r in review)
    reviewer_evidence_ids=[]
    for row in review:
        case_role_ids=[]
        for target in row['role_targets'].values():
            prompt=json.loads(target['messages'][0]['content'])
            ids=[item['evidence_id'] for item in prompt['evidence_records']]
            assert len(ids)==len(set(ids))==6
            case_role_ids.append(ids)
            answer=json.loads(target['messages'][-1]['content'])
            refs=answer.get('evidence_references',[])+[
                citation['evidence_id'] for claim in answer.get('claims',[])
                for citation in claim.get('citations',[])]
            assert set(refs).issubset(set(ids))
        assert all(ids==case_role_ids[0] for ids in case_role_ids)
        reviewer_evidence_ids.append(tuple(case_role_ids[0]))
    assert len(reviewer_evidence_ids)==len(set(reviewer_evidence_ids))
    with pytest.raises(ValueError,match='No human-approved'):
        export(root/'review-queue.jsonl',tmp_path/'export')

    ruling_rows=[]
    agent_rows=[]
    for row in review:
        sid=row['sample']['sample_id']
        approved=sid==review[0]['sample']['sample_id']
        ruling_rows.append({'Sample ID':sid,'Decision':'Approve' if approved else 'Pending',
            'Reviewer':'Owner' if approved else '', 'Reviewed at (ISO 8601)':'2026-10-15T10:00:00+08:00' if approved else '',
            'Policy version':'ryde-policy-1.1.0' if approved else '', 'Rationale':'Reviewed against cited policy.' if approved else ''})
        for role,target in row['role_targets'].items():
            role_approved=approved and role=='rider_advocate'
            agent_rows.append({'Sample ID':sid,'Agent role':role,
                'Decision':'Approve' if role_approved else 'Pending', 'Reviewer':'Owner' if role_approved else '',
                'Reviewed at (ISO 8601)':'2026-10-15T10:00:00+08:00' if role_approved else '',
                'Policy version':'ryde-policy-1.1.0' if role_approved else '',
                'Rationale':'Citations and position checked.' if role_approved else ''})
    reviewed=apply_review_data(review,ruling_rows,agent_rows)
    first=reviewed[0]
    assert first['approved_ruling'] is True
    assert first['role_targets']['rider_advocate']['approved'] is True
    assert first['role_targets']['driver_advocate']['approved'] is False
    assert first['role_targets']['judge']['approved'] is False
    counts=export_from_rows(reviewed,tmp_path/'approved')
    assert counts=={'train':1,'validation':0,'test':0}

    corrected_rulings=[dict(item) for item in ruling_rows]
    corrected_agents=[dict(item) for item in agent_rows]
    corrected_rulings[0]={**corrected_rulings[0], 'Decision':'Correct',
        'Corrected ruling JSON':json.dumps(review[0]['ruling_target'])}
    corrected_agent_index=next(i for i,item in enumerate(corrected_agents)
        if item['Sample ID']==review[0]['sample']['sample_id'] and item['Agent role']=='rider_advocate')
    original_target=json.loads(review[0]['role_targets']['rider_advocate']['messages'][-1]['content'])
    corrected_agents[corrected_agent_index]={**corrected_agents[corrected_agent_index], 'Decision':'Correct',
        'Corrected target JSON':json.dumps(original_target)}
    corrected=apply_review_data(review,corrected_rulings,corrected_agents)
    assert corrected[0]['review_status']=='overridden'
    assert corrected[0]['role_targets']['rider_advocate']['origin']=='human_reviewed'
    assert corrected[0]['role_targets']['rider_advocate']['approved'] is True
    assert corrected[0]['role_targets']['driver_advocate']['approved'] is False

    bad_roles=[dict(item) for item in agent_rows]
    approved_role_index=next(i for i,item in enumerate(bad_roles)
        if item['Sample ID']==review[0]['sample']['sample_id'] and item['Agent role']=='rider_advocate')
    bad_roles[approved_role_index]={**bad_roles[approved_role_index],'Reviewer':''}
    with pytest.raises(ValueError,match='reviewer is required'):
        apply_review_data(review,ruling_rows,bad_roles)
    stale_rulings=[dict(item) for item in ruling_rows]
    stale_rulings[0]={**stale_rulings[0],'Policy version':'ryde-policy-1.0.0'}
    with pytest.raises(ValueError,match='stale policy label'):
        apply_review_data(review,stale_rulings,agent_rows)

    invalid_correction=[dict(item) for item in corrected_agents]
    invalid_correction[corrected_agent_index]={**invalid_correction[corrected_agent_index],
        'Corrected target JSON':'not JSON'}
    with pytest.raises(ValueError,match='corrected target must be valid JSON'):
        apply_review_data(review,corrected_rulings,invalid_correction)

    mismatched_value=json.loads(json.dumps(original_target))
    mismatched_value['claims'][0]['citations'][0]['observed_value']=-999
    bad_value_rows=[dict(item) for item in corrected_agents]
    bad_value_rows[corrected_agent_index]={**bad_value_rows[corrected_agent_index],
        'Corrected target JSON':json.dumps(mismatched_value)}
    with pytest.raises(ValueError,match='observed value does not match evidence'):
        apply_review_data(review,corrected_rulings,bad_value_rows)


def test_repo_output_rejected():
    with pytest.raises(ValueError):outside_repository(__file__)


def test_generator_rejects_stale_policy(tmp_path):
    stale=tmp_path/'policy.json'
    stale.write_text(json.dumps({'version':'ryde-policy-1.0.0','rules':[]}))
    with pytest.raises(ValueError,match='Expected source policy ryde-policy-1.1.0'):
        generate(tmp_path/'should-not-exist',stale)
    assert not (tmp_path/'should-not-exist').exists()


def export_from_rows(rows, output):
    import json
    source=output.parent/'reviewed-queue.jsonl'
    source.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    return export(source,output)
