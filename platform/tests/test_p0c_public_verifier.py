import importlib.util
from pathlib import Path


def module():
    p=Path(__file__).parents[2]/'reports/2026-10-29-p0c-directionality/verify_public.py'
    spec=importlib.util.spec_from_file_location('public_verify',p);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m


def test_full_opportunity_denominators_and_opposite_feed_not_confused():
    rows=[dict(topic='fixture',source_version='v',seed='1',cell='b',window='0',before='5',after='3',feed_direction='lower',prior_slots_band='0',events='2'),
          dict(topic='fixture',source_version='v',seed='1',cell='b',window='0',before='5',after='5',feed_direction='lower',prior_slots_band='0',events='7'),
          dict(topic='fixture',source_version='v',seed='1',cell='b',window='0',before='3',after='5',feed_direction='empty',prior_slots_band='0',events='1')]
    result=module().aggregate_transitions(rows)
    assert result['events']==10
    assert result['categories']['5_to_3']==2
    assert result['categories']['empty_changed']==1
    assert result['opportunities']['fixture|v']['before5']==9
    assert result['opportunities']['fixture|v']['3_to_5']==1
    assert result['opportunities']['fixture|v']['5_lower_opportunities']==9
    assert result['opportunities']['fixture|v'].get('3_higher_opportunities',0)==0
