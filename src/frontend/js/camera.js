// ===== 4. 카메라 출결 =====
// (api.js 가 먼저 로드되어 있어야 함)
//
// 수업 회차는 앞 화면에서 정해져 URL(?lecture=)로 넘어온다.
// 강의실: GET /rooms 목록, 기본값은 그 회차의 강의실. 다른 강의실을 골라도 DB 의 회차는 바꾸지 않는다.
//         (강의실 카메라 연동은 추후 작업. 지금은 이 브라우저의 카메라로 찍는다)
// 촬영 시작: POST /lectures/{id}/start → 즉시 1장 + 60초마다 POST /lectures/{id}/photos

/* ---------- 설정 ---------- */
const INTERVAL_SEC = 60;     // 자동 촬영 주기(초)
const JPEG_QUALITY = 0.92;   // 얼굴 인식을 위해 높은 화질 (원본 해상도 유지)

// 카메라가 지원하는 가장 높은 해상도로 열기.
// ideal 은 "가능하면 이 값"이라는 뜻이라, 카메라가 지원하는 범위 안에서 가장 가까운 해상도가 선택된다
// (4K 를 지원하지 않는 카메라도 오류 없이 그 카메라의 최대 해상도로 열린다).
const VIDEO_CONSTRAINTS = {
  width: { ideal: 4096 },
  height: { ideal: 2160 },
};

/* ---------- 요소 ---------- */
const lectureInfo = document.getElementById('lectureInfo');
const roomBtn = document.getElementById('roomBtn');
const roomPanel = document.getElementById('roomPanel');
const roomSelect = document.getElementById('room');
const roomValue = document.getElementById('roomValue');
const roomMsg = document.getElementById('roomMsg');

const video = document.getElementById('video');
const cameraMsg = document.getElementById('cameraMsg');
const shootBtn = document.getElementById('shootBtn');
const shootInfo = document.getElementById('shootInfo');
const recBadge = document.getElementById('recBadge');
const canvas = document.getElementById('canvas');
const flash = document.getElementById('flash');

/* ---------- 상태 ---------- */
const lectureId = requireLectureId();   // 없으면 과목 목록으로 이동
let lecture = null;      // GET /lectures/{id}
let timer = null;
let starting = false;    // start 요청 중 (중복 클릭 방지)
let count = 0;           // 업로드 성공한 사진 수
let lastResult = '';
let resolutionText = ''; // 카메라가 실제로 준 해상도 (예: 1920×1080)

/* ---------- 강의실 선택 ---------- */
function setPanelOpen(open) {
  roomPanel.classList.toggle('open', open);
  roomBtn.setAttribute('aria-expanded', open);
}

roomBtn.addEventListener('click', () => {
  setPanelOpen(!roomPanel.classList.contains('open'));
});

function roomLabel(roomNo) {
  return lecture && roomNo === lecture.room_no ? `${roomNo} (수업 강의실)` : roomNo;
}

roomSelect.addEventListener('change', () => {
  roomValue.textContent = roomLabel(roomSelect.value);
  setPanelOpen(false);
});

async function loadRooms() {
  let rooms;
  try {
    rooms = await api('/rooms');
  } catch (e) {
    roomMsg.textContent = `강의실 목록을 불러올 수 없어요. ${e.message}`;
    return;
  }
  // 카메라 연결 정보(camera)는 화면에 표시하지 않는다. 강의실 번호만.
  roomSelect.innerHTML = '';
  for (const r of rooms) roomSelect.add(new Option(roomLabel(r.room_no), r.room_no));
  if (lecture && rooms.some(r => r.room_no === lecture.room_no)) {
    roomSelect.value = lecture.room_no;
  }
  roomValue.textContent = roomSelect.value ? roomLabel(roomSelect.value) : '-';
  roomBtn.disabled = rooms.length < 2;
}

