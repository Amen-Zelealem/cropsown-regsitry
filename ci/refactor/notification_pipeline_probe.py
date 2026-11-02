"""Execute installed native classification/transform/payload builders on disposable seed data."""
import asyncio
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4
import yaml
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker

repo,domain=Path(sys.argv[1]),sys.argv[2]
FIRST_REFERENCE_FORM='farmer_registry_notice_to_farmer_reference_form'
sys.path.insert(0,str(repo/f'{domain}-extension/src'))
package=importlib.import_module(f'openg2p_registry_{domain}_extension')
sys.modules['openg2p_registry_extensions']=package
os.environ['REGISTRY_EXTENSION_MODULE']=package.__name__
importlib.import_module('openg2p_registry_celery_worker.main')
support=importlib.import_module('openg2p_registry_celery_worker.tasks.ingestion_classification_support')
transform=importlib.import_module('openg2p_registry_celery_worker.tasks.ingest_data_transformation_worker')
builder=importlib.import_module('openg2p_registry_celery_worker.tasks.change_request_ingest_worker')
ingest=importlib.import_module('openg2p_registry_celery_worker.tasks.ingest_data_worker')
from openg2p_registry_core.models import IncomingRawDataPayload,IncomingClassifiedData
from openg2p_registry_core.helpers import PatternMatcher,TemplateHelper
models=importlib.import_module('openg2p_registry_extensions.register_domain.models')
cfg=yaml.safe_load((repo/'integrations/farmer-reference/config.yaml').read_text(encoding='utf-8'))
host=f'coss-refactor-metadata-{domain}-db'
url=f'postgresql+psycopg2://postgres@{host}/refactor_metadata'
engine=create_engine(url)
identity={'farmer_id':'FR-000000000001','fayda_fan_id':'0000000000000001'}
event={'event_id':'synthetic-event','event_type':'farmer_reference.changed.v1',**identity}
raw=IncomingRawDataPayload(ingest_id=str(uuid4()),raw_data_json={'body':{'header':{'message_id':'synthetic-event','sender_id':'synthetic-partner','signature':'not-a-verification-fixture'},'message':{'payload':event}}})
matcher=PatternMatcher().get_component()
local_id=str(uuid4())
with Session(engine) as session:
    patterns=support.load_register_patterns(session,cfg['data_model_id'])
    matched,identifier=support.match_register_pattern_and_identifier(patterns,raw,matcher)
    assert identifier==identity['farmer_id'] and matched.register_id==cfg['register_id']
    semantic=support.load_semantic_patterns_for_register(session,cfg['data_model_id'],cfg['register_id'])
    action,missing=support.resolve_pipeline_action_and_internal_id(session,cfg['register_id'],identifier)
    assert action=='ADD' and missing is None
    # An unknown Farmer's notice classifies as ADD onto the pipeline-only Farmer intake form.
    add=support.match_semantic_for_add(semantic,raw,matcher)
    assert add.intake_form_id==FIRST_REFERENCE_FORM and add.register_id==cfg['register_id']
    added=IncomingClassifiedData(ingest_id=raw.ingest_id,data_model_id=cfg['data_model_id'],register_id=cfg['register_id'],
        intake_form_id=add.intake_form_id,semantic_pattern_id=add.semantic_pattern_id,pipeline_action='ADD')
    assert transform._enrich_raw_data_json(added,raw,session)==identity
    farmer=models.G2PRegisterFarmer(internal_record_id=local_id,functional_record_id=identifier,
        **identity,first_name='Approved local',created_by='synthetic',created_at=datetime.now(),
        last_approved_at=datetime.now(),last_approved_by='synthetic',record_status='ACTIVE')
    session.add(farmer)
    session.commit()
    action,resolved=support.resolve_pipeline_action_and_internal_id(session,cfg['register_id'],identifier)
    assert action=='UPDATE' and resolved==local_id
    pattern=support.match_semantic_for_update(semantic,raw,matcher)
    classified=IncomingClassifiedData(ingest_id=raw.ingest_id,data_model_id=cfg['data_model_id'],register_id=cfg['register_id'],
        section_id=cfg['section_id'],semantic_pattern_id=pattern.semantic_pattern_id,pipeline_action='UPDATE',internal_record_id=local_id)
    enriched=transform._enrich_raw_data_json(classified,raw,session)
    assert enriched==identity
    template=(repo/f'{domain}-extension/src/{package.__name__}/templates/crop_farmer_reference_update.json.j2').read_text(encoding='utf-8')
    rendered=json.loads(TemplateHelper().get_component().env.from_string(template).render(expanded=enriched))
    transform._validate_transformed_data_json(classified,rendered,session)
    assert next(iter(rendered.values()))==[identity]
    # The same rendered notice is a valid transformed ADD payload for the pipeline-only form.
    transform._validate_transformed_data_json(added,rendered,session)
    assert farmer.first_name=='Approved local'

async def build_payload():
    engine=create_async_engine(f'postgresql+asyncpg://postgres@{host}/refactor_metadata')
    try:
        async with async_sessionmaker(engine)() as session:
            payload=await builder._build_change_request_payload_async(session,classified,SimpleNamespace(transformed_data_json=rendered))
            row=payload.change_payload[0].model_dump(exclude_unset=True)
            assert row=={**identity,'edit_action':'UPDATE','internal_record_id':local_id}
            assert payload.section_register_id==cfg['register_id']
            # The ingest worker accepts the rendered notice against the pipeline-only form's sections.
            sections=await ingest._get_ordered_form_sections(FIRST_REFERENCE_FORM,session)
            assert ingest._validate_transformed_data_json(added,SimpleNamespace(transformed_data_json=rendered),sections)==rendered
    finally: await engine.dispose()
asyncio.run(build_payload())
with Session(engine) as session:
    session.delete(session.get(models.G2PRegisterFarmer,local_id))
    session.commit()
engine.dispose()
result={'registry':domain,'result':'PASS','installed_platform':'1.2.2-rc.614',
    'native_helpers':['two-pass classification','unreferenced ADD onto the pipeline-only Farmer intake form','native enricher factory','native TemplateHelper Jinja environment',
                      'native UPDATE transform validation','native asynchronous CR payload builder'],
    'worker_replaced':False,'existing_environment_modified':False,
    'not_proved':['partner signature validation','MinIO stored-template download','Kafka delivery','real Farmer lookup','live AWE task']}
(repo/'ci-output/refactor/NATIVE_NOTIFICATION_PIPELINE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(result))
