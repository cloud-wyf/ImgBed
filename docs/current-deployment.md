# 当前部署记录

记录日期：2026-11-22。仓库源码与正在运行的部署分别管理。

- 图床地址：https://slanwyf-imgbed.pages.dev
- Cloudflare Pages 项目：`slanwyf-imgbed`，前端静态资源与后端 Pages Functions 合并部署。
- 当前部署后端与网页版本为 `2.7.8`，2026-11-22 已通过本仓库 GitHub Actions 构建和部署；本仓库导入的官方提交另见 `upstreams.json`。
- D1 保存图床元数据；Backblaze B2 私有桶 `slanwyf-typora-imgbed` 保存图片，通过 `S3_env` 渠道访问。
- 运行目录：`D:/Program Files/TyporaImgBed`。Typora 调用该目录中的 `upload.py`，Python 使用本机现有 version-fox 安装。
- Windows 计划任务：`TyporaImgBed-每日图片回收`，每天北京时间 20:00 执行现有运行目录中的 `recycle.py --apply`。
- 本地扫描仅包括 `D:/Notes` 的 `.md` 与 `.markdown`。新图片平铺在 `typora/`；连续 30 天未引用后复制到同级 `回收站/`，验证副本后永久删除源路径全部 B2 版本。
- 去重依据最终上传内容的完整 SHA-256。命中索引时查询云端元数据，不下载图片；成功回收后清除索引。

账户密码、Token 和 B2 密钥使用当前 Windows 用户的 DPAPI 文件保存，不进入本仓库。`config.json`、`upload-index.sqlite3`、回收计时与报告继续留在运行目录。

## 现有部署的构建来源

2026-11-14 的部署使用从 GitHub 下载的官方源码，其中 `frontend-dist/` 已包含上游预构建的前端。本机通过 Wrangler 编译、打包 Pages Functions，生成 `_worker.js`，再与静态资源及 `_routes.json` 组合成部署目录和 ZIP。初期通过 Cloudflare 控制台上传 ZIP，后续修正版也通过本机 Wrangler 发布。

这次部署没有使用 GitHub Actions，也没有由 Cloudflare 拉取源码执行构建；Cloudflare 接收部署产物并托管运行。依据为原任务目录中的 `deployment-state.json`、`prepare_pages.py`、`fix_pages_package.py` 和对应 Wrangler 构建、发布日志。

## 2026-11-22 增加的自动部署入口

本仓库增加 `.github/workflows/pages-deploy.yml`，在后端、网页或部署代码推送到 `main` 后，通过 GitHub Actions 检查并构建前后端，再用 Wrangler 发布到同一个 `slanwyf-imgbed` Pages 项目。首次发布依赖仓库的 Cloudflare Secrets 配置；实际发布提交和结果以 [Actions 运行记录](https://github.com/cloud-wyf/ImgBed/actions/workflows/pages-deploy.yml) 及 Cloudflare 部署历史为准。构建和凭据要求见 [自动部署说明](build.md#自动部署到现有-pages-项目)。

2026-11-22 北京时间 18:16，配置当前账号的 Pages Write Token 并保存为 GitHub Secret 后，首次发布成功。源码提交为 `64754bc3cb9e22b1af3385c9916f2a40b48f2a3b`；后端 278 项、前端 238 项检查、前后端构建、部署以及线上提交标记、首页和 Pages 后端检查均通过，见 [首次成功运行](https://github.com/cloud-wyf/ImgBed/actions/runs/45007214561/attempts/2)。D1、B2 和图床认证继续使用原项目配置。

## 已发现的文档链接问题

2026-11-22 只读核对发现，云端两张图片已从 `typora/2026/11/` 移到 `typora/`，而 `D:/Notes` 仍引用旧路径。旧地址绕过缓存后返回 404。网页移动不会改写本地 Markdown；路径不同也会影响本地引用核对。

建立本仓库没有改写笔记或迁移云端文件。更新笔记链接或增加稳定访问地址的改造需作为独立变更验证，不能将此次源码整理当作链接修复已完成。
