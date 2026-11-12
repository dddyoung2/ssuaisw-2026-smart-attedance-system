// ===== 3페이지: 출결 현황 =====
// (api.js 가 먼저 로드되어 있어야 함)

const REFRESH_SEC = 10;   // 카메라 페이지가 계속 촬영 중일 수 있으므로 주기적으로 새로고침

// 수업 회차: 주소의 ?session=번호 가 있으면 우선, 없으면 카메라 페이지에서 마지막으로 만든 회차
const sessionId = new URLSearchParams(location.search).get('session') || getCurrentSessionId();

const todayEl = document.getElementById('today');
const studentList = document.getElementById('studentList');
const photoGrid = document.getElementById('photoGrid');

let students = [];   // { id, name, present, manual, similarity }

/* ---------- 상단: 날짜 · 강의실 ---------- */
const todayText = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
todayEl.textContent = todayText;

async function loadSessionInfo() {
  if (!sessionId) return;
  try {
    const s = await api(`/sessions/${sessionId}`);
    const started = new Date(s.started_at).toLocaleString('ko-KR', {
      month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit'
    });
    todayEl.textContent = `${started} · ${s.room}`;
  } catch (e) { /* 날짜만 표시 */ }
}

/* ---------- 출결 표 ---------- */
function setSummary(total, present) {
  document.getElementById('total').textContent = total;
  document.getElementById('presentCnt').textContent = present;
  document.getElementById('absentCnt').textContent = total - present;
}

function showTableMessage(msg) {
  studentList.innerHTML = `<tr><td colspan="4" style="text-align:center">${escapeHtml(msg)}</td></tr>`;
  setSummary(0, 0);
}

function renderStudents() {
  if (!students.length) {
    showTableMessage('등록된 학생이 없어요. 서버의 /docs 에서 학생을 등록해 주세요.');
    return;
  }
  studentList.innerHTML = students.map((s, i) => {
    const sim = s.similarity == null ? '' : ` · 유사도 ${s.similarity.toFixed(2)}`;
    const how = s.manual ? '수동 지정' : '자동 인식';
    return `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(s.id)}</td>
      <td>${escapeHtml(s.name)}</td>
      <td class="status">
        <button class="badge ${s.present ? 'present' : 'absent'}" data-i="${i}"
          title="${how}${sim} — 눌러서 출석/결석 바꾸기">${s.present ? '출석' : '결석'}${s.manual ? ' ✎' : ''}</button>
      </td>
    </tr>`;
  }).join('');
  setSummary(students.length, students.filter(s => s.present).length);
}

function applyAttendance(data) {
  students = data.students.map(s => ({
    id: s.student_id,
    name: s.name,
    present: s.status === 'present',
    manual: s.source === 'manual',
    similarity: s.best_similarity
  }));
  renderStudents();
}

async function loadAttendance() {
  if (!sessionId) {
    showTableMessage('아직 진행한 수업이 없어요. 카메라 페이지에서 촬영을 시작해 보세요.');
    return;
  }
  try {
    applyAttendance(await api(`/sessions/${sessionId}/attendance`));
  } catch (e) {
    showTableMessage(e.message);
  }
}

// 배지를 누르면 출석/결석 수동 수정 (서버에 저장, 이후 사진이 올라와도 유지)
studentList.addEventListener('click', async e => {
  const btn = e.target.closest('button[data-i]');
  if (!btn) return;
  const s = students[btn.dataset.i];
  btn.disabled = true;
  try {
    const data = await api(`/sessions/${sessionId}/attendance/${encodeURIComponent(s.id)}`, {
      method: 'PATCH',
      json: { status: s.present ? 'absent' : 'present' }
    });
    applyAttendance(data);
  } catch (err) {
    alert(`출결을 바꾸지 못했어요.\n${err.message}`);
    btn.disabled = false;
  }
});

/* ---------- 촬영된 사진 ---------- */
let lastPhotoKey = '';

async function renderPhotos() {
  let photos = [];
  if (sessionId) {
    try {
      photos = await api(`/sessions/${sessionId}/photos`);
    } catch (e) {
      photoGrid.innerHTML = `<p class="empty">${escapeHtml(e.message)}</p>`;
      lastPhotoKey = '';
      return;
    }
  }

  // 변화가 없으면 다시 그리지 않음(주기적 새로고침 시 이미지 깜빡임 방지)
  const key = photos.map(p => p.photo_id).join(',');
  if (key === lastPhotoKey && photoGrid.children.length) return;
  lastPhotoKey = key;

  if (!photos.length) {
    photoGrid.innerHTML =
      '<p class="empty">아직 촬영된 사진이 없어요. 카메라 페이지에서 촬영을 시작해 보세요.</p>';
    return;
  }
  photoGrid.innerHTML = photos.map(p => {
    const time = new Date(p.captured_at).toLocaleTimeString('ko-KR');
    return `
    <figure>
      <img src="${apiUrl(p.image_url)}" alt="${time} 촬영 사진" loading="lazy">
      <figcaption>${time} · 얼굴 ${p.face_count}명</figcaption>
    </figure>`;
  }).join('');
}

document.getElementById('clearPhotos').addEventListener('click', async () => {
  if (!sessionId) return;
  if (!confirm('이 수업의 사진과 얼굴 인식 결과를 모두 지울까요?\n(수동으로 지정한 출결은 유지돼요)')) return;
  try {
    applyAttendance(await api(`/sessions/${sessionId}/photos`, { method: 'DELETE' }));
  } catch (e) {
    alert(`사진을 지우지 못했어요.\n${e.message}`);
  }
  renderPhotos();
});

/* ---------- 시작 ---------- */
function refresh() {
  loadAttendance();
  renderPhotos();
}

loadSessionInfo();
refresh();
if (sessionId) setInterval(refresh, REFRESH_SEC * 1000);
