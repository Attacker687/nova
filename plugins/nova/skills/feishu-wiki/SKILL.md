---
name: feishu-wiki
description: 体检并整理飞书知识库（wiki）的目录结构：分析一棵 wiki 树，在飞书里出一份带勾选框的整理报告，用户勾选后按勾选执行移动、归档、改名、新建。用户给出 wiki 链接说整理/体检知识库时使用；用户说「按勾选整理」时执行上次报告。
---

# feishu-wiki：整理 wiki 结构

两个阶段，中间隔着用户在飞书报告里打勾：

- **分析**：拉树结构 → 对照规则列整理项 → 在飞书出报告 → 等用户勾选。
- **执行**：读回勾选 → 核对树有没有被改过 → 执行打了勾的项 → 在报告上回填结果。

只做结构调整（移动、归档、改名、新建节点、移入「待删除」），正文内容的修改列为人工处理项。真正的删除永远留给用户自己做。

飞书命令写法和坑以 `../../references/lark-cli.md` 为准。下文的 `scripts/…`、`references/…` 指本 skill 目录下的文件，调用脚本时写成绝对路径。每次整理的文件放在 `~/.nova/wiki/【run-id】/`（run-id 用 `YYYYMMDD-HHMMSS`），命令都在这个目录里运行，文件名直接写相对路径。

## 分析

1. **确定范围**：用户给的 wiki 链接（整理这个节点及其下面）或空间 ID（整个空间，个人文档库是 `my_library`）。用 `wiki +node-get` 读回标题，和用户确认「整理《标题》这棵树」。
2. **确定规则**：用户有自己的整理规范（飞书文档或本地文件）就读它；没有就用 `references/rules.md`。
3. **拉结构**：`python scripts/wiki_tree.py fetch --root 【链接】 --out 【run 目录】/tree.json`（整个空间用 `--space`），再 `python scripts/wiki_tree.py render tree.json --tokens` 查看带 token 的树。输出里提示有读取失败或未展开的，报告里会自动列出。
4. **按需读正文**：只凭标题判断不了的节点（标题含糊、疑似重复、入口页可能过厚），用 `docs +fetch --scope outline` 或读正文确认。
5. **列整理项**：写 `【run 目录】/items.json`，格式见 `scripts/wiki_plan.py` 开头的说明。每项一句理由，编号 `W-001` 起。要移入「待删除」而树里还没有这个容器时，先加一项 `create` 建它，再用 `new:W-00x` 引用。
6. **出报告**：`python scripts/wiki_plan.py report --tree tree.json --items items.json --out report.xml --rules "【规则来源】"`；脚本报整理项有问题就改 items.json 重跑。
7. **放到飞书**：问用户报告放哪（默认放在被整理的树根下面）。在 run 目录里执行
   `lark-cli docs +create --as user --content @report.xml --parent-token 【节点】`（标题已在 report.xml 里）。
8. **记录**：写 `【run 目录】/run.json`：`{"run_id", "root", "report_url", "report_doc", "status": "analyzed"}`。

分析阶段完成的标志：用户拿到了报告链接，并知道勾选后说「按勾选整理」。

## 执行

1. **找到这次整理**：用户指定的，或 `~/.nova/wiki/` 下最近一个 `status` 为 `analyzed` 的 run。
2. **读回勾选**：`docs +fetch --doc 【report_doc】 -q '.data.document.content' > checked.xml`，再 `python scripts/wiki_plan.py checked checked.xml`。一项都没勾就告诉用户，结束。
3. **核对并生成计划**：重新拉一次树到 `tree_now.json`，然后
   `python scripts/wiki_plan.py plan --before tree.json --now tree_now.json --items items.json --checked 【编号,逗号分隔】 --out plan.json`。
   出报告后被移动、改名、删除过的节点会列为冲突，不执行。
4. **按 `plan.json` 的 `steps` 顺序执行**（打勾就是用户的授权）：

   | action | 命令 |
   |---|---|
   | create | `wiki +node-create --space-id 【space】 --parent-node-token 【parent】 --title "【new_title】"`，记下返回的 `node_token`，后面步骤里的 `new:W-00x` 换成它 |
   | rename | `drive +update-title --url https://www.feishu.cn/wiki/【node】 --title "【new_title】"` |
   | move / archive / trash | `wiki +move --node-token 【node】 --target-parent-token 【target】` |

   某一步失败就记下原因继续下一步；依赖它的后续步骤跳过。
5. **回填报告**：在报告里用 `str_replace` 把摘要行（`📊 待处理 N 项 · …` 整行原文，见 report.xml 第二行）换成「✅ 【日期】已执行 X 项 · 冲突 Y 项 · 失败 Z 项 · 未勾选 W 项」，并在文末追加「执行结果」一节，逐项写结果。
6. **收尾**：`run.json` 的 `status` 改为 `applied`。

执行阶段完成的标志：计划里每一步都有结果（成功、失败或跳过），报告已回填，用户收到汇总：执行了什么、哪些冲突或失败及原因、「待删除」里有哪些页面等他自己删。
