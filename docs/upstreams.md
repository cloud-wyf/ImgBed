# 上游维护

三个子树保存完整源码，不使用 `.gitmodules` 或 gitlink。根仓库统一提交、统一推送，各子树从各自上游合并更新。

| 目录 | Remote | 官方地址 | 默认分支 |
| --- | --- | --- | --- |
| `backend/` | `backend-upstream` | https://github.com/MarSeventh/CloudFlare-ImgBed.git | `main` |
| `web/` | `web-upstream` | https://github.com/MarSeventh/Sanyue-ImgHub.git | `master` |
| `desktop/` | `desktop-upstream` | https://github.com/MarSeventh/satellite.git | `main` |

初始化导入使用 `--squash`，把每次官方更新压缩成一份上游快照提交，减少总仓库的日志噪声；个人修改继续保存在根仓库历史中。导入时的提交记录见 `upstreams.json`，后续更新后同步记录新版本。

## 合并官方更新

先确认工作区已保存到 Git 历史或另行保留；有未提交修改时先处理，不覆盖源码。以下命令在总仓库根目录执行，按项目逐个运行，每次检查完成后再更新下一个：

```powershell
git subtree pull --prefix="backend" backend-upstream main --squash
git subtree pull --prefix="web" web-upstream master --squash
git subtree pull --prefix="desktop" desktop-upstream main --squash
```

`subtree pull` 会获取并合并上游代码，成功时产生本地合并提交。有冲突时按正常 Git 合并处理，核对个人定制后再继续。不要进入子目录执行普通 `git pull`，因为它们共享根仓库。

本仓库的三个官方 remote 用于获取源码；个人远程 `origin` 是 `https://github.com/cloud-wyf/ImgBed.git`，仓库为公开。推送根仓库即可上传全部源码，不需要再为三个子树建立独立个人仓库。不要将官方 remote 当作个人发布目标。

## 在另一台电脑恢复

普通 `git clone` 即可获取全部源码，不需要 `--recurse-submodules`。Git remote 配置不会随 clone 自动恢复；需要更新官方代码时，按上表重新添加三个官方 remote。账户凭据、生产配置及运行数据库单独恢复，不从 Git 历史获取。
