# WorkBuddy Bridge（猫娘计划 / N.E.K.O. 插件）

> **本插件由 WorkBuddy 自主完成制作。**

让猫娘把 WorkBuddy 当成自己的"手"：遇到需要真正动手的活，就写进队列；WorkBuddy 定时领走、真去执行，再把成果送回来。

## 队列放在哪（自包含，不依赖任何工作区路径）

默认就在**本插件自己所在目录下的 `queue/`**：

```
workbuddy_bridge/
├── __init__.py
├── plugin.toml
└── queue/              ← 首次启动自动创建
    ├── inbox/          猫娘写任务
    ├── outbox/         WorkBuddy 写成果
    ├── processed/      归档
    └── artifacts/      产出文件
```

好处：插件搬到哪队列就跟到哪；清理 WorkBuddy 的历史对话/工作区不会误伤；别人拿到插件零配置就能跑。

**覆盖优先级**：环境变量 `WORKBUDDY_BRIDGE_ROOT` > `plugin.toml` 的 `[bridge] root` > 插件目录下 `queue/`。

> ⚠️ 若队列留在插件目录内，**重新打包安装插件前请先确认 `queue/inbox/` 已空**，避免未处理任务被覆盖。

## 安装

1. 打开 N.E.K.O. → 插件管理 → **导入插件包**，选择 `workbuddy_bridge.neko-plugin`（**从仓库 Releases 下载**；正式安装可自动启动）。
2. 或在开发模式下 **Plugin studio → Add existing project** 选中本目录（开发模式插件**不能自动启动**，每次要手点 Start）。
3. 启动后在插件详情 → Entries 里点 **桥接状态**，看到 `root` 指向 `.../queue` 且 `channel=file` 即成功。

## 配置

```toml
[bridge]
# 留空 = 使用插件目录下的 queue/（推荐）
root = ""
channel = "file"
```

- `root`：猫娘与 WorkBuddy 共享的队列目录，双方都要能读写。
- `channel`：当前**只实现了 `file`**（零配置默认通道）。`email` 是早期设想，**代码里没有实现**，填了也仍走文件队列——留着字段只是为将来扩展。

## 使用

装好后正常和猫娘聊天即可。当她说"我把这件事交给 WorkBuddy 去办"，就说明工具触发了。你也可以直接说："猫娘，帮我做一份 XX 的分析报告"——只要任务需要动手，她就会调用 `delegate_to_workbuddy`。

想知道结果：问她"WorkBuddy 做好了没？"，她会调用 `check_workbuddy_results` 把成果念给你听（**读走即归档，同一份只能读一次**）。

## 工具说明

| 类型 | 名称 | 说明 |
|---|---|---|
| 对话工具 | `delegate_to_workbuddy(task, priority)` | 猫娘的 LLM 自动调用，写一个待办任务到 `inbox/` |
| 对话工具 | `check_workbuddy_results()` | 读 `outbox/` 成果并归档到 `processed/results/` |
| 手动入口 | `delegate` / `fetch_results` / `bridge_status` | Plugin Manager → Entries，用于测试排障 |

## 依赖

- N.E.K.O. 插件 SDK `>=0.1.0,<0.3.0`
- 需要一个外部执行端（WorkBuddy 侧的定时轮询自动化）来消费 `inbox/`——**插件本身不执行任务**。
