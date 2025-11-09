from django import template
from pathlib import Path

register = template.Library()

@register.filter
def filename(value):
    """从路径中提取文件名。"""
    return Path(value).name


@register.filter(name='icon_for')
def icon_for(filename: str) -> str:
    """根据文件扩展名返回合适的图标相对路径（用于 {% static %}）。
    返回示例：'img/icons/file-pdf.svg'
    """
    ext = (Path(str(filename)).suffix or '').lower().lstrip('.')
    if not ext:
        return 'img/icons/file-earmark.svg'

    img_ext = {'png','jpg','jpeg','gif','webp','bmp','tiff','svg'}
    video_ext = {'mp4','mov','m4v','avi','mkv','webm','wmv'}
    audio_ext = {'mp3','wav','flac','aac','m4a','ogg'}
    text_ext = {'txt','log'}
    md_ext = {'md','markdown'}
    csv_ext = {'csv'}
    json_ext = {'json'}
    pdf_ext = {'pdf'}
    word_ext = {'doc','docx'}
    excel_ext = {'xls','xlsx'}
    ppt_ext = {'ppt','pptx'}
    archive_ext = {'zip','rar','7z','tar','gz','bz2','xz'}
    code_ext = {'py','js','ts','html','htm','css','xml','yml','yaml','sh','bat','ps1','java','go','rb','php','c','cpp','h','hpp','cs'}

    if ext in img_ext:
        return 'img/icons/file-image.svg'
    if ext in video_ext:
        return 'img/icons/file-play.svg'
    if ext in audio_ext:
        return 'img/icons/file-music.svg'
    if ext in md_ext:
        return 'img/icons/file-markdown.svg'
    if ext in csv_ext:
        return 'img/icons/file-csv.svg'
    if ext in json_ext:
        return 'img/icons/file-json.svg'
    if ext in pdf_ext:
        return 'img/icons/file-pdf.svg'
    if ext in word_ext:
        return 'img/icons/file-word.svg'
    if ext in excel_ext:
        return 'img/icons/file-excel.svg'
    if ext in ppt_ext:
        return 'img/icons/file-powerpoint.svg'
    if ext in archive_ext:
        return 'img/icons/file-archive.svg'
    if ext in text_ext or ext in code_ext:
        return 'img/icons/file-code.svg'
    return 'img/icons/file-earmark.svg'
