# 魔兽世界：无限的当前游戏数据

`addons/WhaleBridge` 是独立的游戏内 Lua 插件。它用公开 API 读取非战斗状态，
通过屏幕左上角的小型彩色数据面板单向输出。鲸鱼娘在原始 Quartz 截屏上解码，
再把快照附到已有文字或看屏请求，进入同一个 DSH 会话和 compact。没有第二套记忆，
也不启动另一个 agent。攻略查询仍使用已有的无限图鉴 MCP。

## 本机安装

```bash
.venv/bin/python scripts/install-wow.py
```

默认客户端为 `/Applications/World of Warcraft/_forever_`。首次新增插件后，
完全退出并重新启动游戏，在插件列表启用 **Whale Bridge**。之后照常启动 `dsh web`。
游戏窗口及左上角彩色面板必须可见，桌宠需要屏幕录制权限。输入 `/whale off`
隐藏并停用输出，`/whale on` 恢复。移除客户端 `Interface/AddOns/WhaleBridge`
即可卸载；不修改其他插件、账号设置或存档。

## 数据与行为

插件每秒更新一次区域、子区域、UI 地图 ID、坐标、等级/职业、任务 ID 与完成状态、
选中任务及其目标文字、目标 NPC ID/名称。没有账号、角色名、聊天、背包或战斗数值。
任务资料过长时先省略目标文字，再减少任务条目，并标记 `truncated`；缺失不代表没有。
选中任务不自动等于用户意图，客户端 UI 地图 ID 也不等于攻略库的区域 ID。

战斗中仅传版本、采样时间和战斗标记，不读取或输出任务、位置和目标。
secret 值直接省略，不转换成普通数据。API 失败会发出错误状态。
解码失败、遮挡、游戏最小化或快照超过 5 秒时没有当前快照；不会沿用旧坐标。
文字发送时会额外尝试读取一次当前可见面板，即使自动陪看已暂停；不会向模型附加
这次读取的整屏图片。已接收的数据随 DSH 原生会话保存，不能承诺退出即删除历史。

自动采样在任务列表/完成状态、选中任务、UI 地图发生变化时，可以用一张当前画面
触发观察，不必凑九张。首次连接只建立基线，移动坐标与切换目标 NPC 不单独触发，
仍遵守暂停和既有最小发送间隔。其他画面继续走原来的差分九图。
触发观察不保证开口，模型仍可返回空串。自动轮维持零工具权限；文字轮才能查询攻略。

## 线路与验证

`Protocol.lua` 定义 `WGB1`：14 字节头（magic、big-endian uint16 UTF-8 JSON 长度、
uint32 sequence、uint32 Adler-32）后接 JSON，最多 1400 字节。
面板 64×32 格，每格 4 个 UI 物理像素；前 8 格定位，64 格完整颜色查表校准，
其余每格 RGB 各 2 bit。完整查表也处理 macOS 颜色管理造成的跨通道变换，
灰阶校准不能覆盖这种情况。不是所有 HDR、缩放和遮挡
组合都已验证。`app/game.py` 必须在缩放/JPEG/九图拼接之前读取它。

```bash
uv run --no-sync --with lupa==2.6 python tests/smoke_wow_wire.py --capture
```

该检查执行实际 Lua producer，用合成 API 验证中文转义、NPC ID、坐标、secret 省略、
战斗清空，再把数据面板绘制成独立 Cocoa 窗口，验证真实 Quartz 回读。
这不替代客户端内验证：安装后要确认插件加载、非战斗区域和任务变化、进入战斗、
遮挡面板和切换窗口的实际表现。目标本机客户端为 1.60.1.70862，TOC 16001。

## 参考

- [Tensor-wow](https://github.com/robeson1010/Tensor-wow)：Forever 上像素单向输出与 macOS 截屏的可行路径；没有采用其 CLI、返程槽位或宏生成机制，也未复制代码。
- [Forever addon kit](https://github.com/Thunderz96/forever-addon-kit)：Forever 使用现代 API、secret 限制和 TOC 的实测记录。
- [客户端 API 源码镜像](https://github.com/Gethe/wow-ui-source/tree/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated)：C_Map、C_QuestLog、Unit 接口契约。

这是游戏 Lua 沙箱内读取和屏幕回读，不代表 Blizzard 对外部数据桥作出了许可保证。
不读取进程内存、不注入客户端、不自动按键，也不绕过受保护接口。
