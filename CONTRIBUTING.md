# VAT-AI 개발 및 PR/Merge 규칙

## 1. Branch 규칙

- main 브랜치 직접 작업 및 직접 push 금지
- 모든 작업은 최신 main에서 Feature Branch를 생성하여 진행
- 기능별 Branch 사용
- 작업 완료 후 Pull Request를 통해 main에 병합

## 2. 작업 시작 전

```bash
git checkout main
git pull origin main
git checkout -b feature/<작업명>

3. PR 전 필수 확인
- [ ] 최신 main 변경사항 반영
- [ ] Merge Conflict 없음
- [ ] DB Migration 충돌 없음
- [ ] API Contract 임의 변경 없음
- [ ] 신규 환경변수는 .env.example에 반영
- [ ] 실제 Secret/API Key가 Repository에 포함되지 않음
- [ ] alembic upgrade head 정상 실행
- [ ] PYTHONPATH=. pytest -v 전체 통과
- [ ] 기존 기능 Regression 문제 없음

4. DB / Migration 규칙
- DB Schema 변경 시 Alembic Migration 필수
- Model 추가 시 app/core/database.py의 model import 확인
- Migration 파일 중복 및 복수 head 발생 여부 확인
- PR 전 alembic heads와 alembic current 확인
- PostgreSQL/pgvector 공용 개발환경은 docker-compose.yml 기준 사용

5. Merge 규칙
- PR 생성 후 GitHub Actions CI 통과 확인
- CI 실패 상태에서 Merge 금지
- 필요한 경우 팀원 Review 후 Merge
- Squash and merge 권장
- 각 Merge 후 Smoke/Regression Test 수행

6. Sprint 1 통합 순서
현재 Dependency 기준 권장 순서:
1. business-verification — main 반영 완료
2. devops-staging
3. receipt-pipeline
4. rag-baseline

각 PR Merge 후 다음 PR을 바로 병합하지 않고 아래 검증을 수행한다.

```bash
git checkout main
git pull origin main
alembic upgrade head
PYTHONPATH=. pytest -v
```

필요 시 Backend 실행 후 /health 확인:
```bash
uvicorn app.main:app --reload
curl -i http://127.0.0.1:8000/health
```

7. 완료 기준
다음 조건을 모두 만족해야 main 통합 가능:
- Build/Import 정상
- Migration 정상
- 전체 Test 통과
- GitHub Actions CI 통과
- Secret 노출 없음
- 기존 기능 Regression 없음
