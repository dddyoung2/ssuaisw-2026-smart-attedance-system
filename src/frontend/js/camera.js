// ===== 2페이지: 카메라 출결 =====

/* ---------- 설정 ---------- */
const INTERVAL_SEC = 10;   // 자동 촬영 주기(초)
const MAX_PHOTOS = 20;     // 저장할 최대 사진 수

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
  roomLabel.textContent = '선택한 강의실';
  roomValue.textContent = `${building.value} ${floor.value}층 ${room.value}호`;
  roomPanel.classList.remove('open');
  roomBtn.setAttribute('aria-expanded', false);
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

/* ---------- 주기적 촬영 ---------- */
let timer = null;
let count = 0;

function loadPhotos() {
  try {
    return JSON.parse(localStorage.getItem('photos')) || [];
  } catch (e) {
    return [];
  }
}

function savePhotos(photos) {
  try {
    localStorage.setItem('photos', JSON.stringify(photos.slice(0, MAX_PHOTOS)));
  } catch (e) {
    console.warn('사진 저장 실패:', e);
  }
}

function capture() {
  if (!video.videoWidth) return;   // 카메라가 아직 준비 안 됨

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const data = canvas.toDataURL('image/jpeg', 0.6);

  const photos = loadPhotos();
  photos.unshift({
    time: new Date().toLocaleTimeString('ko-KR'),
    room: roomValue.textContent,
    data
  });
  savePhotos(photos);

  count++;
  shootInfo.textContent = `${count}장 촬영됨 · ${INTERVAL_SEC}초마다 자동 촬영 중`;

  // 찰칵 효과
  flash.classList.remove('go');
  void flash.offsetWidth;
  flash.classList.add('go');
}

function startShooting() {
  capture();                                   // 시작하자마자 1장
  timer = setInterval(capture, INTERVAL_SEC * 1000);
  shootBtn.textContent = '촬영 중지';
  shootBtn.classList.add('stop');
  recBadge.classList.add('on');
}

function stopShooting() {
  clearInterval(timer);
  timer = null;
  shootBtn.textContent = '촬영 시작';
  shootBtn.classList.remove('stop');
  recBadge.classList.remove('on');
  shootInfo.textContent = `촬영을 멈췄어요. 총 ${count}장이 저장됐어요.`;
}

shootBtn.addEventListener('click', () => {
  if (timer) stopShooting();
  else startShooting();
});
