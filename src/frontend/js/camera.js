// ===== 4. 카메라 출결 =====
// (api.js 가 먼저 로드되어 있어야 함)
//
// 수업 회차는 앞 화면에서 정해져 URL(?lecture=)로 넘어온다.
// 강의실: GET /rooms 목록, 기본값은 그 회차의 강의실. 다른 강의실을 골라도 DB 의 회차는 바꾸지 않는다.
//         (강의실 카메라 연동은 추후 작업. 지금은 이 브라우저의 카메라로 찍는다)
// 촬영 시작: POST /lectures/{id}/start → 즉시 1장 + 5분마다 POST /lectures/{id}/photos
//          + 지각 인정 시간(촬영 시작 후 N분)이 지났을 때 1장 더
// 미리보기: 카메라가 켜져 있는 동안 프레임을 줄여 POST /preview → 탐지된 얼굴 박스를 영상 위에 그린다
//          (검출만, 출석 기록 없음. 출석 사진을 처리하는 동안은 멈춘다)

/* ---------- 설정 ---------- */
const INTERVAL_SEC = 300;    // 자동 촬영 주기(초) = 5분
const LATE_MIN_MAX = 20;     // 지각 인정 시간 선택: 1~20분 (1분 단위)
const LATE_MIN_DEFAULT = 10;
const SAME_SHOT_SEC = 30;    // 정기 촬영과 지각 마감 촬영이 이 시간 안에 겹치면 마감 촬영 한 장만
const JPEG_QUALITY = 0.92;   // 얼굴 인식을 위해 높은 화질 (원본 해상도 유지)

// 카메라가 지원하는 가장 높은 해상도로 열기.
// ideal 은 "가능하면 이 값"이라는 뜻이라, 카메라가 지원하는 범위 안에서 가장 가까운 해상도가 선택된다
// (4K 를 지원하지 않는 카메라도 오류 없이 그 카메라의 최대 해상도로 열린다).
const VIDEO_CONSTRAINTS = {
  width: { ideal: 4096 },
  height: { ideal: 2160 },
};

// 실시간 얼굴 탐지 미리보기.
// 원본 해상도 검출은 CPU 에서 한 장에 약 20초라, 긴 변 960px 로 줄인 프레임으로 검출만 한다(약 0.5~1초).
// 줄인 화면이라 작은(먼) 얼굴은 박스가 안 나올 수 있다. 출석 판정은 capture() 가 원본 해상도로 따로 한다.
const PREVIEW_MAX_SIDE = 960;      // 서버 services/preview.py 와 같은 값
const PREVIEW_JPEG_QUALITY = 0.7;
const PREVIEW_GAP_MS = 100;        // 응답을 받고 다음 프레임을 보내기 전 쉬는 시간
const PREVIEW_IDLE_MS = 500;       // 카메라 준비 전·탭 숨김·출석 확인 중일 때 다시 확인하는 간격
const PREVIEW_RETRY_MS = 3000;     // 탐지 요청이 실패하면 이만큼 쉬고 다시 시도
const BOX_COLOR = '#4ADE80';

/* ---------- 요소 ---------- */
const lectureInfo = document.getElementById('lectureInfo');
const roomBtn = document.getElementById('roomBtn');
const roomPanel = document.getElementById('roomPanel');
const roomSelect = document.getElementById('room');
const roomValue = document.getElementById('roomValue');
const roomMsg = document.getElementById('roomMsg');
const lateSelect = document.getElementById('lateMin');

const video = document.getElementById('video');
const cameraMsg = document.getElementById('cameraMsg');
const shootBtn = document.getElementById('shootBtn');
const shootInfo = document.getElementById('shootInfo');
const recBadge = document.getElementById('recBadge');
const canvas = document.getElementById('canvas');
const flash = document.getElementById('flash');
const overlay = document.getElementById('overlay');
const faceBadge = document.getElementById('faceBadge');
const previewCanvas = document.createElement('canvas');   // 미리보기용 축소 프레임 (화면에 안 붙임)

