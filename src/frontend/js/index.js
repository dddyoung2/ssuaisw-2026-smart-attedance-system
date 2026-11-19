// ===== 1. 과목 목록 (첫 화면) =====
// (api.js 가 먼저 로드되어 있어야 함)
// GET /courses → 과목 카드 (과목명 (과목코드), 대면 수업 출결 수 = 회차 수) → course.html?course=코드

const courseList = document.getElementById('courseList');
const listMsg = document.getElementById('listMsg');

function courseCard(c) {
  const href = `course.html?course=${encodeURIComponent(c.course_code)}`;
  return `
    <li class="course-card">
      <h2 class="course-title">${escapeHtml(c.course_name)} <span class="code">(${escapeHtml(c.course_code)})</span></h2>
      <div class="course-stat">
        <strong>${c.lecture_count}</strong><span>대면 수업 출결</span>
      </div>
      <a class="btn course-go" href="${href}">과목 홈 바로가기 <span aria-hidden="true">→</span></a>
    </li>`;
}

async function loadCourses() {
  try {
    const courses = await api('/courses');   // 서버가 과목명 순으로 정렬해서 준다
    courseList.innerHTML = courses.map(courseCard).join('');
    listMsg.textContent = courses.length
      ? ''
      : '등록된 과목이 없어요. 서버에서 예시 데이터(seed)를 먼저 넣어 주세요.';
  } catch (e) {
    listMsg.textContent = e.message;
  }
}

loadCourses();
