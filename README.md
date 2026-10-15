# 勿cue (At Reply)

一个 AstrBot 插件：被 @ 时不再走 LLM，而是从预设的回复池里随机抽一句发出去。

- 被 @ 立刻随机回一句，杜绝 LLM 乱答
- 支持群号白名单，非白名单群不干预
- 支持冷却，避免刷屏
- 支持关键词放行，@ 后紧跟关键词时交给 LLM 正常回答
- 支持喷子模式：同一人短时间内反复 @ 会被连续回怼
- 支持引用屏蔽：引用（回复）bot 消息时，可选择屏蔽机器人的思考与回复

---

## 功能特性

| 特性 | 说明 |
|---|---|
| 随机回复 | 被 @ 时从回复池随机抽一条发送 |
| 群白名单 | 只有白名单群生效，其他群正常走 LLM |
| 冷却 | 群内多人共用冷却，冷却期间不再回复，消息放行给 LLM |
| 关键词放行 | @ 后紧跟指定关键词时，交给 LLM 正常处理 |
| 喷子模式 | 同一人窗口内 @ 超过阈值即进入喷子持续期，持续期内每次 @ 都被怼 |
| 阻止 LLM | 命中随机回复或喷子模式时，阻止 LLM 继续处理，避免双重回复 |
| 引用屏蔽 | 用户引用（回复）bot 消息时会误触发唤醒，可用两个独立开关分别屏蔽「未@ bot」和「@ 了 bot」两种情况 |

---

## 安装

1. 把插件目录放到 AstrBot 的 `data/plugins/` 下：
data/plugins/astrbot_plugin_at_reply/
├── main.py
├── _conf_schema.json
├── metadata.yaml
├── README.md
└── README.en.md

text

2. 在 AstrBot 管理面板中重载插件，或重启 AstrBot。
3. 在插件配置页里填入回复池等内容。

---

## 配置项

| 配置键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `reply_pool` | list | `["厉不厉害你机哥"]` | 被 @ 时的随机回复候选列表 |
| `cooldown_seconds` | int | `0` | 群冷却秒数，0 表示无冷却 |
| `whitelist_enabled` | bool | `false` | 是否启用群号白名单 |
| `group_whitelist` | list | `[]` | 白名单群号；启用白名单后只有这些群会触发 |
| `keyword` | string | `""` | 关键词放行，@ 后紧跟此词则交给 LLM |
| `troll_pool` | list | `["你是不是找骂", "再@我试试", "烦不烦"]` | 喷子模式回复池 |
| `troll_window_seconds` | int | `60` | 喷子计数的时间窗口 |
| `troll_threshold` | int | `5` | 触发喷子模式的 @ 次数阈值 |
| `troll_duration_seconds` | int | `120` | 喷子模式持续时长，持续期内每次 @ 都被怼 |
| `block_quote_without_at` | bool | `false` | 屏蔽【引用 bot 消息且未 @ bot】的回复 |
| `block_quote_with_at` | bool | `false` | 屏蔽【引用 bot 消息且 @ 了 bot】的回复 |

---

## 行为说明

### 触发流程

0. **引用屏蔽检查**（新增）：若本条消息引用了 bot 自己发送的消息，按下面规则处理：
   - 回复里**没有 @ bot**：`block_quote_without_at` 开启 → 直接屏蔽；关闭 → 放行给 LLM（保持原行为）。
   - 回复里**@ 了 bot**：`block_quote_with_at` 开启 → 直接屏蔽；关闭 → 继续走下面第 1 步。
   - 「屏蔽」= 既不思考也不回复（`should_call_llm(False)` + `stop_event()`）。
