import mimetypes
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
    text = models.TextField()
    date_added = models.DateTimeField(auto_now_add=True)
    # 是否公开：False 为私密，True 为公开
    is_public = models.BooleanField(default=False)
    # 日记作者（新增，用于区分谁写的这篇日记）
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'entries'

    def __str__(self):
        """Return a simple string representing the entry."""
        return f"{self.text[:50]}..."


class Comment(models.Model):
    """对公开日记的评论。允许匿名（无 user），或登录用户。"""
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE)
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
    """根据归属（topic/entry/comment）决定存储子目录。"""
    if getattr(instance, 'entry_id', None):
        return f"attachments/entries/{instance.entry_id}/{filename}"
    if getattr(instance, 'topic_id', None):
        return f"attachments/topics/{instance.topic_id}/{filename}"
    if getattr(instance, 'comment_id', None):
        return f"attachments/comments/{instance.comment_id}/{filename}"
    return f"attachments/misc/{filename}"


class Attachment(models.Model):
    """日记附件：由日记作者上传，可选择公开或私密。"""
    # 归属对象三选一（或二选一）：topic / entry / comment
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey('Comment', on_delete=models.CASCADE, null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to=upload_to_attachment)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.BigIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = self.file.name
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