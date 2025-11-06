from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.db.models import Q

from .models import Topic, Entry, Comment, Attachment
from .forms import TopicForm, EntryForm, CommentForm


def index(request):
    """Home page: 未登录展示登录/注册；已登录展示“发现”：左侧日记本列表，右侧浏览所选日记本下的日记。"""
    context = {}
    if request.user.is_authenticated:
        # 可发现的日记本：自己的全部 + 他人公开
        topics_qs = Topic.objects.filter(Q(owner=request.user) | Q(is_public=True)).order_by('-date_added')

        # 选中的日记本
        selected_topic = None
        t_id = request.GET.get('t')
        if t_id:
            try:
                selected_topic = topics_qs.get(id=int(t_id))
            except Exception:
                selected_topic = None

        # 右侧日记列表：若无选中则为空
        entries = None
        if selected_topic is not None:
            if request.user == selected_topic.owner:
                entries = selected_topic.entry_set.order_by('-date_added')
            else:
                entries = selected_topic.entry_set.filter(Q(is_public=True) | Q(owner=request.user)).order_by('-date_added')

        context.update({
            'discover_topics': topics_qs,
            'selected_topic': selected_topic,
            'entries': entries,
        })
    return render(request, 'learning_logs/index.html', context)

@login_required
def topics(request):
    """Show all topics."""
    topics = Topic.objects.filter(owner=request.user).order_by('date_added')
    context = {'topics': topics}
    return render(request, 'learning_logs/topics.html', context)

@login_required
def topic(request, topic_name):
    """按名称展示单个日记本及其日记，遵循可见性规则。"""
    topic = _resolve_topic_by_name_for_user(topic_name, request.user)

    # 条目可见性：
    if request.user == topic.owner:
        entries = topic.entry_set.order_by('-date_added')
    else:
        entries = topic.entry_set.filter(Q(is_public=True) | Q(owner=request.user)).order_by('-date_added')

    comment_form = CommentForm()
    context = {'topic': topic, 'entries': entries, 'comment_form': comment_form}
    return render(request, 'learning_logs/topic.html', context)

@login_required
def new_topic(request):
    """Add a new topic."""
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
            # 处理附件（可选，多文件）
            files = request.FILES.getlist('attachments')
            _save_attachments_from_request(files, request.user, topic=new_topic)
            return redirect('learning_logs:topics')

    # Display a blank or invalid form.
    context = {'form': form}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def new_entry(request, topic_id):
    """Add a new entry for a particular topic."""
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
        files = request.FILES.getlist('attachments')
        if form.is_valid():
            text_val = (form.cleaned_data.get('text') or '').strip()
            # 校验：正文与附件不可同时为空
            if not text_val and not files:
                form.add_error(None, '请填写日记正文或至少上传一个附件。')
            else:
                new_entry = form.save(commit=False)
                new_entry.topic = topic
                new_entry.owner = request.user
                new_entry.save()
                # 附件（可选，批量）
                _save_attachments_from_request(files, request.user, entry=new_entry)
                return redirect('learning_logs:topic', topic_name=topic.text)

    # Display a blank or invalid form.
    context = {'topic': topic, 'form': form}
    return render(request, 'learning_logs/new_entry.html', context)

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry."""
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
            # 可在编辑时追加附件
            files = request.FILES.getlist('attachments')
            _save_attachments_from_request(files, request.user, entry=entry)
            return redirect('learning_logs:topic', topic_name=topic.text)

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
        return redirect('learning_logs:topic', topic_name=topic.text)

    return render(request, 'learning_logs/delete_entry_confirm.html', {
        'entry': entry,
        'topic': topic,
    })


def _save_attachments_from_request(files, owner, *, topic=None, entry=None, comment=None):
    if not files:
        return
    for f in files:
        # 附件公开性由父对象决定
        derived_public = False
        if entry is not None:
            derived_public = bool(entry.is_public)
        elif topic is not None:
            derived_public = bool(topic.is_public)
        elif comment is not None:
            # 评论不允许私密，评论附件一律公开
            derived_public = True
        att = Attachment(owner=owner, topic=topic, entry=entry, comment=comment, file=f, is_public=derived_public)
        att.original_name = f.name
        att.save()


@login_required
def preview_attachment(request, attachment_id):
    """预览文本类附件内容（限制大小），其它类型重定向到文件 URL 或在模板嵌入。仅对有权查看者开放。"""
    from .models import Attachment
    att = Attachment.objects.select_related('entry', 'owner', 'entry__topic', 'topic', 'comment', 'comment__entry', 'comment__entry__topic').get(id=attachment_id)
    entry = att.entry or (att.comment.entry if att.comment_id else None)
    topic = att.topic or (entry.topic if entry else None)
    if topic is None:
        raise Http404
    # 权限：必须登录；需能查看所属对象；如附件私密，仅上传者可看
    if topic.owner == request.user:
        pass
    else:
        # 非作者：
        # - 主题私密：不可见
        if not topic.is_public:
            raise Http404
        # - 若有 entry：私密日记不可见
        if entry and not entry.is_public:
            raise Http404
        # - 附件为私密时仅上传者可见
        if not att.is_public and att.owner != request.user:
            raise Http404

    # 仅文本类提供内联预览
    if not att.is_text_like:
        raise Http404

    # 读取有限大小，避免过大
    max_bytes = 200 * 1024  # 200KB
    try:
        file_obj = att.file.open('rb')
        data = file_obj.read(max_bytes)
        file_obj.close()
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            # 回退 latin-1，避免报错
            text = data.decode('latin-1', errors='replace')
    except Exception:
        text = '(无法读取文件内容)'

    return render(request, 'learning_logs/preview_attachment.html', {
        'attachment': att,
        'entry': entry,
        'topic': topic,
        'text': text,
    })


@login_required
def add_comment(request, entry_id):
    """添加评论：私密日记仅作者可评；公开日记任何登录用户可评。支持评论上传附件。"""
    entry = Entry.objects.get(id=entry_id)
    topic = entry.topic
    # 私密日记：仅作者可评论；公开日记：登录用户可评论
    if not entry.is_public and entry.owner != request.user:
        raise Http404

    if request.method != 'POST':
        raise Http404

    form = CommentForm(data=request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.entry = entry
        # 匿名评论：勾选则不记录用户
        if request.POST.get('anonymous'):
            comment.user = None
            comment.name = '匿名'
        else:
            comment.user = request.user
            comment.name = ''
        files = request.FILES.getlist('comment_attachments')
        # 若文本与附件皆为空，则忽略此次提交
        if (not (comment.text or '').strip()) and not files:
            return redirect('learning_logs:topic', topic_name=topic.text)
        comment.save()
        # 保存评论附件（可多文件）
        _save_attachments_from_request(files, request.user, comment=comment)

    return redirect('learning_logs:topic', topic_name=topic.text)


def _resolve_topic_by_name_for_user(topic_name: str, user):
    """根据名称为当前用户解析可访问的 Topic。
    优先返回用户自己的同名日记本；否则返回他人公开的同名日记本（若存在则取最新创建的一个）。
    若均不存在则 404。
    注意：若名称包含斜杠可能导致路径解析异常，建议避免在名称中使用 '/'
    """
    qs = Topic.objects.filter(text=topic_name)
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