1. 检查消息是否 @ 了机器人。不是则忽略。
2. 若启用白名单，且当前群不在白名单内 → 放行给 LLM。
3. 若处于群冷却中 → 忽略（不回复也不拦截）。
4. 若配置了关键词，且 @ 后紧跟该关键词 → 放行给 LLM。
5. 判断喷子模式：
- 若该用户处于喷子持续期内 → 直接喷。
- 若窗口内 @ 次数达到阈值 → 进入持续期并喷一次。
6. 否则从回复池随机抽一条发送，并更新群冷却。

### 关于冷却

- 冷却按**群**计算，同一群内多人共用。
- 冷却期间收到 @，插件**不做任何操作**，消息会正常走 LLM。
- 这样避免了刷屏时机器人的回复被完全吞掉。

### 关于引用（回复）屏蔽

AstrBot 核心逻辑里，只要用户**引用了 bot 自己发送的消息**，就会被判定为唤醒（`is_wake = True`），随后交给 LLM 处理——即使这条消息里根本没有 @ bot。这会导致「随手回一句 bot 的话」也被当成提问。

本插件提供两个**互相独立**的开关来屏蔽这种情况：

| 开关 | 生效条件 | 效果 |
|---|---|---|
| `block_quote_without_at` | 引用了 bot 消息，且回复里**没有** @ bot | 屏蔽（不思考、不回复） |
| `block_quote_with_at` | 引用了 bot 消息，且回复里**@ 了** bot | 屏蔽（不思考、不回复） |

说明：

- 两个开关都**默认关闭**，此时插件行为与原版完全一致。
- 判定「引用了 bot 消息」与 AstrBot 核心一致：消息链中存在 `Reply` 组件且其 `sender_id` 等于机器人自身 ID。
- 判定「@ 了 bot」只看**本条消息自身**的 @ 段，不会误判被引用消息里的 @。
- 关闭 `block_quote_with_at` 时，引用 + @ bot 依旧走正常的随机回复 / 喷子模式流程。
- 只想彻底解决「引用 bot 就被回复」的问题，把 `block_quote_without_at` 打开即可。

### 关于喷子模式

- 计数以 `(群号, 用户号)` 为单位，窗口内独立累计。
- 一旦触发，清空历史计数，并进入 `troll_duration_seconds` 秒的持续期。
- 持续期内该用户的**每一次** @ 都会触发一条喷子回复。
- 持续期结束后重新累计，需要再次达到阈值才会再触发。
- 把 `troll_duration_seconds` 设为 `0` 表示触发一次只喷一次。

---

## 使用示例

### 最小配置

| 配置项 | 值 |
|---|---|
| `reply_pool` | `厉不厉害你机哥`、`又要我出手？`、`叫机哥干嘛` |
| `cooldown_seconds` | `10` |
| `whitelist_enabled` | `true` |
| `group_whitelist` | `123456789` |

效果：只有在群 `123456789` 里 @ 机器人时，才会从三条回复里随机发一条，且 10 秒内不会重复回复。

### 关键词放行

| 配置项 | 值 |
|---|---|
| `keyword` | `问` |

效果：发送「@机器人 问 今天天气」→ 交给 LLM 正常回答；发送「@机器人 你好」→ 走随机回复。

### 喷子模式

| 配置项 | 值 |
|---|---|
| `troll_threshold` | `5` |
| `troll_window_seconds` | `60` |
| `troll_duration_seconds` | `120` |
| `troll_pool` | `你是不是找骂`、`再@我试试`、`烦不烦` |

效果：同一人在 60 秒内 @ 机器人 5 次 → 触发喷子，之后 120 秒内该人每次 @ 都会被连续回怼。

### 引用屏蔽

| 配置项 | 值 |
|---|---|
| `block_quote_without_at` | `true` |
| `block_quote_with_at` | `false` |

效果：引用（回复）bot 的消息但没 @ 它 → bot 不理你；引用 bot 消息并 @ 了它 → 仍按上面的随机回复 / 喷子模式处理。

---

