/* Workspace tabs keep the Unfold shell mounted while replacing the active view. */
(() => {
  const nav = document.querySelector('.med-workspace-nav');
  const content = document.getElementById('content');
  if (!nav || !content) return;

  const workspacePaths = ['/dashboard/', '/clinical/', '/facility/inventory/', '/doctor/prescriptions/', '/dispense/', '/accounts/users/new/'];
  let pending;

  function isWorkspacePage(url) {
    return url.origin === location.origin && workspacePaths.some(path => url.pathname.startsWith(path)) && !url.pathname.endsWith('/template/');
  }

  function workspaceUrl(url) {
    if (url.origin !== location.origin) return null;
    if (url.pathname.startsWith('/admin/')) {
      const wrapped = new URL('/dashboard/manage/', location.origin);
      wrapped.searchParams.set('view', url.pathname + url.search + url.hash);
      return wrapped;
    }
    return isWorkspacePage(url) ? url : null;
  }

  function syncFrameTheme(frame) {
    try {
      const mode = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
      const root = frame.contentDocument.documentElement;
      frame.contentWindow.Alpine?.$data(root)?.switchTheme(mode);
      root.classList.toggle('dark', mode === 'dark');
      root.classList.toggle('light', mode === 'light');
    } catch (_) { /* A navigation outside this origin is handled by the browser. */ }
  }

  function initAdminFrame() {
    const frame = content.querySelector('.med-admin-frame');
    if (!frame || frame.dataset.ready) return;
    frame.dataset.ready = 'true';
    frame.addEventListener('load', () => {
      try {
        const inner = frame.contentDocument;
        const workspaceHeader = inner.querySelector('.med-workspace-header');
        if (workspaceHeader) workspaceHeader.style.display = 'none';
        const sidebar = inner.querySelector('#nav-sidebar');
        if (sidebar) sidebar.parentElement.parentElement.parentElement.style.display = 'none';
        const header = inner.querySelector('#header-inner');
        if (header) {
          header.parentElement.style.maxWidth = 'none';
          const sidebarToggle = [...header.querySelectorAll('span')].find(element => element.getAttribute('x-on:click') === 'sidebarToggle()');
          if (sidebarToggle) {
            sidebarToggle.nextElementSibling?.style.setProperty('display', 'none');
            sidebarToggle.style.display = 'none';
          }
        }
        const frameStyles = inner.createElement('style');
        frameStyles.textContent = '#page{min-height:0!important}#content.container{max-width:none!important}';
        inner.head.appendChild(frameStyles);
        frame._workspaceResizeObserver?.disconnect();
        const resize = () => { frame.style.height = `${Math.max(400, inner.documentElement.scrollHeight, inner.body.scrollHeight)}px`; };
        frame._workspaceResizeObserver = new ResizeObserver(resize);
        frame._workspaceResizeObserver.observe(inner.body);
        resize();
        syncFrameTheme(frame);
      } catch (_) { /* Keep the embedded page usable if its structure changes. */ }
    });
  }

  document.addEventListener('medlocate:themechange', () => {
    const frame = content.querySelector('.med-admin-frame');
    if (frame) syncFrameTheme(frame);
  });

  function enhanceTables() {
    content.querySelectorAll('.table-wrap table, .med-table-scroll table').forEach(table => {
      if (table.classList.contains('med-operations-table')) return;
      const headings = [...table.querySelectorAll('thead th')].map(cell => cell.textContent.trim());
      table.querySelectorAll('tbody tr').forEach(row => {
        [...row.cells].forEach((cell, index) => {
          if (cell.colSpan === 1 && !cell.dataset.label) cell.dataset.label = headings[index] || 'Action';
        });
      });
      table.classList.add('med-responsive-table');
    });
  }

  document.addEventListener('medlocate:contentloaded', enhanceTables);
  enhanceTables();
  initAdminFrame();

  async function show(url, {push = true} = {}) {
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    content.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: {'Accept': 'text/html', 'X-MedLocate-Workspace': '1'},
        signal: controller.signal,
      });
      const type = response.headers.get('content-type') || '';
      if (!type.includes('text/html')) { location.assign(url); return; }
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      const nextContent = next.getElementById('content');
      const nextNav = next.querySelector('.med-workspace-nav-inner');
      if (!nextContent || !nextNav || !response.ok) { location.assign(url); return; }
      document.dispatchEvent(new Event('medlocate:beforevisit'));
      content.innerHTML = nextContent.innerHTML;
      nav.querySelector('.med-workspace-nav-inner').innerHTML = nextNav.innerHTML;
      document.title = next.title;
      if (push) history.pushState({workspace: true}, '', url);
      content.removeAttribute('aria-busy');
      document.dispatchEvent(new Event('medlocate:contentloaded'));
      initAdminFrame();
      window.scrollTo({top: 0, behavior: 'instant'});
      const heading = content.querySelector('h1');
      if (heading) { heading.tabIndex = -1; heading.focus({preventScroll: true}); }
    } catch (error) {
      if (error.name !== 'AbortError') location.assign(url);
    } finally {
      if (pending === controller) { pending = null; content.removeAttribute('aria-busy'); }
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || (!nav.contains(link) && !content.contains(link) && !link.closest('.med-workspace-brand')) ||
        link.hasAttribute('download') || link.target && link.target !== '_self' ||
        event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const destination = new URL(link.href);
    const url = workspaceUrl(destination);
    if (!url || url.href === location.href || destination.hash && destination.pathname === location.pathname && destination.search === location.search) return;
    event.preventDefault();
    show(url.href);
  });

  window.addEventListener('popstate', () => {
    const url = new URL(location.href);
    if (isWorkspacePage(url)) show(url.href, {push: false});
    else location.reload();
  });

  document.addEventListener('click', event => {
    const button = event.target.closest('#use-location');
    if (!button) return;
    const status = document.getElementById('location-status');
    if (!status) return;
    if (!navigator.geolocation) { status.textContent = 'Location is unavailable. Choose a starting facility or enter coordinates.'; return; }
    status.textContent = 'Requesting location…';
    navigator.geolocation.getCurrentPosition(position => {
      const lat = document.getElementById('lat');
      const lon = document.getElementById('lon');
      const origin = document.getElementById('origin');
      if (!lat || !lon || !origin) return;
      lat.value = position.coords.latitude;
      lon.value = position.coords.longitude;
      origin.value = '';
      status.textContent = 'Location added for this search. Distances are estimates.';
    }, () => { status.textContent = 'Location was not shared. Choose a starting facility or search without distance.'; });
  });
})();
