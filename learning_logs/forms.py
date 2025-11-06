from django import forms

from .models import Topic, Entry, Comment, Attachment


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ['text', 'is_public']
        labels = {
            'text': '日记本名称',
            'is_public': '是否公开',
        }

class EntryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 允许仅上传附件而不填写正文
        self.fields['text'].required = False
    class Meta:
        model = Entry
        fields = ['text', 'is_public']
        labels = {
            'text': '日记正文',
            'is_public': '是否公开',
        }
        widgets = {'text': forms.Textarea(attrs={'cols': 80})}


class CommentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 允许仅上传附件而不填写评论文字
        self.fields['text'].required = False
    class Meta:
        model = Comment
        fields = ['name', 'text']
        labels = {
            'name': '昵称（未登录时必填）',
            'text': '评论内容',
        }
        widgets = {'text': forms.Textarea(attrs={'rows': 3})}


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ['file', 'is_public']
        labels = {
            'file': '选择文件',
            'is_public': '是否公开',
        }