# 协作运行入口

完整的安装、配置与启动步骤统一维护在 [README](README.md) 和 [复现说明](REPRODUCE.md)。

源码包不包含虚拟环境、node_modules、数据库或预处理数据。完整模型演示需另外恢复 [数据附件](docs/DATASETS.md)，并准备 CUDA 环境。

真实邮件演示运行 `./start-real-email.ps1`，按提示输入发件邮箱、SMTP 授权码和管理员收件邮箱。不要分享个人环境目录或密钥。
