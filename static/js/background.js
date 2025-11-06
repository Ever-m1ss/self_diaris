(function () {
  const CONFIG = {
    fallbackRevealMs: 15000
  };

  let bodyRef = null;
  let revealTimerId = null;
  let revealed = false;

  function extractUrl(value) {
    if (!value) return null;
    const match = value.match(/url\(("|'|)(.+?)\1\)/);
    return match ? match[2] : value.trim();
  }

  function revealContent(reason) {
    if (!bodyRef || revealed) {
      return;
    }
    revealed = true;
    bodyRef.classList.remove('page-is-loading');
    bodyRef.classList.add('page-ready');
    if (revealTimerId) {
      window.clearTimeout(revealTimerId);
      revealTimerId = null;
    }
  }

  function preloadBackgroundImage() {
    return new Promise((resolve) => {
      const computed = getComputedStyle(bodyRef).getPropertyValue('--ll-bg-image');
      const url = extractUrl(computed);
      if (!url) {
        resolve();
        return;
      }

      const img = new Image();
      img.fetchPriority = 'high';

      const markReady = () => {
        bodyRef.classList.add('bg-image-ready');
        resolve();
      };

      img.addEventListener('load', markReady, { once: true });
      img.addEventListener('error', markReady, { once: true });
      img.src = url;

      if (img.complete) {
        markReady();
      }
    });
  }

  function getVideoContext() {
    const container = document.getElementById('bg-video');
    if (!container) return null;
    const video = container.querySelector('video');
    if (!video) return null;
    return { container, video };
  }
  function waitForVideoReady(video) {
    return new Promise((resolve) => {
      const markReady = () => {
        if (video.readyState >= 2) {
          video.removeEventListener('loadeddata', markReady);
          video.removeEventListener('canplay', markReady);
          video.removeEventListener('playing', markReady);
          resolve();
        }
      };

      video.addEventListener('loadeddata', markReady);
      video.addEventListener('canplay', markReady);
      video.addEventListener('playing', markReady);
      video.preload = video.getAttribute('preload') || 'auto';
      video.load();
      video.play().catch(() => {});
      markReady();
    });
  }

  function hydrateBackgroundVideo() {
    const ctx = getVideoContext();
    if (!ctx) {
      return Promise.resolve();
    }

    const { video } = ctx;
    video.setAttribute('playsinline', '');
    video.setAttribute('muted', '');
    video.muted = true;
    video.playsInline = true;

    return new Promise((resolve) => {
      let resolved = false;

      const finish = () => {
        if (resolved) return;
        resolved = true;
        bodyRef.classList.add('video-ready');
        resolve();
      };

      waitForVideoReady(video).then(finish);
    });
  }

  async function init() {
    bodyRef = document.body;
    if (!bodyRef) return;

    bodyRef.classList.add('page-is-loading');
    bodyRef.classList.remove('page-ready');

    revealTimerId = window.setTimeout(() => {
      console.warn('Background assets timed out, forcing reveal.');
      revealContent('timeout');
    }, CONFIG.fallbackRevealMs);

    try {
      await Promise.all([
        preloadBackgroundImage(),
        hydrateBackgroundVideo()
      ]);
      revealContent('assets-ready');
    } catch (error) {
      console.warn('Error while preparing background assets, revealing anyway.', error);
      revealContent('asset-error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
