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
const closeLogin = () => {
  if (!loginPanel) return;
  loginPanel.hidden = true;
  loginPanel.classList.remove('is-open');
  loginOpeners.forEach((opener) => opener.setAttribute('aria-expanded', 'false'));
};
const openLogin = () => {
  if (!loginPanel) return;
  document.querySelectorAll('.nav-dropdown').forEach((dropdown) => dropdown.removeAttribute('open'));
  loginPanel.hidden = false;
  window.requestAnimationFrame(() => loginPanel.classList.add('is-open'));
  loginOpeners.forEach((opener) => opener.setAttribute('aria-expanded', 'true'));
  loginPanel.querySelector('input[name="username"]')?.focus();
};
loginOpeners.forEach((opener) => opener.addEventListener('click', (event) => {
  if (!loginPanel) return;
  event.preventDefault();
  loginPanel.hidden ? openLogin() : closeLogin();
}));
loginPanel?.querySelectorAll('[data-login-close]').forEach((button) => button.addEventListener('click', closeLogin));
document.addEventListener('click', (event) => {
  if (!loginPanel || loginPanel.hidden || loginPanel.contains(event.target) || event.target.closest('[data-login-open]')) return;
  closeLogin();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && loginPanel && !loginPanel.hidden) closeLogin();
});
if (window.location.hash === '#sign-in') openLogin();

const registerModal = document.querySelector('[data-register-modal]');
const openRegister = () => {
  if (!registerModal || typeof registerModal.showModal !== 'function') return;
  closeLogin();
  if (!registerModal.open) registerModal.showModal();
  registerModal.querySelector('input[name="first_name"]')?.focus();
};
const closeRegister = () => {
  if (registerModal?.open) registerModal.close();
};
document.querySelectorAll('[data-register-open]').forEach((link) => link.addEventListener('click', (event) => {
  if (!registerModal || typeof registerModal.showModal !== 'function') return;
  event.preventDefault();
  openRegister();
}));
registerModal?.querySelectorAll('[data-register-close]').forEach((button) => button.addEventListener('click', closeRegister));
registerModal?.addEventListener('click', (event) => {
  if (event.target === registerModal) closeRegister();
});
registerModal?.querySelector('[data-register-to-login]')?.addEventListener('click', () => {
  closeRegister();
  openLogin();
});
if (window.location.hash === '#register') openRegister();
