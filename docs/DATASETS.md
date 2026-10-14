# 数据与模型文件

## 目录与用途

| 文件 | 用途 | 是否在源码包中 |
| --- | --- | --- |
| `ssf/NSL_pre_data/PKDDTrain+.csv` | NSL 训练输入 | 否 |
| `ssf/NSL_pre_data/PKDDTest+.csv` | NSL 流式检测输入 | 否 |
| `ssf/UNSW_pre_data/UNSWTrain.csv` | UNSW 实验训练输入 | 否 |
| `ssf/UNSW_pre_data/UNSWTest.csv` | UNSW 实验测试输入 | 否 |
| `ssf/ckpt_nsl_percent08_epoch200_seed5011.pth` | 默认启动权重 | 是 |
| `ssf/ckpt_nsl.pth` | 另一个 NSL 权重 | 是 |

四个 CSV 原始文件合计约 183 MiB。数据目录被 `.gitignore` 排除，完整运行时需从独立数据包恢复。

## 恢复数据

发布者可将 `nids-datasets.zip` 放入同一 GitHub 仓库的 Release 附件。下载后在项目根目录解压：

```powershell
Expand-Archive -LiteralPath .\nids-datasets.zip -DestinationPath . -Force
```

数据包自身包含 `ssf/NSL_pre_data/` 和 `ssf/UNSW_pre_data/` 两级路径。默认启动仅需要 NSL 数据，UNSW 是单独实验用途。

CSV 已经过预处理，不应直接用原始数据集文件替换。NSL 与 UNSW 的特征维度分别为 121 和 196，不能混用模型权重。当前源码未提供从原始数据到这些 CSV 的完整转换流程，也未记录权重完整训练来源，因此复现范围为现有预处理文件和权重上的运行演示。

## 发布前确认

仓库目前没有足够信息确认预处理数据和权重的完整授权来源。对外发布数据附件前应由维护者确认再分发权限；数据包准备完成不代表已获得许可。数据库、邮件记录和本地日志不应包含在发布包中。
