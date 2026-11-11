// ===== 2페이지: 카메라 출결 =====
// (api.js 가 먼저 로드되어 있어야 함: API_BASE, api(), setCurrentSessionId())

/* ---------- 설정 ---------- */
const INTERVAL_SEC = 60;     // 자동 촬영 주기(초)
const JPEG_QUALITY = 0.8;    // 얼굴 인식을 위해 0.6 → 0.8

/* ---------- 요소 ---------- */
const roomBtn = document.getElementById('roomBtn');
const roomPanel = document.getElementById('roomPanel');
const building = document.getElementById('building');
const floor = document.getElementById('floor');
const room = document.getElementById('room');
const roomLabel = document.getElementById('roomLabel');
const roomValue = document.getElementById('roomValue');

const video = document.getElementById('video');
const cameraMsg = document.getElementById('cameraMsg');
const shootBtn = document.getElementById('shootBtn');
const shootInfo = document.getElementById('shootInfo');
const recBadge = document.getElementById('recBadge');
const canvas = document.getElementById('canvas');
const flash = document.getElementById('flash');

/* ---------- 강의실 선택 ---------- */
for (let f = 1; f <= 5; f++) {
  floor.add(new Option(f + '층', f));
}

function fillRooms() {
  room.innerHTML = '';
  for (let r = 1; r <= 6; r++) {
    const no = floor.value + '0' + r;
    room.add(new Option(no + '호', no));
  }
}

// 기본값: 배정 강의실
floor.value = 3;
fillRooms();
room.value = '301';

floor.addEventListener('change', fillRooms);

roomBtn.addEventListener('click', () => {
  const open = roomPanel.classList.toggle('open');
  roomBtn.setAttribute('aria-expanded', open);
});

document.getElementById('applyRoom').addEventListener('click', () => {
  if (timer) stopShooting();   // 촬영 중 강의실을 바꾸면 멈춤
  roomLabel.textContent = '선택한 강의실';
  roomValue.textContent = `${building.value} ${floor.value}층 ${room.value}호`;
  roomPanel.classList.remove('open');
  roomBtn.setAttribute('aria-expanded', false);
  sessionId = null;            // 강의실이 바뀌면 다음 촬영 때 새 수업 회차 생성
  // 실제 서비스에서는 여기서 선택한 강의실의 카메라 스트림 주소로 바꿔 연결합니다.
  startCamera();
});

/* ---------- 카메라 연결 ---------- */
async function startCamera() {
  cameraMsg.style.display = 'flex';
  cameraMsg.textContent = '카메라 연결 중…';
  try {
    if (video.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop());
    }
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = stream;
    cameraMsg.style.display = 'none';
  } catch (err) {
    cameraMsg.textContent = '카메라를 연결할 수 없어요. 브라우저의 카메라 권한을 확인해 주세요.';
  }
}

startCamera();

/* ---------- 수업 회차 ---------- */
let sessionId = null;

// 이 페이지에서 처음 촬영을 시작할 때(또는 강의실을 바꾼 뒤) 수업 회차를 만든다.
async function ensureSession() {
  if (sessionId) return sessionId;
  const sess = await api('/sessions', { method: 'POST', json: { room: roomValue.textContent } });
  sessionId = sess.session_id;
  setCurrentSessionId(sessionId);
  return sessionId;
}

/* ---------- 주기적 촬영 + 업로드 ---------- */
let timer = null;
let count = 0;          // 업로드 성공한 사진 수
let lastResult = '';    // 마지막 인식 결과 문구

function updateInfo(extra) {
  shootInfo.textContent =
    `${count}장 업로드됨 · ${INTERVAL_SEC}초마다 자동 촬영 중` +
    (lastResult ? ` · ${lastResult}` : '') +
    (extra ? ` · ${extra}` : '');
}

function canvasToBlob() {
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
}

async function capture() {
  if (!video.videoWidth || !sessionId) return;   // 카메라/세션이 아직 준비 안 됨

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  // 찰칵 효과
  flash.classList.remove('go');
  void flash.offsetWidth;
  flash.classList.add('go');

  const blob = await canvasToBlob();
  if (!blob) return;
  const form = new FormData();
  form.append('photo', blob, 'capture.jpg');     // 파일명(확장자) 필수: 서버가 jpg/png 만 허용

  updateInfo('업로드 중…');
  try {
    const data = await api(`/sessions/${sessionId}/photos`, { method: 'POST', form });
    count++;
    const s = data.attendance.summary;
    lastResult = `얼굴 ${data.photo.face_count}명 인식, 출석 ${s.present}/${s.total}명`;
    updateInfo();
  } catch (e) {
    updateInfo(`업로드 실패: ${e.message}`);
  }
}

async function startShooting() {
  shootBtn.disabled = true;
  try {
    await ensureSession();
  } catch (e) {
    alert(`수업을 시작할 수 없어요.\n${e.message}`);
    return;
  } finally {
    shootBtn.disabled = false;
  }

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
  shootInfo.textContent = `촬영을 멈췄어요. 총 ${count}장이 서버에 저장됐어요.`;
}

shootBtn.addEventListener('click', () => {
  if (timer) stopShooting();
  else startShooting();
});
