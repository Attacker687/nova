# 飞书 CLI（lark-cli）用法约定

nova 的飞书操作一律用飞书官方命令行 `lark-cli`（npm 包 `@larksuite/cli`）。下面的命令和结论在 lark-cli 1.0.97 上实测过；CLI 升级后行为有出入，以 `lark-cli 【命令】 --help` 为准并更新本文件。

## 1 通用规矩

- **一律带 `--as user`**：用登录用户本人的身份操作。不用 `--as bot`。
- **文档参数接受链接或 token**：`--doc`、`--url`、`--node-token` 直接传飞书链接即可，知识库（wiki）链接会自动解析成底层文档。
- **多行内容先写进临时文件**，用 `--content @【文件】` 传入，shell 转义会弄坏写在命令行里的多行内容。`@` 后面**只能是当前目录下的相对路径**（绝对路径报 `unsafe file path`），所以命令写成 `cd 【文件所在目录】 && lark-cli … --content @文件名`。
- **内容格式**：`--content` 默认按 XML 解析，加 `--doc-format markdown` 才按 Markdown。勾选框、画板、高亮块、@人 这些只有 XML 能表达；Markdown 里也可以直接嵌 XML 标签，标签会生效。两种格式的完整写法用 `lark-cli skills read lark-doc/references/lark-doc-xml.md` 和 `lark-cli skills read lark-doc/references/lark-doc-md.md` 查。
- **转义**：XML 文本里 `<` `>` `&` 写成 `&lt;` `&gt;` `&amp;`，换行写 `<br/>`。Markdown 里字面的 `[ ] * _ \` < $ ~` 要加 `\`；`docs +fetch --doc-format markdown` 读回的内容已经是转义形式，拿去做 `--pattern` 或写回时原样使用。
- **输出是 JSON**：`ok` 为 `true` 才算成功。用 `-q '【jq 表达式】'` 取字段，例如 `-q '.data.document.content'`。
- **通用接口路径不带开头的 `/`**：写 `lark-cli api GET drive/v1/files/【token】/comments`。Windows 的 Git Bash 会把以 `/` 开头的参数改写成本地路径，导致 404。
- **删除类操作要加 `--yes`**，否则 CLI 拒绝执行。
- **长输出先写文件再读**：Claude Code 会截断过长的命令输出。读长文档或大量评论时先 `… > 【临时文件】`，再分段读文件。
- **查登录状态**：`lark-cli auth status`。`.identities.user.tokenStatus` 为 `valid` 即登录有效，`.identities.user.userName` 是用户名。
- **缺权限**时报 `missing_scope` 并列出缺的权限。处理办法：先在飞书开放平台给应用开通该权限（用户身份），再运行 `lark-cli auth login --scope "【原有权限 + 缺的权限】" --no-wait --json`，把返回的 `verification_url` 发给用户去浏览器授权，用户确认后运行 `lark-cli auth login --device-code 【device_code】`。
- **未登录或登录过期**：请用户在自己的终端运行 `lark-cli auth login`。不要替用户输入任何凭证。

## 2 操作对照表

| 要做的事 | 命令 | 结果取哪里 |
|---|---|---|
| 读文档（看内容） | `lark-cli docs +fetch --as user --doc 【文档】 --doc-format markdown` | `.data.document.content`（首行 `<title>…</title>` 是标题）、`.data.document.revision_id` |
| 读文档（要块 ID、画板、表格列宽） | `lark-cli docs +fetch --as user --doc 【文档】 --detail full` | 默认 XML：每个块带 `id`；画板 `<whiteboard token="…" type="mermaid">源码</whiteboard>`；表格 `<colgroup><col width="…"/>` |
| 读大纲 / 某一节 | `docs +fetch … --scope outline --detail with-ids`；`docs +fetch … --scope section --start-block-id 【标题块 id】 --detail with-ids` | 标题块 id、该节所有块 id（`--detail with-ids` 只在默认 XML 格式下生效） |
| 只取版本号 | `docs +fetch … --scope outline -q '.data.document.revision_id'` | 整数，内容变更时递增 |
| 建文档 | `lark-cli docs +create --as user --content @【文件】 [--doc-format markdown] [--parent-token 【知识库节点或文件夹】]`；标题写在内容开头的 `<title>` 里，这时不要再传 `--title`（两个都给会重复，`--title` 生效并报警告）。`--parent-token` 传知识库节点时，新文档成为它的子节点 | `.data.document.document_id`、`.url`、`.new_blocks[]`（画板的 `block_token`） |
| 整篇覆盖 | `lark-cli docs +update --as user --doc 【文档】 --command overwrite --content @【文件】` | `.ok`（规则见第 3 节） |
| 追加到末尾 | `docs +update … --command append --content @【文件】` | `.ok` |
| 查找替换一小段文字 | `docs +update … --command str_replace --pattern "【原文】" --content "【新文】"` | `.ok`。⚠️ 会替换**全部**匹配处 |
| 替换一段连续的块 | `docs +update … --command block_replace --start-block-id 【首块】 --end-block-id 【末块】 --content @【文件】` | `.ok` |
| 在某块后插入 | `docs +update … --command block_insert_after --block-id 【块】 --content @【文件】`；插到最前面用 `--block-id 0` | `.ok` |
| 删除一段块 | `docs +update … --command block_delete --start-block-id 【首块】 --end-block-id 【末块】` | `.ok` |
| 移动块 | `docs +update … --command block_move_after --block-id 【目标位置前一块】 --src-block-ids 【要移的块，逗号分隔】` | `.ok` |
| 改文档标题 / 改知识库节点名 | `lark-cli drive +update-title --as user --url 【文档链接】 --title "【新标题】"`；知识库节点传 `https://www.feishu.cn/wiki/【node_token】`，节点名随之改变（wiki 自带的改名接口要 `wiki:node:update` 权限，用这个就不需要） | `.ok` |
| 读评论 | `lark-cli drive +list-comments --as user --url 【文档链接】 --solved-status all`（只看未解决用 `false`） | `.data.items[]`：`comment_id`、`is_solved`、`is_whole`、`quote`、`reply_list.replies[].content.elements[].text_run.text`；挂在画板上的评论 `parent_type` 为 `WHITEBOARD_BLOCK` |
| 加全文评论 | `lark-cli drive +add-comment --as user --doc 【文档链接】 --full-comment --content '[{"type":"text","text":"【内容】"}]'`（传裸 token 时加 `--type docx`） | `.data.comment_id` |
| 标记评论已解决 | `lark-cli drive +resolve-comment --as user --url 【文档链接】 --comment-id 【comment_id】` | `.ok` |
| 查知识库节点 | `lark-cli wiki +node-get --as user --node-token 【节点 token、文档 token 或链接】` | `.data.node`（或 `.data`）：`node_token`、`obj_token`、`obj_type`、`title`、`parent_node_token`、`space_id` |
| 列子节点 | `lark-cli wiki +node-list --as user --space-id 【空间 ID】 [--parent-node-token 【父节点】] --page-all --page-limit 0` | `.data.nodes[]`：`node_token`、`obj_token`、`obj_type`、`title`、`has_child`、`parent_node_token`。不给父节点时列空间根下的节点 |
| 建知识库节点 | `lark-cli wiki +node-create --as user --space-id 【空间 ID】 --parent-node-token 【父节点】 --title "【标题】" [--obj-type docx\|sheet]` | `.data.node_token`、`.data.obj_token`、`.data.url` |
| 移动知识库节点 | `lark-cli wiki +move --as user --node-token 【节点】 --target-parent-token 【新父节点】` | `.ok` |
| 删知识库节点 | `lark-cli wiki +node-delete --as user --node-token 【节点】 --obj-type wiki --yes`（连子树一起删） | `.ok` |
| 列知识空间 | `lark-cli wiki +space-list --as user`；个人文档库的空间 ID 直接写 `my_library` | `.data.spaces[]` |
| 搜文档 | `lark-cli docs +search --as user --query "【关键词】"` | `.data.results[]` |
| 按类型搜云空间文件 | `lark-cli drive +search --as user --query "【关键词，≤30 字】" --doc-types sheet --only-title` | `.data.results[].result_meta`：`token`、`url` |
| 搜人 | `lark-cli contact +search-user --as user --query "【名字】"`；查自己用 `--user-ids me` | |
| 建电子表格 | `lark-cli sheets spreadsheets create --as user --data '{"title":"【标题】"}'` | `.data.spreadsheet.spreadsheet_token`、`.url` |
| 读表格单元格 | `lark-cli api GET 'sheets/v2/spreadsheets/【token】/values/【子表 id】!A1:F9' --as user` | `.data.valueRange.values` |
| 删云空间文件 | `lark-cli drive +delete --as user --file-token 【token】 --type docx\|sheet --yes` | `.ok` |
| 读画板节点 | `lark-cli whiteboard +export --as user --whiteboard-token 【画板】 --output-type raw` | `.data.nodes[]` |
| 换掉一张画板 | `docs +update … --command block_replace --block-id 【画板所在块的 id】 --content '<whiteboard type="mermaid" path="@./图.mmd"></whiteboard>'`（画板 token 会变，挂在旧画板上的评论随之消失） | `.data.document.new_blocks[]` |
| 往画板里加节点 | `lark-cli api POST board/v1/whiteboards/【画板】/nodes --as user --data @【nodes.json，形如 {"nodes":[…]}】` | `.data.ids` |
| 其他开放接口 | `lark-cli api 【GET/POST/PATCH/DELETE】 【路径，不带开头 /】 --as user [--params '【JSON】'] [--data @【文件】]` | |

