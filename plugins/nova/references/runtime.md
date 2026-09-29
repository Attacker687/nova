# 运行环境：Codex 与 Claude Code

两种环境共用 skills、角色说明、脚本和模板。先按本文件确定工具、路径和派单方式，再执行 skill 的业务步骤。

## 路径与命令

- `【nova】` 是当前 `SKILL.md` 所在目录往上两级的插件根目录。`scripts/`、`references/`、`templates/` 相对当前 skill 目录；跨 skill 的路径相对 `【nova】`。安装后的缓存路径可能变化，每次从实际加载的 skill 路径推导。
- `docs/`、`.nova/` 是目标项目的产物，写到目标项目，不能写进插件安装目录。派单中的输入、输出、脚本和 worktree 都用绝对路径。
- `nova:【skill】` 表示同一插件里的 `skills/【skill】/SKILL.md`：先读取，再按其步骤执行。它不是 shell 命令；Codex 可以直接按文件路径读取，无需模拟 Claude 的斜杠命令。
- 先检查 Python 3.10+ 和 git；`python` 不可用时使用已确认版本的 `python3` 或解释器绝对路径。Windows 下用 `python -X utf8` 调用脚本，避免中文路径和检查结果中的符号受系统编码影响。飞书操作另外检查 `lark-cli` 和登录状态，方法见 [lark-cli.md](lark-cli.md)。
- 命令按当前 shell 改写。PowerShell 不直接照抄 Bash 的 `\` 续行、`&&` 或 heredoc；优先指定命令工具的工作目录，路径加引号，JSON/XML/Markdown 用 UTF-8 文件传入。PowerShell 中把 `@文件名` 参数加引号，例如 `--content '@feishu.md'`。后台命令必须等到完成并取得退出码，不能把启动成功当成检查通过。

## 派子 agent

`nova:【角色】` 的角色说明是 `【nova】/agents/【角色】.md`，包括 codemapper、doc-writer、doc-reviewer、implementer、code-reviewer、verifier、test-runner。

- **Claude Code**：用已注册的 `nova:【角色】` 子 agent。
- **Codex**：这些 Markdown 文件作为角色参考，不会自动注册成 Codex agent 类型。先读对应文件，再用当前环境实际提供的子 agent 工具派单（如 `spawn_agent`）；把角色正文和派单素材交给子 agent，或给出角色文件绝对路径并要求先读。不要把 `nova:implementer` 当成内置 `agent_type`。
- 角色文件头里的 `tools: Read, Grep, Glob, Bash, Write, Edit` 和 `model: inherit` 是 Claude 元数据。Codex 用自身的读写、搜索和命令工具完成相同操作，模型沿用当前配置；正文里的职责和文件修改范围仍须遵守。
- 每份派单同时附本文件的绝对路径，要求子 agent 先读，确保独立上下文也使用正确的 shell、编码和文件路径。
- 写者、评审者、验收者使用独立子 agent。Codex 工具支持 `fork_turns` 时用 `"none"`，仅传所需素材；三路代码评审分别派单，不互传本轮其他评审者的结论。同一角色的后续修改可以续用原子 agent。
- 同时运行的数量以宿主上限为准，给主会话留一个位置。名额不足时等待、回收已完成且不再需要的子 agent（宿主支持时），或分批执行；三路评审仍需三份独立结果。多个写者只有在输出文件、git 索引和测试资源互不冲突时才并行，共用一个 worktree 的测试批次逐批执行。
- 用宿主的消息、等待工具收取完成结果，再读取输出文件并做机械检查。Codex app 的 `create_thread` 创建用户可见聊天，不用于这些内部派单。
- 环境没有子 agent 能力时，先完成可独立做的素材整理和脚本检查，说明缺少哪一步；不能把主会话自评写成已完成独立评审或验收。

## worktree（build / test-run）

skill 中的 worktree 创建与收尾统一按这里处理。分支名沿用 skill 约定，实际路径由创建方式决定。

1. 在目标项目确认基线和分支，用 `git worktree list --porcelain` 查找已有 checkout。Codex app 提供托管工具时，先 `list_artifacts`，优先复用本任务可用且没有未处理工作或运行进程的 worktree；已有路径仍在用时直接接续，不能重置它。
2. **有托管工具**：用 `create_worktree` 创建，明确传入本步骤的基线 `ref`，等待创建完成，使用返回的目录。工具创建的 checkout 可能是 detached HEAD：在该目录用 `git switch -c 【新分支】 【基线】`，分支已存在则 `git switch 【已有分支】`。不能依赖工具默认的远端分支。工具报错时先排查并报告，不能为绕过错误擅自另建手动 worktree。
3. **没有托管工具的 CLI 环境**：用 `git worktree add 【路径】 -b 【新分支】 【基线】`；分支已存在时用 `git worktree add 【路径】 【已有分支】`。默认路径为 `.nova/worktrees/_integration`、`.nova/worktrees/【S】`、`.nova/worktrees/_test`；占用时选另一个路径并记录，不覆盖。
4. 每次创建或复用后，将用途（integration / Story 编号 / test）、实际绝对路径、分支、管理方式（managed / git）写入 `【过程】/worktrees.json`；托管的另存 `list_artifacts` 返回的 `identityKey`。恢复时读取此文件，并用 git / `list_artifacts` 核实路径与分支；旧任务没有记录时从已有 checkout 查回并补记。全部后续命令和派单使用记录里的路径。
5. 功能的过程文件统一保存在主会话选定的项目目录中。worktree 不会复制未提交的 goal.md、design.md、stories.json 等文件，派单必须指向真实存在的绝对路径。
6. **收尾**：确认产物已保存、所需提交已合并、没有进程或其他任务使用 checkout。托管 worktree 仍有后续用途时保留；不再需要时用 `archive_worktree`，不用 `git worktree remove` 删除它。手动 worktree 才用 `git worktree remove 【实际路径】`。临时 Story 分支只有在已合并且未被检出时才 `git branch -d`；集成和测试分支保留。受保护或仍在用的 worktree 保留并报告。

## 进度交接

沿用 `save` / `restore` 的文件与 git 协议。长期经验只有在宿主提供明确的 memory 机制时才写入；否则写进交接单的「注意」，不假定存在 Claude 的 memory 目录。Claude Code 可 `/clear`，Codex 打开新聊天后说「用 nova 恢复进度」。
