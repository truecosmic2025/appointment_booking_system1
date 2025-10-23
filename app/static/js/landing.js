// Mobile nav toggle and small enhancements
document.addEventListener('DOMContentLoaded', () => {
  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();

  const btn = document.getElementById('mobileMenuBtn');
  const menu = document.getElementById('mobileMenu');
  if (btn && menu) {
    btn.addEventListener('click', () => {
      menu.classList.toggle('hidden');
    });
  }
});

window.addEventListener('load', () => {
  if (document.cookie.includes('googtrans=')) return;
  fetch('https://ipapi.co/json/')
    .then(r => (r.ok ? r.json() : Promise.reject()))
    .then(data => {
      if (!data || String(data.country).toUpperCase() !== 'ES') return;
      const apply = lang => {
        const sel = document.querySelector('select.goog-te-combo');
        if (!sel) return false;
        if (sel.value !== lang) {
          sel.value = lang;
          sel.dispatchEvent(new Event('change'));
        }
        return true;
      };
      let tries = 0;
      const max = 20;
      const id = setInterval(() => {
        tries += 1;
        if (apply('es') || tries >= max) clearInterval(id);
      }, 500);
    })
    .catch(() => {});
});
