# 面向移动基线解算的列车安全可信定位方法研究

本仓库提供当前通用移动基线解算代码，包含相对运动预测关闭和相对 CV 运动预测两类配置，每类各有 continuous 与 fix-and-hold 两种整数模式。实验数据、地图和运行输出不随代码发布。

## 环境

- Python 3.9 或更高版本（运行器仅使用 Python 标准库）
- macOS 与 Xcode Command Line Tools 提供的 `clang`（当前构建脚本按本项目的 macOS 构建环境编写）

## 配置和运行

1. 复制 `settings.example.json` 为 `settings.json`。
2. 将示例中的 RINEX 观测文件和导航文件路径换成自己的数据路径，并按需调整 GPST 时间范围。
3. 构建三套源码变体：

   ```bash
   python3 build_solvers.py --variant all
   ```

4. 运行单组或四组顺序对比：

   ```bash
   python3 main.py --profile R0_CONT
   python3 main.py --profile R0_FH
   python3 main.py --profile RR_CONT
   python3 main.py --profile RR_FH
   python3 compare_four.py
   ```

每次运行在 `outputs/` 下生成独立结果。`settings.json`、编译产物和输出目录均为本机文件，不应提交到仓库。

## 当前四组配置

| 配置键 | 相对运动预测 | 整数模式 |
|---|---|---|
| `R0_CONT` | 关闭 | continuous |
| `R0_FH` | 关闭 | fix-and-hold |
| `RR_CONT` | 相对 CV | continuous |
| `RR_FH` | 相对 CV | fix-and-hold |

配置定义见 `configs/profiles.json`。当前四组主线不包含 PVA；载波—伪距独立恢复策略22保留在单独的研究候选目录，不属于本仓库的通用运行入口。

## 源码来源与修改记录

RTKLIB 源码副本分别保存在 `c_src/original/`、`c_src/original_audit/` 和 `c_src/relative_cv/`，各分支用于不同构建身份，不应合并覆盖。保留各源码目录中的原始许可文件与版权声明。项目修改概述见 `docs/第三方代码与修改说明.md`，相对 CV 分支的逐行差异见 `docs/原版至相对CV.patch`。
