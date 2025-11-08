# 服务器同步与背景图 400 故障处理

本指南用于将本次变更同步到服务器（Aliyun ECS/Render 或容器环境），并修复更换背景图片后页面返回 400 的问题。

## 一、同步步骤（非 Docker 部署）

在服务器登录到项目目录后，按顺序执行：

```bash
# 1) 拉取代码
git pull

# 2) 激活虚拟环境（示例路径按实际为准）
source ll_env/bin/activate  # Windows PowerShell: .\ll_env\Scripts\Activate.ps1

# 3) 安装依赖（若有新增）
pip install -r requirements.txt

# 4) 数据库迁移
python manage.py migrate

# 5) 收集静态文件（包含新加的 static/js/attachments.js）
python manage.py collectstatic --noinput

# 6) 重启进程（systemd / supervisor / gunicorn）
# 例如：
sudo systemctl restart diary.service
# 或重启容器/进程管理器对应服务
```

## 二、同步步骤（Docker 部署）

项目提供了 aliyun 相关 compose 文件，可按你的现有流程执行，例如：

```bash
# 拉取最新镜像或重建（根据你的镜像策略）
docker compose -f docker-compose.aliyun.yml pull
# 或
# docker compose -f docker-compose.aliyun.yml build

# 以零停机/快速重启方式更新
docker compose -f docker-compose.aliyun.yml up -d
```

如果使用了 `docker-compose.aliyun.acr.yml`，按相应文件执行即可。

## 三、环境变量与 400 问题定位

本次修复加入了 BACKGROUND_IMAGE 支持，用于安全地更换背景图片：

- BACKGROUND_IMAGE 可为：
  - 绝对 URL（https:// 开头），例如外链图片 CDN；
  - 静态路径（相对 static/ 的路径），例如 `img/backgrounds/bg6.jpg`。
- 当提供静态路径时，应用会在模板渲染前使用 Django staticfiles finders 检查文件是否已存在于静态目录/收集目标，若找不到将自动回退到内置默认背景，避免 Manifest 模式触发异常。

常见导致 400 的原因与对策：

1) DisallowedHost（主机名未加入 ALLOWED_HOSTS）
- 设置环境变量 ALLOWED_HOSTS_EXTRA，例如：
  - `ALLOWED_HOSTS_EXTRA=diary.example.com,1.2.3.4`
- 同时配置 CSRF_TRUSTED_ORIGINS_EXTRA（用于 HTTPS 域名）：
  - `CSRF_TRUSTED_ORIGINS_EXTRA=https://diary.example.com`
- 修改 .env 后务必重启服务。

2) 背景图路径无效导致静态清单（Manifest）查找失败
- 仅在模版中通过 `{% static %}` 且启用 Manifest storage 时会抛错；
- 本次更新在后端做了存在性检查与回退，不会再中断页面。
- 确保执行了 `collectstatic`，使新背景图被收集。

3) 混合内容或外链异常
- 若 BACKGROUND_IMAGE 使用 http 外链且站点为 https，浏览器可能拦截（不是 400，而是混合内容阻止）。
- 建议使用 https 外链或将图片纳入 static。

## 四、如何切换背景图

在服务器的 .env 文件中添加或修改：

```
# 绝对 URL 示例（优先使用）
BACKGROUND_IMAGE=https://your-cdn.example.com/wallpapers/ocean-1920.jpg

# 或静态文件相对路径（相对 static/）
# BACKGROUND_IMAGE=img/backgrounds/bg6.jpg
```

保存后，重启应用（或容器）。若使用静态路径，记得执行 collectstatic：

```bash
python manage.py collectstatic --noinput
```

## 五、验证清单

- 打开首页与登录页：背景正常显示，无 400 错误；
- 未登录首页若配置了 BACKGROUND_VIDEO：视频加载/海报图正常；
- 日记详情页：附件功能（多文件/文件夹上传、单个删除、预览）可用；
- Nginx/应用日志无异常（特别是 DisallowedHost）。

如仍出现 400，请查看服务器日志：
- Django 日志（若有）：`journalctl -u diary.service -e` 或容器日志；
- Nginx 访问/错误日志；
- 将报错栈发给我，我继续排查。
