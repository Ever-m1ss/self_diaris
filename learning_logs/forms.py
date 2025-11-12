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
        # 隐藏字段：parent_id 用于回复时传入父评论 id（后端会在视图中校验所属 entry）
        self.fields['parent_id'] = forms.IntegerField(required=False, widget=forms.HiddenInput())
        # 当前登录用户可选择匿名发布（仅在评论表单中显示）
        self.fields['anonymous'] = forms.BooleanField(required=False, initial=False, label='匿名发表')
    class Meta:
        model = Comment
        # 'parent_id' is a non-model hidden field used to pass the parent comment's id
        # to the view when creating a reply. Do NOT include it in ModelForm Meta.fields
        # because ModelForm expects actual model field names here.
        # 不暴露 name 字段；已使用登录用户的用户名作为默认显示名
        fields = ['text']
        labels = {
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