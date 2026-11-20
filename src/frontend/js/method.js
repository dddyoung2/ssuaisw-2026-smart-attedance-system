// ===== 3. 출결 방식 선택 =====
// (api.js 가 먼저 로드되어 있어야 함)
// 선택된 수업 정보 표시 → [전자 출결] → [카메라] → camera.html?lecture=<id>
// ← 뒤로: 그 회차의 과목 홈 (course.html?course=<과목코드>)

const eBtn = document.getElementById('eBtn');
const eOptions = document.getElementById('eOptions');

// 전자 출결 버튼 → 큐알/코드/카메라 버튼 펼치기
eBtn.addEventListener('click', () => {
  const open = eOptions.classList.toggle('open');
  eBtn.classList.toggle('active', open);
  eBtn.setAttribute('aria-expanded', open);
});

// 아직 만들지 않은 기능들
document.getElementById('manualBtn').addEventListener('click', () => {
  alert('수동 출결 페이지는 준비 중이에요.');
});
document.getElementById('qrBtn').addEventListener('click', () => {
  alert('QR 출결은 준비 중이에요.');
});
document.getElementById('codeBtn').addEventListener('click', () => {
  alert('코드 출결은 준비 중이에요.');
});

const lectureId = requireLectureId();   // 없으면 과목 목록으로 이동

async function init() {
  document.getElementById('cameraLink').href = `camera.html?lecture=${lectureId}`;
  const l = await showLectureInfo(lectureId, document.getElementById('lectureInfo'));
  if (l) {
    document.getElementById('backLink').href = `course.html?course=${encodeURIComponent(l.course_code)}`;
  }
}

if (lectureId) init();