## 3 写回文档的规则（实测结论）

- **文档里有画板时，不要整篇覆盖**：覆盖会丢掉原有画板（即使内容里写了它的 `<whiteboard token="…">` 也一样）。改用按块修改：`block_replace` 替换文字所在的块，画板块原样不动；要挪位置用 `block_move_after`。
- **文档里没有画板时可以整篇覆盖**：用 XML（默认格式）写，表格用 `<colgroup><col width="…"/></colgroup>` 保留列宽。覆盖会丢掉评论锚点和图片，能按块改就按块改。
- **复制画板**：XML 里写 `<whiteboard token="【已有画板 token】"></whiteboard>` 会把那张画板复制进来；前提是那张画板不在正被覆盖的这篇文档里。
- **新建画板**：推荐 `<whiteboard type="mermaid" path="@./图.mmd"></whiteboard>`，从当前目录的文件读源码；也可以把源码直接写在标签里，这时源码**原样写、不做 XML 转义**（转义成 `--&gt;` 的中文图实测稳定失败）；Markdown 里写 mermaid 代码块也行。都会自动转成可编辑画板，读回时（`--detail full`）能直接看到 mermaid 源码。`type="svg"` 把自包含的 SVG 转成可编辑图形；空白画板写 `<whiteboard type="blank"></whiteboard>`。
- **画板转换经常静默失败**：飞书把 mermaid 转成画板偶发失败（实测约三次里有一次，同一段源码重试即成功）。这时命令可能仍返回 `ok: true`，只在 `.data.warnings` 里出现 `degrade_code=2107 … Whiteboard content parse failed`，画板被直接丢掉。所以**凡是写入含画板的内容，都检查 `.data.warnings`**：有 2107 就原样重试，最多 3 次。成功时 `.data.document.new_blocks[]` 里有 `block_type` 为 `whiteboard` 的一项。整篇创建时失败的，用 `docs +fetch --detail with-ids` 找到位置，`block_insert_after` 单独补插。
- **改已有 mermaid 画板用 `block_replace`**：`whiteboard +update --input_format mermaid` 实测对 `flowchart LR` 报 `Unsupported color format`，刚改过的画板还会报 `not ready`，不可靠。改图就把画板所在的块整个换成新的画板标签（见上表「换掉一张画板」）。
- **`--revision-id` 拦不住冲突**：传旧版本号照样能写进去。要防止覆盖别人的新改动，写之前重新读一次 `revision_id`，和之前记下的对比，不一致就停下。
- **查找替换会替换全部匹配处**：只想改一处，要么让 `--pattern` 唯一，要么先读出块 ID 再 `block_replace`。
