# ImgBed

使用简体中文沟通。这是个人维护的通用图床、多上游 Git subtree 仓库，不是官方项目。Typora 是当前唯一使用场景，不代表图床或客户端只服务于 Typora。

- `backend/`、`web/`、`desktop/` 是普通受追踪目录，只在根目录有一个 Git 仓库。不要在内部初始化仓库或改为 submodule。
- 官方 remote 分别为 `backend-upstream`、`web-upstream`、`desktop-upstream`，用于获取更新。个人远程 `origin` 是 `https://github.com/cloud-wyf/ImgBed.git`，统一推送完整仓库；不推送官方上游。
- 子目录中的上游贡献指南、构建说明和许可证继续适用；实际用户授权优先于上游协作流程。
- 前端源码修改放在 `web/`。`backend/frontend-dist/` 是前端发布产物，按构建流程同步，避免直接手改压缩脚本。
- 本地上传、去重和 30 天回收实现维护在 `tools/`。生产运行目录是 `D:/Program Files/TyporaImgBed`；源码整理不授权替换安装、修改计划任务或重新部署云端。
- 不提交凭据、DPAPI 文件、运行数据库、回收状态或笔记。使用示例配置；本机配置留在运行目录。
- 合并官方更新时保留个人定制，冲突逐项核对。更新各子树后记录上游提交并运行与改动相关的检查。
- 仅在用户授权范围内执行 Git 提交、推送和部署。仓库初始化及 subtree 导入必需的本地提交属于已授权的建立仓库工作。
