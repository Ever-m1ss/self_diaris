from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class CustomUserCreationForm(UserCreationForm):
    """自定义用户注册表单：提供中文标签与帮助文本，避免默认英文说明。"""

    error_messages = {
        **UserCreationForm.error_messages,
        "password_mismatch": "两次输入的密码不一致。",
    }

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "password1", "password2")
        labels = {
            "username": "用户名",
            "password1": "密码",
            "password2": "确认密码",
        }
        # 注意：Meta.help_texts 对 password1 可能不会生效，因为父类会动态设置。
        help_texts = {
            "username": "4-150 个字符，只能包含字母、数字和 @/./+/-/_",
            "password1": "至少 8 个字符，不能过于简单或与个人信息相似，且不能全部为数字。",
            "password2": "请再次输入相同的密码进行确认。",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 强制覆盖可能由父类或验证器注入的英文帮助文本/标签
        self.fields["username"].label = "用户名"
        # 不展示帮助小字：置空帮助文本（模板也不再渲染 help_text）
        self.fields["username"].help_text = ""
        self.fields["password1"].label = "密码"
        self.fields["password1"].help_text = ""
        self.fields["password2"].label = "确认密码"
        self.fields["password2"].help_text = ""

        # 增加占位符和较大输入框样式（与模板风格一致）
        self.fields["username"].widget = forms.TextInput(attrs={
            "class": "form-control form-control-lg",
            "placeholder": "请输入用户名",
            "autofocus": True,
        })
        self.fields["password1"].widget = forms.PasswordInput(attrs={
            "class": "form-control form-control-lg",
            "placeholder": "请输入密码",
        })
        self.fields["password2"].widget = forms.PasswordInput(attrs={
            "class": "form-control form-control-lg",
            "placeholder": "请再次输入密码",
        })

    def clean_username(self):
        """用户名唯一性（忽略大小写）校验，给出更友好的中文提示。

        说明：Django 内置 User.username 已设置 unique=True，但在部分数据库中
        大小写可能被视为不同值。这里通过应用层校验实现“大小写不敏感”的唯一性，
        避免出现 user 与 User 并存的情况。
        """
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            return username
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("该用户名已被占用，请更换一个。")
        return username
