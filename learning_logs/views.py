from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model, login as auth_login
from django.http import Http404, JsonResponse, HttpResponseBadRequest
from django.http import FileResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from .models import Topic, Entry, Comment, Attachment
import re
from .forms import TopicForm, EntryForm, CommentForm
from django.db import transaction
from django.utils import timezone
import json
from django.conf import settings

# Max files per folder allowed in a single upload (server-side enforcement)
MAX_FOLDER_UPLOAD_FILES = getattr(settings, 'LL_MAX_FOLDER_UPLOAD_FILES', 10000)


def _parse_relative_paths(post_data):
    """Parse relative_paths_json or per-file relative_path[*] inputs from POST data.
    Returns (rel_index_map, rel_meta_map)
    - rel_index_map: dict mapping index (string) -> path
    - rel_meta_map: dict mapping 'name|size' -> path (from object entries)
    """
    rel_index_map = {}
    rel_meta_map = {}
    rp_json = post_data.get('relative_paths_json')
    if rp_json:
        try:
            parsed = json.loads(rp_json)
            if isinstance(parsed, list):
                # If the list contains objects with name/size/lastModified/path, build meta map
                if len(parsed) and isinstance(parsed[0], dict):
                    for i, item in enumerate(parsed):
                        if not isinstance(item, dict):
                            continue
                        name = item.get('name')
                        size = item.get('size')
                        lastm = item.get('lastModified')
                        # Support either 'path' or 'rel' (legacy) or 'webkitRelativePath' from certain client payloads
                        path = item.get('path') or item.get('rel') or item.get('webkitRelativePath') or ''
                        if name and size is not None and lastm is not None:
                            rel_meta_map[f"{name}|{size}|{lastm}"] = path
                        elif name and size is not None:
                            rel_meta_map[f"{name}|{size}"] = path
                        rel_index_map[str(i)] = path
                else:
                    for i, p in enumerate(parsed):
                        rel_index_map[str(i)] = p
            elif isinstance(parsed, dict):
                for k, v in parsed.items():
                    rel_index_map[str(k)] = v
        except Exception:
            rel_index_map = {}
            rel_meta_map = {}
    else:
        # Fallback: parse per-file inputs relative_path[<idx>]
        for k, v in post_data.items():
            if k.startswith('relative_path[') and k.endswith(']'):
                try:
                    idx = k.split('relative_path[')[1].split(']')[0]
                    rel_index_map[idx] = v
                except Exception:
                    continue
            elif k.startswith('relative_path_'):
                try:
                    idx = k.split('relative_path_')[1]
                    rel_index_map[idx] = v
                except Exception:
                    continue
    return rel_index_map, rel_meta_map


def index(request):
    """Home page: 未登录展示登录/注册；已登录展示“发现”：左侧日记本列表，右侧浏览所选日记本下的日记。"""
    # 左侧日记本：已登录用户看到自己 + 公开，未登录用户仅看到公开
    if request.user.is_authenticated:
        topics_qs = Topic.objects.filter(Q(owner=request.user) | Q(is_public=True)).order_by('-date_added')
    else:
        topics_qs = Topic.objects.filter(is_public=True).order_by('-date_added')

    # 选中的日记本：支持通过 ?t=<id> 指定；若未指定，则默认选择第一个（便于匿名用户点击“立即开始”后看到内容）
    selected_topic = None
    t_id = request.GET.get('t')
    if t_id:
        try:
            selected_topic = topics_qs.get(id=int(t_id))
        except Exception:
            selected_topic = None

    if selected_topic is None and topics_qs.exists():
        selected_topic = topics_qs.first()

    # 右侧日记列表：若无选中则为空
    entries = None
    if selected_topic is not None:
        if request.user.is_authenticated and request.user == selected_topic.owner:
            entries = selected_topic.entry_set.order_by('-date_added')
        else:
            # 对于未登录或非作者用户，仅展示公开或属于当前用户（若登录）的日记
            entries = selected_topic.entry_set.filter(Q(is_public=True) | Q(owner=request.user) if request.user.is_authenticated else Q(is_public=True)).order_by('-date_added')

    context = {
        'discover_topics': topics_qs,
        'selected_topic': selected_topic,
        'entries': entries,
    }
    return render(request, 'learning_logs/index.html', context)


def start_traveler(request):
    """Log the visitor in as the special 'traveler' user (create if missing),
    then redirect to the first public topic's discovery page (or discovery home).
    This allows anonymous visitors to quickly browse public content under a
    consistent username without going through the normal login flow.
    """
    User = get_user_model()
    username = 'traveler'
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        # Create a minimal traveler user with unusable password.
        user = User(username=username)
        try:
            user.set_unusable_password()
        except Exception:
            pass
        # Ensure active so login succeeds
        user.is_active = True
        user.save()

    # Perform login using the default ModelBackend. This requires that the
    # backend string is available in AUTHENTICATION_BACKENDS (default case).
    try:
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    except Exception:
        # Fallback: set session backend marker (older Django versions may accept)
        request.session['_auth_user_id'] = user.pk
        request.session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'

    # Redirect to first public topic's discovery page when possible
    from django.urls import reverse
    topics_qs = Topic.objects.filter(is_public=True).order_by('-date_added')
    if topics_qs.exists():
        t = topics_qs.first()
        try:
            return redirect(reverse('learning_logs:discovey_by_user', kwargs={'username': t.owner.username, 'topic_name': t.text}))
        except Exception:
            return redirect('learning_logs:discovey_home')
    return redirect('learning_logs:discovey_home')

@login_required
def topics(request):
    """Show all topics."""
    topics = Topic.objects.filter(owner=request.user).order_by('date_added')
    context = {'topics': topics}
    return render(request, 'learning_logs/topics.html', context)

def build_attachment_tree(attachments):
    """将扁平的附件列表构造成树状结构（字典）。"""
    tree = {}
    for att in attachments:
        # 使用 original_name 以防 relative_path 为空
        path = att.relative_path or att.original_name
        parts = path.split('/')
        
        current_level = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # 文件节点
                if 'files' not in current_level:
                    current_level['files'] = []
                current_level['files'].append(att)
            else:
                # 目录节点
                if 'dirs' not in current_level:
                    current_level['dirs'] = {}
                if part not in current_level['dirs']:
                    current_level['dirs'][part] = {}
                current_level = current_level['dirs'][part]
    return tree


