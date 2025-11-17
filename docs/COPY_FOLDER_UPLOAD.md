# 拷贝后运行方法（从代码拷贝/克隆到部署与验证）

本文档只说明：把仓库拷贝/克隆到本地或服务器后，如何一步步配置虚拟环境、安装依赖、完成 Django 初始化（迁移、创建管理员）、以及如何把应用部署到生产服务器（systemd + gunicorn + nginx），并包含上传相关的服务级配置（例如 Nginx 的 body 大小限制）。

适用场景：你已经把仓库复制到一台 Linux 服务器或本地开发机器，准备运行或部署该项目。

目录：
- 本地开发（Windows / PowerShell）快速运行
- 服务器部署（Ubuntu 20.04+/Debian 系列）—— virtualenv、依赖、gunicorn、systemd、nginx
- 上传大文件注意项（Nginx 与 Django 设置）
- 验证与排查

1) 克隆或拷贝仓库到一个目录（假设目标路径为 `D:\work\diary`）：

```powershell
# 克隆
git clone <repo-url> "D:\work\diary"
cd "D:\work\diary"

# 如果是直接拷贝代码，切换到该目录即可
```

2) 创建虚拟环境并激活（使用内置 venv）：

```powershell
python -m venv ll_env
.\ll_env\Scripts\Activate.ps1
```

3) 安装项目依赖（推荐使用项目根的 `requirements.txt` 或 `wheels/`）：

```powershell
# 使用 pip 安装 requirements.txt
pip install -U pip
pip install -r requirements.txt

# 如果你想使用本地 wheels（离线安装）, 例如在没有网络的环境：
pip install wheels\*.whl
```

4) 本地配置环境变量（简单方式，可在 PowerShell 中临时设置）：

```powershell
# Windows 示例：
$env:DJANGO_SETTINGS_MODULE = 'll_project.settings'
$env:SECRET_KEY = 'your-local-secret-key'
# SQLite: 默认项目可能已经配置为 sqlite db.sqlite3，无需额外 DB 环境
```

5) 运行迁移并创建管理员：

```powershell
python manage.py migrate
python manage.py createsuperuser
```

6) 运行开发服务器并访问：

```powershell
python manage.py runserver
# 访问 http://127.0.0.1:8000
```

提示：若需要测试大文件/文件夹上传，请在 `ll_project/settings.py` 中临时增加：

```python
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024
```

