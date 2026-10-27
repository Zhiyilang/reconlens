# ReconLens

**一个会解释差异的金融对账引擎。**

把两份账交给 ReconLens。它配对一致的条目，并对每一条残差给出**原因**，
附上可审计的证据链。没有证据支撑的原因一律标为 `UNEXPLAINED`，绝不猜测——
在审计场景里，一个自信的错误答案比承认不知道更贵。

为**第二届「新致杯」AI + 无限万象人工智能创新大赛**而建。
完整的 AI 全流程开发记录在 [`AI_CODING_JOURNEY.md`](AI_CODING_JOURNEY.md)，
该文档是赛事要求的独立提交材料。

零依赖，仅用标准库，任何有 Python 的地方都能跑。

---

## 要解决的问题

市面上所有对账工具都停在同一步：列出未匹配项。那不是结果，那是一张待办清单——
对账真正的成本不在**找出**差异，而在**解释**差异，而这一步今天仍由人工一条条完成。

ReconLens 攻的是后半段。对每条残差，它输出：

- **原因**（取自固定分类表，绝非自由文本）
- **证据链**（有序、带权重、每条注明来源）
- **反证**（它选择推翻的那些事实，如实记录）
- **置信度**（由上述权重机械推导，任何读者都能重算）

一条没有反证的判定，说明分析做得太浅，而不是答案太确定。

---

## 快速开始

```bash
python -m reconlens --demo                      # 内置示例
python -m reconlens --bank bank.csv --ledger ledger.csv
python -m reconlens --bank examples/bank.csv --ledger examples/ledger.csv \
        --format markdown --out report.md
python eval.py                                  # 129 条断言
```

输入支持 CSV / JSON。列名不区分大小写地匹配常见别名
（`id`、`ref`、`date`、`amount`、`currency`、`description`，以及中文别名），
因此未加工的银行导出文件通常无需编辑即可加载。

---

## 匹配级联

匹配是一条确定性级联。每一阶段严格比后一阶段更紧，且被前一阶段消费掉的条目
绝不被重新考虑——因此更松的阶段永远无法从更紧的阶段手里抢走高质量配对，
结果可复现。

| 阶段 | 规则 |
|---|---|
| `EXACT_REF` | 凭证号**与**金额同时一致（黄金标准） |
| `EXACT_AMOUNT_DATE` | 金额与日期一致 |
| `AMOUNT_DATE_WINDOW` | 金额一致，日期在 ±N 天内（清算在途） |
| `SPLIT_OR_MERGE` | 单边 ≤3 笔之和等于对方 1 笔 |
| `UNMATCHED` | 残余，交给解释器归因 |

不同币种分组匹配，绝不互相等式化。100 元不等于 100 美元；
需要跨币种对账时传入 `fx_rates`。

---

## 原因分类

| 原因 | 含义 |
|---|---|
| `FEE_DEDUCTION` | 缺口落在手续费特征区间内（≤ 2%） |
| `DATE_MISMATCH` | 金额完全相同、日期超出窗口——清算延迟 |
| `AMOUNT_MISMATCH` | 同日，金额确实不同 |
| `SPLIT_OR_MERGE` | 一方拆单/合并，另一方整笔记账 |
| `DUPLICATE` | 同一侧出现两笔相同金额 |
| `CURRENCY_MISMATCH` | 只有经过汇率换算才一致 |
| `REF_MISMATCH` | 一切一致，仅凭证号不同 |
| `MISSING_IN_LEDGER` | 银行有、账本无 |
| `MISSING_IN_BANK` | 账本有、银行无 |
| `UNEXPLAINED` | 无证据支撑——刻意留给人工 |

---

## 输出长什么样

```
[FEE_DEDUCTION] bank  conf=0.53
    b02  2026-09-03  475.00    INV-1002 payment
    delta: 5.00
    + shortfall of 500 minor units (1.053% of the entry)
    + shortfall is within the fee-shaped band (<= 2%)
    - a small shortfall can also be a data-entry or rounding error
    note: confirm against the fee schedule
```

文本 / Markdown / JSON 三套渲染共用同一份字典，因此不可能彼此漂移。

---

## 实测指标

全部由 `python eval.py` 复现；每个数字都在运行时重算得出，无一处手抄。

| 指标 | 数值 |
|---|---|
| 断言通过数（`python eval.py`） | **129 / 129** |
| 示例：银行 / 账本条目 | 8 / 9 |
| 示例：匹配对数 | 5 |
| 示例：残差条数 | 6 |
| 示例：已解释 / 无法解释 | 4 / 2 |
| 示例：解释率 | **66.7%** |
| 引擎代码行数 | 1,310 |
| 断言套件行数 | 488 |

示例集经过刻意设计，一次运行即可覆盖全部四个匹配阶段与五类原因——
它同时也是引擎行为的可读规格说明。

2 条无法解释的残差是刻意的。引擎拒绝宣称自己没有证据支撑的原因；
把解释率注得好看易如反掌，但那会毁掉这个工具的意义。

---

## 目录结构

```
reconlens/
  model.py      数据模型 + 证据链
  loader.py     敌意格式解析（会计括号负数、¥ 符号、日/月/年）
  matcher.py    四阶段确定性级联
  explain.py    原因归因（含证据/反证记账）
  report.py     text / markdown / JSON 渲染
  samples.py    覆盖全部阶段与原因的示例
  __main__.py   命令行入口
eval.py         离线断言套件（129 条，含敌意 locale 验证）
AI_CODING_JOURNEY.md   独立的 AI 开发全流程记录（赛事提交材料）
examples/       bank.csv、ledger.csv
```

---

## 设计取舍

**金额统一用整数最小单位（分）。** 浮点无法表示 `0.1`。一个静默消失的半分钱
正是本库存在的理由的反面，因此解析使用 `Decimal` + `ROUND_HALF_UP`——
用 `round()` 会走银行家舍入，把 `0.005` 变成 `0`。

**确定性级联，而非全局最优。** 全局最优分配无法回答「为什么是这一对」。
级联可以：每一对都能说出它命中了哪条规则。

**置信度是推导出来的，不是调出来的。** 公式为 `pro / (pro + con + 1)`，
权重全部来自记录。不做逐案手调，意味着没有任何结果能被悄悄美化。

**`UNEXPLAINED` 是一等公民**，并有断言保证其置信度低于 0.5。

**守恒律被强制。** 两侧都满足「已匹配条目数 + 残余条目数 == 总条目数」。
对账引擎最坏的失败，就是某条记录无声无息地消失。

---

## 验证

```bash
python eval.py
```

129 条断言覆盖：敌意格式下的金额与日期解析、每一个匹配阶段、每一类原因、
证据机制、端到端示例契约、三套渲染、CSV 往返，并**通过子进程在
`LC_ALL=C LANG=C` 且清空 `PYTHONUTF8` 的环境下真实重跑 CLI**，
证明非 UTF-8 控制台无法让工具崩溃。

---

## 作者

由 **支一郎** 构建——一名正在转向智能体工程的 RPA 开发者（影刀 / 来也 UiBot）。
本工具的领域洞察来自手工搭建对账自动化的经历：匹配从来都是容易的那一半。

## 许可

MIT。见 [LICENSE](LICENSE)。
