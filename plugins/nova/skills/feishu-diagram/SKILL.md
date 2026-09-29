---
name: feishu-diagram
description: 在飞书文档里画可编辑的图（飞书画板，不是图片）：流程图、时序图、类图、状态图、ER 图、思维导图、甘特图等，也能改已有画板。用户要把图画进飞书、把 mermaid 放进飞书文档、改飞书里的某张图时使用；其他 skill 需要往飞书文档里放图时也用它。
---

# feishu-diagram：飞书画板

飞书命令写法和坑以 `../../references/lark-cli.md` 为准，第一次调用 lark-cli 前先读它。

## 1. 选画法

| 画法 | 适用 | 产物 |
|---|---|---|
| **mermaid**（默认） | 流程、时序、类、状态、ER、思维导图、时间线、甘特、饼图、象限图、XY 图 | 飞书把 mermaid 转成可编辑画板，以后读回能看到源码 |
| **SVG** | 要自己设计版式的图：架构分层、能力地图、对比图 | 飞书把 SVG 转成可编辑图形 |
| **配色思维导图** | 大型层级树（组织架构、功能清单），要按层级配色或左右展开 | 飞书原生思维导图节点 |

mermaid 写法要点：

- 用 `classDef`、`style` 这类自定义样式会转换失败；需要配色时改用 SVG 或配色思维导图。
- `journey`、`gitGraph` 飞书不支持，换成 flowchart 或 timeline 表达。
- 节点文字保持简短（10 字以内），一张图的节点控制在 60 个以内；更大的图拆成几张，或改用配色思维导图。

## 2. 确定落点

| 落点 | 做法 |
|---|---|
| 新建文档 | `docs +create`，内容里放画板标签 |
| 插进已有文档 | `docs +fetch --detail with-ids` 找到要插在哪个块后面，`docs +update --command block_insert_after --block-id 【块】` |
| 追加到文档末尾 | `docs +update --command append` |
| 改已有画板 | 从 `docs +fetch --detail full` 的 `<whiteboard token="…">` 取画板 token，见第 4 节 |

用户没说插在哪时，问一句「放在哪一节后面？」。

## 3. 写入

把图的源码存成当前目录下的文件，用画板标签引用（`@` 后面只能是相对路径）：

```bash
cd 【临时目录】 && lark-cli docs +update --as user --doc 【文档】 --command block_insert_after \
  --block-id 【块】 --content '<whiteboard type="mermaid" path="@./图.mmd"></whiteboard>'
```

SVG 用 `type="svg" path="@./图.svg"`，SVG 必须自包含（有 `viewBox`，不引用外部资源）。

写入后必做两件事：

1. 查返回的 `.data.warnings`：出现 `2107` 说明画板被静默丢掉了（常见），原样重试，最多 3 次。
2. `docs +fetch --detail full` 确认该位置出现了 `<whiteboard …>`；mermaid 画板读回时能看到源码。

## 4. 改已有画板

在 `docs +fetch --detail full` 的结果里找到画板：`<whiteboard id="【块 id】" token="…" type="mermaid">源码</whiteboard>`。

- **mermaid 画板**：取出源码改好存成 `图.mmd`，用 `block_replace --block-id 【块 id】` 把这个块换成 `<whiteboard type="mermaid" path="@./图.mmd"></whiteboard>`，同样检查 2107。
- **其他画板**（SVG、配色思维导图、手工画的）：读不回源码。按用户描述重新生成整张图，同样用 `block_replace` 换掉。

换掉的画板 token 会变，挂在旧画板上的评论和手工调整会丢失，动手前告诉用户。

## 5. 配色思维导图

1. 把树写成缩进文本（每层 2 个空格，一行一个节点，字面 `\n` 表示节点内换行）。
2. 生成节点：`python 【本 skill 目录】/scripts/mindmap.py 树.txt --out nodes.json`（在放 `树.txt` 的临时目录里运行）。超过 50 个节点自动左右展开，颜色按层级由深到浅。
3. 在目标位置插入空白画板 `<whiteboard type="blank"></whiteboard>`，从返回的 `.data.document.new_blocks[]` 取画板的 `block_token`。
4. `lark-cli api POST board/v1/whiteboards/【block_token】/nodes --as user --data @./nodes.json`，返回 `.data.ids` 即成功。
5. 在画板下方紧跟一个代码块放缩进树原文。这种画板读不回源码，以后改图靠这份原文重新生成。

## 6. 完成

告诉用户：文档链接、图放在哪一节、用的哪种画法；有重试或没画成的图如实说明。
