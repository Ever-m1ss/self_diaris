import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Topic(models.Model):
    """A topic the user is learning about."""
    text = models.CharField(max_length=200)
    date_added = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    # 是否公开：False 为私密，True 为公开
    is_public = models.BooleanField(default=False)

    def __str__(self):
        """Return a string representation of the model."""
        return self.text


class Entry(models.Model):
    """Something specific learned about a topic."""
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    # 可选的日记标题，允许为空
    title = models.CharField(max_length=255, blank=True, default='')
    text = models.TextField()
    date_added = models.DateTimeField(auto_now_add=True)
    # 记录最后编辑时间（nullable：创建时为空，编辑时由视图设置）
    last_edited = models.DateTimeField(null=True, blank=True)
    # 是否公开：False 为私密，True 为公开
    is_public = models.BooleanField(default=False)
    # 日记作者（新增，用于区分谁写的这篇日记）
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'entries'

    def __str__(self):
        """Return a simple string representing the entry.

        Prefer to show title when present for easier debugging and listing.
        """
        if self.title:
            return f"{self.title[:60]}"
        return f"{self.text[:50]}..."


class Comment(models.Model):
    """对公开日记的评论。允许匿名（无 user），或登录用户。"""
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100, blank=True)
    text = models.TextField()
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_added"]

    def display_name(self):
        return self.user.username if self.user else (self.name or "匿名")

    def __str__(self):
        return f"评论 by {self.display_name()} on {self.entry_id}"


def upload_to_attachment(instance, filename):
    """根据归属（topic/entry/comment）决定存储子目录，
    同时在归属目录下附加相对路径（如通过“上传文件夹”功能带来的子目录）。"""
    # 清理潜在的目录穿越
    def _safe_rel(p: str) -> str:
        p = (p or '').replace('\\', '/').strip('/')
        # 去掉 .. 等危险片段
        parts = [seg for seg in p.split('/') if seg not in ('', '.', '..')]
        return '/'.join(parts)

    base = "attachments/misc"
    if getattr(instance, 'entry_id', None):
        base = f"attachments/entries/{instance.entry_id}"
    elif getattr(instance, 'topic_id', None):
        base = f"attachments/topics/{instance.topic_id}"
    elif getattr(instance, 'comment_id', None):
        base = f"attachments/comments/{instance.comment_id}"

    subdir = ''
    rel = _safe_rel(getattr(instance, 'relative_path', '') or '')
    if rel:
        # 只取目录部分，文件名仍以上传的 filename 为准
        rel_dir = _safe_rel(str(Path(rel).parent))
        if rel_dir:
            subdir = f"/{rel_dir}"

    return f"{base}{subdir}/{filename}"


class Attachment(models.Model):
    """日记附件：由日记作者上传，可选择公开或私密。"""
    # 归属对象三选一（或二选一）：topic / entry / comment
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey('Comment', on_delete=models.CASCADE, null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to=upload_to_attachment)
    original_name = models.CharField(max_length=255)
    relative_path = models.CharField(max_length=500, blank=True, default='')
    content_type = models.CharField(max_length=100, blank=True)
    size = models.BigIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # 临时上传 session key：用于 new_entry 情况下在创建 entry 后将 topic-level临时附件附加到该 entry
    upload_session = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = self.file.name
        # 规范化 relative_path
        if self.relative_path:
            rp = self.relative_path.replace('\\', '/').strip('/')
            parts = [seg for seg in rp.split('/') if seg not in ('', '.', '..')]
            self.relative_path = '/'.join(parts)
        if self.file and not self.content_type:
            guessed, _ = mimetypes.guess_type(self.file.name)
            self.content_type = guessed or "application/octet-stream"
        try:
            self.size = self.file.size
        except Exception:
            pass
        super().save(*args, **kwargs)

    @property
    def is_image(self):
        return self.content_type.startswith('image/')

    @property
    def is_audio(self):
        return self.content_type.startswith('audio/')

    @property
    def is_video(self):
        return self.content_type.startswith('video/')

    @property
    def is_text_like(self):
        # 常见可文本预览的类型
        return self.content_type.startswith('text/') or self.original_name.lower().endswith((
            '.txt', '.md', '.py', '.c', '.cpp', '.h', '.html', '.css', '.js', '.json', '.csv', '.log'
        ))


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    """删除数据库记录后同步清理对应的物理文件和空目录。"""
    file_field = instance.file
    if not file_field:
        return

    try:
        file_path = Path(file_field.path)
    except (ValueError, FileNotFoundError, AttributeError, NotImplementedError):
        file_path = None

    file_name = file_field.name
    storage = file_field.storage
    if file_name:
        try:
            storage.delete(file_name)
        except Exception:
            # 存储后端可能已删除或不支持 delete，忽略即可。
            pass

    if file_path is not None:
        _cleanup_empty_directories(file_path)


def _cleanup_empty_directories(file_path: Path) -> None:
    """向上递归删除空目录，直至 media 根目录。"""
    media_root = Path(settings.MEDIA_ROOT).resolve()

    try:
        resolved_path = file_path.resolve()
    except FileNotFoundError:
        resolved_path = file_path.resolve(strict=False)

    try:
        resolved_path.relative_to(media_root)
    except ValueError:
        return

    current_dir = resolved_path.parent
    while current_dir != media_root:
        try:
            next(current_dir.iterdir())
            break
        except StopIteration:
            try:
                current_dir.rmdir()
            except OSError:
                break
            current_dir = current_dir.parent
        except OSError:
            break