> 本文彻底重写，移除之前的 Docker / ACR 路径，针对「网络极慢/HTTPS 失败/无法在线拉取」的阿里云 ECS（CentOS 系）提供一套可靠的“国内资源 + 离线打包”部署方法，并附最小在线方案及故障排查。请严格按顺序执行，避免重复踩坑。

# 一览总流程

本方案分两端操作：

本地 Windows（可正常访问公网）
1. 打包部署素材：项目代码 + Python3.10 源码 + 所有依赖 wheels。
2. 压缩为 deploy_package.zip 上传到 ECS。

ECS 服务器（网络受限）
3. 解压离线包，编译安装 Python3.10（带 SSL）。
4. 创建虚拟环境 + 离线安装依赖。
5. 进行数据库迁移 / 收集静态 / 临时启动验证。
6. 配置 systemd（守护）+ Nginx（反代 + 可选 HTTPS）。
7. 后续更新与故障排查。

# 0. 回滚与清理（如果之前已多次失败）

登录 ECS，执行：
```bash
cd ~
rm -rf self_diaris Python-3.* deploy_package* venv *.tgz wheels
```
说明：清除之前残留的源码目录、旧虚拟环境、下载碎片，确保一个干净起点。

# 1. 本地 Windows 打包离线部署包

## 1.1 准备目录
在桌面创建文件夹：`deploy_package`。

## 1.2 获取项目代码
将你的项目完整文件夹（例如 `d:\桌面\Temporary folder\diary`）复制进 `deploy_package`，重命名为 `project`（便于统一脚本）。

## 1.3 下载 Python 源码（与本地一致更省事）
优先与本地 Python 主版本对齐（例如你本地是 3.11，就用 3.11）：

- 3.11.9：`https://registry.npmmirror.com/-/binary/python/3.11.9/Python-3.11.9.tgz`
- 3.10.13：`https://registry.npmmirror.com/-/binary/python/3.10.13/Python-3.10.13.tgz`

下载后放入 `deploy_package`。本文后续以“3.10.13”为例，若你选了 3.11.9，则将所有出现的 `3.10.13 / 3.10 / cp310` 替换为 `3.11.9 / 3.11 / cp311` 即可。

## 1.4 下载依赖 wheels（离线）
打开 PowerShell：
```powershell
cd "d:\桌面\Temporary folder\diary"
mkdir wheels
pip download -r requirements.txt -d wheels
```
完成后把生成的 `wheels` 文件夹复制到 `deploy_package` 下。

> 重要提醒：你的本地 Python 版本可能与 ECS 上的 Python（3.10）不同，`pip download` 会按“本地环境”解析条件依赖，导致在 ECS 上离线安装时出现缺包（常见：`typing_extensions`、`charset_normalizer`、`idna`）。为一次性补齐，建议在下载完上面的依赖后，再执行：
>
> ```powershell
> # ECS 运行的是 Python 3.10，按其需要补齐常见条件依赖
> pip download typing_extensions==4.12.2 -d wheels
> pip download "charset_normalizer>=3,<4" "idna<4,>=2.5" -d wheels
> ```
>
> 若你清楚 ECS 的架构/平台，也可以更严格：
> ```powershell
> # 可选：针对 manylinux2014_x86_64 + py310 预解依赖（需要较新 pip）
> pip download -r requirements.txt -d wheels --only-binary=:all: --platform manylinux2014_x86_64 --python-version 310 --implementation cp --abi cp310
> ```
>
> 平台兼容警告：不要把“你本地生成的 Windows 平台轮子”直接当成可在 Linux 安装的包。例如看到名字形如 `charset_normalizer-3.4.4-cp311-cp311-win_amd64.whl`，这是 Windows 专用，放到 CentOS 上离线安装时会被忽略，pip 就会说“from versions: none”。正确的跨平台纯 Python 轮子形如：`charset_normalizer-3.4.4-py3-none-any.whl`。如果你已经出现了 win_amd64 结尾的文件，请：
> 1. 删除该文件：`del .\wheels\charset_normalizer-3.4.4-cp311-cp311-win_amd64.whl`（PowerShell）
> 2. 重新下载官方发布的通用轮子：`pip download charset_normalizer==3.4.4 -d wheels`
> 3. 再次上传新的 `py3-none-any` 轮子到服务器。

