# NIDS · 网络流量入侵检测系统

基于 Vue 3、FastAPI 和 PyTorch 的网络流量入侵检测演示项目，结合自监督学习、持续学习和概念漂移检测，展示从检测结果到告警分析的完整流程。

> 当前检测入口使用预处理数据集进行流式回放，不是直接抓取网卡流量。完整模型运行需要 NVIDIA GPU 和可用的 CUDA 版 PyTorch。

## 功能

- **态势总览**：检测数量、攻击分布和流量趋势。
- **流量与日志**：实时展示检测结果，按协议、服务、标签和时间筛选。
- **告警中心**：攻击聚合、风险提示和邮件通知。
- **统计与模型**：统计图表、模型性能及漂移信息。
- **AI 助手**：本地检测数据查询，可选连接外部兼容 API。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vue Router、Vite 6、ECharts |
| 后端 | FastAPI、Uvicorn |
| 模型 | PyTorch、NumPy、pandas、scikit-learn、SciPy |
| 存储 | 默认 SQLite，可选 MySQL |
| 启动 | Windows PowerShell |

## 快速开始

推荐 Windows 10/11、Node.js 22、Python 3.10。Python 依赖未锁定全部版本，其他版本组合需要自行验证。

在项目根目录打开 PowerShell：

```powershell
npm ci
python -m venv .venv-ssf
.\.venv-ssf\Scripts\python.exe -m pip install -r requirements.txt
```

### 仅启动界面和 API（不需要 GPU）

```powershell
$env:NIDS_DB_BACKEND = "sqlite"
$env:NIDS_AI_PROVIDER = "local"
.\.venv-ssf\Scripts\python.exe -m uvicorn backend:app --host 127.0.0.1 --port 8000
```

另开终端：

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 [本地界面](http://localhost:5173)，API 文档位于 [Swagger UI](http://localhost:8000/docs)。默认演示账号为 `admin` / `hust2026`。首次启动自动初始化空数据库；源码仓库不包含历史检测记录，运行模型后才会产生检测数据。

### 完整检测演示（需要 GPU 和数据文件）

1. 按 [数据文件说明](docs/DATASETS.md) 放置预处理 CSV，模型权重已包含在源码中。
2. 安装与本机驱动匹配的 CUDA 版 PyTorch，确认以下命令最后输出 `True`：

   ```powershell
   .\.venv-ssf\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
   ```

3. 启动：

   ```powershell
   .\start.ps1
   ```

**注意：`start.ps1` 每次启动会删除 `data/ssf.sqlite3` 并重新生成检测记录，请先备份需要保留的数据。** 脚本固定使用 SQLite、NSL 数据集及 GPU 0。按 `Ctrl+C` 停止脚本管理的服务，日志位于 `logs/`。

## 项目结构

```text
src/                  Vue 页面、路由与组件
public/               静态资源
backend.py            API、SQLite 初始化、通知和 AI 查询
ssf/ssf.py            SSF 检测入口
ssf/utils.py          模型和数据处理工具
ssf/*.pth             预训练权重
start.ps1             完整检测启动脚本
start-real-email.ps1  交互式邮件配置与启动
pretrain-ssf.ps1      预训练脚本
requirements.txt      Python 依赖
package-lock.json     前端依赖锁文件
docs/                 数据、上传和模型设计说明
```

## 配置

配置通过环境变量传入，示例见 [.env.example](.env.example)。程序**不会自动加载 `.env`**，PowerShell 中需使用 `$env:变量名 = "值"`。

- 默认演示密码仅适合本地使用；可通过 `NIDS_DEFAULT_USER`、`NIDS_DEFAULT_PASSWORD` 配置首次初始化账号。
- 默认管理员邮箱为占位地址 `admin@example.com`，通过 `NIDS_DEFAULT_EMAIL` 设置真实收件人。已有 SQLite 账号仅在邮箱为空或占位地址时自动更新邮箱。
- 外部 AI 默认提供方及地址见 `backend.py`。外部服务可用性不保证；设置 `NIDS_AI_PROVIDER=local` 可只使用本地查询。启用外部 AI 会将问题及部分检测摘要发送至该服务。
- 真实邮件发送使用 `start-real-email.ps1`，交互输入发件邮箱、SMTP 授权码和收件邮箱；不要提交授权码或 API 密钥。
- MySQL 参数为 `NIDS_MYSQL_HOST`、`NIDS_MYSQL_PORT`、`NIDS_MYSQL_DATABASE`、`NIDS_MYSQL_USER`、`NIDS_MYSQL_PASSWORD`；`docker-compose.yml` 是本地演示配置。

当前版本面向本地演示与研究；生产部署前需完善认证、授权、密码存储及接口访问控制。

## 文档

- [安装、复现与常见问题](REPRODUCE.md)
- [预处理数据与权重](docs/DATASETS.md)
- [GitHub 上传指南](docs/GITHUB_UPLOAD.md)
- [模型设计说明](docs/FRAMEWORK_IMPROVEMENTS.md)

## 授权与来源

本项目尚未指定开源许可证；公开可见不代表授权他人再分发或商用。发布前应确认源码、权重及数据的来源和授权，再选择适合的许可证。预处理数据单独发布，不能推定原始数据集允许任意再分发。
