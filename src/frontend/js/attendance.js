// ===== 5. 출결 현황 =====
// (api.js 가 먼저 로드되어 있어야 함)
// GET /lectures/{id}/attendance 를 10초마다 다시 요청해 표시
// ← 뒤로: camera.html?lecture=<id>

const REFRESH_SEC = 10;

const lectureId = requireLectureId();   // 없으면 과목 목록으로 이동

const lectureInfo = document.getElementById('lectureInfo');
const studentList = document.getElementById('studentList');

function setSummary(s) {
  document.getElementById('total').textContent = s.total;
  document.getElementById('presentCnt').textContent = s.present;
  document.getElementById('absentCnt').textContent = s.absent;
}

function showMessage(msg) {
  studentList.innerHTML = `<tr><td colspan="4" class="empty-row">${escapeHtml(msg)}</td></tr>`;
  setSummary({ total: 0, present: 0, absent: 0 });
}

function render(data) {
  lectureInfo.textContent = lectureLine(data.lecture);
  lectureInfo.classList.remove('error');
  setSummary(data.summary);

  if (!data.students.length) {
    showMessage('아직 출석부가 없어요. 카메라 화면에서 촬영을 시작하면 수강생 명단이 만들어져요.');
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
  try {
    render(await api(`/lectures/${encodeURIComponent(lectureId)}/attendance`));
  } catch (e) {
    lectureInfo.textContent = `${e.message} 과목 목록에서 수업을 다시 골라 주세요.`;
    lectureInfo.classList.add('error');
    showMessage(e.message);
  }
}

if (lectureId) {
  document.getElementById('backLink').href = `camera.html?lecture=${lectureId}`;
  refresh();
  setInterval(refresh, REFRESH_SEC * 1000);
}
