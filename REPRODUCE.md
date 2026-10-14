# 安装与复现

基础安装与两种启动方式见 [README](README.md)。本文补充复现条件和排错步骤。

## 完整运行的前提

- Windows PowerShell、Node.js 22、Python 3.10（推荐组合）。
- NVIDIA GPU，Python 环境中 `torch.cuda.is_available()` 返回 `True`。
- [数据说明](docs/DATASETS.md) 中列出的 NSL 两个预处理 CSV。
- `ssf/ckpt_nsl_percent08_epoch200_seed5011.pth` 权重。

`start.ps1` 优先使用 `.venv-ssf/Scripts/python.exe`，也可使用 Conda：

```powershell
$env:NIDS_CONDA_ENV = "ssf"
.\start.ps1
```

脚本会清空旧 SQLite 数据库，然后启动 API、NSL 检测模型及前端。它使用数据集回放，不是网络抓包。初始结果和后续性能受数据、权重、随机种子及依赖版本影响，仓库不承诺固定指标。

## 无 GPU 时

按 README 中“仅启动界面和 API”操作，不运行 `start.ps1`。空数据库时没有检测历史，这是预期行为；也可自行恢复备份到 `data/ssf.sqlite3`。项目不包含样例数据库。

## 功能入口

| 功能 | 路径 |
| --- | --- |
| 总览 | `/app/dashboard` |
| 实时流量 | `/app/traffic` |
| 完整日志 | `/app/traffic-logs` |
| 告警中心 | `/app/alerts` |
| 统计分析 | `/app/statistics` |
| 模型性能 | `/app/model` |
| AI 助手 | `/app/assistant` |

## 常见问题

### PowerShell 禁止执行 npm.ps1

使用 `npm.cmd ci` 和 `npm.cmd run dev`。如启动脚本被组织策略禁止，请按本机策略处理。

### 缺少 CSV

下载数据附件并在项目根目录解压，最终路径须为 `ssf/NSL_pre_data/PKDDTrain+.csv` 等，不能多套一层目录。

### CUDA 不可用

检查显卡驱动和 PyTorch 构建是否匹配。CPU 版 PyTorch 无法运行当前 SSF 入口；可先使用无 GPU 的界面/API 模式。

### 端口冲突或模型立即退出

检查 8000、5173 是否被其他服务使用，以及 `logs/backend.err.log`、`logs/ssf.err.log`。完整脚本发现 8000 已占用时会复用现有服务，请确认该服务确实属于此项目。

### 更换账号密码或收件邮箱

`NIDS_DEFAULT_USER` 和 `NIDS_DEFAULT_PASSWORD` 用于创建初始账号，已有账号不会随密码环境变量自动更新。`NIDS_DEFAULT_EMAIL` 仅在邮箱为空或占位地址时更新对应账号邮箱。保留数据库时应区分这两种行为。

### AI 或邮件不可用

设置 `NIDS_AI_PROVIDER=local` 排除外部服务问题。真实邮件需要有效 SMTP 配置；未配置时使用演示通知逻辑。API 密钥和 SMTP 授权码只放在本地环境变量中。
