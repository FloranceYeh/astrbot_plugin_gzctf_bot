<div align="center">
  <img src="logo.svg" width="128" height="128" alt="AstrBot GZCTF Bot"/>
  <h1>AstrBot GZCTF Bot</h1>
</div>

用于查询 GZCTF 赛事数据、执行赛事管理操作，并将新公告和作弊记录推送到 QQ 群。

## 功能

- 查询赛事列表、状态和访问链接
- 查询总排行榜、队伍排名、题目列表和队伍信息
- 解锁或封禁队伍
- 开启/关闭公告播报和自动封禁
- 开放/关闭题目，添加赛事公告和题目提示
- 后台定时轮询 GZCTF 公告与作弊信息

## 安装

1. 将本目录放入 AstrBot 的插件目录。
2. 在 AstrBot 插件管理页面安装依赖，或执行 `pip install -r requirements.txt`。
3. 启用插件并填写配置。
4. 重启 AstrBot，使配置和后台轮询任务生效。

插件需要能够访问 GZCTF 面板。管理类接口需要填写具有相应权限的 GZCTF 账号；仅查询时也建议填写账号，以避免接口权限不足。

## 配置

| 字段 | 说明 |
| --- | --- |
| `gzctf_url` | GZCTF 面板地址，例如 `https://ctf.example.com`，不要以 `/` 结尾也可以正常工作 |
| `gz_user` | GZCTF 管理员用户名 |
| `gz_pass` | GZCTF 管理员密码 |
| `send_list` | 接收播报的 QQ 群号数组，例如 `["123456789"]` |
| `game_list` | 要监听的赛事名称数组；留空表示监听全部赛事 |
| `poll_interval` | 后台轮询间隔，单位为秒，默认 `20`，最小按 `5` 秒执行 |
| `verify_ssl` | 是否校验 HTTPS 证书。生产环境建议保持 `true` |

配置示例：

```json
{
    "gzctf_url": "https://ctf.example.com",
    "gz_user": "admin",
    "gz_pass": "change-me",
    "send_list": ["123456789"],
    "game_list": ["春季赛"],
    "poll_interval": 20,
    "verify_ssl": true
}
```

## 命令

命令前缀为 `gz`。参数可以使用参考项目兼容的方括号格式，也可以使用普通空格分隔。例如 `gzrank [春季赛]` 和 `gzrank 春季赛` 等价。

### 查询命令

| 命令 | 用法 | 说明 |
| --- | --- | --- |
| `gzhelp` | `gzhelp` | 显示帮助 |
| `gzgame` | `gzgame` | 查看配置范围内的赛事、时间、状态和链接 |
| `gzrank` | `gzrank [赛事名]` | 查看赛事总排行榜前 20 名；不填赛事名时查询所有监听赛事 |
| `gztrank` | `gztrank [队伍名或队伍ID] [赛事名]` | 查询指定队伍排名 |
| `gzq` | `gzq [赛事名] [题目名]` | 查看题目列表；填写题目名时只显示该题目 |
| `gzteam` | `gzteam [队伍名]` | 查看队伍和成员信息 |

### 管理命令

以下命令需要 AstrBot 管理员权限：

| 命令 | 用法 | 说明 |
| --- | --- | --- |
| `gzopen` / `gzclose` | `gzopen` | 开启或关闭后台播报 |
| `gzopenb` / `gzcloseb` | `gzopenb` | 开启或关闭自动封禁作弊队伍 |
| `gzunlock` | `gzunlock [队伍ID]` | 解锁队伍 |
| `gzban` | `gzban [队伍ID]` | 封禁队伍参与资格 |
| `gzqa` | `gzqa [赛事名]` | 以管理视角查看题目列表 |
| `gzopenq` / `gzcloseq` | `gzopenq [赛事名] [题目名]` | 开放或关闭指定题目 |
| `gzaddnotice` | `gzaddnotice [赛事名] [公告内容]` | 添加赛事公告 |
| `gzaddhint` | `gzaddhint [赛事名] [题目名] [提示内容]` | 为题目添加提示 |

## 播报机制

插件启动后台轮询任务，按 `poll_interval` 请求选定赛事的公告和作弊记录。发现新公告时会发送到 `send_list` 中的群；开启 `gzopenb` 后，发现新的作弊记录会尝试封禁提交队伍和 flag 所属队伍，并发送封禁通知。

播报使用 AstrBot 的 `aiocqhttp:GroupMessage:<群号>` 会话格式，因此需要使用支持群消息发送的 QQ 平台适配器。

## 注意事项

- `game_list` 按赛事标题精确匹配，标题变更后需要同步修改配置。
- 插件只保存运行期间已见过的公告和作弊记录，重启后会重新建立基线，不会补发历史记录。
- `gzban` 和自动封禁属于高风险管理操作，请确认 GZCTF 账号权限及 API 行为后再启用。
- 如果使用自签名 HTTPS 证书，可临时将 `verify_ssl` 设置为 `false`，但不建议长期关闭证书校验。
- 网络错误会记录到 AstrBot 日志，后台轮询会在下一周期自动重试。

## 鸣谢

感谢 [MoRan23](https://github.com/MoRan23) 的 [GZCTF-BOT-QQ](https://github.com/MoRan23/GZCTF-BOT-QQ) 项目，本插件的开发借鉴了该项目的许多设计和实现思路。

## 许可证

本项目遵循上游 [GZCTF-BOT-QQ](https://github.com/MoRan23/GZCTF-BOT-QQ) 项目的 GNU Affero General Public License v3.0（AGPLv3）协议。完整协议文本见 [LICENSE](LICENSE)。
