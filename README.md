# 自用 Typora 图床

基于 CloudFlare ImgBed、Sanyue ImgHub 和 Satellite 的个人维护仓库，非官方发行版。三个上游项目通过 Git subtree 纳入同一仓库，保留各自许可证和版权声明。

```text
typora-imgbed/
├── backend/   CloudFlare-ImgBed 子树
├── web/       Sanyue-ImgHub 子树
├── desktop/   Satellite 子树
├── tools/     本地 Typora 上传、去重和图片回收
├── docs/      上游维护、构建和当前部署记录
└── README.md
```

后端和网页端组合部署到一个 Cloudflare Pages 项目；D1 保存元数据，Backblaze B2 保存图片。桌面端是独立 Windows/macOS 应用。本仓库建立时，生产部署及 Typora 的运行入口仍沿用现有安装目录；导入上游源码不等于升级云端或桌面应用。

维护方式见 [上游维护](docs/upstreams.md)，构建与部署关系见 [构建说明](docs/build.md)，当前已部署系统见 [部署记录](docs/current-deployment.md)，本地工具见 [tools/README.md](tools/README.md)。

本仓库完整保存三份源码，只需一个自己的 GitHub 仓库。日后依次合并各子树的上游更新，完成验证后统一推送。初始化仅添加只读用途的官方上游 remote，自己的发布 remote 在明确仓库地址后再配置。
