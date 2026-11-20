// ===== 공용: 백엔드 API 호출 =====

// 백엔드 주소
//  - 백엔드가 직접 서빙(/app/...)하면 → 같은 서버 (포트 상관없음)
//  - Live Server(5500) 등으로 열면    → 같은 호스트(127.0.0.1/localhost)의 8000번 포트
const API_BASE = location.pathname.startsWith('/app/')
  ? location.origin
  : `${location.protocol}//${location.hostname}:8000`;

// API 경로(/lectures/1/attendance 등)를 절대주소로
function apiUrl(path) {
  return API_BASE + path;
}

// fetch 래퍼: 실패하면 서버의 detail 메시지로 Error 를 던진다.
async function api(path, { method = 'GET', json, form } = {}) {
  const opts = { method };
  if (json !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(json);
  } else if (form) {
    opts.body = form;               // Content-Type 은 브라우저가 boundary 포함해 자동 설정
  }

  let res;
  try {
    res = await fetch(apiUrl(path), opts);
  } catch (e) {
    throw new Error('백엔드 서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.');
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && data.detail;
    const msg = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg).join(', ')
      : `요청 실패 (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

// 서버 데이터를 innerHTML 에 넣을 때 사용
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// ===== 선택한 수업 회차(lecture_id) =====
// 화면 사이에는 URL 쿼리(?lecture=7)로 넘기고, 마지막 값은 localStorage 에도 저장해 둔다.
const LECTURE_KEY = 'currentLectureId';

function getCurrentLectureId() {
  try { return localStorage.getItem(LECTURE_KEY); } catch (e) { return null; }
}

function setCurrentLectureId(id) {
  try { localStorage.setItem(LECTURE_KEY, id); } catch (e) {}
}

// URL 의 ?lecture= → 없으면 마지막으로 고른 회차 → 그것도 없으면 과목 목록으로 이동(null 반환)
function requireLectureId() {
  const id = new URLSearchParams(location.search).get('lecture') || getCurrentLectureId();
  if (!id || !/^\d+$/.test(id)) {
    location.replace('index.html');
    return null;
  }
  setCurrentLectureId(id);
  return id;
}

// ===== 날짜·회차 표시 =====
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

// 'YYYY-MM-DD' → 로컬 날짜 (new Date('YYYY-MM-DD')는 UTC 로 해석돼 하루 밀릴 수 있음)
function parseISODate(s) {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

// 브라우저 기준 오늘 날짜 (YYYY-MM-DD)
function todayISO() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// '2026-09-15' → '9/15 (화)'
function formatDate(iso) {
  const d = parseISODate(iso);
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEKDAYS[d.getDay()]})`;
}

// 주차-차수, 예: 3-1
function weekLabel(l) {
  return `${l.week}-${l.session_no}`;
}

// 수업 정보 한 줄: '알고리즘 (2150163303) · 3-1 · 9/15 (화) · 21304'
function lectureLine(l) {
  return `${l.course_name} (${l.course_code}) · ${weekLabel(l)} · ${formatDate(l.date)} · ${l.room_no}`;
}

// GET /lectures/{id} 로 수업 정보를 받아 el 에 한 줄로 표시. 실패하면 메시지를 표시하고 null.
async function showLectureInfo(lectureId, el) {
  try {
    const l = await api(`/lectures/${encodeURIComponent(lectureId)}`);
    el.textContent = lectureLine(l);
    return l;
  } catch (e) {
    el.textContent = `${e.message} 과목 목록에서 수업을 다시 골라 주세요.`;
    el.classList.add('error');
    return null;
  }
}
