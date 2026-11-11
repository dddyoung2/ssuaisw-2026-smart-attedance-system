# FR-based Smart Attedance System

> 오픈소스기반기초설계 수업 프로젝트

---

## 개요

- **목적:** 기존 공개된 얼굴인식 및 분류 오픈소스를 정확도를 보다 개선하여 실제 출석에 활용할 수 있는 스마트 출석 시스템을 개발하는 것
- **핵심 기능 요약:** 얼굴인식 -> 데이터베이스에 있는 출석 대상자들과 대조 -> 출석 여부 반영

---

## 핵심 기능

| 기능명 | 설명 |
|---|---|
| 강의실 사진 촬영 | 강의실 카메라로 수업 중 단체 사진을 촬영 |
| 얼굴 탐지 | 단체 사진에서 학생 얼굴 위치를 찾음 |
| 얼굴 인식 | 찾은 얼굴을 수강생 명단의 등록 사진과 대조 |
| 출석 판정 | 한 장이라도 인식되면 출석, 학생별 출석 여부 표 생성 |
| 교수 확인 | 인식되지 않은 학생은 "확인 필요"로 표시, 교수가 최종 확정 |
| 사진 즉시 삭제 | 판정이 끝나면 원본 사진 삭제 |

---

## 시스템 아키텍처
<img width="2212" height="1438" alt="image" src="https://github.com/user-attachments/assets/b8085246-d59c-4a75-9659-9dc088505531" />

---

## 기술 스택

**Frontend**
- HTML / CSS / JavaScript

**Backend**
- 미정

**AI / 모델**
- Face Detection Model: 미정
- Face Recognition: 미정
- Python / PyTorch / OpenCV
- Visualization
    - matplotlib / seaborn

**Database / Infra**
- 미정

---

## 프로젝트 구조
```
ssuaisw-2026-smart-attedance-system/
│  .gitignore
│  CONTRIBUTING.md                    # 규칙 문서
│  README.md                          # 프로젝트 소개 문서
├─.github                             # GitHub 설정 및 자동화
│  │  pull_request_template.md        # PR 템플릿
│  └─workflows
├─docs                                # 프로젝트 관련 문서 파일
└─src
   ├─frontend                         # 출결 화면
   └─exp                              # 실험 코드
      ├─face-detection                # 얼굴 탐지: 비교, 확정, 튜닝
      └─face-recognition              # 얼굴 인식
```
---

## 설치 방법 (Installation)

### 저장소 클론

``` bash
git clone https://github.com/dddyoung2/ssuaisw-2026-smart-attedance-system.git

cd ssuaisw-2026-smart-attedance-system
```

### 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 실행 방법 (Usage)

```bash
python main.py
```

---

## 환경 변수 설정

`.env.example` 파일을 참고하여 `.env` 파일을 생성하세요.

```env
API_KEY=your_api_key_here
DB_URL=your_db_url_here
```

---

## 성능 / 벤치마크

| 지표 | 결과 |
|---|---|
| 정확도 | |
| 응답 속도 | |

---

## 팀 (Contributors)

| 이름 | 역할 | GitHub |
|---|---|---|
| 김도영 | A | [![Github](https://img.shields.io/badge/dddyoung2-181717?style=flat&logo=github&logoColor=white)](https://github.com/dddyoung2) |
| 이승호 | B | [![Github](https://img.shields.io/badge/Lsh9716-181717?style=flat&logo=github&logoColor=white)](https://github.com/Lsh9716) |
| 이예찬 | C | [![Github](https://img.shields.io/badge/dpdcks-181717?style=flat&logo=github&logoColor=white)](https://github.com/dpdcks) |