/* ---------- 카메라 연결 ---------- */
async function startCamera() {
  cameraMsg.style.display = 'flex';
  cameraMsg.textContent = '카메라 연결 중…';
  try {
    if (video.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop());
    }
    const stream = await navigator.mediaDevices.getUserMedia({ video: VIDEO_CONSTRAINTS, audio: false });
    video.srcObject = stream;
    cameraMsg.style.display = 'none';
    const s = stream.getVideoTracks()[0].getSettings();
    resolutionText = s.width && s.height ? `${s.width}×${s.height}` : '';
  } catch (err) {
    cameraMsg.textContent = '카메라를 연결할 수 없어요. 브라우저의 카메라 권한을 확인해 주세요.';
  }
}

/* ---------- 주기적 촬영 + 업로드 ---------- */
function updateInfo(extra) {
  shootInfo.textContent =
    `${count}장 확인됨 · ${INTERVAL_SEC}초마다 자동 촬영 중` +
    (resolutionText ? ` · ${resolutionText}` : '') +
    (lastResult ? ` · ${lastResult}` : '') +
    (extra ? ` · ${extra}` : '');
}

function canvasToBlob() {
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
}

async function capture() {
  if (!video.videoWidth) return;               // 카메라가 아직 준비 안 됨

  // 캡처 크기 = 카메라가 실제로 보내는 프레임 크기 (축소하지 않음)
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, w, h);

  // 찰칵 효과
  flash.classList.remove('go');
  void flash.offsetWidth;
  flash.classList.add('go');

  const blob = await canvasToBlob();
  if (!blob) return;
  const form = new FormData();
  form.append('photo', blob, 'capture.jpg');     // 파일명(확장자) 필수: 서버가 jpg/png 만 허용

  updateInfo('확인 중…');
  try {
    // 사진은 서버에서 처리만 하고 저장하지 않는다
    const data = await api(`/lectures/${lectureId}/photos`, { method: 'POST', form });
    count++;
    const s = data.summary;
    lastResult = `얼굴 ${data.face_count}명 중 ${data.matched_count}명 인식, 출석 ${s.present}/${s.total}명`;
    updateInfo();
  } catch (e) {
    updateInfo(`실패: ${e.message}`);
  }
}

async function startShooting() {
  if (!lecture || starting) return;
  starting = true;
  shootBtn.disabled = true;
  shootInfo.textContent = '수강생 출석부를 준비하는 중…';
  try {
    // 수강생 전원의 출석 행 준비 (이미 있으면 그대로, 여러 번 호출해도 안전)
    const res = await api(`/lectures/${lectureId}/start`, { method: 'POST' });
    shootInfo.textContent = `수강생 ${res.student_count}명`;
  } catch (e) {
    shootInfo.textContent = `촬영을 시작할 수 없어요. ${e.message}`;
    return;
  } finally {
    starting = false;
    shootBtn.disabled = false;
  }

  capture();                                   // 시작하자마자 1장
  timer = setInterval(capture, INTERVAL_SEC * 1000);
  shootBtn.textContent = '촬영 중지';
  shootBtn.classList.add('stop');
  recBadge.classList.add('on');
  roomBtn.disabled = true;                     // 촬영 중에는 강의실 변경 막기
  setPanelOpen(false);
  updateInfo();
}

function stopShooting() {
  clearInterval(timer);
  timer = null;
  shootBtn.textContent = '촬영 시작';
  shootBtn.classList.remove('stop');
  recBadge.classList.remove('on');
  roomBtn.disabled = roomSelect.options.length < 2;
  shootInfo.textContent = `촬영을 멈췄어요. 총 ${count}장으로 출석을 확인했어요.`;
}

shootBtn.addEventListener('click', () => {
  if (timer) stopShooting();
  else startShooting();
});

/* ---------- 시작 ---------- */
async function init() {
  document.getElementById('backLink').href = `method.html?lecture=${lectureId}`;
  document.getElementById('attendanceLink').href = `attendance.html?lecture=${lectureId}`;

  lecture = await showLectureInfo(lectureId, lectureInfo);
  await loadRooms();
  shootBtn.disabled = !lecture;
}

if (lectureId) {
  startCamera();
  init();
}
