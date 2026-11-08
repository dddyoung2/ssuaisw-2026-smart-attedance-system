// ===== 3페이지: 출결 현황 =====

/* 오늘 날짜 표시 */
document.getElementById('today').textContent =
  new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });

/* 예시 학생 데이터 (나중에 서버/얼굴인식 결과로 교체) */
const students = [
  { id: '20231001', name: '김민준', present: true },
  { id: '20231002', name: '이서연', present: true },
  { id: '20231003', name: '박도윤', present: false },
  { id: '20231004', name: '최지우', present: true },
  { id: '20231005', name: '정하준', present: true },
  { id: '20231006', name: '강수아', present: false },
  { id: '20231007', name: '윤시우', present: true },
  { id: '20231008', name: '한예린', present: true }
];

const studentList = document.getElementById('studentList');
const photoGrid = document.getElementById('photoGrid');

/* ---------- 출결 표 ---------- */
function renderStudents() {
  studentList.innerHTML = students.map((s, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${s.id}</td>
      <td>${s.name}</td>
      <td class="status">
        <button class="badge ${s.present ? 'present' : 'absent'}" data-i="${i}"
          title="눌러서 출석/결석 바꾸기">${s.present ? '출석' : '결석'}</button>
      </td>
    </tr>`).join('');

  const presentCount = students.filter(s => s.present).length;
  document.getElementById('total').textContent = students.length;
  document.getElementById('presentCnt').textContent = presentCount;
  document.getElementById('absentCnt').textContent = students.length - presentCount;
}

// 배지를 누르면 출석/결석 수동 수정
studentList.addEventListener('click', e => {
  const i = e.target.dataset.i;
  if (i === undefined) return;
  students[i].present = !students[i].present;
  renderStudents();
});

/* ---------- 촬영된 사진 ---------- */
function loadPhotos() {
  try {
    return JSON.parse(localStorage.getItem('photos')) || [];
  } catch (e) {
    return [];
  }
}

function renderPhotos() {
  const photos = loadPhotos();
  if (!photos.length) {
    photoGrid.innerHTML =
      '<p class="empty">아직 촬영된 사진이 없어요. 카메라 페이지에서 촬영을 시작해 보세요.</p>';
    return;
  }
  photoGrid.innerHTML = photos.map(p => `
    <figure>
      <img src="${p.data}" alt="${p.time} 촬영 사진">
      <figcaption>${p.time} · ${p.room}</figcaption>
    </figure>`).join('');
}

document.getElementById('clearPhotos').addEventListener('click', () => {
  try { localStorage.removeItem('photos'); } catch (e) {}
  renderPhotos();
});

/* ---------- 시작 ---------- */
renderStudents();
renderPhotos();
