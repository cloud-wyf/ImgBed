# 构建与部署关系

三个子树保留上游的依赖锁文件、构建入口和文档。导入源码不会安装依赖、升级生产环境或启动桌面 UI。

## 后端与网页端

`backend/` 提供上传、认证、文件管理和存储适配接口。`web/` 是 Vue 网页前端源码。网页编译后的 HTML/JS/CSS 发布到 `backend/frontend-dist/`，随 Pages Functions 一起部署到一个 Pages 项目。

后端自带的 `frontend-dist/` 是上游已发布的前端快照，不保证与当前独立导入的 `web/` 提交完全一致。只有网页构建及兼容性检查通过后，才替换后端中的前端发布产物。

在网页目录按上游锁文件安装依赖后构建：

```powershell
Set-Location "D:/Development/WorkSpace/typora-imgbed/web"
npm ci
npm run build
```

后端部署有 Pages、Workers 和 Docker 多种入口，应按 `backend/CONTRIBUTING.md` 与 `backend/deploy/` 的当前说明选择。个人生产系统采用 Pages + D1 + B2；不要将其他部署示例误当成本机已配置的生产入口。

## 桌面端

`desktop/` 为 Tauri/Rust/Svelte 应用。Windows 构建需要 Rust 与 MSVC Build Tools，前端依赖按 `package-lock.json` 安装：

```powershell
Set-Location "D:/Development/WorkSpace/typora-imgbed/desktop"
npm ci
npm run tauri build
```

本地 Python 工具尚未迁入 Rust 桌面模块。此阶段整理仓库并保存现有实现；桌面 UI、Typora CLI 和回收逻辑共用核心实现的改造后续单独验证。

## 本地工具检查

Python 代码编译检查可在不生成缓存文件的情况下完成；单元测试在 `tools/tests/`，使用模拟接口与内存数据库，不调用生产 API。真实云端测试另外明确安排，不随普通单元测试自动运行。
