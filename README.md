# nova

自用的 Claude Code 插件：飞书文档协作 + 工作进度交接，后续扩展到方案写作、开发和测试流水线。

## 包含什么

| skill | 做什么 | 怎么触发 |
|---|---|---|
| `nova:feishu-comment` | 按飞书评论改文档：明确的意见改进正文，要拍板的记进文档末尾的「待决策」表，处理过的评论标为已解决 | 给文档链接，说「处理评论」 |
| `nova:feishu-diagram` | 在飞书文档里画可编辑的图（mermaid / SVG / 配色思维导图），也能改已有的图 | 「把这个流程画到飞书文档里」 |
| `nova:feishu-wiki` | 体检 wiki 目录结构，出带勾选框的整理报告；勾选后执行移动、归档、改名、新建 | 给 wiki 链接说「整理这个知识库」；勾选后说「按勾选整理」 |
| `nova:save` | 写交接单，推到项目 git 的 `nova-handoff` 分支 | 「保存进度」 |
| `nova:restore` | 找到最新交接单，对齐代码，接着干 | 「恢复进度」 |

## 准备

- [Claude Code](https://claude.com/claude-code)
- Python 3.10+、git
- 飞书官方命令行：`npm install -g @larksuite/cli`，然后在自己的终端里 `lark-cli auth login` 用个人身份登录。需要的用户身份权限：云文档读写（`docx:document:*`）、文档评论（`docs:document.comment:*`）、知识库节点（`wiki:node:read/create/move/retrieve`、`wiki:space:read`）、画板（`board:whiteboard:node:create/read`）。缺权限时 lark-cli 会报 `missing_scope` 并列出缺什么。

## 安装

在 Claude Code 里：

```text
/plugin marketplace add E:\Code\nova
/plugin install nova@nova
```

改了插件源码后，重新安装（先 `/plugin uninstall nova@nova` 再 install），并开一个新会话才会生效。

## 会在哪里留下文件

| 位置 | 内容 | 建议 |
|---|---|---|
| 项目里的 `.nova/` | 本机的交接单等运行时文件 | 加进项目的 `.gitignore` |
| 项目 git 的 `nova-handoff` 分支 | 推到远端的交接单，供其他机器恢复 | 与主分支历史无关，可随时删 |
| `~/.nova/wiki/【时间戳】/` | 每次 wiki 整理的树快照、整理项、报告和执行计划 | 用完可删 |

## 开发

```text
.claude-plugin/marketplace.json   本地插件市场（只有 nova 一个插件）
plugins/nova/
  .claude-plugin/plugin.json
  references/lark-cli.md          飞书 CLI 用法与实测坑，所有 skill 共用这一份
  skills/【skill】/SKILL.md        skill 主流程
  skills/【skill】/scripts/        确定性的辅助脚本（只用 Python 标准库）
tests/                            脚本的测试
```

- 跑测试：`python -m pytest tests/`
- 飞书命令的写法、限制和坑只记在 `references/lark-cli.md`，skill 里引用它，不重复写。
- 能用脚本确定算出来的（树结构、报告渲染、勾选解析、git 操作）放脚本并写测试；需要判断的留给 SKILL.md。

## 路线

1. ✅ 飞书协作 + 进度交接
2. 代码地图 + 方案写作（一个 agent 写、一个 agent 评）
3. Story 拆分 + TDD 实现 + 三路代码评审 + 独立验收
4. 测试方案 → 测试执行 → 测试报告
