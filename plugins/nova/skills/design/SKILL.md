---
name: design
description: 写方案：先和用户对齐目标，再由一个 agent 写、另一个 agent 评审，最多 3 轮，最后交用户拍板定稿；支持技术方案和通用方案（流程、规范、调研等文档），可发布到飞书收评论。用户要写技术方案、设计一个功能、出方案、写一份文档方案时使用；用户说处理这份方案的飞书评论时也用它。
---

# design：写方案

一份方案 = `docs/nova/【功能】/goal.md`（目标）+ `docs/nova/【功能】/design.md`（方案）。本地文件是正本；飞书只用来展示和收评论，评论处理完同步回本地再重新发布。

`【nova】` 指本 skill 目录往上两级的插件根目录，下文路径都写成绝对路径使用。

## 1. 立题

- **功能名**：小写短横线，如 `coupon-expiry`，和用户确认。过程目录 `.nova/【功能】/design/`。
- **类型**：改代码的用「技术方案」（模板 `templates/tech.md`）；其他（流程、规范、调研、计划）用「通用方案」（模板 `templates/general.md`）。
- **素材**：用户给的需求文字存成 `【过程目录】/inputs/需求.md`；本地文件记下路径；飞书链接用 `lark-cli docs +fetch --as user --doc 【链接】 --doc-format markdown` 存进 `inputs/`（命令写法见 `【nova】/references/lark-cli.md`）。

## 2. 代码地图（技术方案）

找到相关程序的 `docs/codemap/【程序】/_meta.json`：
- 没有：告诉用户需要先建代码地图，然后按 `nova:codemap` 建。
- 有，但记录的 `commit` 之后代码有改动：按 `nova:codemap` 做增量更新。

代码地图目录和程序根目录都记入素材；写评循环核对代码出处时也用这个程序根目录。

## 3. 对齐目标

按 `templates/goal.md` 起草 `docs/nova/【功能】/goal.md`，把草稿给用户看，并请他确认或改这四件事：

1. 哪个是核心目标，哪些是顺带的；
2. 每个目标怎么判定达成；
3. 明确不做什么；
4. 最终产出物是什么、给谁用。

目标要过三道关才能往下走：**范围明确**（包括和不包括都写了）、**产出物单一**（一份方案只交付一样东西）、**每个目标可判定**。不过关就就具体缺口追问，最多 3 次；仍不清楚的，把缺口写进 goal.md 的「约束」并告诉用户。`python scripts/doc_check.py goal.md --template templates/goal.md` 通过、用户确认后，把 goal.md 的 `status` 改为 `approved`。

## 4. 写评循环

按 `【nova】/references/review-loop.md` 执行，参数如下：

| 参数 | 取值 |
|---|---|
| 文档 | `docs/nova/【功能】/design.md` |
| 模板 | 第 1 步选定的模板 |
| 评审要点 | `references/review-points.md` |
| 素材 | goal.md、`inputs/` 下的文件、代码地图目录 |
| 过程目录 | `.nova/【功能】/design/` |
| 机械检查 | `python scripts/doc_check.py design.md --template 【模板】` 退出码为 0；技术方案另跑 `python 【nova】/skills/codemap/scripts/refcheck.py design.md --root 【程序根】`，退出码为 0 |

## 5. 交用户拍板

向用户汇报：每个目标由哪一节支撑、方案要点（3～5 条）、第 3 轮后仍未解决的问题，然后逐项处理「待决策」表：

- **待定项**：每项给出选项和建议，请用户选择。一次问多项时，每次最多 4 项。
- **默认项**：列出来，用户没意见就保持。

用户的结论写进「待决策」表（状态改为「已定：【结论】」），再派 `nova:doc-writer` 执行「落实决策」任务。改动涉及方案主体（换方案、改范围）时，再走一轮写评循环。

用户确认定稿后，把 design.md 的 `status` 改为 `approved`，并告诉用户可以接着用 `nova:stories` 拆 Story。

## 6. 飞书评审（用户要时）

**发布**：
1. `python scripts/doc_check.py design.md --export 【过程目录】/feishu.md`，记下它打印的标题。
2. 在过程目录里执行 `lark-cli docs +create --as user --title "【标题】" --doc-format markdown --content @feishu.md`；放到指定知识库节点下时加 `--parent-token 【节点】`，放哪里先问用户。
3. 检查返回的 `.data.warnings`，有 `2107` 就原样重试，最多 3 次。
4. 把文档链接写进 design.md 文件头的 `feishu:` 字段。

**处理评论**（用户说「处理飞书评论」时）：
1. `lark-cli drive +list-comments --as user --url 【feishu 链接】 --solved-status false` 读出全部未解决评论；再用 `lark-cli docs +fetch --as user --doc 【feishu 链接】 --scope outline -q '.data.document.revision_id'` 记下版本号。
2. 按 `nova:feishu-comment` 第 3 步的四类归类，连同 `comment_id` 写进 `【过程目录】/feishu-comments-【日期】.md`。
3. 派 `nova:doc-writer` 按这些意见修改本地 design.md：「改」和「答」直接改，「定」进待决策表。改动大时再走一轮写评循环。
4. 写回前核对：
   - 再取一次版本号。和第 1 步不一致，说明飞书上的正文在这期间被人改过，整篇覆盖会冲掉这些改动：停下，问用户是先把飞书上的改动同步回本地，还是直接覆盖。
   - 再读一次未解决评论。有第 1 步之后新加的，先按第 2、3 步处理，再回到这一步。
5. 对第 2 步记下的每条评论（四类都算，「定」已进待决策表）执行 `lark-cli drive +resolve-comment --as user --url 【feishu 链接】 --comment-id 【comment_id】`。这一步必须在覆盖之前做：整篇覆盖会丢掉评论和正文的对应位置。
6. 重新导出，在过程目录里执行 `lark-cli docs +update --as user --doc 【feishu 链接】 --command overwrite --doc-format markdown --content @feishu.md` 覆盖飞书文档（方案里的图都来自 mermaid 源码，覆盖后会重新生成），同样检查 2107。
7. 回到本 skill 第 5 节，处理新增的待定项。

## 7. 完成

告诉用户：goal.md 和 design.md 的路径、状态、写评跑了几轮、待决策的处理情况、飞书链接（有的话）、下一步建议。
