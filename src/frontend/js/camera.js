// ===== 2페이지: 카메라 출결 =====
// (api.js 가 먼저 로드되어 있어야 함: api(), setCurrentLectureId(), todayISO())
//
// 시퀀스 ② 강의실·카메라 선택 → 오늘 수업 회차 확인 → 회차 시작
//        ③ 촬영 시작: 즉시 1장, 이후 60초마다 단체 사진 업로드

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
const roomBtn = document.getElementById('roomBtn');
const roomPanel = document.getElementById('roomPanel');
const roomSelect = document.getElementById('room');
const findLectureBtn = document.getElementById('findLecture');
const lecturePick = document.getElementById('lecturePick');
const lectureSelect = document.getElementById('lecture');
const applyLectureBtn = document.getElementById('applyLecture');
const roomMsg = document.getElementById('roomMsg');
const roomLabel = document.getElementById('roomLabel');
const roomValue = document.getElementById('roomValue');

const video = document.getElementById('video');
const cameraMsg = document.getElementById('cameraMsg');
const shootBtn = document.getElementById('shootBtn');
const shootInfo = document.getElementById('shootInfo');
const recBadge = document.getElementById('recBadge');
const canvas = document.getElementById('canvas');
const flash = document.getElementById('flash');

/* ---------- 상태 ---------- */
let rooms = [];          // [{room_no, camera}]
let lectures = [];       // 오늘 이 강의실의 회차 목록
let lectureId = null;    // 확정된 회차
let timer = null;
let count = 0;           // 업로드 성공한 사진 수
let lastResult = '';
let resolutionText = ''; // 카메라가 실제로 준 해상도 (예: 1920×1080)

function setPanelOpen(open) {
  roomPanel.classList.toggle('open', open);
  roomBtn.setAttribute('aria-expanded', open);
}

roomBtn.addEventListener('click', () => {
  setPanelOpen(!roomPanel.classList.contains('open'));
});

function lectureLabel(l) {
  return `${l.course_name} · ${l.week}주차 ${l.session_no}차시`;
}

/* ---------- ② 강의실 목록 ---------- */
async function loadRooms() {
  roomMsg.textContent = '강의실 목록을 불러오는 중…';
  try {
    rooms = await api('/rooms');
  } catch (e) {
    roomMsg.textContent = e.message;
    return;
  }
  roomSelect.innerHTML = '';
  for (const r of rooms) {
    roomSelect.add(new Option(r.camera ? `${r.room_no} · ${r.camera}` : r.room_no, r.room_no));
  }
  roomMsg.textContent = rooms.length
    ? ''
    : '등록된 강의실이 없어요. 서버에서 예시 데이터(seed)를 먼저 넣어 주세요.';
  findLectureBtn.disabled = !rooms.length;
}

/* ---------- ② 오늘 수업 회차 확인 ---------- */
findLectureBtn.addEventListener('click', async () => {
  if (timer) stopShooting();
  resetLecture();
  const roomNo = roomSelect.value;
  if (!roomNo) return;

  findLectureBtn.disabled = true;
  roomMsg.textContent = '오늘 수업을 찾는 중…';
  try {
    lectures = await api(`/lectures?room_no=${encodeURIComponent(roomNo)}&date=${todayISO()}`);
  } catch (e) {
    roomMsg.textContent = e.message;
    return;
  } finally {
    findLectureBtn.disabled = false;
  }

  if (!lectures.length) {
    roomMsg.textContent = '오늘 이 강의실에 등록된 수업이 없습니다.';
    return;
  }
  if (lectures.length === 1) {          // 하나면 바로 확정
    roomMsg.textContent = '';
    await startLecture(lectures[0]);
    return;
  }
  // 여러 개면 교수가 고른다 (LECTURE 에 시간 정보가 없음)
  lectureSelect.innerHTML = '';
  lectures.forEach((l, i) => lectureSelect.add(new Option(lectureLabel(l), i)));
  lecturePick.hidden = false;
  roomMsg.textContent = `오늘 이 강의실에 수업이 ${lectures.length}개 있어요. 진행할 수업을 골라 주세요.`;
});

applyLectureBtn.addEventListener('click', () => {
  const l = lectures[Number(lectureSelect.value)];
  if (l) startLecture(l);
});

function resetLecture() {
  lectureId = null;
  lectures = [];
  lecturePick.hidden = true;
  shootBtn.disabled = true;
  count = 0;
  lastResult = '';
}

// 회차 확정 → 수강생 출석 행 준비 (POST /lectures/{id}/start)
async function startLecture(l) {
  applyLectureBtn.disabled = true;
  try {
    const res = await api(`/lectures/${l.lecture_id}/start`, { method: 'POST' });
    lectureId = l.lecture_id;
    setCurrentLectureId(lectureId);
    roomLabel.textContent = `${l.room_no} 강의실 · ${l.date}`;
    roomValue.textContent = lectureLabel(l);
    lecturePick.hidden = true;
    roomMsg.textContent = '';
    setPanelOpen(false);
    shootBtn.disabled = false;
    shootInfo.textContent =
      `수강생 ${res.student_count}명 · 촬영을 시작하면 ${INTERVAL_SEC}초마다 자동으로 출석을 확인해요.`;
  } catch (e) {
    roomMsg.textContent = `수업을 시작할 수 없어요. ${e.message}`;
  } finally {
    applyLectureBtn.disabled = false;
  }
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

/* ---------- ③ 주기적 촬영 + 업로드 ---------- */
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
  if (!video.videoWidth || !lectureId) return;   // 카메라/회차가 아직 준비 안 됨

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

function startShooting() {
  if (!lectureId) return;
  capture();                                   // 시작하자마자 1장
  timer = setInterval(capture, INTERVAL_SEC * 1000);
  shootBtn.textContent = '촬영 중지';
  shootBtn.classList.add('stop');
  recBadge.classList.add('on');
  updateInfo();
}

function stopShooting() {
  clearInterval(timer);
  timer = null;
  shootBtn.textContent = '촬영 시작';
  shootBtn.classList.remove('stop');
  recBadge.classList.remove('on');
  shootInfo.textContent = `촬영을 멈췄어요. 총 ${count}장으로 출석을 확인했어요.`;
}

shootBtn.addEventListener('click', () => {
  if (timer) stopShooting();
  else startShooting();
});

/* ---------- 시작 ---------- */
startCamera();
loadRooms();
