# 本地 Typora 图床工具

这里维护现有 Python 工具的源码。正式运行目录仍是 `D:/Program Files/TyporaImgBed`；本次复制源码不会切换 Typora 自定义上传命令或每日计划任务。

- `upload.py`：Typora 上传入口，JPG/PNG 按现有策略压缩为 WebP，全部图片成功后逐行输出链接。
- `deduplicate.py`、`local_index.py`：最终内容 SHA-256 去重；云端元数据验证、SQLite 索引和上传/回收进程锁。
- `recycle.py`：扫描 `D:/Notes`，连续 30 天未引用后复制到回收站，验证后永久删除源路径所有 B2 版本并清除去重索引。
- `setup.py`：录入图床上传配置并使用 Windows DPAPI 加密 Token。
- `configure_typora.py`：预览或应用 Typora 上传命令，应用前要求退出 Typora 并保存备份。
- `collect_b2.py`、`collect_b2_gui.py`、`show_backend.py`：本机凭据录入和查看辅助工具。界面程序需要用户自行按需运行。

## 本机配置

源码执行时默认读取同目录配置。`config.example.json` 与 `recycle-config.example.json` 仅为无凭据的结构示例，不能直接代替已配置的生产文件。实际 `config.json`、DPAPI 文件、SQLite 索引和回收状态不加入 Git；不要把空示例覆盖到生产目录。

要求 Python 3.12 或更新版本，依赖为 Pillow，凭据解密和进程锁依赖 Windows。当前安装使用 version-fox 的 Python 3.14.2、Pillow 12.2.0；`.cmd` 保留现有个人运行路径。恢复到其他电脑时需要调整运行入口并重新配置当前用户凭据。

仓库版 `configure_typora.py` 把后续备份写入同目录的 `backups/`，该目录不提交；旧安装版及已生成的备份继续保留。

维护验证：

```powershell
Set-Location "D:/Development/WorkSpace/ImgBed"
python -B -m unittest discover -s "tools/tests" -p "test_*.py"
python -B "tools/tests/verify_protocol.py"
```

单元测试使用内存索引和模拟云端接口；协议测试仅启动本机 HTTP 测试服务，产物放在已忽略的 `tools/tests/artifacts/`，不读取生产凭据或运行数据库。历史真实上传测试不随普通检查自动执行。

回收的实际运行、空间释放和隐藏版本说明见 [图片回收说明](图片回收说明.md)。现有笔记中的旧路径与云端移动后新路径不一致的问题另见 [部署记录](../docs/current-deployment.md)。
