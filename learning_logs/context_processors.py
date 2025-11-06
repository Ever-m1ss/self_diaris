import random

from django.templatetags.static import static
from django.conf import settings

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
    """Expose background video relative static path to templates.
    Reads settings.BACKGROUND_VIDEO, falls back to default mp4 in static/video.
    """
    path = getattr(settings, 'BACKGROUND_VIDEO', 'video/Ghost of Tsushima Tree (Seamless).mp4')
    return {
        'BACKGROUND_VIDEO': path,
    }