def topic(request, topic_name, username=None):
    """按名称展示单个日记本及其日记，遵循可见性规则。"""
    # If username provided, prefer topic owned by that username
    topic = _resolve_topic_by_name_for_user(topic_name, request.user, username=username)

    # 条目可见性：
    if request.user == topic.owner:
        entries = topic.entry_set.order_by('-date_added')
    else:
        entries = topic.entry_set.filter(Q(is_public=True) | Q(owner=request.user)).order_by('-date_added')

    # 为每个 entry 构建附件树
    for entry in entries:
        entry.attachment_tree = build_attachment_tree(entry.attachment_set.all())
        # 预计算顶级评论 QuerySet，模板中直接使用，避免在模板里调用带参数的方法导致解析问题
        try:
            entry.top_comments = entry.comment_set.filter(parent__isnull=True)
        except Exception:
            entry.top_comments = entry.comment_set.none()
        # 为该 entry 下的每条评论构建附件树与编辑权限标志
        for c in entry.comment_set.all():
            try:
                c.attachment_tree = build_attachment_tree(c.attachment_set.all())
            except Exception:
                c.attachment_tree = {}
            # 评论附件的编辑权限：评论作者或日记作者可修改
            c.allow_modify = bool((c.user and c.user == request.user) or (entry.owner == request.user))

    # 为 topic 本身构建附件树，过滤掉还带 upload_session 的临时资源
    try:
        topic.attachment_tree = build_attachment_tree(topic.attachment_set.filter(upload_session__isnull=True).all())
    except Exception as e:
        try:
            import logging
            log = logging.getLogger('learning_logs.topic')
            log.exception('Failed to build topic attachment tree for topic_id=%s name=%s user=%s headers=%s error=%s', getattr(topic,'id',None), topic_name, getattr(request.user,'id',None), { 'UA': request.META.get('HTTP_USER_AGENT'), 'Referer': request.META.get('HTTP_REFERER') }, e)
        except Exception:
            pass
        # On error building tree, use empty tree to avoid failing whole page
        topic.attachment_tree = {}

    comment_form = CommentForm()
    context = {'topic': topic, 'entries': entries, 'comment_form': comment_form}
    return render(request, 'learning_logs/topic.html', context)


def discovey(request, topic_name, username=None):
    """Discovery route: render the same layout as index but for a specific topic name.
    This is used from the "发现" page and is read-only (no edit links shown there).
    If `username` is provided (via username-prefixed URL), prefer resolving the topic for that owner.
    """
    topic = _resolve_topic_by_name_for_user(topic_name, request.user, username=username)

    # 条目可见性：与 topic 视图一致
    if request.user == topic.owner:
        entries = topic.entry_set.order_by('-date_added')
    else:
        entries = topic.entry_set.filter(Q(is_public=True) | Q(owner=request.user)).order_by('-date_added')

    # 为每个 entry 构建附件树
    for entry in entries:
        entry.attachment_tree = build_attachment_tree(entry.attachment_set.all())
        # 预计算顶级评论 QuerySet，模板中直接使用，避免在模板里调用带参数的方法导致解析问题
        try:
            entry.top_comments = entry.comment_set.filter(parent__isnull=True)
        except Exception:
            entry.top_comments = entry.comment_set.none()
        # 为该 entry 下的每条评论构建附件树与编辑权限标志
        for c in entry.comment_set.all():
            try:
                c.attachment_tree = build_attachment_tree(c.attachment_set.all())
            except Exception:
                c.attachment_tree = {}
            c.allow_modify = bool((c.user and c.user == request.user) or (entry.owner == request.user))

    # 为 topic 本身构建附件树
    topic.attachment_tree = build_attachment_tree(topic.attachment_set.filter(upload_session__isnull=True).all())

    comment_form = CommentForm()

    # 左侧的可发现日记本列表（兼容匿名用户）
    topics_qs = Topic.objects.filter(Q(owner=request.user) | Q(is_public=True)).order_by('-date_added') if request.user.is_authenticated else Topic.objects.filter(is_public=True).order_by('-date_added')

    context = {
        'discover_topics': topics_qs,
        'selected_topic': topic,
        'entries': entries,
        'comment_form': comment_form,
        # 标记为发现页视图，模板可据此在匿名情况下隐藏首页 hero
        'is_discovery_view': True,
    }
    return render(request, 'learning_logs/index.html', context)


def public_discovey(request):
    """Public discovery landing: allow anonymous users to browse public topics and entries.

    This renders the same layout as index/discovey but selects the first public topic by default
    so the left topic list and right entry column are populated for unauthenticated visitors.
    """
    # public topics only
    topics_qs = Topic.objects.filter(is_public=True).order_by('-date_added')
    selected_topic = topics_qs.first() if topics_qs.exists() else None

    entries = None
    if selected_topic:
        entries = selected_topic.entry_set.filter(is_public=True).order_by('-date_added')
        for entry in entries:
            entry.attachment_tree = build_attachment_tree(entry.attachment_set.all())
            try:
                entry.top_comments = entry.comment_set.filter(parent__isnull=True)
            except Exception:
                entry.top_comments = entry.comment_set.none()
            for c in entry.comment_set.all():
                try:
                    c.attachment_tree = build_attachment_tree(c.attachment_set.all())
                except Exception:
                    c.attachment_tree = {}
                c.allow_modify = False

    context = {
        'discover_topics': topics_qs,
        'selected_topic': selected_topic,
        'entries': entries,
        'comment_form': CommentForm(),
        'is_discovery_view': True,
    }
    return render(request, 'learning_logs/index.html', context)