目录结构现在应为：
```
deploy_package/
	project/              # Django 项目代码
	wheels/               # 所有依赖的 .whl / .tar.gz
	Python-3.10.13.tgz    # Python 源码包
```

## 1.5 （可选）加入快速脚本
在 `deploy_package` 新建文件 `install_on_ecs.sh`（UTF-8，无 BOM），内容：
```bash
#!/usr/bin/env bash
set -e
echo "[1] 解压 Python 源码" && tar -xzf Python-3.10.13.tgz
cd Python-3.10.13
echo "[2] 编译 Python3.10 (开启优化)" && ./configure --enable-optimizations
make -j $(nproc)
sudo make altinstall
cd ..
echo "[3] 创建虚拟环境" && python3.10 -m venv venv
source venv/bin/activate
echo "[4] 离线安装依赖" && pip install --no-index --find-links=wheels -r project/requirements.txt
echo "[5] Django 初始化" && cd project && python manage.py migrate && python manage.py collectstatic --noinput
echo "[6] 试运行 Gunicorn" && gunicorn ll_project.wsgi:application --bind 0.0.0.0:8000 --workers 3
```
（若不想交互验证，可后续再移除第 6 步并改成 systemd）。

## 1.6 打包上传文件
右键 `deploy_package` → “发送到 → 压缩(zipped)文件夹”，得到 `deploy_package.zip`。

# 2. 上传离线包到 ECS

在本地 PowerShell：
```powershell
scp C:\路径\deploy_package.zip root@你的公网IP:~
```
（若首次连接提示主机指纹，添加 `-o StrictHostKeyChecking=no` 绕过）

登录 ECS：
```bash
cd ~
unzip deploy_package.zip
cd deploy_package
```

> 若 `unzip` 不存在：`sudo yum install -y unzip`

# 3. 编译安装 Python（带 SSL）

CentOS 常见依赖（提前装，避免缺模块）：
```bash
sudo yum groupinstall -y "Development Tools"
sudo yum install -y openssl-devel bzip2-devel libffi-devel zlib-devel xz-devel sqlite-devel readline-devel wget
```

开始编译（下例以 3.10.13 为例；若你使用 3.11.9，请替换对应版本号）：
```bash
tar -xzf Python-3.10.13.tgz
cd Python-3.10.13
./configure --enable-optimizations
make -j $(nproc)
sudo make altinstall
python3.10 -V   # 期望输出: Python 3.10.13（或 3.11.9）
cd ..
```

> 如果仍出现 SSL 缺失，检查是否真的安装了 `openssl-devel`；若版本过旧，可 `sudo yum update -y openssl openssl-libs` 后重新 `make clean && ./configure ...` 再编译。

# 4. 创建虚拟环境 + 离线安装依赖

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip   # 离线不升级可跳过，若能访问镜像可保留
pip install --no-index --find-links=wheels -r project/requirements.txt
```

验证：`python -c "import django; print(django.get_version())"` 应显示 4.x。

# 5. 初始化 Django

```bash
cd project
cp .env.example .env   # 若存在示例文件，填入 SECRET_KEY / DEBUG=false / ALLOWED_HOSTS_EXTRA=你的IP
python manage.py migrate
python manage.py collectstatic --noinput
```

临时前台验证：
```bash
gunicorn ll_project.wsgi:application --bind 0.0.0.0:8000 --workers 3
### 背景视频优化（在服务器上直接处理）

若首页视频卡顿但希望维持分辨率上限为 1080p，可直接在服务器用脚本重新编码（需要 ffmpeg）：

