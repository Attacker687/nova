---
name: codemap
description: 给一个程序（整个仓库或其中一个模块）生成或更新代码地图，写到 docs/codemap/，供之后写方案、写代码、写测试时了解现状。用户说扫代码、建代码地图、更新代码地图时使用；design、test-plan 发现缺少代码地图时也用它。
---

# codemap：代码地图

开始前先读 [运行环境约定](../../references/runtime.md)，按当前宿主处理路径、命令和子 agent。

代码地图由 `nova:codemapper` agent 读代码写成，主会话只做编排：盘点、分批派单、核对、记录。代码不会被修改。

下文 `scripts/…`、`references/…` 指本 skill 目录下的文件，调用时写成绝对路径；`【nova】` 指本 skill 目录往上两级的插件根目录。

## 1. 确定范围

- **程序根目录**：用户指定的目录；没指定就用当前仓库根。仓库里有多个独立服务时，问用户要扫哪个，一个程序一份地图。
- **程序名**：程序根目录名的小写短横线形式，如 `order-service`。
- **地图目录** `docs/codemap/【程序名】/`（相对仓库根），**过程目录** `.nova/codemap/【程序名】/`。
- 地图目录里已有 `_meta.json` 时，默认走增量更新（第 5 节）；用户要求重扫时走全量。

## 2. 盘点

`python scripts/inventory.py 【程序根】 --out 【过程目录】/inventory.json`

把输出的一行摘要告诉用户（文件数、行数、模块数、批数）。源码超过 2000 个文件时，先和用户确认是全扫还是只扫某几个模块。

## 3. 扫描

派单都要写明：代码根目录、模式、格式说明 `references/map-format.md` 和有据可查规则 `【nova】/references/grounding.md` 的绝对路径、要写的文件路径。

- **批数 ≤ 2**：派一个 codemapper 用「合成」模式直接读全部源码，写地图目录。派单附上 `inventory.json` 路径。
- **批数 > 2**：
  1. 每批派一个 codemapper，模式「扫描一批」，派单里列出该批文件和落在该批里的入口线索，笔记写到 `【过程目录】/notes/【批次号】.md`。互不依赖的批次在一条消息里同时派出，每次最多 6 个，同时受运行环境的可用子 agent 名额限制。
  2. 全部笔记到齐后（缺哪批就补派哪批），派一个 codemapper 用「合成」模式，派单给出 `inventory.json` 和 `notes/` 目录，写地图目录。

## 4. 核对并记录

1. `python scripts/refcheck.py docs/codemap/【程序名】 --root 【程序根】`。有问题的出处，派 codemapper 按清单修正（派单附问题清单），再核一次，直到没有问题或只剩确实无法定位的（在报告里列出）。
2. 自己打开 README.md 和 05-rules.md 读一遍，检查是否符合格式说明；缺篇或明显空洞的，派 codemapper 补写。
3. 写 `docs/codemap/【程序名】/_meta.json`：`program`、`root`、`commit`（取 inventory.json 的 `commit`）、`generated_at`、`mode`、`batches`、`source_files`。

## 5. 增量更新

1. `python scripts/inventory.py 【程序根】 --since 【_meta.json 里的 commit】 --out 【过程目录】/changed.json`。没有变化就告诉用户地图已是最新，结束。
2. 派一个 codemapper，模式「增量更新」，派单给出地图目录、`changed.json`，写回地图目录。变动超过 200 个文件时改走全量。
3. 按第 4 节核对并记录（`mode` 写 `update`）。

## 6. 完成

告诉用户：地图目录、各篇的规模（入口数、规则数、流程数）、出处核对结果、「待确认」有几条及所在位置。提醒把 `.nova/` 加进 `.gitignore`（还没加的话），`docs/codemap/` 建议提交。
