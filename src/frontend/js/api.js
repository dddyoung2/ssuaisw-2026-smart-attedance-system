// ===== 공용: 백엔드 API 호출 =====

// 백엔드 주소
//  - 백엔드가 직접 서빙(/app/...)하면 → 같은 서버 (포트 상관없음)
//  - Live Server(5500) 등으로 열면    → 같은 호스트(127.0.0.1/localhost)의 8000번 포트
const API_BASE = location.pathname.startsWith('/app/')
  ? location.origin
  : `${location.protocol}//${location.hostname}:8000`;

// 응답 안의 상대경로(/photos/1/image 등)를 절대주소로
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

// 두 페이지가 같은 수업 회차를 보도록 localStorage 에 공유
const SESSION_KEY = 'currentSessionId';

function getCurrentSessionId() {
  try { return localStorage.getItem(SESSION_KEY); } catch (e) { return null; }
}

function setCurrentSessionId(id) {
  try { localStorage.setItem(SESSION_KEY, id); } catch (e) {}
}