```bash
# 一次性安装 ffmpeg（CentOS 可能需要 EPEL，若无法在线就用本地处理后上传）
sudo yum install -y epel-release || true
sudo yum install -y ffmpeg || true

# 在项目根目录执行（~/deploy_package/project）
bash scripts/optimize_video.sh static/video/bg_source.mp4 static/video/bg.mp4

# 也可调参（示例：更清晰）
# CRF=20 PRESET=medium FPS=30 MAX_HEIGHT=1080 bash scripts/optimize_video.sh static/video/bg_source.mp4 static/video/bg.mp4

# 替换后重新收集静态
python manage.py collectstatic --noinput
```

脚本说明：
- 保持不超过 1080p 的分辨率（等比缩放），默认 CRF=23、FPS=30、去音轨、+faststart，提高首帧可播放速度。
- 也可以生成“高/低码率”两份视频并在模板中通过多个 `<source>` 提供回退选项。
```
浏览器访问 `http://服务器IP:8000/` 测试是否正常。

> 访问不通（超时）怎么办？
> - 先在服务器本机验证服务确实起来了：
>   ```bash
>   curl -I http://127.0.0.1:8000/ || true
>   ss -tlnp | grep 8000 || true
>   ```
>   能看到 200/301 等响应头且 0.0.0.0:8000 正在监听，说明应用正常，是“网络侧”阻断。
> - 阿里云安全组：到 ECS 控制台 → 网络与安全 → 安全组 → 入方向规则 → 新增一条，协议 TCP、端口 8000、源 0.0.0.0/0（或你的公网 IP/32）。
> - 系统防火墙（firewalld）：
>   ```bash
>   sudo firewall-cmd --zone=public --add-port=8000/tcp --permanent
>   sudo firewall-cmd --reload
>   ```
>   若你准备用 Nginx 对外，仅需开放 80/443：
>   ```bash
>   sudo firewall-cmd --zone=public --add-port=80/tcp --permanent
>   sudo firewall-cmd --zone=public --add-port=443/tcp --permanent
>   sudo firewall-cmd --reload
>   ```

# 6. 创建 systemd 服务（守护）

退出当前 gunicorn（Ctrl+C），创建 unit：
```bash
sudo tee /etc/systemd/system/diary.service > /dev/null <<'EOF'
[Unit]
Description=Gunicorn for self_diaris
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/deploy_package/project
Environment="PATH=/root/deploy_package/venv/bin"
ExecStart=/root/deploy_package/venv/bin/gunicorn ll_project.wsgi:application --bind 0.0.0.0:8000 --workers 3
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now diary.service
sudo systemctl status diary.service --no-pager
```

# 7. Nginx 反向代理（可选）

开放安全组 80/443 后安装：
```bash
sudo yum install -y nginx
sudo systemctl enable --now nginx
```

简单反代：
```bash
sudo tee /etc/nginx/conf.d/diary.conf > /dev/null <<'EOF'
server {
		listen 80;
		server_name _;
		# 注意：STATIC_ROOT=project/staticfiles，Nginx 应该指向 staticfiles
		location /static/ { alias /root/deploy_package/project/staticfiles/; }
		location / {
			proxy_pass http://127.0.0.1:8000;
			proxy_set_header Host $host;
			proxy_set_header X-Real-IP $remote_addr;
			proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
			proxy_set_header X-Forwarded-Proto $scheme;
		}
}
EOF
sudo nginx -t && sudo systemctl reload nginx
```

> 注意：若你只是使用内置 SQLite，不要在 `.env` 中保留 `DATABASE_URL=postgresql://...`（这是 docker/Postgres 示例）。复制 `.env.example` 后请删除或注释该行，否则 Django 会尝试用 Postgres 引擎，启动时缺失 `psycopg2` 导致 Gunicorn worker 退出（报 `Error loading psycopg2 module` / `ImproperlyConfigured`）。

### 7.1 HTTPS（国内可选方案：acme.sh + ZeroSSL）

