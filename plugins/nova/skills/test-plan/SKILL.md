---
name: test-plan
description: 设计测试：从需求、方案、Story 验收标准和代码业务规则里列出判据项，拆成有依据的原子测试点，再生成用例；一个 agent 写、另一个 agent 评审，交用户确认。用户说写测试方案、设计测试用例、拆测试点时使用。
---

# test-plan：设计测试

产物是 `docs/nova/【功能】/testplan.json`（正本，test-run 读它）和由它渲染出的 `test-plan.md`（给人读）。分两段：先定测试点，用户确认后再生成用例。

`【nova】` 指本 skill 目录往上两级的插件根目录；下文路径都写成绝对路径使用。过程目录 `.nova/【功能】/test-plan/`。

## 1. 准备素材

收集 `docs/nova/【功能】/` 下的 goal.md、design.md、stories.json，以及相关程序的代码地图目录。

- 这些都没有、只有一份需求（文字、文件或飞书链接）时也可以做：把需求存进过程目录的 `inputs/`，飞书文档用 `lark-cli docs +fetch` 读取。
- 测的是现有代码却没有代码地图时，先按 `nova:codemap` 建一份，业务规则清单是拆测试点的重要依据。

## 2. 拆测试点

按 `【nova】/references/review-loop.md` 执行，参数：

| 参数 | 取值 |
|---|---|
| 文档 | `docs/nova/【功能】/testplan.json` |
| 文档类型 | 测试方案（测试点）；给 doc-writer 的任务写明「按方法的任务一拆测试点，不写用例」 |
| 模板 | 无；方法与格式见 `references/method.md` 和 `scripts/testplan.py` 开头的说明，两个文件都放进派单 |
| 评审要点 | `references/review-points.md`（用例一节本段不适用） |
| 素材 | 第 1 步收集的全部文件 |
| 过程目录 | `.nova/【功能】/test-plan/points/` |
| 机械检查 | `python scripts/testplan.py check testplan.json [--stories stories.json]` 退出码为 0；通过后 `python scripts/testplan.py render testplan.json --out docs/nova/【功能】/test-plan.md` |

## 3. 用户确认测试点

给用户看：判据项和测试点数量、按类型和优先级的分布、覆盖情况、需求缺口、测试策略。缺口需要用户补充说明的，逐条问清楚，再让 doc-writer 更新。用户确认后进入下一步。

## 4. 生成用例

再按写评循环执行一遍，参数同上，但：
- 任务写明「按方法的任务二为全部测试点生成用例」；
- 过程目录 `.nova/【功能】/test-plan/cases/`；
- 机械检查加 `--need-cases`。

## 5. 定稿

用户确认后，testplan.json 的 `status` 改为 `approved`，重新渲染。用户要在飞书评审时，按 `nova:design` 第 6 节的做法发布 test-plan.md 和处理评论（修改都改在 testplan.json 上，再重新渲染）。

告诉用户：文件路径、测试点和用例数量、人工用例有多少、下一步可以用 `nova:test-run` 执行。