@login_required
def new_topic(request):
    """Add a new topic."""
    # Prevent the special 'traveler' user from creating content; force real login
    if getattr(request.user, 'username', None) == 'traveler':
        login_url = reverse('accounts:login')
        return redirect(f"{login_url}?next={request.get_full_path()}")
    if request.method != 'POST':
        # No data submitted; create a blank form.
        form = TopicForm()
    else:
        # POST data submitted; process data.
        form = TopicForm(data=request.POST)
        if form.is_valid():
            new_topic = form.save(commit=False)
            new_topic.owner = request.user
            new_topic.save()
            # 处理附件（可选，多文件/文件夹）
            files = request.FILES.getlist('attachments') or request.FILES.getlist('attachments[]') or request.FILES.getlist('files') or request.FILES.getlist('files[]')
            # Server-side guard for new_topic form: limit per-folder files
            if files and len(files) > MAX_FOLDER_UPLOAD_FILES:
                form.add_error(None, f'文件数量超出单个文件夹上限（{MAX_FOLDER_UPLOAD_FILES}）。请分批上传。')
                files = []
            # Server-side guard for new_entry form: limit per-folder files
            if files and len(files) > MAX_FOLDER_UPLOAD_FILES:
                form.add_error(None, f'文件数量超出单个文件夹上限（{MAX_FOLDER_UPLOAD_FILES}）。请分批上传。')
                files = []
            # 支持两种前端传参格式：
            # 1) 多个 hidden inputs: relative_path[0]=..., relative_path[1]=... （向后兼容）
            # 2) 单个 hidden JSON 字段: relative_paths_json = JSON array or dict
            rel_index_map, rel_meta_map = _parse_relative_paths(request.POST)
            _save_attachments_from_request(files, request.user, topic=new_topic, relative_paths=rel_index_map, relative_meta=rel_meta_map)
            return redirect('learning_logs:topics')

    # Display a blank or invalid form.
    context = {'form': form}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def new_entry(request, topic_id):
    """Add a new entry for a particular topic."""
    # Prevent the special 'traveler' user from creating content; force real login
    if getattr(request.user, 'username', None) == 'traveler':
        login_url = reverse('accounts:login')
        return redirect(f"{login_url}?next={request.get_full_path()}")
    topic = Topic.objects.get(id=topic_id)
    # 非作者只能在公开的日记本下添加
    if topic.owner != request.user and not topic.is_public:
        raise Http404

    if request.method != 'POST':
        # No data submitted; create a blank form.
        form = EntryForm()
    else:
        # POST data submitted; process data.
        form = EntryForm(data=request.POST)
        # 尝试从多种可能的字段名读取上传的文件（兼容不同前端实现）
        try:
            files = request.FILES.getlist('attachments') or request.FILES.getlist('attachments[]') or request.FILES.getlist('files') or request.FILES.getlist('files[]')
        except Exception as e:
            import logging
            log = logging.getLogger('learning_logs.new_entry')
            log.exception('Failed to parse uploaded files in new_entry: %s', e)
            form.add_error(None, '上传的表单内容无法解析（可能文件过大或请求异常）。')
            files = []
        # 支持文件夹上传：前端通过 single JSON hidden input `relative_paths_json` 或多个 hidden inputs `relative_path[...]`
        rel_index_map, rel_meta_map = _parse_relative_paths(request.POST)
        # 简短调试日志（仅在需要时可查看）
        try:
            import logging
            log = logging.getLogger('learning_logs.new_entry')
            session_key_debug = request.POST.get('upload_session')
            content_length = request.META.get('CONTENT_LENGTH')
            log.debug('new_entry BEGIN parse files=%s names=%s rel_index_map=%s rel_meta_map=%s upload_session=%s content_length=%s referer=%s',
                      len(files) if files is not None else 0,
                      [getattr(f, 'name', None) for f in files],
                      rel_index_map, rel_meta_map, session_key_debug, content_length, request.META.get('HTTP_REFERER'))
        except Exception:
            pass
        if form.is_valid():
            text_val = (form.cleaned_data.get('text') or '').strip()
            # 校验：正文与附件或 upload_session 不能同时为空（支持异步上传）
            session_key = request.POST.get('upload_session')
            if not text_val and not files and not session_key:
                form.add_error(None, '请填写日记正文或至少上传一个附件。')
            else:
                new_entry = form.save(commit=False)
                new_entry.topic = topic
                new_entry.owner = request.user
                new_entry.save()
                # 附件（可选，批量）
                _save_attachments_from_request(files, request.user, entry=new_entry, relative_paths=rel_index_map, relative_meta=rel_meta_map)
                # If the client used async upload to the topic before creating the entry,
                # reassign any topic-level attachments for this upload_session to this new entry.
                session_key = request.POST.get('upload_session')
                if session_key:
                    try:
                        reassigned = Attachment.objects.filter(topic=topic, owner=request.user, entry__isnull=True, upload_session=session_key)
                        for a in reassigned:
                            a.entry = new_entry
                            a.upload_session = None
                            a.save()
                        try:
                            import logging
                            logging.getLogger('learning_logs.new_entry').debug('reassigned %s topic attachments to entry id=%s for session=%s', reassigned.count(), new_entry.id, session_key)
                        except Exception:
                            pass
                    except Exception:
                        # ignore reassignment errors by design (log if needed)
                        pass
                    # If there were no reassigned attachments, log a debug message so we can see whether session matched
                    try:
                        import logging
                        if session_key and reassigned.count() == 0:
                            logging.getLogger('learning_logs.new_entry').warning('No topic attachments found to reassign for session=%s topic=%s owner=%s', session_key, topic.id, request.user.id)
                    except Exception:
                        pass
                try:
                    url = reverse('learning_logs:topic_by_user', kwargs={'username': topic.owner.username, 'topic_name': topic.text})
                    return redirect(url)
                except Exception:
                    return redirect('learning_logs:topic', topic_name=topic.text)

    # Display a blank or invalid form.
    # 构建日记本附件树供页面展示
    try:
        topic.attachment_tree = build_attachment_tree(topic.attachment_set.filter(upload_session__isnull=True).all())
    except Exception:
        topic.attachment_tree = {}
    context = {'topic': topic, 'form': form}
    return render(request, 'learning_logs/new_entry.html', context)

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry."""
    # Prevent the special 'traveler' user from editing content; force real login
    if getattr(request.user, 'username', None) == 'traveler':
        login_url = reverse('accounts:login')
        return redirect(f"{login_url}?next={request.get_full_path()}")
    entry = Entry.objects.get(id=entry_id)
    topic = entry.topic
    # 只能由日记作者本人编辑
    if entry.owner != request.user:
        raise Http404

    if request.method != 'POST':
        # Initial request; pre-fill form with the current entry.
        form = EntryForm(instance=entry)
    else:
        # POST data submitted; process data.
        form = EntryForm(instance=entry, data=request.POST)
        if form.is_valid():
            entry = form.save()
            # 标记最后编辑时间以便在展示时显示“最后编辑于 ...”。始终在用户成功提交编辑后更新。
            try:
                entry.last_edited = timezone.now()
                entry.save()
            except Exception:
                # 若时区模块不可用或保存失败，忽略但不要阻止后续操作
                pass
            # 可在编辑时追加附件（含文件夹）
            try:
                files = request.FILES.getlist('attachments') or request.FILES.getlist('attachments[]') or request.FILES.getlist('files') or request.FILES.getlist('files[]')
            except Exception as e:
                import logging
                log = logging.getLogger('learning_logs.edit_entry')
                log.exception('Failed to parse uploaded files in edit_entry: %s', e)
                files = []
            rel_index_map, rel_meta_map = _parse_relative_paths(request.POST)
            try:
                import logging
                log = logging.getLogger('learning_logs.edit_entry')
                log.debug('edit_entry files=%s names=%s rel_index_map=%s rel_meta_map=%s', len(files) if files is not None else 0, [getattr(f, 'name', None) for f in files], rel_index_map, rel_meta_map)
            except Exception:
                pass
            _save_attachments_from_request(files, request.user, entry=entry, relative_paths=rel_index_map, relative_meta=rel_meta_map)
            try:
                url = reverse('learning_logs:topic_by_user', kwargs={'username': topic.owner.username, 'topic_name': topic.text})
                return redirect(url)
            except Exception:
                return redirect('learning_logs:topic', topic_name=topic.text)

    # 构建本日记附件树供页面展示
    try:
        entry.attachment_tree = build_attachment_tree(entry.attachment_set.all())
    except Exception:
        entry.attachment_tree = {}
    context = {'entry': entry, 'topic': topic, 'form': form}
    return render(request, 'learning_logs/edit_entry.html', context)


@login_required
def delete_entry(request, entry_id):
    """删除单篇日记（仅作者）。GET 显示确认页，POST 确认后删除并返回所属日记本。"""
    try:
        entry = Entry.objects.select_related('topic').get(id=entry_id)
    except Entry.DoesNotExist:
        raise Http404

    topic = entry.topic

    # 仅作者可删
    if entry.owner != request.user:
        raise Http404

    if request.method == 'POST':
        entry.delete()
        try:
            url = reverse('learning_logs:topic_by_user', kwargs={'username': topic.owner.username, 'topic_name': topic.text})
            return redirect(url)
        except Exception:
            return redirect('learning_logs:topic', topic_name=topic.text)

    return render(request, 'learning_logs/delete_entry_confirm.html', {
        'entry': entry,
        'topic': topic,
    })


def _save_attachments_from_request(files, owner, *, topic=None, entry=None, comment=None, relative_paths=None, relative_meta=None, upload_session=None):
    if not files:
        return []
    try:
        import logging
        logging.getLogger('learning_logs.save_attach').debug('_save_attachments_from_request called files=%s rel_index_keys=%s rel_meta_keys=%s topic=%s entry=%s comment=%s upload_session=%s',
            len(files), list(relative_paths.keys()) if relative_paths else [], list(relative_meta.keys()) if relative_meta else [], getattr(topic,'id', None), getattr(entry,'id', None), getattr(comment,'id', None), upload_session)
    except Exception:
        pass
    created = []
    rel_map = {}
    meta_map = {}
    if relative_paths:
        # relative_paths may be a mapping of numeric indices to paths or be a dict/list parsed from JSON
        for idx, rp in relative_paths.items():
            try:
                rel_map[int(idx)] = rp
            except Exception:
                # keep non-numeric mapping as-is; we'll also build name-based fallback later
                rel_map[str(idx)] = rp
    if relative_meta:
        for k, v in relative_meta.items():
            try:
                meta_map[str(k)] = v
            except Exception:
                continue

    def _sanitize_rel_path(p: str) -> str:
        """清洗相对路径，确保：
        - 使用正斜杠；
        - 去掉前导斜杠，禁止绝对路径；
        - 折叠 . 与 ..，移除空段；
        - 限制长度，避免异常数据；
        """
        try:
            p = (p or '').replace('\\', '/').strip()
            p = p.lstrip('/')
            parts = []
            for seg in p.split('/'):
                if not seg or seg == '.':
                    continue
                if seg == '..':
                    if parts:
                        parts.pop()
                    continue
                parts.append(seg)
            safe = '/'.join(parts)
            return safe[:255]
        except Exception:
            return ''
    for idx, f in enumerate(files):
        try:
            if not isinstance(f, UploadedFile):
                continue
        except Exception:
            # In rare cases UploadedFile check can fail; skip this file but log
            try:
                import logging
                log = logging.getLogger('learning_logs.save_attach')
                log.exception('Skipped non-uploaded file at index=%s repr=%r', idx, getattr(f, 'name', None))
            except Exception:
                pass
            continue
        derived_public = False
        if entry is not None:
            derived_public = bool(entry.is_public)
        elif topic is not None:
            derived_public = bool(topic.is_public)
        elif comment is not None:
            derived_public = True
        att = Attachment(owner=owner, topic=topic, entry=entry, comment=comment, file=f, is_public=derived_public)
        att.original_name = getattr(f, 'name', '')
        # Attempt to find a relative path for this file in several ways
        rp_raw = None
        matched_source = None
        # 1) Index-based mapping (preferred; used for chunked uploads)
        try:
            if idx in rel_map:
                rp_raw = rel_map[idx]
                matched_source = 'index'
        except Exception:
            # rel_map keys might be strings; try string keys as fallback
            try:
                if str(idx) in rel_map:
                    rp_raw = rel_map[str(idx)]
                    matched_source = 'index'
            except Exception:
                pass

        # 2) Basename mapping: if any provided relative path ends with the filename
        if not rp_raw and rel_map:
            for v in rel_map.values():
                try:
                    if not isinstance(v, str):
                        continue
                    if v.endswith('/' + f.name) or v.endswith('\\' + f.name) or v == f.name:
                        rp_raw = v
                        matched_source = 'basename'
                        break
                except Exception:
                    continue

        # 3) Meta mapping by name|size
        if not rp_raw and meta_map:
            try:
                n = getattr(f, 'name', '')
                s = getattr(f, 'size', '')
                for k, v in meta_map.items():
                    try:
                        if k.split('|', 2)[0] == n and str(k.split('|', 2)[1]) == str(s):
                            rp_raw = v
                            matched_source = 'meta'
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if rp_raw:
            _rp = _sanitize_rel_path(rp_raw)
            if _rp:
                att.relative_path = _rp
                try:
                    import logging
                    logging.getLogger('learning_logs.save_attach').debug('match set relative path for file idx=%s name=%s size=%s source=%s path=%s', idx, getattr(f,'name',None), getattr(f,'size',None), matched_source, _rp)
                except Exception:
                    pass
            else:
                # If rp_raw sanitized to empty string, log for diagnostics
                try:
                    import logging
                    logging.getLogger('learning_logs.save_attach').warning('relative path sanitized to empty for file idx=%s name=%s size=%s original=%s source=%s', idx, getattr(f,'name',None), getattr(f,'size',None), rp_raw, matched_source)
                except Exception:
                    pass
        else:
            try:
                import logging
                logging.getLogger('learning_logs.save_attach').debug('No relative path match for file idx=%s name=%s size=%s rel_map_keys=%s meta_keys_sample=%s', idx, getattr(f,'name',None), getattr(f,'size',None), list(rel_map.keys())[:5], list(meta_map.keys())[:5])
            except Exception:
                pass
        if upload_session:
            att.upload_session = upload_session
        try:
            att.save()
        except Exception:
            # If saving a single attachment fails (e.g. storage error, name issue), log and continue with others
            try:
                import logging
                log = logging.getLogger('learning_logs.save_attach')
                log.exception('Failed to save attachment for file index=%s name=%s owner=%s topic=%s entry=%s', idx, getattr(att, 'original_name', None), getattr(owner, 'id', None), getattr(topic, 'id', None) if topic else None, getattr(entry, 'id', None) if entry else None)
            except Exception:
                pass
            continue
        try:
            import logging
            log = logging.getLogger('learning_logs.save_attach')
            log.debug('Saved attachment id=%s name=%s rel=%s owner=%s topic=%s entry=%s comment=%s', att.id, att.original_name, att.relative_path, getattr(owner, 'id', None), getattr(att.topic, 'id', None), getattr(att.entry, 'id', None), getattr(att.comment, 'id', None))
        except Exception:
            pass
        created.append(att)
    return created


@login_required
@require_POST
def delete_attachment(request, attachment_id):
    att = get_object_or_404(Attachment, id=attachment_id)
    # 权限：仅上传者或所属 topic/entry 作者可删
    parent_owner = None
    if att.entry_id and att.entry:
        parent_owner = att.entry.owner
    elif att.topic_id and att.topic:
        parent_owner = att.topic.owner
    elif att.comment_id and att.comment and att.comment.entry:
        parent_owner = att.comment.entry.owner
    if att.owner != request.user and parent_owner != request.user:
        raise Http404
    att.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    # 回退：返回来源页
    return redirect(request.META.get('HTTP_REFERER', 'learning_logs:index'))


@login_required
@require_POST
def delete_folder_api(request):
    """删除某个归属对象下指定 relative_path 前缀对应的所有附件。
    接收参数：
      parent_type: topic|entry|comment
      parent_id: 数字
      folder_path: 相对路径（不以 / 开头，末尾不带 / 或带都可）
    权限：必须是该对象作者。
    """
    parent_type = request.POST.get('parent_type')
    parent_id = request.POST.get('parent_id')
    folder_path = request.POST.get('folder_path', '')
    if parent_type not in {'topic', 'entry', 'comment'}:
        return JsonResponse({'ok': False, 'error': 'invalid parent_type'}, status=400)
    try:
        parent_id_int = int(parent_id)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid parent_id'}, status=400)
    # 规范化 folder_path
    folder_path = (folder_path or '').replace('\\', '/').strip('/')
    if not folder_path:
        return JsonResponse({'ok': False, 'error': 'empty folder_path'}, status=400)

    obj = None
    if parent_type == 'topic':
        obj = get_object_or_404(Topic, id=parent_id_int)
        if obj.owner != request.user:
            raise Http404
        base_qs = obj.attachment_set.all()
    elif parent_type == 'entry':
        obj = get_object_or_404(Entry, id=parent_id_int)
        if obj.owner != request.user:
            raise Http404
        base_qs = obj.attachment_set.all()
    else:
        obj = get_object_or_404(Comment, id=parent_id_int)
        # 评论作者或日记作者都可？这里严格限制为日记作者（即 entry.owner）
        if obj.entry.owner != request.user:
            raise Http404
        base_qs = obj.attachment_set.all()

    # 查找所有以 folder_path 为前缀的附件：
    # relative_path 可能是 '图片/a.png'，folder_path 传入 '图片' 时应匹配。
    # 需要匹配 folder_path == relative_path 的目录（即该目录下直接上传的文件）和 folder_path/ 后续子路径。
    prefix = folder_path + '/'  # 用于子项匹配
    targets = base_qs.filter(Q(relative_path=folder_path) | Q(relative_path__startswith=prefix))
    count = targets.count()
    if not count:
        return JsonResponse({'ok': True, 'deleted': 0})
    with transaction.atomic():
        for att in targets:
            att.delete()
    return JsonResponse({'ok': True, 'deleted': count})


@login_required
@require_POST
def upload_attachments_api(request):
    """异步上传接口：支持多文件与文件夹（相对路径）。
    期望前端 name=files，多值；对应相对路径通过 formData.append('relative_path[index]', path)
    需提供 parent_type 与 parent_id 指向归属（topic/entry/comment）。
    """
    try:
        parent_type = request.POST.get('parent_type')
        parent_id = request.POST.get('parent_id')
        if parent_type not in {'topic', 'entry', 'comment'}:
            return JsonResponse({'ok': False, 'error': 'invalid parent_type'}, status=400)
        try:
            parent_id_int = int(parent_id)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'invalid parent_id'}, status=400)

        parent_obj = None
        kw = {'topic': None, 'entry': None, 'comment': None}
        if parent_type == 'topic':
            parent_obj = get_object_or_404(Topic, id=parent_id_int)
            kw['topic'] = parent_obj
        elif parent_type == 'entry':
            parent_obj = get_object_or_404(Entry, id=parent_id_int)
            kw['entry'] = parent_obj
        else:
            parent_obj = get_object_or_404(Comment, id=parent_id_int)
            kw['comment'] = parent_obj

        # 权限：必须是作者或符合创建附件的约束（例如公开 topic 允许匿名/其他用户在其下添加日记）
        if parent_type == 'topic':
            if not (parent_obj.owner == request.user or (parent_obj.is_public and request.user.is_authenticated)):
                raise Http404
        elif parent_type == 'entry':
            if parent_obj.owner != request.user:
                raise Http404
        elif parent_type == 'comment':
            if parent_obj.user != request.user:
                raise Http404

        # 从这里继续正常逻辑
    except Exception as e:
        import logging
        logging.getLogger('learning_logs.upload').exception('Unexpected error before file parsing in upload_attachments_api: %s', e)
        return JsonResponse({'ok': False, 'error': 'Invalid upload request.'}, status=400)

    try:
        files = request.FILES.getlist('files')
    except Exception as e:
        import logging
        log = logging.getLogger('learning_logs.upload')
        log.exception('Failed to parse uploaded files: %s', e)
        return JsonResponse({'ok': False, 'error': 'Failed to parse uploaded files. Request size may be too large or form is invalid.'}, status=400)
    # Server-side guard: do not accept more than MAX_FOLDER_UPLOAD_FILES
    try:
        if files and len(files) > MAX_FOLDER_UPLOAD_FILES:
            return JsonResponse({'ok': False, 'error': f'Too many files in upload (max {MAX_FOLDER_UPLOAD_FILES}).'}, status=400)
    except Exception:
        pass
    # Log basic request info to help diagnose folder-specific failures
    try:
        import logging
        upl = logging.getLogger('learning_logs.upload')
        upl.debug('upload_attachments_api POST keys=%s FILES=%s', list(request.POST.keys()), [getattr(f,'name',None) for f in files])
    except Exception:
        pass

    # Parse relative paths from POST (supports object list with name/size/path)
    # Defensive: if client sent extremely large JSON, limit its length
    rp_json = request.POST.get('relative_paths_json')
    if isinstance(rp_json, str) and len(rp_json) > 20000:
        try:
            import logging
            logging.getLogger('learning_logs.upload').warning('relative_paths_json unusually large, truncating length=%s', len(rp_json))
        except Exception:
            pass
        # truncate to avoid parsing overly large payloads
        rp_json = rp_json[:20000]
    rel_index_map, rel_meta_map = _parse_relative_paths(request.POST)
    try:
        try:
            import logging
            upload_log = logging.getLogger('learning_logs.upload')
            total_bytes = sum([getattr(f,'size',0) for f in files])
            upload_log.debug('upload_attachments_api files=%s total_bytes=%s names=%s rel_index_map_keys=%s rel_meta_map_keys_sample=%s referer=%s', len(files), total_bytes, [getattr(f, 'name', None) for f in files], list(rel_index_map.keys()), list(rel_meta_map.keys())[:10], request.META.get('HTTP_REFERER'))
        except Exception:
            pass
        upload_session = request.POST.get('upload_session')
        created = _save_attachments_from_request(files, request.user, **kw, relative_paths=rel_index_map, relative_meta=rel_meta_map, upload_session=upload_session)
        try:
            import logging
            upl = logging.getLogger('learning_logs.upload')
            details = [(a.id, a.original_name, a.relative_path) for a in created]
            upl.debug('upload_attachments_api saved attachments: %s', details)
        except Exception:
            pass
    except Exception as e:
        import logging
        log = logging.getLogger('learning_logs.upload')
        log.exception('Error saving attachments: %s', e)
        return JsonResponse({'ok': False, 'error': 'Server error when saving attachments.'}, status=500)
    data = []
    for a in created:
        data.append({
            'id': a.id,
            'name': a.original_name,
            'url': a.file.url,
            'is_image': a.is_image,
            'is_text': a.is_text_like,
            'is_audio': a.is_audio,
            'is_video': a.is_video,
            'size': a.size,
            'relative_path': a.relative_path,
        })
    return JsonResponse({'ok': True, 'files': data})


def preview_attachment(request, attachment_id):
    """预览文本类附件内容（限制大小），其它类型重定向到文件 URL 或在模板嵌入。仅对有权查看者开放。"""
    from .models import Attachment
    att = Attachment.objects.select_related('entry', 'owner', 'entry__topic', 'topic', 'comment', 'comment__entry', 'comment__entry__topic').get(id=attachment_id)
    entry = att.entry or (att.comment.entry if att.comment_id else None)
    topic = att.topic or (entry.topic if entry else None)
    if topic is None:
        raise Http404
    # 调试日志：记录访问者与附件公开性，用于排查游客访问问题
    try:
        import logging
        log = logging.getLogger('learning_logs.preview')
        log.debug('preview_attachment access id=%s user=%s user_id=%s topic_id=%s topic_public=%s entry_id=%s entry_public=%s att_public=%s att_owner=%s',
                  att.id, getattr(request.user, 'username', None), getattr(request.user, 'id', None), getattr(topic, 'id', None), bool(getattr(topic, 'is_public', False)),
                  getattr(entry, 'id', None), bool(getattr(entry, 'is_public', False)) if entry else None, bool(getattr(att, 'is_public', False)), getattr(att.owner, 'id', None))
    except Exception:
        pass
    # 权限判定（更明确）：允许访问的情况为：
    # - 当前用户为主题作者；
    # - 或主题为公开且（无 entry 或 entry 为公开）；
    # - 或附件自身为公开；
    # - 或当前用户为附件上传者。
    user_is_owner = (topic.owner == request.user)
    topic_public = bool(getattr(topic, 'is_public', False))
    entry_public = True if entry is None else bool(getattr(entry, 'is_public', False))
    att_public = bool(getattr(att, 'is_public', False))
    user_is_att_owner = getattr(att.owner, 'id', None) == getattr(request.user, 'id', None)

    allowed = user_is_owner or (topic_public and entry_public) or att_public or user_is_att_owner
    if not allowed:
        raise Http404

    # 根据附件类型选择预览方式：文本类读取片段，图片/音视频在模板中直接嵌入
    context = {'attachment': att, 'entry': entry, 'topic': topic}
    if att.is_text_like:
        max_bytes = 200 * 1024  # 200KB
        try:
            file_obj = att.file.open('rb')
            data = file_obj.read(max_bytes)
            file_obj.close()
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                text = data.decode('latin-1', errors='replace')
        except Exception:
            text = '(无法读取文件内容)'
        context['text'] = text
        context['preview_type'] = 'text'
    elif att.is_image:
        context['preview_type'] = 'image'
    elif att.is_video:
        context['preview_type'] = 'video'
    elif att.is_audio:
        context['preview_type'] = 'audio'
    else:
        context['preview_type'] = 'unsupported'

    return render(request, 'learning_logs/preview_attachment.html', context)


def download_attachment(request, attachment_id):
    """提供单个附件文件下载，带原始文件名；遵循与预览相同的权限规则。"""
    att = get_object_or_404(Attachment, id=attachment_id)
    try:
        import logging
        log = logging.getLogger('learning_logs.download')
        log.debug('download_attachment request id=%s user=%s user_id=%s att_public=%s att_owner=%s', att.id, getattr(request.user, 'username', None), getattr(request.user, 'id', None), bool(getattr(att, 'is_public', False)), getattr(att.owner, 'id', None))
    except Exception:
        pass
    # 临时调试日志：定位不能下载的问题（仅在出问题阶段，后续可去掉）
    import logging
    log = logging.getLogger('learning_logs.download')
    log.info('download_attachment start id=%s name=%s content_type=%s', att.id, att.original_name, att.content_type)
    entry = att.entry or (att.comment.entry if att.comment_id else None)
    topic = att.topic or (entry.topic if entry else None)
    if topic is None:
        log.warning('download_attachment topic_missing id=%s', att.id)
        raise Http404
    # 权限判定（与 preview_attachment 保持一致）
    user_is_owner = (topic.owner == request.user)
    topic_public = bool(getattr(topic, 'is_public', False))
    entry_public = True if entry is None else bool(getattr(entry, 'is_public', False))
    att_public = bool(getattr(att, 'is_public', False))
    user_is_att_owner = getattr(att.owner, 'id', None) == getattr(request.user, 'id', None)

    allowed = user_is_owner or (topic_public and entry_public) or att_public or user_is_att_owner
    if not allowed:
        log.warning('download_attachment forbidden id=%s user=%s user_id=%s topic_public=%s entry_public=%s att_public=%s att_owner=%s', att.id, getattr(request.user, 'username', None), getattr(request.user, 'id', None), topic_public, entry_public, att_public, getattr(att.owner, 'id', None))
        raise Http404
    f = att.file
    try:
        # 诊断读写：尝试读取首字节确认 storage 真正返回内容，然后重新打开以供 FileResponse 使用
        try:
            # 先记录一些元信息
            size_attr = getattr(f, 'size', None)
            name_attr = getattr(f, 'name', None)
            log.info('download_attachment attempt open id=%s name=%s size_attr=%s content_type=%s att.size=%s', att.id, name_attr, size_attr, att.content_type, att.size)
        except Exception:
            log.exception('download_attachment metadata read failed for id=%s', att.id)

        # 尝试读取一小段以确认后端是否返回有效数据
        try:
            tmp = f.open('rb')
            first = tmp.read(1)
            tmp.close()
            log.info('download_attachment first_byte_len=%d id=%s', 0 if first is None else len(first), att.id)
        except Exception:
            log.exception('download_attachment quick_read failed id=%s', att.id)

        # 重新打开用于返回，部分 storage backend 在重复 open 上表现不同但通常可行
        fh = f.open('rb')
        response = FileResponse(fh)
    except Exception:
        # 无法通过 storage.open 读取（例如 Cloudinary 未正确配置或网络问题），退回到重定向到文件外链
        log.exception('download_attachment file_open_failed id=%s storage_name=%s, falling back to redirect', att.id, getattr(f, 'name', None))
        try:
            url = f.url
        except Exception:
            url = None
        if url:
            return redirect(url)
        raise Http404
    # 设置文件名（处理非 ASCII），并尽量设置 Content-Type / Content-Length 以兼容各浏览器
    from urllib.parse import quote
    # 允许通过 ?download_name=... 指定建议的下载文件名（仅建议，浏览器可忽略）
    def _sanitize_name(n: str) -> str:
        if not n:
            return ''
        # 去掉路径部分及危险字符，限制长度
        n = n.replace('\\', '/').split('/')[-1]
        return n[:200]

    download_name = _sanitize_name(request.GET.get('download_name', '') or att.original_name or 'download')
    response['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(download_name)
    try:
        # 明确告知浏览器真实的 MIME 类型
        if att.content_type:
            response['Content-Type'] = att.content_type
    except Exception:
        pass
    try:
        if getattr(att, 'size', None):
            response['Content-Length'] = str(att.size)
    except Exception:
        pass
    log.info('download_attachment success id=%s filename=%s size=%s', att.id, download_name, getattr(f, 'size', None))
    return response


@login_required
def download_folder(request):
    """将指定父对象下某个相对路径前缀对应的所有附件打包 zip 下载。
    GET 参数：parent_type=topic|entry|comment, parent_id=数字, folder_path=路径
    权限：与附件访问一致；不要求作者身份（只要能看到附件即可下载）。
    """
    parent_type = request.GET.get('parent_type')
    parent_id = request.GET.get('parent_id')
    folder_path = (request.GET.get('folder_path') or '').replace('\\', '/').strip('/')
    if parent_type not in {'topic', 'entry', 'comment'}:
        raise Http404
    try:
        pid = int(parent_id)
    except Exception:
        raise Http404
    if not folder_path:
        raise Http404
    if parent_type == 'topic':
        obj = get_object_or_404(Topic, id=pid)
        attachments_qs = obj.attachment_set.all()
        topic = obj
        entry = None
    elif parent_type == 'entry':
        obj = get_object_or_404(Entry, id=pid)
        attachments_qs = obj.attachment_set.all()
        topic = obj.topic
        entry = obj
    else:
        obj = get_object_or_404(Comment, id=pid)
        attachments_qs = obj.attachment_set.all()
        topic = obj.entry.topic
        entry = obj.entry
    # 访问权限（复用 preview 逻辑）
    if topic.owner == request.user:
        pass
    else:
        if not topic.is_public:
            raise Http404
        if entry and not entry.is_public:
            raise Http404
    prefix = folder_path + '/'
    targets = attachments_qs.filter(Q(relative_path=folder_path) | Q(relative_path__startswith=prefix))
    if not targets.exists():
        raise Http404
    # 构建 zip 流
    import io, zipfile
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    for att in targets:
        # 计算在 zip 中的相对路径：使用 att.relative_path 的后缀部分（去掉前缀文件夹）
        rel = att.relative_path or att.original_name
        if rel.startswith(folder_path):
            arcname = rel
        else:
            arcname = folder_path + '/' + (att.original_name or 'file')
        try:
            with att.file.open('rb') as rf:
                zf.writestr(arcname, rf.read())
        except Exception:
            continue
    zf.close()
    buf.seek(0)
    from urllib.parse import quote
    # 支持 ?download_name=custom_name.zip 来建议客户端下载时的文件名（浏览器可选择忽略）
    def _sanitize_name(n: str) -> str:
        if not n:
            return ''
        n = n.replace('\\', '/').split('/')[-1]
        return n[:200]

    requested_name = _sanitize_name(request.GET.get('download_name', ''))
    zip_name = requested_name or (folder_path + '.zip')
    resp = FileResponse(buf, as_attachment=True, filename=zip_name)
    resp['Content-Type'] = 'application/zip'
    resp['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(zip_name)
    return resp


@login_required
def add_comment(request, entry_id):
    """添加评论：私密日记仅作者可评；公开日记任何登录用户可评。支持评论上传附件。"""
    entry = Entry.objects.get(id=entry_id)
    topic = entry.topic
    # Treat 'traveler' as read-only: prompt for real login before allowing comments/replies
    if getattr(request.user, 'username', None) == 'traveler':
        login_url = reverse('accounts:login')
        return redirect(f"{login_url}?next={request.get_full_path()}")
    # 私密日记：仅作者可评论；公开日记：登录用户可评论
    if not entry.is_public and entry.owner != request.user:
        raise Http404

    # 支持 GET 展示单独的评论页面（统一在单页进行评论输入/提交）
    if request.method == 'GET':
        parent_id = request.GET.get('parent_id')
        form = CommentForm(initial={'parent_id': parent_id} if parent_id else None)
        return render(request, 'learning_logs/add_comment.html', {
            'entry': entry,
            'topic': topic,
            'form': form,
            'parent_id': parent_id,
        })

    form = CommentForm(data=request.POST)
    # If form is invalid, show the form with errors instead of silently redirecting.
    if not form.is_valid():
        parent_id = request.POST.get('parent_id')
        return render(request, 'learning_logs/add_comment.html', {
            'entry': entry,
            'topic': topic,
            'form': form,
            'parent_id': parent_id,
        })

    if form.is_valid():
        comment = form.save(commit=False)
        comment.entry = entry
        # 支持回复（parent），从表单 cleaned_data 中读取 parent_id 并校验归属
        parent_id = form.cleaned_data.get('parent_id')
        if parent_id:
            try:
                p = Comment.objects.get(id=int(parent_id))
                if p.entry_id == entry.id:
                    comment.parent = p
            except Exception:
                pass
        # 匿名评论：优先使用表单 cleaned_data（更安全）
        anonymous = form.cleaned_data.get('anonymous', False)
        if anonymous:
            comment.user = None
            # 留空 name，models.display_name 会回退为 '匿名' 或 name 字段
            comment.name = ''
        else:
            # 使用登录用户作为评论者
            comment.user = request.user
            comment.name = ''
        files = request.FILES.getlist('comment_attachments')
        # 支持文件夹上传的相对路径映射：relative_paths_json (优先) 或 relative_path[<index>] = path
        rel_index_map, rel_meta_map = _parse_relative_paths(request.POST)
        # 若文本与附件皆为空，则忽略此次提交
        if (not (comment.text or '').strip()) and not files:
            try:
                url = reverse('learning_logs:topic_by_user', kwargs={'username': topic.owner.username, 'topic_name': topic.text})
                return redirect(url)
            except Exception:
                return redirect('learning_logs:topic', topic_name=topic.text)
        comment.save()
        # 保存评论附件（可多文件）
        _save_attachments_from_request(files, request.user, comment=comment, relative_paths=rel_index_map, relative_meta=rel_meta_map)

    # Redirect back to discovery view for the topic if available (preserve user-prefixed path)
    try:
        owner_username = topic.owner.username
        url = reverse('learning_logs:discovey_by_user', kwargs={'username': owner_username, 'topic_name': topic.text})
        return redirect(url)
    except Exception:
        return redirect('learning_logs:topic', topic_name=topic.text)


@login_required
@require_POST
def delete_comment(request, comment_id):
    """删除某条评论（仅评论作者可删）。删除同时清理该评论的所有附件及回复。"""
    c = get_object_or_404(Comment, id=comment_id)
    # 仅评论作者可删
    if c.user != request.user:
        raise Http404
    # 删除该评论下的所有附件（Attachment 的 post_delete 会清理文件）
    for a in c.attachment_set.all():
        a.delete()
    # 删除所有子回复（递归删除）
    def _del_subtree(comment):
        for r in comment.replies.all():
            _del_subtree(r)
            for a in r.attachment_set.all():
                a.delete()
            r.delete()
    _del_subtree(c)
    c.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(request.META.get('HTTP_REFERER', 'learning_logs:index'))


def _resolve_topic_by_name_for_user(topic_name: str, user, username: str = None):
    """根据名称为当前用户解析可访问的 Topic。
    优先返回用户自己的同名日记本；否则返回他人公开的同名日记本（若存在则取最新创建的一个）。
    若均不存在则 404。
    注意：若名称包含斜杠可能导致路径解析异常，建议避免在名称中使用 '/'
    """
    qs = Topic.objects.filter(text=topic_name)
    # If username provided, try to resolve by username first
    if username:
        from django.contrib.auth.models import User
        try:
            owner = User.objects.get(username=username)
            try:
                return qs.get(owner=owner)
            except Topic.DoesNotExist:
                pass
        except User.DoesNotExist:
            pass

    if user.is_authenticated:
        try:
            return qs.get(owner=user)
        except Topic.DoesNotExist:
            pass

    public_qs = qs.filter(is_public=True).order_by('-date_added')
    topic = public_qs.first()
    if not topic:
        raise Http404
    return topic


@login_required
def delete_topic(request, topic_name):
    """删除日记本（仅作者）。GET 显示确认页，POST 确认后删除并返回“我的日记本”。"""
    topic = _resolve_topic_by_name_for_user(topic_name, request.user)
    # 仅作者可删
    if topic.owner != request.user:
        raise Http404

    if request.method == 'POST':
        # 确认删除
        topic.delete()
        return redirect('learning_logs:topics')

    # 确认页
    return render(request, 'learning_logs/delete_topic_confirm.html', {
        'topic': topic,
    })