## 目录结构
astrbot_plugin_at_reply/
├── main.py # 插件主逻辑
├── _conf_schema.json # WebUI 配置 schema
├── metadata.yaml # 插件元信息
├── README.md # 中文说明
└── README.en.md # English README

text

---

## 升级与配置备份（重要）

> ⚠️ **升级 / 重装本插件前，请先备份配置文件，否则 WebUI 里配过的回复词、白名单等会全部变回默认值。**

插件在 WebUI 里保存的配置**不存在插件目录里**，而是由 AstrBot 统一存放在：

```
<AstrBot 数据目录>/config/astrbot_plugin_at_reply_config.json
```

数据目录按以下顺序确定（见 AstrBot `astrbot_path.py`）：

1. 环境变量 `ASTRBOT_ROOT` → `$ASTRBOT_ROOT/data`
2. 否则 `~/.astrbot/data`
3. 否则 `当前工作目录/data`

Docker 部署通常是 `/AstrBot/data/config/astrbot_plugin_at_reply_config.json`。

### 配置在什么情况下会丢

AstrBot 只在少数场景下会删除该文件，之后重新加载插件时会用 schema 默认值重建：

- 在面板**卸载插件**时勾选了「同时删除配置」；
- 插件**安装失败**被清理时（日志会打印 `Removed configuration for the failed plugin installation`）；
- **卸载后重新安装**（相当于全新安装，配置从默认值重建）。

注意：**只是"重载插件"或"覆盖更新插件目录"不会丢配置**；单纯修改 `_conf_schema.json` 新增配置项也不会丢——AstrBot 会把旧值原样保留，只补上新键的默认值。

### 推荐的升级方式（不会丢配置）

1. 先备份：把 `config/astrbot_plugin_at_reply_config.json` 复制一份；
2. 直接把新版本文件**覆盖**到插件目录（`data/plugins/astrbot_plugin_at_reply/`）；
3. 在 AstrBot 面板点「重载插件」。

**不要"卸载 → 重新安装"**，那样配置会没。

### 恢复办法

- AstrBot 的备份目录为 `<AstrBot 数据目录>/backups/`，若之前做过备份，可从里面取回 `config/astrbot_plugin_at_reply_config.json`；
- 没有备份就只能在 WebUI 里重新填一次。

---

## 常见问题

**Q: 配置后 LLM 仍然回复了？**

1. 确认插件使用 `priority=maxsize` 注册，保证在 LLM 请求前执行。
2. 确认 AstrBot 版本 ≥ v3.4.31，`should_call_llm` 才可用。
3. 查看日志中是否出现 `[AtReply] 检测到@机器人` 和 `[AtReply] 回复已发送`。

**Q: 想让机器人只回随机话术，彻底不接 LLM？**

默认行为就是这样：命中随机回复或喷子模式后都会调用 `event.should_call_llm(False)` 和 `event.stop_event()`，LLM 不会介入。

**Q: 想让某些群完全不受插件影响？**

把 `whitelist_enabled` 设为 `true`，并把这些群排除在 `group_whitelist` 之外即可。

**Q: 喷子模式会一直喷下去吗？**

不会。持续期结束后自动失效，需重新累计达到阈值才会再次触发。

**Q: 只是引用了 bot 的一句话，没 @ 它，为什么它还是会思考并回复？**

这是 AstrBot 的默认行为：引用 bot 消息会被判定为唤醒。把本插件的 `block_quote_without_at` 打开即可屏蔽（想连「引用 + @ bot」一起屏蔽，再打开 `block_quote_with_at`）。

**Q: 更新插件后，之前配好的回复词变回默认值了？**

配置由 AstrBot 存在 `<数据目录>/config/astrbot_plugin_at_reply_config.json`，不在插件目录内。只有当该文件被删除（卸载勾选删配置 / 卸载重装 / 安装失败清理）时，重载才会用默认值重建，看起来就是「配置没了」。详见上文「升级与配置备份」。

---

## 许可

MIT License。