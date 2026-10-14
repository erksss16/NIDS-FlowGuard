# GitHub 上传指南

## 已准备的文件

`release/` 是本地交付目录，已被 Git 忽略：

- `github-ready/`：可直接上传的源码目录，包含隐藏配置文件。
- `nids-github-source.zip`：同一份源码的压缩包，解压后上传其内容。
- `nids-datasets.zip`：四个预处理 CSV，适合作为 Release 数据附件。
- `SHA256SUMS.txt`：压缩包校验值。

源码包包含前后端、启动脚本、文档和两个小体积模型权重；不含 `dist`、数据库、日志、依赖目录、虚拟环境和预处理 CSV。原项目中的数据保留不动。

## 方式一：网页上传源码

1. 在 GitHub 创建空仓库，例如 `nids-dashboard`，先不要自动创建 README 或许可证。
2. 选择 **Add file → Upload files**。
3. 将 `release/github-ready/` 中的文件及子目录拖入上传区；使 `README.md`、`package.json` 位于仓库根目录。
4. 确认 `.gitignore`、`.gitattributes`、`.editorconfig`、`.env.example` 也在上传列表中。
5. 提交信息可填 `Initial commit: NIDS dashboard and SSF detection demo`。

不要把 ZIP 本身当作源码上传，否则 GitHub 无法直接展示目录和 README。网页上传不会执行 `.gitignore` 的排除逻辑，因此应使用已筛选的 `github-ready/` 目录。

GitHub 网页上传目前限制每文件 25 MiB、每次最多 100 个文件，详见 [GitHub 官方说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。本源码包按这些限制准备。

## 方式二：Git 上传源码

在安装 Git 的电脑上，进入 `release/github-ready/`，把下面地址替换为自己的仓库地址：

```powershell
git init
git add .
git commit -m "Initial commit: NIDS dashboard and SSF detection demo"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/nids-dashboard.git
git push -u origin main
```

这些命令适用于新建空仓库。当前整理环境未检测到 Git，因此本次没有创建提交或推送。

## 数据附件

确认数据再分发权限后，在仓库 **Releases → Draft a new release** 新建版本，附上 `nids-datasets.zip` 和 `SHA256SUMS.txt`。发布后可在 README 中补充实际 Release 链接。使用者按 [数据恢复步骤](DATASETS.md) 解压即可运行完整模型。

建议仓库简介：

> 基于 Vue 3、FastAPI 与 PyTorch 的网络入侵检测演示系统，支持流式检测、概念漂移分析、告警聚合与 AI 查询。

可选 Topics：`network-security`、`intrusion-detection`、`vue3`、`fastapi`、`pytorch`、`continual-learning`。

尚未替你选择开源许可证或发布数据；源码及数据来源确认后再补充相应授权声明。
