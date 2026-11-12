'use strict';
(() => {
 const dialog = document.querySelector('#codexSetupDialog');
 if (!dialog) return;

 const cliLine = dialog.querySelector('[data-setup-cli]');
 const accountLine = dialog.querySelector('[data-setup-account]');
 const errorLine = dialog.querySelector('#codexSetupError');
 const loginButton = dialog.querySelector('#codexSetupLogin');
 const cancelButton = dialog.querySelector('#codexSetupCancelLogin');
 const refreshButton = dialog.querySelector('#codexSetupRefresh');
 const repairButton = dialog.querySelector('#codexSetupRepair');
 const loginLink = dialog.querySelector('#codexSetupLoginLink');
 let status = null;
 let pollTimer = null;
 let pollPending = false;
 let autoInstallStarted = false;
 let loginStartPending = false;
 let loginWindow = null;
 let loginWindowNavigated = false;
 let loginUrl = null;
 let requiredInstalledFlow = false;

 function safeLoginUrl(value) {
  if (typeof value !== 'string' || value.length > 4096) return null;
  try {
   const url = new URL(value);
   const trusted = ['chatgpt.com', 'auth.openai.com'].includes(url.hostname.toLowerCase());
   const trustedPort = !url.port || url.port === '443';
   return url.protocol === 'https:' && trusted && trustedPort && !url.username && !url.password ? url.href : null;
  } catch { return null; }
 }

 function displayPlan(plan) {
  const normalized = String(plan || '').trim().toLowerCase();
  if (normalized === 'plus') return 'ChatGPT Plus';
  if (normalized === 'pro') return 'ChatGPT Pro';
  if (normalized === 'team') return 'ChatGPT Team';
  if (normalized === 'business') return 'ChatGPT Business';
  if (normalized === 'enterprise') return 'ChatGPT Enterprise';
  if (normalized === 'edu') return 'ChatGPT Edu';
  return '';
 }

 function setProviderToCodex() {
  state.provider = 'codex';
  try { localStorage.setItem('qm-provider', 'codex'); } catch { /* Browser storage may be disabled. */ }
  const providerSelect = document.querySelector('#provider');
  const claudeOption = providerSelect?.querySelector('option[value="claude"]');
  if (claudeOption) {
   claudeOption.hidden = true;
   claudeOption.disabled = true;
  }
  if (providerSelect) providerSelect.value = 'codex';
 }

 function closeBlankLoginWindow() {
  if (loginWindow && !loginWindowNavigated) {
   try {
    if (loginWindow.location.href === 'about:blank') loginWindow.close();
   } catch { /* The window may already have navigated elsewhere. */ }
  }
  loginWindow = null;
  loginWindowNavigated = false;
 }

 function showStatus(next) {
  if (!next || typeof next !== 'object') return;
  status = next;
  const installed = next.installed === true;
  const phase = String(next.phase || 'checking');
  dialog.dataset.phase = phase;
  if (installed) setProviderToCodex();
  const busy = ['checking', 'installing', 'login_starting', 'login', 'cancelling'].includes(phase);
  const error = phase === 'error';
  const version = typeof next.version === 'string' && next.version ? ` · ${next.version}` : '';

  if (installed) {
   cliLine.textContent = phase === 'installing' ? 'Codex CLI를 준비하고 있습니다.' : `✓ Codex CLI${version} 준비됨`;
  } else if (phase === 'installing') {
   cliLine.textContent = 'Codex CLI를 설치하고 있습니다.';
  } else if (phase === 'checking') {
   cliLine.textContent = 'Codex CLI 상태를 확인하고 있습니다.';
  } else {
   cliLine.textContent = 'Codex CLI를 설치해야 계속할 수 있습니다.';
  }

  const plan = displayPlan(next.plan);
  if (next.ready === true) {
   accountLine.textContent = plan ? `✓ ${plan} 연결됨` : '✓ 유료 ChatGPT 계정 연결됨';
  } else if (next.authenticated === true) {
   accountLine.textContent = plan ? `${plan} 계정 확인됨 · 연결을 완료해 주세요.` : '유료 ChatGPT 계정 확인이 필요합니다.';
  } else if (phase === 'login' || phase === 'login_starting' || phase === 'cancelling') {
   accountLine.textContent = phase === 'login' ? '브라우저에서 ChatGPT 로그인을 완료해 주세요.' : '로그인 창을 준비하고 있습니다.';
  } else {
   accountLine.textContent = '유료 ChatGPT 계정 로그인이 필요합니다.';
  }

  errorLine.hidden = !error;
  errorLine.textContent = error ? (typeof next.error === 'string' && next.error.trim() ? next.error : '연결을 완료하지 못했습니다. 다시 시도해 주세요.') : '';
  loginButton.disabled = !installed || busy;
  loginButton.textContent = next.authenticated === true ? 'ChatGPT 계정으로 다시 로그인' : 'ChatGPT 계정으로 로그인';
  cancelButton.hidden = !['login_starting', 'login', 'cancelling'].includes(phase);
  cancelButton.disabled = phase === 'cancelling';
  refreshButton.hidden = !error;
  repairButton.hidden = !error;
  refreshButton.disabled = pollPending;
  repairButton.disabled = busy;

  const safeUrl = safeLoginUrl(next.login_url);
  if (safeUrl) {
   loginUrl = safeUrl;
   loginLink.href = safeUrl;
   loginLink.hidden = false;
   if (loginWindow && !loginWindowNavigated) {
    try {
     loginWindow.opener = null;
     loginWindow.location.replace(safeUrl);
     loginWindowNavigated = true;
    } catch {
     loginWindow = null;
    }
   }
  } else {
   loginUrl = null;
   loginLink.removeAttribute('href');
   loginLink.hidden = true;
  }

  if (next.ready === true) {
   setProviderToCodex();
   closeBlankLoginWindow();
   closeSetup();
  }
 }

 function openSetup() {
  if (!dialog.open) dialog.showModal();
  if (!pollTimer) pollTimer = window.setInterval(() => { void refreshStatus(); }, 1200);
 }

 function closeSetup() {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = null;
  if (dialog.open) dialog.close();
 }

 async function refreshStatus() {
  if (pollPending || !requiredInstalledFlow) return;
  pollPending = true;
  try {
   const next = await api('/api/codex/status');
   showStatus(next);
   if (next?.phase === 'missing' && next.installed !== true && !autoInstallStarted) {
    autoInstallStarted = true;
    await startInstall(false);
   }
  } catch (error) {
   showStatus({ ...(status || {}), required: true, phase: 'error', error: error?.message || '연결 상태를 확인하지 못했습니다.' });
  } finally {
   pollPending = false;
   refreshButton.disabled = false;
  }
 }

 async function startInstall(repair) {
  try {
   const next = await api('/api/codex/install', repair ? { repair: true } : {});
   showStatus(next);
  } catch (error) {
   showStatus({ ...(status || {}), required: true, phase: 'error', error: error?.message || 'Codex CLI를 준비하지 못했습니다.' });
  }
 }

 async function startLogin() {
  if (loginStartPending || !status?.installed) return;
  // Open synchronously from the user's click so popup blockers allow it.
  loginWindow = window.open('about:blank', '_blank');
  loginWindowNavigated = false;
  if (loginWindow) {
   try { loginWindow.opener = null; } catch { /* Navigation remains restricted to the validated URL below. */ }
  }
  loginStartPending = true;
  loginButton.disabled = true;
  errorLine.hidden = true;
  try {
   const next = await api('/api/codex/login/start', {});
   showStatus(next);
   if (next?.phase === 'error') closeBlankLoginWindow();
  } catch (error) {
   closeBlankLoginWindow();
   showStatus({ ...(status || {}), required: true, phase: 'error', error: error?.message || 'ChatGPT 로그인을 시작하지 못했습니다.' });
  } finally {
   loginStartPending = false;
  }
 }

 async function cancelLogin() {
  cancelButton.disabled = true;
  try {
   showStatus(await api('/api/codex/login/cancel', {}));
  } catch (error) {
   showStatus({ ...(status || {}), required: true, phase: 'error', error: error?.message || '로그인을 취소하지 못했습니다.' });
  }
 }

 dialog.addEventListener('cancel', event => event.preventDefault());
 dialog.addEventListener('click', event => {
  if (event.target === dialog) event.preventDefault();
 });
 loginButton.addEventListener('click', () => { void startLogin(); });
 cancelButton.addEventListener('click', () => { void cancelLogin(); });
 refreshButton.addEventListener('click', () => { void refreshStatus(); });
 repairButton.addEventListener('click', () => { void startInstall(true); });
 loginLink.addEventListener('click', event => {
  const safeUrl = safeLoginUrl(loginUrl);
  if (!safeUrl) { event.preventDefault(); return; }
  loginLink.href = safeUrl;
 });

 async function initialize() {
  // Wait for the existing app bootstrap before using its CSRF-aware api() helper.
  for (let attempt = 0; attempt < 300 && !state.boot; attempt++) {
   await new Promise(resolve => window.setTimeout(resolve, 50));
  }
  if (!state.boot || state.boot.installed !== true) return;

  requiredInstalledFlow = true;
  if (state.boot.codex?.installed === true) setProviderToCodex();
  let initial = state.boot.codex || null;
  try { initial = await api('/api/codex/status'); }
  catch (error) { initial = { required: true, installed: state.boot.codex?.installed === true, phase: 'error', error: error?.message }; }

  showStatus(initial);
  if (initial?.ready === true) return;
  openSetup();
  if (initial?.phase === 'missing' && initial.installed !== true && !autoInstallStarted) {
   autoInstallStarted = true;
   await startInstall(false);
  }
 }

 void initialize();
})();