```bash
curl https://get.acme.sh | sh
~/.acme.sh/acme.sh --register-account -m your@mail.com --server zerossl
~/.acme.sh/acme.sh --issue -d yourdomain.com --standalone -k ec-256
~/.acme.sh/acme.sh --install-cert -d yourdomain.com --ecc \
	--fullchain-file /etc/nginx/ssl/fullchain.pem \
	--key-file /etc/nginx/ssl/key.pem
sudo tee /etc/nginx/conf.d/diary-ssl.conf > /dev/null <<'EOF'
server {
		listen 443 ssl http2;
		server_name yourdomain.com;
		ssl_certificate /etc/nginx/ssl/fullchain.pem;
		ssl_certificate_key /etc/nginx/ssl/key.pem;
		location /static/ { alias /root/deploy_package/project/staticfiles/; }
		location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
}
server { listen 80; server_name yourdomain.com; return 301 https://$host$request_uri; }
EOF
sudo nginx -t && sudo systemctl reload nginx
```

# 8. 更新与迭代（离线包方式）

本地修改 → 重新执行 1.4 打包新 wheels（若依赖更新） → 覆盖 `project` → 重新压缩 `deploy_package.zip` → 上传 → 替换服务器旧目录：
```bash
sudo systemctl stop diary.service
mv deploy_package deploy_package_old
unzip deploy_package.zip
cd deploy_package
python3.10 -m venv venv   # 若原 venv 可复用则跳过并直接激活
source venv/bin/activate
pip install --no-index --find-links=wheels -r project/requirements.txt
cd project && python manage.py migrate && python manage.py collectstatic --noinput
sudo systemctl restart diary.service
```
确认无误后删除旧目录：`rm -rf ~/deploy_package_old`。

# 9. 最小“在线”快速安装（若网络问题已修复）

```bash
sudo yum groupinstall -y "Development Tools"
sudo yum install -y openssl-devel bzip2-devel libffi-devel zlib-devel xz-devel sqlite-devel readline-devel wget git
wget https://registry.npmmirror.com/-/binary/python/3.10.13/Python-3.10.13.tgz
tar -xzf Python-3.10.13.tgz && cd Python-3.10.13 && ./configure --enable-optimizations && make -j $(nproc) && sudo make altinstall && cd ..
git clone https://gitclone.com/github.com/Ever-m1ss/self_diaris.git
cd self_diaris
python3.10 -m venv venv && source venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python manage.py migrate && python manage.py collectstatic --noinput
gunicorn ll_project.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

# 10. 常见故障速查

| 问题 | 现象 | 处理 |
|------|------|------|
| SSL 模块缺失 | pip 提示 "ssl module is not available" | 确保已安装 openssl-devel，重新 `make clean && ./configure --enable-optimizations && make -j` |
| requirements.txt 找不到 | pip 报 errno2 | 当前目录不对，进入 `project` 或使用绝对路径 `project/requirements.txt` |
| gunicorn 启动后端口不可访问 | 浏览器连接被拒绝 | 防火墙/安全组未开放 8000 或 Nginx 未配置 80；使用 `ss -tlnp | grep 8000` 检查进程 |
| collectstatic 卡住 | 输出停在某个静态文件 | 使用 `--noinput` 参数；若权限问题检查目录属主 |
| systemd 服务反复重启 | `systemctl status` 中 Exit code | 查看 `journalctl -u diary.service -xe`，确认 WorkingDirectory 与 PATH 正确 |
| HTTPS 证书失败 | acme.sh 验证不通过 | 检查 80 端口未被占用/安全组已开放；可临时停 Nginx 再签发 |

# 11. 安全与优化建议（后续可做）

- 使用非 root 用户运行：创建用户，修改 unit 中 User 与路径。
- 打开 SELinux / Fail2Ban 增强安全（当前为快速上线可暂忽略）。
- 将 SQLite 替换为云数据库或本地 PostgreSQL（需要额外安装与 DATABASE_URL 配置）。
- 使用 `supervisor` 或 `pm2`（若未来混合多进程）。
- 配置日志轮转：`/etc/logrotate.d/gunicorn`。

---
完成以上步骤后，你的站点应在 `http://<公网IP>/` （或绑定域名）正常访问。若任一步骤仍出现问题，优先在 10. 常见故障速查表中比对，再反馈具体报错。祝部署顺利。
