import random

from django.templatetags.static import static
from django.conf import settings
from django.contrib.staticfiles import finders

COMMON_BACKGROUNDS = [
    'img/backgrounds/bg1.jpg',
    'img/backgrounds/bg2.jpg',
    'img/backgrounds/bg3.jpg',
    'img/backgrounds/bg4.jpg',
    'img/backgrounds/bg5.jpg',
    'img/backgrounds/bg6.jpg',
    'img/backgrounds/bg7.jpg',
    'img/backgrounds/bg8.jpg',
]
HOME_BACKGROUNDS = [
    'img/hero/hero1.jpg',
    'https://images.unsplash.com/photo-1517816743773-6e0fd518b4a6?auto=format&fit=crop&w=1920&q=80',
]
AUTH_BACKGROUNDS = ['img/auth/auth1.jpg']


def _resolve_path(path: str) -> str:
    if path.startswith(('http://', 'https://')):
        return path
    return static(path)


def _choose(path_list: list[str]) -> str:
    if not path_list:
        return static('img/backgrounds/bg1.jpg')
    choice = random.choice(path_list)
    return _resolve_path(choice)


def background_image(request):
    """Provide page-level background image URL without relying on client JS."""
    path = request.path
    if path.startswith('/accounts/login') or path.startswith('/accounts/register'):
        url = _choose(AUTH_BACKGROUNDS)
    elif path == '/' and not request.user.is_authenticated:
        url = _choose(HOME_BACKGROUNDS)
    else:
        url = _choose(COMMON_BACKGROUNDS)

    return {
        'background_image_url': url,
    }


def background_video(request):
    """Expose background video path or absolute URL to templates.
    If settings.BACKGROUND_VIDEO is an absolute URL (e.g., Cloudinary), pass through.
    Otherwise treat it as a static-relative path.
    Default is empty string to avoid 100MB+ assets in repo; template will simply not preload if empty.
    """
    path = getattr(settings, 'BACKGROUND_VIDEO', '') or ''

    # Fallback: if not explicitly configured, try common default locations
    # like static/video/bg.mp4 to preserve behavior after env resets.
    if not path:
        for candidate in ('video/bg.mp4', 'video/bg.webm'):
            try:
                if finders.find(candidate):
                    path = candidate
                    break
            except Exception:
                # Ignore lookup errors and continue
                pass

    # Absolute URLs pass through directly
    if path.startswith(('http://', 'https://')):
        return {
            'BACKGROUND_VIDEO': path,
            'BACKGROUND_VIDEO_PRELOAD': getattr(settings, 'BACKGROUND_VIDEO_PRELOAD', 'metadata'),
        }

    # For local static paths, suppress template errors when file isn't collected yet.
    # If the static file can't be found by Django's finders (including STATIC_ROOT/manifest),
    # return empty so templates won't call `{% static %}` and trigger a manifest error.
    if path:
        try:
            found = finders.find(path)
        except Exception:
            found = None
        if not found:
            return {
                'BACKGROUND_VIDEO': '',
                'BACKGROUND_VIDEO_PRELOAD': getattr(settings, 'BACKGROUND_VIDEO_PRELOAD', 'metadata'),
            }
    return {
        'BACKGROUND_VIDEO': path,
        'BACKGROUND_VIDEO_PRELOAD': getattr(settings, 'BACKGROUND_VIDEO_PRELOAD', 'metadata'),
    }
