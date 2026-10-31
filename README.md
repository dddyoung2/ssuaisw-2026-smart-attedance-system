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
| | |
| | |

---

## 시스템 아키텍처
<img width="2212" height="1438" alt="image" src="https://github.com/user-attachments/assets/b8085246-d59c-4a75-9659-9dc088505531" />

---

## 기술 스택

**Frontend**
- 

**Backend**
- 

**AI / 모델**
- Face Detection Model
- Face Recognition

**Database / Infra**
- 

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
└─src                                 # 프로그램 코드    
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
