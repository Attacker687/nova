---
name: build
description: 按 Story 清单逐个实现功能：每个 Story 在独立 git worktree 里测试驱动开发，经通用、对抗、边界三路代码评审和独立验收后合并进功能分支，最多返工 3 轮。用户说开始开发、实现这些 Story、按清单写代码时使用；也用于继续中断的开发。
---

# build：逐个实现 Story

输入是 `docs/nova/【功能】/stories.json`（`status` 应为 `approved`）。所有开发都在 `.nova/worktrees/` 下的 worktree 里进行，用户当前的工作目录和分支不受影响；结果是功能分支 `nova/【功能】`。

`【nova】` 指本 skill 目录往上两级的插件根目录；`state.py` 指 `scripts/build_state.py`，`review_check.py` 指 `【nova】/skills/design/scripts/review_check.py`。路径都写成绝对路径使用，git 命令在仓库根目录运行。过程目录 `.nova/【功能】/build/`，下文简称【过程】；每个 Story 的文件放 `【过程】/【S】/`。

## 1. 开工准备（首次）

`【过程】/state.json` 已存在时，跳到第 2 步继续。否则：

1. stories.json 的 `status` 不是 `approved` 时，先问用户是否仍要开始。
2. `git status --porcelain` 有输出时，提醒用户：未提交的改动不会进入功能分支。
3. `git check-ignore -q .nova` 失败时，把 `.nova/` 追加到 `.git/info/exclude`（只影响本机），并告诉用户。
4. **测试命令**：从代码地图 README 的「怎么跑」、构建文件、CI 配置里找出跑全部测试的命令，以及 worktree 里需要先执行的准备命令（如 `npm ci`，没有就留空），请用户确认。
5. 建分支和集成 worktree（基线分支默认是当前分支，和用户确认）：
   `git branch nova/【功能】 【基线】`，`git worktree add .nova/worktrees/_integration nova/【功能】`，在集成 worktree 里跑一次准备命令和测试命令，把基线上本来就失败的测试（测试名和一句话原因）写进 `【过程】/baseline-failures.md`，没有就写「无」。之后判断「新失败」都以这个文件为准，中断后恢复也靠它。
6. `python state.py init --stories 【stories.json】 --state 【过程】/state.json --feature-branch nova/【功能】 --base 【基线】 --test-cmd "…" --setup-cmd "…"`

## 2. 逐个 Story

`python state.py next --state 【过程】/state.json` 给出下一个 Story（`resume: true` 表示接着上次做到的状态继续）。没有可做的就进第 3 步。

派单都附上：worktree 绝对路径、stories.json 中该 Story 的完整内容、design.md、代码地图目录、`【nova】/references/grounding.md`、测试命令、基线失败清单 `【过程】/baseline-failures.md`；给 code-reviewer 的还要附 `【nova】/references/review-format.md`。

### 2.1 建 worktree（新 Story）

`git worktree add .nova/worktrees/【S】 -b nova/【功能】-【S】 nova/【功能】`，在其中跑准备命令。用 `git rev-parse nova/【功能】` 取分叉点提交，记下：
`python state.py set --state … 【S】 --status implementing --round 1 --base 【分叉点提交】`

### 2.2 实现（第 r 轮）

派 `nova:implementer`，证据文件 `【过程】/【S】/implement-r【r】.md`。修复轮附上要修的问题清单（上一轮裁定采纳的评审问题，或验收失败项）。

返回后确认：`git -C 【worktree】 status --porcelain` 为空（有未提交改动就让它提交），`git -C 【worktree】 log --oneline 【base】..HEAD` 有新提交。实现者报告卡住时，按第 2.6 节处理。

### 2.3 三路评审

`state.py set … --status reviewing`。在一条消息里同时派 3 个 `nova:code-reviewer`，视角分别为 `general`、`adversarial`、`edge`，输出 `【过程】/【S】/review-【视角】-r【r】.json`。

- 第 1 轮评审范围 `【base】..HEAD`。
- 之后的轮次评审范围 `【reviewed】..HEAD`，并附上一轮的合并问题清单和裁定，以及本轮改动的文件列表；让评审员核对修复、只看新改动和受影响的调用方。

用 `review_check.py` 校验三个文件，不合格的发回重写。然后
`python state.py merge-reviews 【三个文件】 --out 【过程】/【S】/merged-r【r】.json`，并 `state.py set … --reviewed 【当前 HEAD】`。

### 2.4 裁定

逐条处理合并后的问题，写 `【过程】/【S】/triage-r【r】.md`（表格：编号、严重程度、裁定、理由）：

- `critical` / `high`：打开所指代码核实，属实「采纳」，不属实「不采纳」并写理由；
- `medium` / `low`：属实的记入 `【过程】/followups.md`（Story 编号、问题、位置），不阻塞本 Story。

有采纳的 `critical` / `high` 时：r < 3 就把它们（连同本 Story 已记下的 medium）作为修复清单，回到 2.2 进入第 r+1 轮；r = 3 按 2.6 处理。没有就进入验收。

### 2.5 验收与合并

1. `state.py set … --status verifying`，派 `nova:verifier`，附实现者最新的证据文件，输出 `【过程】/【S】/verify-r【r】.json`。
2. `verdict` 为 `fail`：r < 3 就把失败项作为修复清单回到 2.2；修复后的评审只派 `general` 一路，范围是修复的改动。r = 3 按 2.6 处理。
3. `pass`：`state.py set … --status merging`，在集成 worktree 里 `git merge --no-ff nova/【功能】-【S】 -m "【S】 【标题】"`。
   - 有冲突：`git merge --abort`，按 2.6 处理。
   - 合并后在集成 worktree 跑测试命令。出现 `baseline-failures.md` 之外的新失败，按 2.6 处理。
4. 清理：`git worktree remove .nova/worktrees/【S】`，在集成 worktree 里 `git branch -d nova/【功能】-【S】`；
   `state.py set … --status done --commit 【合并提交】`。回到第 2 步开头。

### 2.6 卡住

`state.py set … --status blocked --note "【原因】"`，停下来告诉用户：卡在哪一步、原因、相关文件（证据、评审、验收结果）。给出选择：用户介入后继续这个 Story / 跳过它、继续不依赖它的 Story / 停止。worktree 保留，方便查看。

## 3. 收尾

1. `python state.py show --state 【过程】/state.json`。
2. 全部完成时：在集成 worktree 跑一次测试命令，对照 `baseline-failures.md` 分出新失败和原有失败，然后 `git worktree remove .nova/worktrees/_integration`。
3. 告诉用户：功能分支 `nova/【功能】`（相对基线的提交数）、每个 Story 的轮次、最终测试结果、`followups.md` 里的待办、卡住的 Story。建议下一步：用 `nova:test-plan` 设计测试，或审阅后合并功能分支。推送和建 PR 等用户要求再做。
