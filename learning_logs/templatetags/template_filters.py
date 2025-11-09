from django import template
from pathlib import Path

register = template.Library()

@register.filter
def filename(value):
    """从路径中提取文件名。"""
    return Path(value).name
