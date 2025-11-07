# 阿里云 ECS 极简部署指南 (本地构建镜像)

本文档提供一套最稳妥、最简单的部署方案，彻底绕开在服务器上构建慢、依赖安装失败等问题。

**核心思想：**

1.  **本地电脑**：负责编译和打包，生成一个完整的 Docker 镜像。
2.  **阿里云服务器 (ECS)**：只负责接收这个镜像并运行，不执行任何编译或安装。

---

## Part 1: 服务器一次性准备

这些步骤在你的 ECS 上只需要执行一次。

**你的 ECS 环境：**
- 操作系统：CentOS / Alibaba Linux (使用 `yum` 或 `dnf`)
- 登录用户：`root` (无需 `sudo`)

**1. 安装 Docker 和 Docker Compose**

```bash
# 自动选择包管理器 (yum 或 dnf)
PKG=$(command -v dnf || command -v yum)

# 安装 Docker 依赖
$PKG install -y yum-utils device-mapper-persistent-data lvm2

# 添加 Docker 官方镜像源（使用阿里云镜像加速）
yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo

# 安装 Docker
$PKG install -y docker-ce docker-ce-cli containerd.io

# 启动并设置开机自启
systemctl start docker
systemctl enable docker

# 安装 Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose # 创建软链接方便使用
```
验证安装成功：
```bash
docker --version
docker-compose --version
```
如果都显示版本号，则安装成功。

**2. 安装 Git 并拉取代码**

```bash
# 安装 Git
$PKG install -y git

# 在 /opt 目录下创建项目文件夹并拉取代码
mkdir -p /opt/self_diaris
cd /opt/self_diaris
git clone https://github.com/Ever-m1ss/self_diaris.git .
```

---

## Part 2: 本地电脑操作 (Windows)

这些步骤在你的 Windows 电脑上执行。

**前提：** 你的电脑已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

**1. 构建 Docker 镜像**

打开 PowerShell，进入你本地的项目代码目录。

```powershell
# 进入项目根目录
cd "d:\桌面\Temporary folder\diary"

# 执行构建，这会把你的 Django 项目和所有依赖打包成一个名为 self_diaris 的镜像
docker build -t self_diaris:latest .
```
等待命令执行完毕，最后应显示 `Successfully tagged self_diaris:latest`。

**2. 导出镜像为压缩包**

```powershell
# 将刚刚构建的镜像保存为一个 .tar.gz 文件
docker save self_diaris:latest | gzip > self_diaris.tar.gz
```
执行完毕后，你的项目目录下会多出一个 `self_diaris.tar.gz` 文件。

**3. 上传镜像到服务器**

你需要知道你的服务器 IP 地址和登录密码/密钥。

```powershell
# 使用 scp 命令将镜像文件上传到服务器的 /opt/self_diaris 目录下
# 把 <ECS_IP> 替换成你的服务器公网 IP
scp .\self_diaris.tar.gz root@<ECS_IP>:/opt/self_diaris/
```
等待上传完成。

---

## Part 3: 服务器部署

回到你的 ECS 服务器终端。

**1. 导入镜像**

```bash
# 进入项目目录
cd /opt/self_diaris

# 从你上传的压缩包中加载 Docker 镜像
docker load -i self_diaris.tar.gz
```
执行完毕后，运行 `docker images` 应该能看到 `self_diaris` 这个镜像。

**2. 配置环境变量**

项目需要一个 `.env` 文件来读取配置。

```bash
# 从模板复制一份配置文件
cp .env.example .env

# 编辑配置文件
nano .env
```
在 `nano` 编辑器中，**至少修改以下几项**：
- `SECRET_KEY`: 随便填写一长串无序的字符串。
- `DEBUG`: 必须为 `false`。
- `ALLOWED_HOSTS_EXTRA`: 填写你的服务器公网 IP，如果有域名也加上，用逗号隔开。例如：`ALLOWED_HOSTS_EXTRA=123.45.67.89,www.yourdomain.com`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: 数据库的用户名、密码、库名，可以保持默认。

按 `Ctrl+X`，然后按 `Y`，再按 `Enter` 保存退出。

**3. 启动服务**

我们将巧妙地复用 `docker-compose.aliyun.acr.yml` 文件，因为它正好是为“运行一个已存在的镜像”而设计的。

```bash
# 告诉 Docker Compose 我们要运行的镜像是我们刚刚导入的本地镜像
export ACR_IMAGE=self_diaris:latest

# 启动服务 (后台运行)
docker-compose -f docker-compose.aliyun.acr.yml up -d
```

**4. 验证**

```bash
# 查看容器是否正在运行
docker ps
```
你应该能看到 `self_diaris_web_1` 和 `self_diaris_db_1` 两个容器，状态为 `Up`。

```bash
# 查看 `web` 服务的日志，确保没有报错
docker-compose -f docker-compose.aliyun.acr.yml logs -f web
```
如果没有红色的错误信息，说明启动成功。按 `Ctrl+C` 退出日志查看。

此时，你的网站已经在服务器的 `8000` 端口上运行，但只能从服务器内部访问。

---

## Part 4: 配置公网访问 (Nginx)

为了让所有人都能通过 IP 或域名访问你的网站，我们需要用 Nginx 做反向代理。

**1. 安装并配置 Nginx**

```bash
# 安装 Nginx
PKG=$(command -v dnf || command -v yum)
$PKG install -y nginx

# 创建 Nginx 配置文件
nano /etc/nginx/conf.d/diary.conf
```
将以下内容**完整复制**并粘贴到 `nano` 编辑器中：

```nginx
server {
    listen 80;
    # 在这里填写你的服务器公网 IP 或域名
    server_name <你的公网IP或域名>;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/self_diaris/staticfiles/;
    }

    location /media/ {
        alias /opt/self_diaris/media/;
    }
}
```
**重要：** 将 `<你的公网IP或域名>` 替换成你自己的。保存并退出 (`Ctrl+X`, `Y`, `Enter`)。

**2. 启动 Nginx**

```bash
# 启动 Nginx 并设置开机自启
systemctl start nginx
systemctl enable nginx

# 检查 Nginx 配置是否正确
nginx -t
```
如果显示 `syntax is ok` 和 `test is successful`，说明配置无误。

**3. 开放防火墙端口**

```bash
# 开放 HTTP (80) 和 HTTPS (443) 端口
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
```

现在，你应该可以通过你的服务器公网 IP 地址直接访问你的网站了！

---

## 如何更新网站？

当你修改了代码后，只需重复 **Part 2 (本地操作)** 和 **Part 3 (服务器部署)** 的步骤即可。

1.  **本地**：`docker build` -> `docker save` -> `scp`
2.  **服务器**：`docker load` -> `docker-compose up -d`

这套流程最稳，请严格按照步骤执行。如果遇到任何命令报错，请将完整的命令和错误信息截图给我。