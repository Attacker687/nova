# 写评循环

一个 doc-writer 写，一个 doc-reviewer 评，主会话裁定，最多 3 轮。调用方（design、stories、test-plan）给出这些参数：

| 参数 | 说明 |
|---|---|
| 文档 | 输出路径，如 `docs/nova/【功能】/design.md` |
| 文档类型 | 技术方案 / 通用方案 / Story 清单 / 测试方案 |
| 模板 | 模板文件路径 |
| 评审要点 | 评审要点文件路径 |
| 素材 | goal.md 和其他素材的路径清单 |
| 过程目录 | 如 `.nova/【功能】/design/` |
| 代码根 | 有代码出处要核对时给出 |

`【nova】` 指插件根目录；脚本 `doc_check.py`、`review_check.py` 在 `【nova】/skills/design/scripts/`，`refcheck.py` 在 `【nova】/skills/codemap/scripts/`。派单里的文件一律写绝对路径，并附上 `【nova】/references/grounding.md`；给 doc-reviewer 的派单还要附 `【nova】/references/review-format.md`。

## 每一轮（N = 1、2、3）

1. **写**：派 `nova:doc-writer`。第 1 轮任务「起草」；之后「按评审修改」，附 `review-【N-1】.json` 和 `triage-【N-1】.md`。
2. **机械检查**：
   - `doc_check.py 【文档】 --template 【模板】`：缺章节，就把缺的章节名发回给 doc-writer 补写，补完再查。这仍然算同一轮。
   - 有代码根时，运行 `refcheck.py 【文档】 --root 【代码根】`：有坏出处，就把清单发回给 doc-writer 修正，修完再核。这也算同一轮。
3. **存档**：把文档复制到 `【过程目录】/round-【N】.md`。
4. **评**：派 `nova:doc-reviewer`，输出 `【过程目录】/review-【N】.json`；第 2 轮起附上一轮的评审结果和裁定。然后运行 `review_check.py` 校验格式，不合格就把问题发回重写。
5. **裁定**：主会话逐条处理评审问题，写 `【过程目录】/triage-【N】.md`（表格：编号、严重程度、裁定、理由）：
   - `critical` / `high`：打开问题所指的位置核实，属实就「采纳」，不属实就「不采纳」并写明理由；
   - `medium`：默认「采纳」，明显误判的「不采纳」；
   - `low`：改动很小才「采纳」；
   - `kind` 为 `decide` 的，裁定为「进待决策」：由 doc-writer 写进「待决策」表，状态「待定」，不在正文里替用户决定。
6. **是否继续**：还有「采纳」的 `critical`、`high`、`medium` 问题，且 N < 3，就进入下一轮。否则结束循环：只剩 `low` 或「进待决策」项时，再派一次 doc-writer 处理掉，这次改动不必再评审。

## 结束时交回调用方

最终文档、跑了几轮、第 3 轮后仍未解决的问题（编号、严重程度、一句话）、「待决策」里的待定项和默认项。
