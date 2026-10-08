---
name: openlist-mcp-setup
description: 把 OpenList MCP 服务器接入 DSH 或其他 MCP 客户端时的安装与档位选择流程。当用户要求"接入/安装/配置 OpenList MCP"、"把 openlist 挂到 agent 上"、"openlist 工具太多/太少"、"改 openlist 的工具档位"或用英文说 install/configure the OpenList MCP server 时使用。核心要求:安装前必须让用户选档位,不要替他默认。
---

# 接入 OpenList MCP 服务器(含档位选择)

## 为什么必须先让用户选档位

工具 schema 是**每一步模型请求都要常驻**的上下文成本,不同档位差 3 倍以上:

| 档位 | 工具数 | ≈常驻 tokens/步 | 含哪些组 |
|---|---|---|---|
| `core` | 30 | ~4.4k | auth, fs, transfer |
| `default` | 49 | ~6.5k | core + task, share |
| `all` | 110 | **~14.7k** | 全部 + admin, advanced |
| 自定义 | 任意 | 按组计 | 7 个组任意组合 |

组明细(`SKILL_GROUP_TOOLS`):`auth` 6、`fs` 16、`transfer` 8、`task` 11、`share` 8、`admin` 42、`advanced` 16。

**不要替用户决定档位**,也不要因为"测试套件期望 110"就默认 `all` —— 那会让用户每次对话都多付约 1 万 tokens。

## 步骤

### 1. 确认连接信息

需要 `OPENLIST_URL`、`OPENLIST_USERNAME`、`OPENLIST_PASSWORD`。缺哪个就问哪个,不要猜。若地址是 `http://`(常见于内网),还要记得带上 `OPENLIST_ALLOW_HTTP=true`,否则服务端会拒绝启动。

### 2. 让用户选档位(必做)

用 `ask_user_question` 弹出选项,推荐项放第一个并标注"(推荐)":

- **`default` — 49 个工具(~6.5k tokens/步)(推荐)**:在 core 之上补 `task` 与 `share`。选它因为 `fs/copy`、`fs/move`、`fs/archive/decompress` 都是**异步任务**,没有 `task` 组就无法确认操作是否真的完成。
- **`core` — 30 个工具(~4.4k tokens/步)**:只浏览/上传下载/搜索,最省。代价是失去任务与分享。
- **`all` — 110 个工具(~14.7k tokens/步)**:含 `admin`(存储/用户/设置/元数据)与 `advanced`(压缩包/种子)。仅当确实要做服务器管理时选。
- **自定义**:按组拼,例如 `fs,transfer,share`(告诉用户可用的 7 个组名)。

### 3. 按选择安装

**DSH**(面板托管,HMR 热加载,无需重启):

```bash
dsh-panel mcp add --name openlist --stdio \
  --command <openlist-mcp-server>/.venv/bin/python \
  --args -m --args openlist_mcp.server \
  --env OPENLIST_URL=... \
  --env OPENLIST_USERNAME=... \
  --env OPENLIST_PASSWORD=... \
  --env OPENLIST_ALLOW_HTTP=true \
  --env OPENLIST_SKILLS=<档位> \
  --profile web
```

`openlist-mcp-server` 是本项目 checkout 的路径。配置写入 profile 的 `cordis.patch.yml` 受管块(`dsh-skill-mcp-panel:mcp:begin` / `:end` 之间),**块内不要手改** —— 改档位用下面第 5 步的方式。

**其他 MCP 客户端**(Claude Desktop / Codex 等):把同样的键写进其配置的 `mcpServers.openlist.env`。档位同样生效。

### 4. 验证档位真的生效

不要假设装完就对。核对**实际暴露的工具数**是否等于所选档位:

| 档位 | 期望工具数 |
|---|---|
| core | 30 |
| default | 49 |
| all | 110 |

- DSH:看该会话可见的 `mcp__openlist__*` 工具数量;或调一个**不属于该档位**的工具(如 `core`/`default` 下不存在 `list_storages`),应报 `unknown tool`。
- 通用:服务器的启动日志会打印 `Skills: preset=<档位>, groups=..., total=<N> tools`。
- MCP 客户端也可 `list_tools` 后计数。

**数量不符 = `OPENLIST_SKILLS` 没生效**,先查 env 是否写进了正确的位置,再查是否有多个 openlist 服务器条目在同时注册工具。

### 5. 之后改档位

改 `env.OPENLIST_SKILLS` 的值即可,DSH 的 HMR 会热重载该行并重启服务器进程:

```bash
dsh-panel mcp remove openlist --yes --profile web   # 或直接在面板 UI 里编辑 env
dsh-panel mcp add ... --env OPENLIST_SKILLS=<新档位> ...
```

改完回到第 4 步重新验证。**别只改受管块的 YAML 就当完成** —— 用面板自己的读写路径改,格式才不会被写坏。

## 常见坑

- **忘了 `OPENLIST_ALLOW_HTTP=true`**:内网 `http://` 地址会被服务端主动拒绝(默认不允许明文 HTTP),表现为启动即失败。
- **`admin` 组的确认门禁**:所有写操作需要 `confirm=true`,这不是 bug,是设计。
- **`delete_meta` / `delete_setting` 的参数位置**:这两个端点的 id/key 读的是 **query string**,不是 JSON body —— 自己拼请求时别放错位置。
- **升级档位后工具数没变**:多为配置写到了另一个 profile,或该客户端有自己的 env 覆盖。
