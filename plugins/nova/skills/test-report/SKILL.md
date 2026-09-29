---
name: test-report
description: 根据测试方案、执行结果和缺陷清单生成测试报告，按固定规则给出「通过 / 有条件通过 / 不通过」的结论，可发布到飞书。用户说出测试报告、总结测试结果时使用。
---

# test-report：测试报告

`【nova】` 指本 skill 目录往上两级的插件根目录；下文路径都写成绝对路径使用。

## 1. 生成

找到三份输入：`docs/nova/【功能】/testplan.json`、`.nova/【功能】/test/results.json`、`docs/nova/【功能】/defects.json`（没有缺陷时可以没有这个文件）。然后运行：

`python scripts/report.py 【testplan.json】 --results 【results.json】 --defects 【defects.json】 --out docs/nova/【功能】/test-report.md --env "【测试环境一句话】" --json`

结论由脚本按固定规则算出（规则见脚本开头的说明），不做人为调整。用户认为某个缺陷不该算（比如属于设计如此）时，由用户决定改缺陷的状态（改为 `wontfix`）或严重程度，改完重新生成。

## 2. 补充分析

在报告末尾加一节「7. 分析与建议」，依据报告里的数据写，每条都能在前面的章节找到依据：
- 失败和缺陷集中在哪些功能或模块；
- 未执行、被阻塞的用例对结论的影响；
- 上线前必须处理的事项，以及可以之后再处理的事项。

## 3. 发布（用户要时）

按 `nova:design` 第 6 节「发布」的做法，把 test-report.md 发布到飞书：用 `【nova】/skills/design/scripts/doc_check.py test-report.md --export 【临时目录】/feishu.md` 取出标题和正文，再 `docs +create --title "【标题】" --doc-format markdown --content @feishu.md`。

## 4. 完成

告诉用户：结论和依据（一句话）、报告路径、未关闭的缺陷数（按严重程度），以及飞书链接（有的话）。