/* ---------- 상태 ---------- */
const lectureId = requireLectureId();   // 없으면 과목 목록으로 이동
let lecture = null;      // GET /lectures/{id}
let timer = null;        // 정기 촬영 (5분마다)
let lateTimer = null;    // 지각 마감 촬영 (한 번)
let lateAt = 0;          // 지각 마감 시각 (ms)
let lateState = '';      // '' | 'done' | 'fail'
let starting = false;    // start 요청 중 (중복 클릭 방지)
let count = 0;           // 업로드 성공한 사진 수
let lastResult = '';
let resolutionText = ''; // 카메라가 실제로 준 해상도 (예: 1920×1080)
let uploading = false;   // 출석 사진 처리 중 (이때는 미리보기를 멈춘다)
let previewGen = 0;      // 출석 사진을 찍을 때마다 +1. 그 전에 보낸 미리보기 응답은 버린다
let previewResult = null; // 마지막 미리보기 결과 {width, height, boxes}

/* ---------- 지각 인정 시간 ---------- */
for (let m = 1; m <= LATE_MIN_MAX; m++) lateSelect.add(new Option(`${m}분`, m));
lateSelect.value = LATE_MIN_DEFAULT;

function clockText(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function lateText() {
  if (!lateAt) return '';
  if (lateState === 'done') return '지각 마감 사진 확인됨';
  if (lateState === 'fail') return '지각 마감 사진 실패';
  return `지각 마감 ${clockText(lateAt)}`;
}

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
  const late = lateText();
  shootInfo.textContent =
    `${count}장 확인됨 · ${INTERVAL_SEC / 60}분마다 자동 촬영 중` +
    (late ? ` · ${late}` : '') +
    (resolutionText ? ` · ${resolutionText}` : '') +
    (lastResult ? ` · ${lastResult}` : '') +
    (extra ? ` · ${extra}` : '');
}

function canvasToBlob() {
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
}

// 한 장 찍어 업로드. 업로드에 성공하면 true.
async function capture() {
  if (!video.videoWidth) return false;         // 카메라가 아직 준비 안 됨

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
  if (!blob) return false;
  const form = new FormData();
  form.append('photo', blob, 'capture.jpg');     // 파일명(확장자) 필수: 서버가 jpg/png 만 허용

  updateInfo('확인 중…');
  // 출석 사진을 처리하는 동안(CPU 약 20초)은 미리보기를 멈춰 서버 CPU 를 출석 판정에 쓴다
  uploading = true;
  previewGen++;
  clearPreview();
  try {
    // 사진은 서버에서 처리만 하고 저장하지 않는다
    const data = await api(`/lectures/${lectureId}/photos`, { method: 'POST', form });
    count++;
    const s = data.summary;
    lastResult = `얼굴 ${data.face_count}명 중 ${data.matched_count}명 인식, 출석 ${s.present}/${s.total}명`;
    updateInfo();
    return true;
  } catch (e) {
    updateInfo(`실패: ${e.message}`);
    return false;
  } finally {
    uploading = false;
  }
}

// 정기 촬영. 지각 마감 촬영과 겹치는 때(앞뒤 30초)는 마감 촬영이 대신 찍으므로 건너뛴다.
function periodicCapture() {
  if (lateAt && Math.abs(Date.now() - lateAt) < SAME_SHOT_SEC * 1000) return;
  capture();
}

// 지각 인정 시간이 지났을 때 한 장
async function lateCapture() {
  lateTimer = null;
  lateState = (await capture()) ? 'done' : 'fail';
  if (timer) updateInfo();
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

  // 지각 마감 = 촬영 시작 + 선택한 분 (DB 에 수업 시작 시간이 없어 촬영 시작을 기준으로 한다)
  const lateMs = Number(lateSelect.value) * 60 * 1000;
  lateAt = Date.now() + lateMs;
  lateState = '';
  lateTimer = setTimeout(lateCapture, lateMs);

  timer = setInterval(periodicCapture, INTERVAL_SEC * 1000);
  shootBtn.textContent = '촬영 중지';
  shootBtn.classList.add('stop');
  recBadge.classList.add('on');
  roomBtn.disabled = true;                     // 촬영 중에는 강의실·지각 인정 시간 변경 막기
  lateSelect.disabled = true;
  setPanelOpen(false);
  updateInfo();
  capture();                                   // 시작하자마자 1장
}

