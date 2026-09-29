---
name: stories
description: 把定稿的技术方案拆成可以逐个实现和验收的 Story，每个 Story 带可验证的验收标准和生产入口；一个 agent 拆、另一个 agent 评审，最后交用户确认。用户说拆 Story、拆任务、准备开发时使用；build 发现没有 Story 清单时也用它。
---

# stories：拆 Story

输入是 `docs/nova/【功能】/design.md`（状态应为 `approved`），输出是 `docs/nova/【功能】/stories.json`（正本，build 读它）和由它渲染出的 `stories.md`（给人读）。

`【nova】` 指本 skill 目录往上两级的插件根目录；下文路径都写成绝对路径使用。

## 1. 准备

- 方案状态不是 `approved` 时，先告诉用户，问是否仍要拆（方案可能还会变）。
- 找到方案对应的程序根目录（design.md 素材里的代码地图 `_meta.json` 的 `root`），作为「代码根」。

## 2. 写评循环

按 `【nova】/references/review-loop.md` 执行，参数如下：

| 参数 | 取值 |
|---|---|
| 文档 | `docs/nova/【功能】/stories.json` |
| 文档类型 | Story 清单（格式见 `scripts/stories.py` 开头的说明，派单里给出这个文件路径） |
| 模板 | 无，格式以 `scripts/stories.py` 的说明为准 |
| 评审要点 | `references/review-points.md` |
| 素材 | goal.md、design.md、代码地图目录 |
| 过程目录 | `.nova/【功能】/stories/` |
| 机械检查 | `python scripts/stories.py check stories.json --root 【代码根】` 退出码为 0；通过后运行 `python scripts/stories.py render stories.json --out docs/nova/【功能】/stories.md`，评审时两个文件一起给 |

给 doc-writer 的派单里强调：验收标准的 `entry` 要写生产代码里真实经过的入口；写到的现有文件、函数、参数都要回代码核实。

## 3. 交用户确认

把 `stories.md` 的总览表和依赖图给用户看，说明 Story 数量、实现顺序、第 3 轮后仍未解决的问题。用户要调整的，改 stories.json 后重新跑机械检查和渲染；改动大时再走一轮写评循环。

用户确认后，把 stories.json 的 `status` 改为 `approved`，重新渲染，并告诉用户可以用 `nova:build` 开始实现。
