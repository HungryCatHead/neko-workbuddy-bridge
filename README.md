# WorkBuddy Bridge for N.E.K.O.（猫娘计划）

让 AI 桌宠「猫娘计划（Project N.E.K.O.）」把需要动手的活交给 [WorkBuddy](https://www.workbuddy.cn) 真正去做——查资料、写文档、做表格/PPT、写代码、分析数据。猫娘负责对话与调度，WorkBuddy 负责执行，成果再送回猫娘嘴里念给你听。

> **设计定位**：给一个擅长提供情绪价值的前端（AI 桌宠），配一个能真正干活的后端（WorkBuddy），专门接**不着急、可异步**的任务。正因为不强求实时，这套桥用「定时轮询 + 文件队列」就够，换来零服务、零网络、可整体搬走；代价是分钟到小时级的响应延迟，不适合要秒回的场景。

- 本项目的插件代码、排障、打包与文档，由 **WorkBuddy** 在一次对话中独立完成——一次「AI 给自己造手」的实践：从读懂宿主随包附带的示例插件，到写出自己的插件，再到把自己打包、安装、设成开机自启。

## 它怎么工作

```
你在猫娘对话框说话
      ↓  猫娘调用 delegate_to_workbuddy
queue/inbox/<task_id>.json         ← 插件写入（插件目录内，自包含）
      ↓  WorkBuddy 定时轮询领取
queue/outbox/<task_id>.json        ← 执行完写回成果
      ↓  猫娘调用 check_workbuddy_results
她念出成果 → 成果归档到 processed/results/
```

- **零服务、零端口、零网络**：两边只靠一个文件夹通信。
- **零配置**：队列默认就在插件自己目录下的 `queue/`，搬到哪跟到哪。
- **可覆盖**：环境变量 `WORKBUDDY_BRIDGE_ROOT` > `plugin.toml` 的 `[bridge].root` > 插件目录 `queue/`。

> 早期试过一版 HTTP 回调方案，因为需要常驻服务、宿主重启即丢注册、还会和插件重复挂出同名工具，最终重构为纯文件队列。仓库里不保留那部分实现。

## 插件

| 项 | 值 |
|---|---|
| id | `workbuddy_bridge` |
| 版本 | 0.1.0 |
| SDK | `>=0.1.0,<0.3.0`（推荐 `>=0.1.0,<0.2.0`） |
| 对话工具 | `delegate_to_workbuddy(task, priority)`、`check_workbuddy_results()` |
| 手动入口 | `delegate`、`fetch_results`、`bridge_status` |

## 安装

1. 从 [Releases](../../releases) 下载 `workbuddy_bridge.neko-plugin`（若还没发布，按第 4 条自行打包）
2. N.E.K.O. → 插件管理 → **导入插件包** → 选刚下载的文件
3. 启动后进入插件详情 → Entries → **桥接状态**，看到 `root` 指向 `.../queue`、`channel=file` 即成功
4. **从源码自行打包**：把 `workbuddy_bridge/` 放进 N.E.K.O. 的插件目录，用插件管理器的「打包」功能生成 `.neko-plugin`

> 安装包不进版本库：它每次 build 都会变，留在仓库里会污染历史，也容易和源码不一致。

> 用开发模式（加载未打包插件）也能跑，但 **N.E.K.O. 不允许开发态插件自动启动**，每次都要手点 Start。想要开机自启请走导入安装包这条路。

## 配套：WorkBuddy 侧需要什么

插件本身**不执行任务**，需要一个消费 `inbox/` 的执行端。本项目的做法是在 WorkBuddy 里建一个定时自动化，prompt 要点：

1. 扫描 `queue/inbox/*.json`，只处理 `status == "pending"`
2. 把 `task` 字段当真实任务执行，产出放 `queue/artifacts/`
3. 按约定结构原子写 `queue/outbox/<task_id>.json`
4. 原任务移到 `queue/processed/tasks/`
5. 处理完发现还有新任务，就自建一个 1 分钟后的续跑

👉 **完整 prompt 与创建步骤见 [WorkBuddy自动化配置.md](WorkBuddy自动化配置.md)**（可直接照抄）。不配这一条，插件照样派活，但没人执行。

成果 JSON 结构：

```json
{
  "version": 1,
  "task_id": "tsk_xxx",
  "status": "done",
  "task": "原任务描述",
  "result": "给人看的成果正文",
  "artifacts": ["产出文件绝对路径"],
  "handled_by": "WorkBuddy",
  "finished_at": "2026-11-16T11:00:00+08:00"
}
```

## 目录结构

```
README.md                         ← 你在这里：项目是什么、怎么装、有问题看哪份文件
LICENSE                           MIT
NOTICE.md                         上游许可、本项目用到的能力范围、商标与数据说明

总说明.md                         架构全貌 + 运维模式 + 注意事项 + 故障排查
WorkBuddy自动化配置.md            执行端必读：轮询器的完整 prompt 与创建步骤
WorkBuddy模型说明.md              WorkBuddy 侧：内置模型清单、自定义模型边界、订阅与积分
WorkBuddy外部模型接入指南.md      换模型：接云端中转 / 本地 Ollama 的配置与硬件建议

workbuddy_bridge/                 ← 插件本体，装插件只需要这个目录
  __init__.py                     插件实现：2 个生命周期钩子 + 3 个手动入口 + 2 个对话工具
  plugin.toml                     插件清单：id / 版本 / 入口点 / SDK 版本约束 / 作者与许可
  config.example.toml             配置样例（队列路径、轮询参数），复制到用户配置目录后生效
  README.md                       插件自身的说明（给只想装插件、不关心仓库结构的人）

docs/
  设计决策与已知问题记录.md       技术留档：为什么这么设计、踩过哪些坑（开发向，非使用文档）
```

### 该看哪个文件

| 你的目的 | 看这里 |
|---|---|
| 先搞清楚这东西是干嘛的 | 本文件（前两节） |
| 装插件 | 本文件的「安装」+ `workbuddy_bridge/README.md` |
| 装完没人干活 / 换机器重建 | `WorkBuddy自动化配置.md` ← **最容易漏的一步** |
| 队列在哪、怎么自启、出问题怎么查 | `总说明.md` |
| 想换个模型跑（云端或本地） | `WorkBuddy外部模型接入指南.md` |
| 想了解 WorkBuddy 有哪些模型、怎么计费 | `WorkBuddy模型说明.md` |
| 想改代码 / 二次开发 | `workbuddy_bridge/__init__.py` + `docs/设计决策与已知问题记录.md` |
| 关心许可、合规、商标 | `NOTICE.md` + `LICENSE` |

## 已知限制

- **不是秒级响应**：执行端靠定时轮询领活，平台的**最小调度粒度是 1 小时**——队列里没活时，新任务最长要等约 1 小时才被领走；一旦某一轮领到了活，会自动续跑、1 分钟一轮很快清空。调度规则里写 `BYMINUTE` 想压到每几分钟**没用**（平台会存下配置但调度器忽略），实测细节见 [WorkBuddy自动化配置.md](WorkBuddy自动化配置.md) 第一节。
- 成果**读走即归档**：`check_workbuddy_results` 调用一次后，同一份成果再问就没了。
- 猫娘可能"脑补完成"：没查成果就说做完了。验真办法是让她复述成果里的具体细节。
- 重装插件会覆盖插件目录，**装前请确认 `queue/inbox/` 为空**。
- 轮询器**空跑也消耗积分**（量小，但一小时一轮会累积），且必须开**完全访问权限**才能无人值守跑。两件事的量级、边界与护栏见 [WorkBuddy自动化配置.md](WorkBuddy自动化配置.md) 第六、七节。
- **它对任务描述的质量很敏感**：这条链路上有两次自然语言理解（你说的 → 猫娘压成任务 → 执行端理解），写得太模糊就会被"合理补全"。派活模板与止损办法见同一文档第八节。

实现细节、架构取舍与已知坑见 [docs/设计决策与已知问题记录.md](docs/设计决策与已知问题记录.md)。

## 许可与声明

本项目代码以 **MIT** 发布，见 [LICENSE](LICENSE)。

- **非官方作品**：第三方独立开发，与 Project N.E.K.O. 项目方无隶属、赞助或背书关系。
- **不含第三方代码**：仓库内只有本项目自己的代码，未复制或打包宿主源码；N.E.K.O. 本体采用 [Apache-2.0](https://github.com/Project-N-E-K-O/N.E.K.O) 许可。
- **名称使用**："N.E.K.O."、"猫娘计划" 等名称仅用于说明兼容对象，权利归其各自所有者。

完整的能力范围界定、商标与数据说明、异议联络方式见 [NOTICE.md](NOTICE.md)。

## Credits

- 感谢 [Project N.E.K.O.](https://github.com/Project-N-E-K-O/N.E.K.O) 提供插件 SDK 与公开的插件管理流程。
- **特别感谢 WorkBuddy 在架构设计、代码实现和文档编写上的贡献。** 本项目的插件代码、排障、打包与文档均由其在一次对话中独立完成。
