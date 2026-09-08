# SW 동아리 활동 · 시험 운영

동아리의 공개 GitHub 활동을 자동으로 모으고, 학생이 제출한 역할·성과·증빙을 함께 확인합니다.

**[활동 페이지](https://sauntertl.github.io/activities-clubs/) · [동아리 등록](../../issues/new?template=01-register.yml) · [성과 제출](../../issues/new?template=02-activity.yml) · [운영 안내](docs/OPERATIONS.md)**

현재 `sauntertl` 계정은 운영자 테스트로 구분합니다. 테스트 기록은 학생 실적이 아닙니다.

## 참여 방법

1. 본인의 GitHub 계정으로 **동아리 활동 등록** 이슈를 작성합니다. 동아리명, 본인 ID, 공개 저장소 주소, 활동 기간을 입력합니다.
2. 담당자가 내용을 확인하고 `approved` 라벨을 붙이면 자동 수집을 시작합니다.
3. 주요 성과와 본인 역할은 **동아리 성과 제출**에서 등록 번호와 증빙 링크를 연결해 작성합니다.
4. 담당자가 성과에 `approved` 라벨을 붙이면 확인된 제출 성과에 표시됩니다.

등록과 성과 이슈는 승인 후에도 열린 상태로 유지합니다. 내용 수정 시 재승인이 필요합니다. 등록 이슈를 닫으면 다음 갱신부터 해당 등록과 관련 기록을 페이지에서 제외합니다.

## 수집 범위

- 승인된 공개 저장소의 기본 브랜치 커밋, 작성한 PR·이슈, 제출한 코드 리뷰
- 등록 기간 내 활동을 한국 시간으로 구분
- 수집 이력 누적 및 원문 링크 보관
- 비공개 저장소와 GitHub에 올리지 않은 작업은 수집하지 않음
- 자동 수집 기록과 담당자 확인 성과는 별도 표시하며 합산 점수·순위를 만들지 않음

조회 오류·조회량 한도는 화면의 확인 사항에 표시합니다. 수집 기록은 모든 개발 활동의 완전한 목록을 보장하지 않습니다.

## 개발 및 실행

추가 패키지 없이 Python 표준 라이브러리와 정적 HTML/CSS/JavaScript를 사용합니다.

```text
python -m unittest discover -s tests -v
node --test tests/test_frontend.js
python -m http.server 8765 --directory site
```

수집은 GitHub Actions에서 실행합니다. 인증 값은 서버 측 `GITHUB_TOKEN`으로만 사용하며 페이지에 포함하지 않습니다. 상세 수집·배포·이관 절차는 [운영 안내](docs/OPERATIONS.md)를 참고하세요.

## Git 템플릿

[학생 프로젝트 공통 템플릿](https://github.com/sauntertl/sw-project-template)은 현재 비공개 시험 배포 중이며 접근 권한이 필요합니다.
