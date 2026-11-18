// ===== 3페이지: 출결 현황 =====
// (api.js 가 먼저 로드되어 있어야 함)
// 시퀀스 ④: GET /lectures/{id}/attendance 를 10초마다 다시 요청해 표시

const REFRESH_SEC = 10;

// 수업 회차: 주소의 ?lecture=번호 가 있으면 우선, 없으면 카메라 페이지에서 고른 회차
const lectureId = new URLSearchParams(location.search).get('lecture') || getCurrentLectureId();

const todayEl = document.getElementById('today');
const titleEl = document.getElementById('lectureTitle');
const studentList = document.getElementById('studentList');

todayEl.textContent = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });

function setSummary(s) {
  document.getElementById('total').textContent = s.total;
  document.getElementById('presentCnt').textContent = s.present;
  document.getElementById('absentCnt').textContent = s.absent;
}

function showMessage(msg) {
  studentList.innerHTML = `<tr><td colspan="4" style="text-align:center">${escapeHtml(msg)}</td></tr>`;
  setSummary({ total: 0, present: 0, absent: 0 });
}

function render(data) {
  const l = data.lecture;
  titleEl.textContent = `${l.course_name} · ${l.week}주차 ${l.session_no}차시`;
  todayEl.textContent = `${l.date} · ${l.room_no} 강의실`;
  setSummary(data.summary);

  if (!data.students.length) {
    showMessage('이 과목의 수강생이 없어요.');
    return;
  }
  studentList.innerHTML = data.students.map((s, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(s.student_id)}</td>
      <td>${escapeHtml(s.name)}</td>
      <td class="status">
        <span class="badge ${s.present ? 'present' : 'absent'}">${s.present ? '출석' : '결석'}</span>
      </td>
    </tr>`).join('');
}

async function refresh() {
  if (!lectureId) {
    showMessage('아직 선택한 수업이 없어요. 카메라 페이지에서 강의실과 수업을 골라 주세요.');
    return;
  }
  try {
    render(await api(`/lectures/${encodeURIComponent(lectureId)}/attendance`));
  } catch (e) {
    showMessage(e.message);
  }
}

refresh();
if (lectureId) setInterval(refresh, REFRESH_SEC * 1000);
