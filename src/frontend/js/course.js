// ===== 2. 과목 홈: 회차 목록 =====
// (api.js 가 먼저 로드되어 있어야 함)
// GET /courses/{code} + GET /courses/{code}/lectures → 표 (주차 | 수업일 | 출결 체크)
// [출결 확인] → method.html?lecture=<lecture_id>

const courseCode = new URLSearchParams(location.search).get('course');

const courseNameEl = document.getElementById('courseName');
const lectureList = document.getElementById('lectureList');
const sortButtons = document.querySelectorAll('.seg button');

let lectures = [];
let sortKey = 'date';
let scrolledToToday = false;

// 정렬: 수업일순 = 날짜 → 주차 → 차수, 주차순 = 주차 → 차수 → 날짜
const SORTS = {
  date: (a, b) => a.date.localeCompare(b.date) || a.week - b.week || a.session_no - b.session_no,
  week: (a, b) => a.week - b.week || a.session_no - b.session_no || a.date.localeCompare(b.date),
};

function showMessage(msg) {
  lectureList.innerHTML = `<tr><td colspan="3" class="empty-row">${escapeHtml(msg)}</td></tr>`;
}

function row(l, today) {
  const isToday = l.date === today;
  return `
    <tr${isToday ? ' class="today"' : ''}>
      <td class="week"><span class="week-badge">${weekLabel(l)}</span></td>
      <td>
        <div class="lec-date">${formatDate(l.date)}${isToday ? ' <span class="today-tag">오늘</span>' : ''}</div>
        <div class="lec-room">${escapeHtml(l.room_no)}</div>
      </td>
      <td class="action">
        <a class="btn outline small" href="method.html?lecture=${l.lecture_id}">출결 확인</a>
      </td>
    </tr>`;
}

function render() {
  if (!lectures.length) {
    showMessage('등록된 수업 회차가 없어요.');
    return;
  }
  const today = todayISO();
  lectureList.innerHTML = [...lectures].sort(SORTS[sortKey]).map(l => row(l, today)).join('');

  // 처음 열 때 오늘 회차가 보이도록
  const todayRow = lectureList.querySelector('tr.today');
  if (todayRow && !scrolledToToday) {
    todayRow.scrollIntoView({ block: 'center' });
    scrolledToToday = true;
  }
}

sortButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    sortKey = btn.dataset.sort;
    sortButtons.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    render();
  });
});

async function load() {
  const code = encodeURIComponent(courseCode);
  try {
    const [course, list] = await Promise.all([
      api(`/courses/${code}`),
      api(`/courses/${code}/lectures`),
    ]);
    courseNameEl.textContent = `${course.course_name} (${course.course_code})`;
    document.title = `${course.course_name} · 과목 홈`;
    lectures = list;
    render();
  } catch (e) {
    courseNameEl.textContent = '';
    showMessage(e.message);
  }
}

if (!courseCode) {
  location.replace('index.html');        // 과목이 없으면 과목 목록으로
} else {
  load();
}
