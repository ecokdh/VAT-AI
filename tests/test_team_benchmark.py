import hashlib,json
from pathlib import Path
from app.main import app
from app.core.database import get_session
from app.core.config import settings
from app.auth.models import User
from app.core.security import create_access_token
from app.team_benchmark.models import TeamMember,BenchmarkCase

def test_team_access_matrix_revocation_and_read_only(client,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'STORAGE_DIR',str(tmp_path))
    gen=app.dependency_overrides[get_session]();db=next(gen)
    try:
        users=[User(email=f'{name}@example.com',name=name,password_hash='fixture') for name in ('manager','viewer','outsider')]
        db.add_all(users);db.flush()
        manager,viewer,outsider=users
        db.add(TeamMember(user_id=manager.id,role='maintainer'))
        db.add(TeamMember(user_id=viewer.id,role='viewer'))
        image=b'private-image';(tmp_path/'private.png').write_bytes(image)
        db.add(BenchmarkCase(case_id='KR01',category='음식점',image_key='private.png',image_sha256=hashlib.sha256(image).hexdigest(),tags_json='{}',gold_json='{}',prediction_json='{}',metadata_json='{"image_mime":"image/png"}'));db.commit()
        headers=lambda u:{'Authorization':'Bearer '+create_access_token(u.id,u.email)}
        for path in ['/v2/team-benchmark/cases','/v2/team-benchmark/cases/KR01','/v2/team-benchmark/cases/KR01/image']:
            assert client.get(path).status_code==401
            assert client.get(path,headers=headers(outsider)).status_code==403
            assert client.get(path,headers=headers(viewer)).status_code==200
        assert client.get('/v2/team-benchmark/members',headers=headers(viewer)).status_code==403
        assert client.put('/v2/team-benchmark/members',headers=headers(outsider),json={'email':outsider.email}).status_code==403
        assert client.put('/v2/team-benchmark/members',headers=headers(manager),json={'email':outsider.email}).status_code==200
        assert client.get('/v2/team-benchmark/cases',headers=headers(outsider)).status_code==200
        assert client.put('/v2/team-benchmark/members',headers=headers(manager),json={'email':viewer.email,'enabled':False}).status_code==200
        assert client.get('/v2/team-benchmark/cases/KR01/image',headers=headers(viewer)).status_code==403
        assert client.put('/v2/team-benchmark/members',headers=headers(manager),json={'email':manager.email,'enabled':False}).status_code==409
        assert client.put('/v2/team-benchmark/cases/KR01',headers=headers(manager),json={}).status_code==405
        assert client.delete('/v2/team-benchmark/cases/KR01',headers=headers(manager)).status_code==405
        assert client.get('/v2/team-benchmark/cases/KR99',headers=headers(manager)).status_code==404
        (tmp_path/'private.png').write_bytes(b'changed')
        assert client.get('/v2/team-benchmark/cases/KR01/image',headers=headers(manager)).status_code==503
    finally:gen.close()
