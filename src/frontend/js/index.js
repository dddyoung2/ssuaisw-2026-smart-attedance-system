// ===== 1페이지: 출결 방식 선택 =====
const eBtn = document.getElementById('eBtn');
const eOptions = document.getElementById('eOptions');

// 전자 출결 버튼 → 큐알/코드/카메라 버튼 펼치기
eBtn.addEventListener('click', () => {
  const open = eOptions.classList.toggle('open');
  eBtn.classList.toggle('active', open);
  eBtn.setAttribute('aria-expanded', open);
});

// 아직 만들지 않은 기능들
document.getElementById('manualBtn').addEventListener('click', () => {
  alert('수동 출결 페이지는 준비 중이에요.');
});
document.getElementById('qrBtn').addEventListener('click', () => {
  alert('QR 출결은 준비 중이에요.');
});
document.getElementById('codeBtn').addEventListener('click', () => {
  alert('코드 출결은 준비 중이에요.');
});
