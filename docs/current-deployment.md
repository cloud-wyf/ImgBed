# 当前部署记录

记录日期：2026-11-22。仓库源码与正在运行的部署分别管理。

- 图床地址：https://slanwyf-imgbed.pages.dev
- Cloudflare Pages 项目：`slanwyf-imgbed`，前端静态资源与后端 Pages Functions 合并部署。
- 当前部署源快照版本：`CloudFlare-ImgBed 2.7.8`，来自 2026-11-14 的部署记录；本仓库导入的官方提交另见 `upstreams.json`。
- D1 保存图床元数据；Backblaze B2 私有桶 `slanwyf-typora-imgbed` 保存图片，通过 `S3_env` 渠道访问。
- 运行目录：`D:/Program Files/TyporaImgBed`。Typora 调用该目录中的 `upload.py`，Python 使用本机现有 version-fox 安装。
- Windows 计划任务：`TyporaImgBed-每日图片回收`，每天北京时间 20:00 执行现有运行目录中的 `recycle.py --apply`。
- 本地扫描仅包括 `D:/Notes` 的 `.md` 与 `.markdown`。新图片平铺在 `typora/`；连续 30 天未引用后复制到同级 `回收站/`，验证副本后永久删除源路径全部 B2 版本。
- 去重依据最终上传内容的完整 SHA-256。命中索引时查询云端元数据，不下载图片；成功回收后清除索引。

账户密码、Token 和 B2 密钥使用当前 Windows 用户的 DPAPI 文件保存，不进入本仓库。`config.json`、`upload-index.sqlite3`、回收计时与报告继续留在运行目录。

## 已发现的文档链接问题

2026-11-22 只读核对发现，云端两张图片已从 `typora/2026/11/` 移到 `typora/`，而 `D:/Notes` 仍引用旧路径。旧地址绕过缓存后返回 404。网页移动不会改写本地 Markdown；路径不同也会影响本地引用核对。

建立本仓库没有改写笔记或迁移云端文件。更新笔记链接或增加稳定访问地址的改造需作为独立变更验证，不能将此次源码整理当作链接修复已完成。
