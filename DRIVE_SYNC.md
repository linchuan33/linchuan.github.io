# Google Drive → GitHub Pages 相册同步

## 日常使用

当前上传入口为私人 Google 账号下的 [linchuan.github.io](https://drive.google.com/drive/u/1/folders/1X-hAVIHzDDuJwUWXlwJH_qFBIyzwa7E5)。学校账号中原来的同名文件夹不再是同步来源。

将照片放入以下三个分类文件夹，自动任务在每小时第 17 和第 47 分钟检查。
GitHub 调度及部署可能延迟，不保证 30 分钟内上线。公开仓库长期无活动时，GitHub 可能停用定时任务，需要在 Actions 中重新启用。

- Cute Animals：`1InYYGX8bhyh7i5__7fPsq8oE7RkOV6a3`
- Landscape：`1OhZZ0QUvshDp2sCrh46ZlWCqsQYfwtZl`
- Portrait：`1b4V4wPY6Mf4Q0dzxArqZgFtrbnwDxtb_`

地点可用子文件夹，例如 `Landscape/香港/照片.jpg`。多层地点文件夹会合并成地点标签。
直接放在分类根目录的照片归到 `New uploads`。

支持 JPEG、PNG、WebP、HEIC/HEIF、BMP、TIFF。单张最大 80 MiB。
新照片会校正方向、转换 JPEG、移除 EXIF（包括 GPS）、生成最大边 2560px 的网页图和 960px 预览。
原始照片保留在 Drive。已有大图只在部署包中压缩，仓库和本地原图保持不变。网站首页每个分类优先轮播最近四张上传图和原来的精选图，间隔仍为 3000ms。

**只新增，不删除、不覆盖**：同一个 Drive 文件 ID 只导入一次。删除、移动或修改已导入的 Drive 文件不会删除、更改已发布照片。
如果要发布修改后的版本，请作为新的 Drive 文件上传。相同 MD5 内容会跳过，避免重复。
现有 196 张照片由 `data/gallery-baseline.json` 管理，导入记录为 `data/drive-state.json`，不要清空这些记录。
Drive 中这三个文件夹只放打算公开的照片；同步后照片将公开在网站及 GitHub 仓库。

## 已配置的云端资源

- Google Cloud 项目：`our-monolith-514514-s2`（Linchuan Gallery Sync）
- 专用账号：`gallery-sync@our-monolith-514514-s2.iam.gserviceaccount.com`
- Drive API 已启用；相册根文件夹仅给该账号 Viewer 权限。
- GitHub Repository Secret：`GOOGLE_SERVICE_ACCOUNT_JSON`；Pages Source：GitHub Actions。

## 一次性配置（重建时参考）

1. 使用可访问 Google Cloud 的账号创建专用项目，启用 **Google Drive API**。
   不需要启动付费试用或绑定结算账号。学校账号禁用 Cloud 时，可用个人账号创建项目。
2. 创建服务账号（例如 `gallery-sync`），**不授予项目 IAM 角色**，不启用全域委派。
3. 将相册根文件夹 `1X-hAVIHzDDuJwUWXlwJH_qFBIyzwa7E5` 分享给该服务账号邮件，权限选择 **Viewer/查看者**。
   原文件夹无需改为“知道链接的所有人”，只授予这个专用账号。若学校禁止外部共享，需要学校管理员允许或将相册迁到个人 Drive 后修改 `data/drive-config.json` 中的 ID。
4. 为服务账号生成 JSON 密钥，在仓库 Settings → Secrets and variables → Actions 创建名为
   `GOOGLE_SERVICE_ACCOUNT_JSON` 的 Repository secret，值为完整 JSON。不要将密钥提交到仓库、粘贴到聊天或前端代码。
5. 在 Settings → Pages 中将 Source 切换为 **GitHub Actions**。
6. 将本次代码发布到 `main`，在 Actions → **Sync Drive photos and publish gallery** → Run workflow 手动测试。
   先用一张明确要公开的照片验证，检查任务绿色、照片显示、再次运行不会重复，然后日常只需上传。

任务使用 `GITHUB_TOKEN` 提交新增图和状态，并在同一个任务中直接部署 Pages（不依赖机器人提交触发下一轮构建）。
公共站点部署包只包含 HTML 和图片，不包含同步状态、脚本和凭据。GitHub 公共仓库本身仍公开非密钥源代码。

## 本地验证

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/sync_drive.py --build-only
.venv/bin/python -m unittest discover -s tests -v
```

真实同步需要通过环境变量 `GOOGLE_SERVICE_ACCOUNT_JSON` 提供凭据，不能使用聊天中 Drive 连接的授权来替代无人值守任务的授权。
失败任务不会部署，线上保留上一次成功版本。Drive 无权限、下载失败、格式损坏都明确报错；到 Actions 查看日志修复后重跑。

本地代码不会随着云端提交自动更新。以后在这台电脑修改网站前先 `git pull --ff-only`，避免与同步任务产生冲突。

如果要停止后续导入，在 GitHub Actions 禁用该 workflow；现有网站和照片保留。

## 已有照片归档

原有 196 张正片会以保留地点子文件夹、文件名的方式归档到上述三个分类。
`data/drive-archive.json` 精确记录它们的压缩文件 MD5、地点和文件名；同步遇到匹配的云端副本时只登记已有照片，不重复添加到网站。
同名但内容不同的新照片仍按新照片导入。不要清空此归档清单。

根目录另有三个仅供归档管理的预览文件夹：`CuteAnimal-preView`（9 张）、`Landscape-preView`（8 张）、`Portrait-preView`（7 张）。它们不作为新的正片导入网站。
以后上传新照片仍只需放到三个正片分类中；网站会自动生成新照片的网页预览。
