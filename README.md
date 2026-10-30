# OriginPro MCP × Qoder 接入

让 Qoder Desktop 通过 MCP 控制本机 OriginLab OriginPro。MCP 服务本身使用 [youngminsw/Origin-Pro-MCP](https://github.com/youngminsw/Origin-Pro-MCP)（MIT）；本仓库只保存 Qoder 侧的接入配置、安装/探活脚本和实测说明。

链路：

```
Qoder Desktop → stdio MCP (origin-pro) → Origin COM Automation → OriginPro
```

## 实测环境

| 项 | 版本 |
| --- | --- |
| OS | Windows 10/11 x64 |
| Origin | OriginPro 2021（`Origin64.exe`） |
| uv | 0.12.10 |
| origin-pro-mcp | 0.3.1（commit `1e9741af`） |
| MCP SDK | `mcp` 1.30.0（钉 `<2`） |
| Qoder | Desktop，用户级 MCP |

已验证：MCP 握手、`tools/list`（45 个工具）、独立实例 `list_worksheets` 返回正常。

前置条件：Windows x64、OriginPro 2020+（实测 2021）、uv（会自带 Python）、Git（uv 从 GitHub 安装时需要）。

## 快速开始

### 1. 安装 uv

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 安装 MCP 服务（固定版本）

```powershell
uv tool install "git+https://github.com/youngminsw/Origin-Pro-MCP.git@1e9741af96c45bcac9e619c3ba32264bac6950e7" --with "mcp<2" --force
```

必须钉 `mcp<2`。`mcp` 2.x 移除了 `FastMCP`，直接装最新版会在启动时报：

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

也不要用 PyPI 上的 `origin-pro-mcp`：目前 PyPI 只有 0.1.0，落后于 GitHub `main`。

确认可执行文件：

```powershell
Get-Command origin-pro-mcp
```

### 3. 注册到 Qoder

编辑 `%USERPROFILE%\.qoder-cn\settings.json`，在 `mcpServers` 下加入：

```json
"origin-pro": {
  "command": "C:\\Users\\<你>\\.local\\bin\\origin-pro-mcp.exe",
  "args": [],
  "env": {
    "ORIGIN_PRO_MCP_USE_DAEMON": "1",
    "ORIGIN_PRO_MCP_ATTACH": "0"
  }
}
```

`command` 用绝对路径，避免 Qoder 继承不到 PATH。保存后重启 Qoder 或新开一个会话；MCP 工具在会话启动时加载，旧会话里不会出现。

## 两种实例模式

| 模式 | env | 行为 |
| --- | --- | --- |
| 独立实例（默认） | `USE_DAEMON=1`、`ATTACH=0` | 第一次工具调用拉起自己的 Origin 窗口，不碰你手动打开的项目 |
| 附着现有窗口 | `USE_DAEMON=1`、`ATTACH=1` | 接管已打开的 Origin；同一时间只允许一个会话附着，且禁用自动保存/强制回收 |

独立实例在第一次工具调用时打开自己的 Origin 窗口；会话结束后是否保留取决于服务的生命周期设置，残留时手动关闭即可。附着模式请显式保存工程，避免误改。

## 验证

```powershell
python scripts/probe_mcp.py --daemon --call list_worksheets
```

预期输出（节选）：

```
INIT: origin-pro 1.30.0
TOOL COUNT: 45
TOOLS: run_labtalk, get_labtalk_variable, create_worksheet, ...
CALL: {"workbooks": [], "graphs": [], "matrices": []}
```

`--daemon` 会在第一次工具调用时打开一个 Origin 窗口；探活脚本不会自动关闭它，也不会停止后台 daemon。需要清理时结束 `Origin64.exe` 和 `python.exe -m origin_pro_mcp.daemon`。

`--attach` 只用于已经手动打开 Origin 的情况：

```powershell
python scripts/probe_mcp.py --attach --call list_worksheets
```

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `No module named 'mcp.server.fastmcp'` | 装了 `mcp` 2.x；按上面的命令重装，并带 `--with "mcp<2"` |
| `Could not connect to Origin via COM` | Origin 未安装或未授权；先手动启动一次 Origin，确认 `Origin.ApplicationSI` 可用 |
| `GetActiveObject` 报 `MK_E_UNAVAILABLE` | 运行对象表（ROT）里没有实例；改用 `Dispatch("Origin.ApplicationSI")`，不要用 `GetActiveObject` 判断存活 |
| 第一次调用后多了一个 Origin 窗口 | 独立实例模式的预期行为；保存后关闭即可 |
| Qoder 里看不到工具 | 新开一个会话；MCP 工具在会话启动时加载 |
| 会话结束仍有 Origin 窗口 | detach 设计可能保留工程；手动关闭，或设置 `ORIGIN_PRO_MCP_REAP_CLOSE=1` |

## 切换模式

把 `ORIGIN_PRO_MCP_ATTACH` 改为 `1`（附着）或 `0`（独立），重启会话即可，无需改代码。

## 卸载

```powershell
uv tool uninstall origin-pro-mcp
```

再从 `settings.json` 中删除 `origin-pro` 条目。

## 许可与来源

本仓库的配置、脚本与文字为 MIT。MCP 服务来自 [youngminsw/Origin-Pro-MCP](https://github.com/youngminsw/Origin-Pro-MCP)（MIT），版权归原作者。本项目与 OriginLab 无关联。
