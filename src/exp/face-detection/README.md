# 얼굴 탐지 모델 실험(/src/exp/face-detection/)

> 출결 시스템의 얼굴 탐지 모델을 고르고자 후보 모델끼리의 성능을 비교하고, 사용할 모델을 확정하기 위한 코드   
> 확정된 모델의 성능 개선 코드

| 분류 | 디렉터리 | 내용 |
|---|---|---|
| 성능 비교 | `fd-model-compare/` | 얼굴 탐지 모델 비교 |
| 모델 확정 | `fd-model-select/` | 얼굴 탐지 모델 확정 |
| 모델 튜닝 | `fd-model-tuning/` | 얼굴 탐지 모델 튜닝 |

## 성능 비교 실험
> 후보로 뽑았던 얼굴 탐지 모델을 WIDER FACE, MAFA, WACV19(결정용)에서 같은 조건으로 비교
### 00. 실험에 활용한 데이터셋
| 데이터셋 이름 | 용도 | 출처 |
|---|---|---|
| WIDER FACE | 다중 인원 탐지 | [WIDER-FACE](https://www.cv-foundation.org/openaccess/content_cvpr_2016/html/Yang_WIDER_FACE_A_CVPR_2016_paper.html) |
| MAFA | 마스크로 가린 얼굴 탐지 | [MAFA](https://openaccess.thecvf.com/content_cvpr_2017/html/Ge_Detecting_Masked_Faces_CVPR_2017_paper.html) |
| WACV19 | 실사용 유사 환경 내 인원 탐지 | [WACV19](https://github.com/mackenney/attendance-system-wacv19) |

## 모델 확정
> 비교 결과로 탐지 모델과 운영 임계값을 확정하고 근거를 기록

## 모델 튜닝
> 확정한 모델의 성능 향상 실험