# 构建与部署关系

三个子树保留上游的依赖锁文件、构建入口和文档。导入源码不会安装依赖、升级生产环境或启动桌面 UI。

## 后端与网页端

`backend/` 提供上传、认证、文件管理和存储适配接口。`web/` 是 Vue 网页前端源码。自动部署将网页编译后的 HTML/JS/CSS 与后端 Functions 组合到 `build/pages/`，发布到同一个 Pages 项目；不改写上游跟踪的 `backend/frontend-dist/`。

后端自带的 `frontend-dist/` 是上游已发布的前端快照，不保证与当前独立导入的 `web/` 提交完全一致。只有网页构建及兼容性检查通过后，才替换后端中的前端发布产物。

在网页目录按上游锁文件安装依赖后构建：

```powershell
Set-Location "D:/Development/WorkSpace/ImgBed/web"
npm ci
npm run build
```

后端部署有 Pages、Workers 和 Docker 多种入口，应按 `backend/CONTRIBUTING.md` 与 `backend/deploy/` 的当前说明选择。个人生产系统采用 Pages + D1 + B2；不要将其他部署示例误当成本机已配置的生产入口。

## 桌面端

`desktop/` 为 Tauri/Rust/Svelte 应用。Windows 构建需要 Rust 与 MSVC Build Tools，前端依赖按 `package-lock.json` 安装：

```powershell
Set-Location "D:/Development/WorkSpace/ImgBed/desktop"
npm ci
npm run tauri build
```

本地 Python 工具尚未迁入 Rust 桌面模块。此阶段整理仓库并保存现有实现；桌面 UI、Typora CLI 和回收逻辑共用核心实现的改造后续单独验证。

## 本地工具检查

Python 代码编译检查可在不生成缓存文件的情况下完成；单元测试在 `tools/tests/`，使用模拟接口与内存数据库，不调用生产 API。真实云端测试另外明确安排，不随普通单元测试自动运行。

## 源码、构建产物与仓库可见性

GitHub 中保存完整源码、依赖锁文件和维护说明。运行部署依赖构建产物，不能把 Vue `.vue` 文件和未打包的后端依赖当成可以直接拖放上传的站点。后端内已有的 `frontend-dist/` 是上游预构建页面；只使用它时无需重建网页，但修改 `web/` 后必须重新构建并同步产物。

两种部署途径都可以使用私有 GitHub 仓库：

- Pages Git integration：授权 Cloudflare GitHub App 访问仓库，设置项目根目录、构建命令和静态输出目录，由 Cloudflare 构建及部署。此仓库含多个项目，需明确选择 `backend/` 为后端工程根目录，并让构建流程处理 `web/`。`functions/` 位于该 Pages 工程根目录，不能只部署 `web/dist/`。
- GitHub Actions + Wrangler：在 CI 中构建网页及函数，然后发布到 Pages。这样本机只需维护和推送源码，不必每次手工构建。

此前生产图床来自直接上传部署：使用上游预构建前端，在本机用 Wrangler 打包后端函数，然后上传到 Cloudflare；当时未使用 GitHub Actions 或 Cloudflare 源码构建。详细记录见 [当前部署记录](current-deployment.md)。目前选择 GitHub Actions + Wrangler 发布到原项目，保留项目和地址。Cloudflare 不支持将 Direct Upload 项目直接切换为 Git integration；使用 Pages 原生 Git integration 需新建相应项目并处理绑定配置。

本仓库为公开仓库。桌面客户端需要另行编译成 Windows/macOS 应用，不作为 Pages 后端或网页资产部署。GitHub 仓库可见性决定源码访问范围，部署后图床的访问权限仍由图床认证和 Cloudflare 访问设置决定。

官方依据：[私有仓库支持](https://developers.cloudflare.com/pages/get-started/git-integration/)、[构建配置](https://developers.cloudflare.com/pages/configuration/build-configuration/)、[Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)。

## 自动部署到现有 Pages 项目

根工作流为 `.github/workflows/pages-deploy.yml`。GitHub 使用 Node.js 22 和两个上游的锁文件安装依赖，运行后端回归及模块检查、前端回归，再构建 `web/` 并执行 `node ci/build-pages.mjs`。该脚本清理固定产物目录 `build/pages/`，复制前端，调用后端锁定的 Wrangler 编译 Functions 到 `_worker.js/`，写入静态资源路由和源码提交标记 `deployment.json`。不使用 Workers 部署配置。

触发范围为 `main` 上的后端、网页、CI 脚本或部署工作流变更。Pull Request 执行构建检查，不访问部署凭据或发布；也可在 Actions 页面手动运行 `main` 的工作流。同一分支发布按顺序执行。只有构建成功才会进入发布阶段，打包产物保留 7 天。文档、桌面端和本地工具变更不会单独触发 Pages 发布。

在仓库 **Settings → Secrets and variables → Actions** 配置以下 Secrets：

| 名称 | 内容 |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | 现有 Pages 项目所属的 Cloudflare 账号 ID |
| `CLOUDFLARE_API_TOKEN` | 限定该账号、具有 `Cloudflare Pages: Edit` 权限的 API Token |

Token 不进入仓库或聊天。B2 密钥、图床密码和 D1 绑定继续保存在现有 Cloudflare 项目中，不复制到 GitHub。部署脚本不上传 Wrangler 项目配置，不修改数据库结构或存储对象。发布前检查现有 `main` 生产分支、`img_d1` 和必要的环境变量，以及兼容日期 `2026-11-14`；日期需要调整时，应核对线上设置并与构建脚本一起更新。

发布使用现有项目 `slanwyf-imgbed` 的生产分支 `main`。成功后核对线上 `deployment.json` 中的源码提交、首页和 `/api/userConfig` 的 Pages 响应。检查失败不会触发新发布；发布后的验证失败会报告失败，但不会自动回滚，也不代表完成了上传、存储和全部业务行为验证。需要回滚时，可在 Cloudflare 的部署历史回滚到此前成功版本；D1 和 B2 数据不随代码回滚。

本地只验证构建的命令（依赖安装后）：

```powershell
Set-Location "D:/Development/WorkSpace/ImgBed/web"
npm run build
Set-Location "D:/Development/WorkSpace/ImgBed"
node "ci/build-pages.mjs"
```

官方依据：[Direct Upload 与 GitHub Actions](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)、[Pages Functions 配置](https://developers.cloudflare.com/pages/functions/wrangler-configuration/)、[Worker 模块部署](https://developers.cloudflare.com/pages/functions/advanced-mode/)。
