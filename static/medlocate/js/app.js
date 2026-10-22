const toggle = document.querySelector('.menu-toggle');
const nav = document.querySelector('.main-nav');
toggle?.addEventListener('click', () => {
  const open = nav.classList.toggle('is-open');
  toggle.setAttribute('aria-expanded', String(open));
});

const dropdowns = [...document.querySelectorAll('.nav-dropdown')];
dropdowns.forEach((dropdown) => dropdown.addEventListener('toggle', () => {
  if (!dropdown.open) return;
  dropdowns.forEach((other) => { if (other !== dropdown) other.removeAttribute('open'); });
}));
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  dropdowns.forEach((dropdown) => dropdown.removeAttribute('open'));
  nav?.classList.remove('is-open');
  toggle?.setAttribute('aria-expanded', 'false');
});
nav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
  nav.classList.remove('is-open');
  toggle?.setAttribute('aria-expanded', 'false');
}));

document.querySelectorAll('[data-carousel]').forEach((carousel) => {
  const slides = [...carousel.querySelectorAll('[data-carousel-slide]')];
  const dots = [...carousel.querySelectorAll('[data-carousel-dot]')];
  if (slides.length < 2) return;
  let index = 0;
  let timer;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const show = (nextIndex) => {
    index = (nextIndex + slides.length) % slides.length;
    slides.forEach((slide, position) => {
      const active = position === index;
      slide.classList.toggle('is-active', active);
      slide.setAttribute('aria-hidden', String(!active));
    });
    dots.forEach((dot, position) => {
      const active = position === index;
      dot.classList.toggle('is-active', active);
      dot.setAttribute('aria-current', String(active));
    });
  };
  const stop = () => window.clearInterval(timer);
  const start = () => {
    stop();
    if (!reducedMotion) timer = window.setInterval(() => show(index + 1), 6000);
  };

  carousel.querySelector('[data-carousel-previous]')?.addEventListener('click', () => { show(index - 1); start(); });
  carousel.querySelector('[data-carousel-next]')?.addEventListener('click', () => { show(index + 1); start(); });
  dots.forEach((dot) => dot.addEventListener('click', () => { show(Number(dot.dataset.carouselDot)); start(); }));
  carousel.addEventListener('mouseenter', stop);
  carousel.addEventListener('mouseleave', start);
  carousel.addEventListener('focusin', stop);
  carousel.addEventListener('focusout', start);
  start();
});

const loginPanel = document.querySelector('[data-login-panel]');
const loginOpeners = [...document.querySelectorAll('[data-login-open]')];
let lastLoginOpener;
const syncLoginClosed = () => {
  loginOpeners.forEach(opener => opener.setAttribute('aria-expanded', 'false'));
  const password = document.getElementById('dropdown-password');
  const reveal = loginPanel?.querySelector('[data-password-toggle]');
  if (password) password.type = 'password';
  if (reveal) { reveal.textContent = 'Show'; reveal.setAttribute('aria-label', 'Show password'); reveal.setAttribute('aria-pressed', 'false'); }
  lastLoginOpener?.focus();
};
const closeLogin = () => { if (loginPanel?.open) loginPanel.close(); };
const openLogin = () => {
  if (!loginPanel || loginPanel.open) return;
  document.querySelectorAll('.nav-dropdown').forEach(dropdown => dropdown.removeAttribute('open'));
  nav?.classList.remove('is-open');
  toggle?.setAttribute('aria-expanded', 'false');
  loginPanel.show();
  loginOpeners.forEach(opener => opener.setAttribute('aria-expanded', 'true'));
  document.getElementById('dropdown-username')?.focus({preventScroll: true});
};
loginOpeners.forEach(opener => opener.addEventListener('click', event => {
  if (!loginPanel) return;
  event.preventDefault(); lastLoginOpener = opener; openLogin();
}));
loginPanel?.addEventListener('close', syncLoginClosed);
loginPanel?.querySelector('[data-login-close]')?.addEventListener('click', closeLogin);
document.addEventListener('click', event => {
  if (loginPanel?.open && !loginPanel.contains(event.target) && !event.target.closest('[data-login-open]')) closeLogin();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && loginPanel?.open) closeLogin();
});
loginPanel?.querySelector('[data-password-toggle]')?.addEventListener('click', event => {
  const password = document.getElementById('dropdown-password');
  const visible = password.type === 'password';
  password.type = visible ? 'text' : 'password';
  event.currentTarget.textContent = visible ? 'Hide' : 'Show';
  event.currentTarget.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  event.currentTarget.setAttribute('aria-pressed', String(visible));
});
if (window.location.hash === '#sign-in') openLogin();
window.addEventListener('hashchange', () => { if (window.location.hash === '#sign-in') openLogin(); });