注意：这是开发测试用，生产请谨慎设置内存限制。
1) 在服务器上更新并安装基础依赖：

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nginx git build-essential libpq-dev
```

2) 创建系统用户和目录（可选，推荐为应用创建独立用户）：

```bash
sudo useradd -m -s /bin/bash diary || true
sudo mkdir -p /var/www/diary
sudo chown diary:diary /var/www/diary
```

3) 切换用户并拉取代码（或通过 scp/rsync 上传代码至 `/var/www/diary`）：

```bash
sudo -i -u diary
cd /var/www/diary
git clone <repo-url> .
```

或者从本地上传（示例用 rsync）：

```bash
# 在本地
rsync -av --exclude="ll_env" ./ diary@server:/var/www/diary/
```

4) 在服务器上创建并激活虚拟环境，安装依赖（优先使用 wheels 文件夹以减少网络依赖）：

```bash
cd /var/www/diary
python3.11 -m venv ll_env
source ll_env/bin/activate
pip install -U pip
# 优先使用本地 wheels
pip install wheels/*.whl || pip install -r requirements.txt
```

5) 配置环境变量（systemd 环境或使用 `.env`）：

- 推荐在 `/var/www/diary/.env` 中放置：

```
DJANGO_SETTINGS_MODULE=ll_project.settings
SECRET_KEY=your-production-secret
DATABASE_URL=sqlite:///var/www/diary/db.sqlite3  # 或你的 postgres URL
ALLOWED_HOSTS=your.domain.com
```

确保 `.env` 的权限只对应用用户可读：

```bash
chmod 600 /var/www/diary/.env
```

6) 配置 Django（settings 中的关键项）：

- `ll_project/settings.py` 中设置 `DEBUG = False`，配置 `ALLOWED_HOSTS`。
- 配置 `MEDIA_ROOT` 与 `STATIC_ROOT`：

```python
STATIC_ROOT = '/var/www/diary/staticfiles'
MEDIA_ROOT = '/var/www/diary/media'
```

确保目录存在并可写：

```bash
mkdir -p /var/www/diary/staticfiles /var/www/diary/media
chown -R diary:diary /var/www/diary/staticfiles /var/www/diary/media
```

7) 迁移并收集静态文件：

```bash
source ll_env/bin/activate
cd /var/www/diary
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

8) 配置 Gunicorn `systemd` 服务（示例 `/etc/systemd/system/diary-gunicorn.service`）：

```ini
[Unit]
Description=gunicorn daemon for diary
After=network.target

[Service]
User=diary
Group=www-data
WorkingDirectory=/var/www/diary
EnvironmentFile=/var/www/diary/.env
ExecStart=/var/www/diary/ll_env/bin/gunicorn --access-logfile - --workers 3 --bind unix:/var/www/diary/diary.sock ll_project.wsgi:application

[Install]
WantedBy=multi-user.target
```

然后启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now diary-gunicorn
sudo systemctl status diary-gunicorn
```

9) 配置 Nginx（示例 `/etc/nginx/sites-available/diary`）：

```nginx
server {
  listen 80;
  server_name your.domain.com;

  client_max_body_size 1G; # 允许大文件上传

  location /static/ {
    alias /var/www/diary/staticfiles/;
  }

  location /media/ {
    alias /var/www/diary/media/;
  }

  location / {
    include proxy_params;
    proxy_pass http://unix:/var/www/diary/diary.sock;
  }
}
```

启用并重载 nginx：

```bash
sudo ln -s /etc/nginx/sites-available/diary /etc/nginx/sites-enabled/diary
sudo nginx -t
sudo systemctl restart nginx
```

10) 检查 SELinux / AppArmor（若适用）和目录权限，确保 `gunicorn` 用户能访问 `/var/www/diary/media` 与 socket。

11) 验证：访问 `http://your.domain.com`，登录 admin 并尝试上传文件夹/文件进行验证。
# 复制/上传文件夹（Folder Upload）配置与使用说明

本文档说明项目中“上传文件夹 / 多文件夹”功能的配置方法、前端实现、后端接收逻辑、服务端配置（Nginx / Django）以及调试与常见问题排查步骤。

> 语言：中文

---

## 概览

本项目支持：

- 在表单（提交新建日记 / 编辑日记 / 新建日记本）中上传文件或文件夹；
- 在日记本（topic）页面使用异步上传（拖拽或选择文件 / 选择文件夹）；
- 保留上传的相对路径（`Attachment.relative_path`），以便在 UI 中重建文件夹结构或打包下载文件夹。

实现要点：
- 前端：使用 `input type="file" multiple webkitdirectory directory` 支持文件夹选择；通过 hidden inputs `relative_path[<index>]` 提交每个文件的相对路径。
- 后端（Django）：接收 `request.FILES` 列表和 `relative_path[...]` 映射，并在保存 `Attachment` 时将相对路径写入数据库。
- 异步上传：使用 `fetch` + `FormData`，以 `files` 字段上传并附上 `relative_path[index]`。
- 服务配置：Nginx 与 Django 的上传大小限制需调整以支持大文件（例如 1G）。

---

## 1. 前端（HTML）示例

表单内的“选择文件/选择文件夹”按钮示例（用于 `new_entry.html` / `edit_entry.html` / `new_topic.html`）：

```html
<div class="mt-2 d-flex gap-2 flex-wrap">
  <label class="btn btn-outline-primary btn-sm mb-0">
    选择文件
    <input class="d-none" type="file" name="attachments" multiple data-no-async>
  </label>
  <label class="btn btn-outline-primary btn-sm mb-0">
    选择文件夹
    <input class="d-none" type="file" name="attachments" multiple webkitdirectory directory data-no-async>
  </label>
</div>
```

要点：

- `name="attachments"`：统一字段名，后端会从 `request.FILES.getlist('attachments')` 或若干兼容字段中读取；
- `multiple`：允许多文件或（在支持的浏览器中）多文件夹选择；
- `webkitdirectory directory`：启用选择文件夹（目前大多数 Chromium 系列浏览器支持）；
- `data-no-async`：本项目的异步上传脚本 `static/js/attachments.js` 会忽略带此属性的 inputs，避免把表单内 uploads 误触发为异步上传（表单提交时再统一处理）。

> 注意：各浏览器对一次性选择多个文件夹的支持不同。Chromium 系列（Chrome / Edge）通常支持，但并非所有浏览器或版本都允许一次选择多个文件夹。

---

## 2. 前端（提交时生成相对路径）

在提交表单前，将收集表单内所有 `input[type=file][name="attachments"]` 的文件并生成 `relative_path[<index>]` 隐藏字段，示例逻辑（已实现于模板）：

```javascript
// 在表单 submit 事件中
const fileInputs = Array.from(formEl.querySelectorAll('input[type=file][name="attachments"]'));
let allFiles = [];
fileInputs.forEach(function(inp){
  if(inp.files && inp.files.length) allFiles = allFiles.concat(Array.from(inp.files));
});
allFiles.forEach(function(f, idx){
  const rel = f.webkitRelativePath || f.relativePath || f.name;
  const clean = (rel || '').replace(/\\/g, '/').replace(/^\/+/, '');
  const inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'relative_path['+idx+']'; inp.value = clean;
  formEl.appendChild(inp);
});
```

- 浏览器会把 `File` 的 `webkitRelativePath` 属性（如果可用）包含文件相对路径，例如：`photos/2025/IMG001.jpg`。
- 我们把这些路径规范为正斜杠并去掉前导 `/`。

---

## 3. 异步上传（topic 页面）

在日记本页面，我们使用异步上传（点击“选择文件/选择文件夹”或拖拽）实现即时上传。关键点：

- JS 构建 `FormData`：对每个文件调用 `fd.append('files', file, file.name)`，并对每个文件同时添加 `fd.append('relative_path[index]', rel)`；
- 异步接口：POST 到 `/attachments/upload/`（示例路由），后端会读取 `files` 与 `relative_path[...]` 并保存。

示例（简化）：

```javascript
const fd = new FormData();
files.forEach((f,i)=>{
  fd.append('files', f, f.name);
  const rel = f.webkitRelativePath || f.relativePath || '';
  if(rel) fd.append(`relative_path[${i}]`, rel);
});
fd.append('parent_type', 'topic');
fd.append('parent_id', topicId);
fetch('/attachments/upload/', { method:'POST', headers:{'X-CSRFToken': csrftoken, 'X-Requested-With':'XMLHttpRequest'}, body: fd });
```

后端异步处理视图示例位于 `learning_logs/views.py` 的 `upload_attachments_api`，响应包含已创建附件的元数据（id/name/url/relative_path 等）。

---

## 4. 后端（Django）接收逻辑要点

视图需要：

1. 从 `request.FILES` 获取文件列表（可能是 `attachments` 或 `files`，本项目兼容多种字段名）；
2. 从 `request.POST` 中提取 `relative_path[...]` 映射（键为索引）；
3. 在保存附件时，按文件顺序将对应的 `relative_path` 赋给 `Attachment.relative_path`。

核心函数（本项目已实现）：

- `_save_attachments_from_request(files, owner, *, topic=None, entry=None, comment=None, relative_paths=None)`
  - 接收 `files`（UploadedFile 列表）和 `relative_paths`（索引->路径 映射）；
  - 对每个文件（按 enumerate 顺序）查找 `relative_paths[idx]` 并清洗后写入 `att.relative_path`，再 `att.save()`。

后端视图示例（伪代码）：

```python
files = request.FILES.getlist('attachments') or request.FILES.getlist('files')
rel_paths = {k.split('relative_path[')[1].split(']')[0]: v for k,v in request.POST.items() if k.startswith('relative_path[')}
_save_attachments_from_request(files, request.user, topic=new_topic, relative_paths=rel_paths)
```

注意：如果前端以不同字段名发送文件（例如 `files`），后端需要兼容以上几种常见命名，本项目已做兼容处理。

---

## 5. 服务端配置（上传大小）

若需要上传较大文件或大量文件夹，请同时调整 Nginx 与 Django 的上传限制：

- Nginx（示例：`deploy/nginx/diary.conf` / `deploy/nginx/diary-ssl.conf`）：

```nginx
# 支持最多 1G
client_max_body_size 1G;
```

修改后需要重启/重载 Nginx：

```powershell
# Windows 下如果用 WSL / Linux 实例部署，请在对应主机执行
sudo systemctl reload nginx
```

- Django（`ll_project/settings.py`）：

```python
# 允许 1 GiB
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024
```

备注：具体生产环境的值请根据可用内存与需求调整。对于非常大的上传，建议使用分片上传或异步后台处理。

---

## 6. 测试步骤（本地）

1. 启动开发服务器：

```powershell
python manage.py runserver
```

2. 打开浏览器（推荐 Chrome / Edge），按下列顺序验证：

- 新建日记本：选择“选择文件夹”，选择一个包含子目录的文件夹或同时选择多个文件夹（若浏览器支持），提交后到管理界面或数据库查看 `Attachment.relative_path` 是否保留目录结构。
- 新建日记：在某日记本下新建日记，使用“选择文件夹”上传，提交并查看挂载结果。
- 编辑日记：在已有日记中编辑并追加文件夹，提交并检查。
- 日记本异步上传（选择文件夹按钮/拖拽）：选择文件夹后观察页面是否即时显示分层附件列表。

3. 若出现表单提交时附件丢失或 `relative_path` 为空：

- 打开浏览器 Network 面板，查看该 POST 请求的 Form Data，确认 `files` / `attachments` 列表和 `relative_path[0]` / `relative_path[1]` 等隐藏字段是否随表单提交；
- 查看 Django 控制台日志（本项目在 `new_entry` / `edit_entry` 视图中写入了简短 DEBUG 日志），如果需要，可把 logger 临时设为 DEBUG 并重启 `runserver` 以看到日志行，例如：

```
learning_logs.new_entry DEBUG: new_entry files=12 rel_paths_keys=['0','1','2',...]
```

---

## 7. 常见问题与排查

- 问：浏览器无法一次性选择多个文件夹。
  - 答：由浏览器实现决定。Chromium 系列在多数版本中支持一次选择多个文件夹（当 `multiple` 与 `webkitdirectory` 一起使用时），但 Safari / Firefox 行为可能不同。建议使用 Chrome/Edge 验证。

- 问：提交后 `Attachment.relative_path` 为空或不匹配文件名。
  - 答：检查浏览器 Network 的 Form Data，确认 `relative_path[index]` 是否随表单提交（隐藏字段）；如果 JS 在 submit 前没有正确插入 hidden inputs，会导致后端无法读到路径映射。

- 问：上传大文件/大量文件时报 413（Request Entity Too Large）或 Django 报错。
  - 答：检查 Nginx 的 `client_max_body_size` 与 Django 的 `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` 是否已同步设置并重启相应服务。

- 问：异步上传接口处理失败。
  - 答：在浏览器 Network 面板查看异步请求响应，后端 `upload_attachments_api` 返回 JSON 中 `ok` 或错误信息；查看 Django 日志以获取 trace 信息。

---

## 8. 代码位置（参考）

- 前端模板：
  - `learning_logs/templates/learning_logs/new_entry.html`
  - `learning_logs/templates/learning_logs/edit_entry.html`
  - `learning_logs/templates/learning_logs/new_topic.html`
  - `learning_logs/templates/learning_logs/topic.html`（异步上传按钮）
- 前端脚本：
  - `static/js/attachments.js`（异步上传、拖放、文件夹树构建）
- 后端视图：
  - `learning_logs/views.py`：`new_entry`, `edit_entry`, `new_topic`, `_save_attachments_from_request`, `upload_attachments_api`, `delete_folder_api` 等
- 模型：
  - `learning_logs/models.py`（Attachment 模型包含 `relative_path` 字段）

---

## 9. 后续改进建议

- 如果需要更可靠的大文件/大目录上传，建议引入分片上传（chunked upload）或专门的对象存储上传直传（前端直传到 S3/Cloudinary 等）。
- 增加单元 / 集成测试覆盖上传逻辑，模拟表单上传与异步上传的各种字段名与顺序。
- 在 UI 上增加上传进度和冲突提示（例如同名文件覆盖策略）。

---

如需我把此文档转换为 README 的一部分、添加到仓库根目录并在 `README.md` 中添加链接，或把示例命令加入 CI 检查脚本，我可以继续帮助完成这些变更。