function stopShooting() {
  clearInterval(timer);
  clearTimeout(lateTimer);
  timer = null;
  lateTimer = null;
  lateAt = 0;
  shootBtn.textContent = '촬영 시작';
  shootBtn.classList.remove('stop');
  recBadge.classList.remove('on');
  roomBtn.disabled = roomSelect.options.length < 2;
  lateSelect.disabled = false;
  shootInfo.textContent = `촬영을 멈췄어요. 총 ${count}장으로 출석을 확인했어요.`;
}

shootBtn.addEventListener('click', () => {
  if (timer) stopShooting();
  else startShooting();
});

/* ---------- 실시간 얼굴 탐지 미리보기 ---------- */
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function clearPreview() {
  previewResult = null;
  faceBadge.textContent = '';
  drawBoxes();
}

// 박스 그리기. 영상은 object-fit: cover 로 화면을 꽉 채우며 잘려 보이므로 같은 변환을 적용한다.
function drawBoxes() {
  const dpr = window.devicePixelRatio || 1;
  const cw = overlay.clientWidth;
  const ch = overlay.clientHeight;
  const pw = Math.round(cw * dpr);
  const ph = Math.round(ch * dpr);
  if (overlay.width !== pw || overlay.height !== ph) {
    overlay.width = pw;
    overlay.height = ph;
  }
  const ctx = overlay.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, pw, ph);

  const r = previewResult;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!r || !vw || !r.width) return;
  const s = Math.max(cw / vw, ch / vh);   // 원본 프레임 → 화면 (cover)
  const ox = (cw - vw * s) / 2;
  const oy = (ch - vh * s) / 2;
  const k = (vw / r.width) * s;           // 미리보기 이미지 → 화면 (가로세로 비율은 원본과 같음)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.strokeStyle = BOX_COLOR;
  ctx.lineWidth = 2;
  for (const b of r.boxes) ctx.strokeRect(ox + b.x * k, oy + b.y * k, b.w * k, b.h * k);
}

// 현재 프레임을 긴 변 PREVIEW_MAX_SIDE 이하로 줄여 JPEG 로
function previewFrame() {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const scale = Math.min(1, PREVIEW_MAX_SIDE / Math.max(vw, vh));
  const w = Math.round(vw * scale);
  const h = Math.round(vh * scale);
  if (previewCanvas.width !== w || previewCanvas.height !== h) {
    previewCanvas.width = w;
    previewCanvas.height = h;
  }
  previewCanvas.getContext('2d').drawImage(video, 0, 0, w, h);
  return new Promise(resolve => previewCanvas.toBlob(resolve, 'image/jpeg', PREVIEW_JPEG_QUALITY));
}

// 요청은 한 번에 하나만: 응답이 오면 다음 프레임을 보낸다 (갱신 간격 ≈ 서버 탐지 시간)
async function previewLoop() {
  for (;;) {
    if (!video.videoWidth || document.hidden || uploading) {
      await sleep(PREVIEW_IDLE_MS);
      continue;
    }
    const gen = previewGen;
    let wait = PREVIEW_GAP_MS;
    try {
      const blob = await previewFrame();
      if (!blob) throw new Error('프레임 캡처 실패');
      const form = new FormData();
      form.append('photo', blob, 'frame.jpg');
      const r = await api('/preview', { method: 'POST', form });
      if (gen === previewGen && !uploading) {   // 그사이 출석 사진을 찍었으면 버림
        previewResult = r;
        faceBadge.textContent = `탐지된 얼굴 ${r.boxes.length}개`;
        drawBoxes();
      }
    } catch (e) {
      if (gen === previewGen && !uploading) {
        clearPreview();
        faceBadge.textContent = '얼굴 탐지 실패';
      }
      wait = PREVIEW_RETRY_MS;
    }
    await sleep(wait);
  }
}

window.addEventListener('resize', drawBoxes);

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
  previewLoop();
}
