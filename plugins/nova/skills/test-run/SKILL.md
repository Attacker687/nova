---
name: test-run
description: 执行测试方案：把用例写成自动化测试并运行，人工用例交给用户执行，汇总结果，把产品缺陷登记进缺陷清单；也用于修复后的复测。用户说执行测试、跑测试用例、复测时使用。
---

# test-run：执行测试

开始前先读 [运行环境约定](../../references/runtime.md)，按当前宿主处理路径、命令和子 agent。

输入是 `docs/nova/【功能】/testplan.json`（`status` 应为 `approved`，且已有用例）。产出：
- 测试代码：写在独立分支 `nova/【功能】-test` 上；
- 执行结果：`.nova/【功能】/test/results.json`；
- 缺陷清单：`docs/nova/【功能】/defects.json`，格式见 `【nova】/skills/test-report/scripts/report.py` 开头的说明。

测试只写测试代码，不改产品代码；发现的产品缺陷交给开发修（`nova:build` 或手工）。

`【nova】` 指本 skill 目录往上两级的插件根目录；`results.py` 指 `scripts/results.py`，`testplan.py` 指 `【nova】/skills/test-plan/scripts/testplan.py`。路径都写成绝对路径使用，git 命令在仓库根目录运行。过程目录 `.nova/【功能】/test/`，下文简称【过程】。

## 1. 准备

1. **被测分支**：默认用 `nova/【功能】`（build 的结果），没有就用当前分支，和用户确认。
2. **worktree**：按 `../../references/runtime.md` 创建或复用测试 worktree，分支 `nova/【功能】-test`，基线为 `【被测分支】`，实际路径记入 `【过程】/worktrees.json`。`.nova` 没被 git 忽略时，按 `nova:build` 第 1 步的办法处理。
3. **运行方式**：按类型确认，写进 `【过程】/env.md`。
   - 单元测试：项目的测试命令。
   - 接口测试：服务怎么启动、地址是什么、测试账号怎么拿。
   - 端到端测试：应用地址、浏览器驱动（项目没有的话用 Playwright）。
   - 能从代码地图的「怎么跑」和项目配置里查到的直接用，查不到的问用户。需要启动服务时，用后台命令启动并等它就绪。

## 2. 执行自动化用例

1. 把 `automatable` 为 true 的用例按测试点类型（unit / api / e2e）分组，每组再切成每批不超过 15 条。
2. 每批派一个 `nova:test-runner`。派单附：worktree 路径、这批用例和对应测试点、代码地图目录、`env.md`、`【nova】/references/grounding.md`；测试放在哪里，按项目惯例定，没有惯例就放 `tests/nova/【功能】/`；JUnit 输出 `【过程】/junit-【批次】.xml`；运行记录 `【过程】/run-【批次】.md`。
   - 共用这个测试 worktree 的各批逐批派出，避免同时改文件、提交或运行测试而互相干扰；有独立 checkout 和独立测试资源时才按运行环境约定并行。
3. 每批返回后导入结果：`python results.py import 【过程】/junit-【批次】.xml --plan 【testplan.json】 --out 【过程】/results.json`。提示「没有用例编号」的测试，让该批的 test-runner 改名后重跑。

## 3. 人工用例

把 `automatable` 为 false 的用例和没能自动化的用例整理成 `【过程】/manual-checklist.md`（编号、步骤、数据、预期），请用户执行后告诉你结果，再逐条登记：
`python results.py set 【过程】/results.json TC-xxx --result pass|fail|blocked --message "…"`。
用户暂时不执行的，保持未执行，报告里会如实体现。

## 4. 登记缺陷

1. 汇总各批运行记录里的缺陷草稿，同一个问题引起的多条失败合并成一个缺陷，写进 `defects.json`：编号 `BUG-001` 起，状态 `open`，`cases` 列出相关用例。已有 defects.json 时接着编号。
2. 每条失败用例登记原因和缺陷：`python results.py set … TC-xxx --result fail --kind product --defect BUG-00x`；环境问题用 `--result blocked --kind env`。
3. `python results.py summary 【过程】/results.json --plan 【testplan.json】`：`fail_without_kind` 必须为空。每个失败都要有原因。

## 5. 复测（修复之后）

用户说缺陷修好了，要复测时：把被测分支的最新提交合并进 `nova/【功能】-test`，重跑相关用例所在的批次，再导入结果。复测通过的缺陷，状态改为 `closed`；仍然失败的，改回 `open` 并补充新的现象。

## 6. 收尾

提交 worktree 里的测试代码。告诉用户：通过、失败、阻塞、未执行的数量，缺陷清单（按严重程度），测试代码所在的分支。建议下一步用 `nova:test-report` 出报告；测试代码合并进功能分支之前先征求用户意见。
