(() => {
  let timer;
  let canInstall = false;
  function display(data) {
    const messages = {
      idle:'Можно проверить наличие новой версии.', checking:'Проверяем GitHub Releases…',
      current:`Установлена актуальная версия ${data.current}.`,
      available:`Доступна версия ${data.latest} · ${mb(data.size || 0)} МБ`,
      downloading:`Скачиваем версию ${data.latest} · ${data.progress}%`,
      ready:`Версия ${data.latest} скачана. SHA-256 проверен.`,
      installing:'Открываем установщик. Приложение закроется.',
      error:'Проверка обновлений не завершена.'
    };
    $('updateStatus').textContent = messages[data.status] || '';
    $('updateError').textContent = data.error || '';
    $('updateError').hidden = !data.error;
    $('updateProgress').hidden = data.status !== 'downloading';
    motion.progress($('updateProgress'),data.progress || 0);
    $('checkUpdateButton').disabled = ['checking','downloading','installing'].includes(data.status);
    $('downloadUpdateButton').hidden = data.status !== 'available';
    $('installUpdateButton').hidden = data.status !== 'ready' || !canInstall;
    if (data.status === 'ready' && !canInstall) $('updateStatus').textContent += ' Установку запустите из Windows-приложения.';
    $('updatesButton').textContent = ['available','downloading','ready'].includes(data.status) ? `Обновление ${data.latest}` : 'Проверить обновления';
  }
  async function poll() {
    clearTimeout(timer);
    try {
      const data = await api('/api/updates'); display(data);
      if (['checking','downloading'].includes(data.status)) timer = setTimeout(poll,1000);
    } catch (e) { $('updateError').textContent=e.message; $('updateError').hidden=false; }
  }
  async function action(name) {
    try { await api(`/api/updates/${name}`,{}); await poll(); }
    catch (e) { $('updateError').textContent=e.message; $('updateError').hidden=false; }
  }
  $('updatesButton').onclick = () => {
    const panel = $('updatesPanel'); motion.visible(panel,panel.hidden);
    $('updatesButton').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) { poll(); panel.scrollIntoView({block:'nearest'}); }
  };
  $('checkUpdateButton').onclick = () => action('check');
  $('downloadUpdateButton').onclick = () => action('download');
  $('installUpdateButton').onclick = () => action('install');
  api('/api/config').then(data => {
    canInstall = data.can_install_update;
    document.querySelector('.version').textContent = data.version;
    return action('check');
  }).catch(() => {});
})();
