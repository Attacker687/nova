# 评审结果格式

doc-reviewer 和 code-reviewer 都把评审结果写成一个 JSON 文件，由 `skills/design/scripts/review_check.py` 校验。

```json
{
  "round": 1,
  "target": "被评审的文件或目录",
  "verdict": "approved",
  "summary": "两三句总体判断",
  "goal_check": [
    {"goal": "G1", "supported": true, "where": "§4.2", "note": ""}
  ],
  "findings": [
    {
      "id": "F1",
      "severity": "high",
      "axis": "complete",
      "kind": "fix",
      "where": "§4.2 第 3 段 / src/order/Service.java:88",
      "problem": "一句话说清问题",
      "evidence": "为什么说这是问题：引用原文、代码出处或推理",
      "suggestion": "最小的可执行改法",
      "verify": "改完之后怎么确认改好了"
    }
  ]
}
```

## 取值

| 字段 | 取值 |
|---|---|
| `verdict` | `approved`（可以交付）、`changes_requested`（要改）。只要有 `critical` 或 `high` 的问题就必须是 `changes_requested` |
| `severity` | `critical`：做错了会造成严重后果（数据错误、安全漏洞、方向性错误）；`high`：不改就达不成目标或会出明显问题；`medium`：应该改，但不阻塞；`low`：可改可不改 |
| `axis` | `goal` 支撑目标、`complete` 完整、`clear` 清晰无歧义、`consistent` 前后一致、`grounded` 有据可查、`decision` 决策处理得当、`testable` 可验证、`correct` 代码正确、`robust` 边界与异常、`maintainable` 可维护 |
| `kind` | `fix`：作者能直接改；`decide`：需要用户拍板（方向、范围、优先级、取舍），写进「待决策」表，不由作者自行决定 |

- `goal_check` 只在有 goal.md 时填，逐条对应每个目标。代码评审可以省略。
- `findings` 按严重程度从高到低排；`low` 的问题最多列 5 条。
- 没有问题时 `findings` 写空数组。
