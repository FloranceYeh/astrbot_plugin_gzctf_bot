from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.star.star_tools import StarTools
from astrbot.api.message_components import Plain


def parse_args(text: str) -> list[str]:
    bracketed = re.findall(r"\[([^\]]*)\]", text)
    return [x.strip() for x in bracketed] if bracketed else text.split()


def fmt_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return str(value)


class GZClient:
    def __init__(self, config: AstrBotConfig):
        self.base = str(config.get("gzctf_url", "")).rstrip("/")
        self.user = str(config.get("gz_user", ""))
        self.password = str(config.get("gz_pass", ""))
        self.verify = bool(config.get("verify_ssl", True))
        self.client = httpx.AsyncClient(verify=self.verify, timeout=15, headers={"Cache-Control": "no-cache"})
        self.logged_in = False

    async def close(self):
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs) -> Any:
        if not self.base:
            raise RuntimeError("尚未配置 gzctf_url")
        response = await self.client.request(method, self.base + path, **kwargs)
        if response.status_code == 401 and not self.logged_in:
            await self.login()
            response = await self.client.request(method, self.base + path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    async def login(self):
        if not self.user or not self.password:
            return
        response = await self.client.post(self.base + "/api/account/login", json={"userName": self.user, "password": self.password})
        response.raise_for_status()
        self.logged_in = True

    async def games(self): return (await self.request("GET", "/api/game")).get("data", [])
    async def game(self, game_id): return await self.request("GET", f"/api/game/{game_id}")
    async def notices(self, game_id): return await self.request("GET", f"/api/game/{game_id}/notices")
    async def cheats(self, game_id): return await self.request("GET", f"/api/game/{game_id}/CheatInfo")
    async def scoreboard(self, game_id): return await self.request("GET", f"/api/game/{game_id}/scoreboard")
    async def challenges(self, game_id): return await self.request("GET", f"/api/edit/games/{game_id}/challenges")
    async def challenge(self, game_id, challenge_id): return await self.request("GET", f"/api/game/{game_id}/challenges/{challenge_id}")
    async def teams(self, game_id): return await self.request("GET", f"/api/game/{game_id}/participations")

    async def put(self, path, **kwargs): return await self.request("PUT", path, **kwargs)
    async def post(self, path, **kwargs): return await self.request("POST", path, **kwargs)


class GZCTFBot(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context, self.config = context, config
        self.client = GZClient(config)
        self.data_dir = StarTools.get_data_dir()
        self.poll_task: asyncio.Task | None = None
        self.broadcast = {str(g): set() for g in config.get("send_list", [])}
        self.enabled = True
        self.ban_enabled = False
        self.last_notices: dict[int, list] = {}
        self.last_cheats: dict[int, list] = {}

    async def initialize(self):
        self.poll_task = asyncio.create_task(self._poll_loop())

    async def terminate(self):
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task, return_exceptions=True)
        await self.client.close()

    async def _selected_games(self):
        games = await self.client.games()
        names = {str(x) for x in self.config.get("game_list", []) if str(x)}
        return [g for g in games if not names or g.get("title") in names]

    async def _reply(self, event, text: str):
        yield event.plain_result(text)

    @filter.command("gzhelp", alias={"gz帮助"})
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result("GZCTF: gzgame gzrank gztrank gzq gzteam gzunlock gzban gzopen gzclose gzopenb gzcloseb gzqa gzopenq gzcloseq gzaddnotice gzaddhint\n参数支持 [方括号]，管理命令需要管理员权限。")

    @filter.command("gzgame")
    async def game_list(self, event: AstrMessageEvent):
        try:
            games = await self._selected_games()
            lines = ["======比赛列表======"]
            now = datetime.now(timezone.utc).timestamp() * 1000
            for game in games:
                start, end = game.get("start"), game.get("end")
                status = "未开始" if start and now < start else ("进行中" if end and now < end else "已结束")
                lines.append(f"{game.get('title')} | {status}\n开始: {fmt_time(start)} 结束: {fmt_time(end)}\n{self.client.base}/games/{game.get('id')}")
            yield event.plain_result("\n".join(lines) if len(lines) > 1 else "暂无赛事")
        except Exception as exc: yield event.plain_result(f"获取赛事失败: {exc}")

    async def _game_arg(self, args: list[str]):
        games = await self._selected_games()
        if args:
            games = [g for g in await self.client.games() if g.get("title") == args[0]]
        return games[0] if games else None

    @filter.command("gzrank")
    async def rank(self, event: AstrMessageEvent):
        try:
            args = parse_args(event.message_str.partition(" ")[2])
            selected = await self._selected_games() if not args else await self._game_arg(args)
            games = selected if isinstance(selected, list) else ([selected] if selected else [])
            out = []
            for game in games:
                board = (await self.client.scoreboard(game["id"])).get("items", [])
                out.append(f"==={game['title']}===")
                out.extend(f"[{x.get('rank')}] | [{x.get('name')}] - {x.get('score')}" for x in board[:20])
            yield event.plain_result("\n".join(out) if out else "未找到赛事或暂无排行榜")
        except Exception as exc: yield event.plain_result(f"获取排行榜失败: {exc}")

    @filter.command("gztrank")
    async def team_rank(self, event: AstrMessageEvent):
        args = parse_args(event.message_str.partition(" ")[2])
        try:
            game = await self._game_arg(args[1:] if len(args) > 1 else [])
            if not game: yield event.plain_result("未找到赛事"); return
            board = (await self.client.scoreboard(game["id"])).get("items", [])
            target = args[0] if args else ""
            rows = [x for x in board if str(x.get("id")) == target or x.get("name") == target]
            yield event.plain_result("\n".join(f"[{x.get('rank')}] {x.get('name')} - {x.get('score')}" for x in rows) or "未找到队伍")
        except Exception as exc: yield event.plain_result(f"查询失败: {exc}")

    @filter.command("gzq")
    async def challenge_query(self, event: AstrMessageEvent):
        args = parse_args(event.message_str.partition(" ")[2])
        try:
            game = await self._game_arg(args[:1]); game = game or await self._game_arg([])
            if not game: yield event.plain_result("未找到赛事"); return
            challenges = await self.client.challenges(game["id"])
            if len(args) > 1:
                challenges = [x for x in challenges if x.get("title") == args[1]]
            yield event.plain_result("\n".join(f"[{x.get('tag', x.get('category',''))}] {x.get('title')} | {x.get('score')} | {'开放' if x.get('isEnabled') else '关闭'}" for x in challenges) or "暂无题目")
        except Exception as exc: yield event.plain_result(f"获取题目失败: {exc}")

    @filter.command("gzteam")
    async def team(self, event: AstrMessageEvent):
        args = parse_args(event.message_str.partition(" ")[2])
        try:
            game = await self._game_arg([])
            if not game: yield event.plain_result("未找到赛事"); return
            teams = await self.client.teams(game["id"])
            if args: teams = [x for x in teams if x.get("name") == args[0]]
            yield event.plain_result("\n".join(f"{x.get('name')} | 成员: {', '.join(m.get('userName','') for m in x.get('members', []))}" for x in teams) or "未找到队伍")
        except Exception as exc: yield event.plain_result(f"获取队伍失败: {exc}")

    def _admin(self): return filter.permission_type(filter.PermissionType.ADMIN)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzopenb")
    async def open_ban(self, event): self.ban_enabled = True; yield event.plain_result("已开启自动封禁")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzcloseb")
    async def close_ban(self, event): self.ban_enabled = False; yield event.plain_result("已关闭自动封禁")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzopen")
    async def open_push(self, event): self.enabled = True; yield event.plain_result("已开启 GZCTF 播报")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzclose")
    async def close_push(self, event): self.enabled = False; yield event.plain_result("已关闭 GZCTF 播报")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzunlock")
    async def unlock(self, event):
        args = parse_args(event.message_str.partition(" ")[2])
        if not args: yield event.plain_result("用法: gzunlock [队伍ID]"); return
        try: await self.client.put(f"/api/admin/teams/{args[0]}", json={"locked": False}); yield event.plain_result("队伍已解锁")
        except Exception as exc: yield event.plain_result(f"解锁失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzban")
    async def ban(self, event):
        """按队伍 ID 封禁参与资格；支持 gzban [队伍ID]。"""
        args = parse_args(event.message_str.partition(" ")[2])
        if not args:
            yield event.plain_result("用法: gzban [队伍ID]")
            return
        try:
            await self.client.put(f"/api/admin/participation/{args[0]}", json={"status": "Suspended"})
            yield event.plain_result("队伍已封禁")
        except Exception as exc:
            yield event.plain_result(f"封禁失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzqa")
    async def admin_questions(self, event):
        async for result in self.challenge_query(event): yield result

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzaddnotice")
    async def add_notice(self, event):
        args = parse_args(event.message_str.partition(" ")[2])
        if len(args) < 2:
            yield event.plain_result("用法: gzaddnotice [赛事名] [公告]")
            return
        try:
            game = await self._game_arg(args[:1])
            if not game:
                yield event.plain_result("未找到赛事")
                return
            await self.client.post(f"/api/edit/games/{game['id']}/notices", json={"content": args[1]})
            yield event.plain_result("公告已添加")
        except Exception as exc:
            yield event.plain_result(f"添加公告失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzaddhint")
    async def add_hint(self, event):
        args = parse_args(event.message_str.partition(" ")[2])
        if len(args) < 3:
            yield event.plain_result("用法: gzaddhint [赛事名] [题目名] [提示]")
            return
        try:
            game = await self._game_arg(args[:1])
            challenges = await self.client.challenges(game["id"]) if game else []
            challenge = next((x for x in challenges if x.get("title") == args[1]), None)
            if not game or not challenge:
                yield event.plain_result("未找到赛事或题目")
                return
            detail = await self.client.challenge(game["id"], challenge["id"])
            hints = detail.get("hints", [])
            hints.append(args[2])
            await self.client.put(f"/api/edit/games/{game['id']}/challenges/{challenge['id']}", json={**detail, "hints": hints})
            yield event.plain_result("提示已添加")
        except Exception as exc:
            yield event.plain_result(f"添加提示失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("gzopenq", alias={"gzcloseq"})
    async def toggle_question(self, event):
        args = parse_args(event.message_str.partition(" ")[2]); enable = event.message_str.split()[0].lower() == "gzopenq"
        try:
            game = await self._game_arg(args[:1]); challenges = await self.client.challenges(game["id"]) if game else []
            target = next((x for x in challenges if len(args) > 1 and x.get("title") == args[1]), None)
            if not target: yield event.plain_result("未找到题目"); return
            await self.client.put(f"/api/edit/games/{game['id']}/challenges/{target['id']}", json={"isEnabled": enable})
            yield event.plain_result("题目已" + ("开放" if enable else "关闭"))
        except Exception as exc: yield event.plain_result(f"操作失败: {exc}")

    async def _poll_loop(self):
        interval = max(5, int(self.config.get("poll_interval", 20)))
        while True:
            try:
                if self.enabled: await self._poll_once()
            except asyncio.CancelledError: raise
            except Exception as exc: logger.warning("GZCTF 轮询失败: %s", exc)
            await asyncio.sleep(interval)

    async def _poll_once(self):
        for game in await self._selected_games():
            gid, title = game["id"], game.get("title", "")
            notices = await self.client.notices(gid)
            old = self.last_notices.setdefault(gid, notices)
            for notice in notices[len(old):]:
                await self._broadcast(f"【GZCTF公告】\n比赛: {title}\n时间: {fmt_time(notice.get('time'))}\n{(notice.get('values') or [''])[0]}")
            self.last_notices[gid] = notices
            if self.ban_enabled:
                cheats = await self.client.cheats(gid)
                old_cheats = self.last_cheats.setdefault(gid, cheats)
                for cheat in cheats[len(old_cheats):]:
                    for participation in (cheat.get("submitTeam"), cheat.get("ownedTeam")):
                        team_id = participation.get("id") if isinstance(participation, dict) else None
                        if team_id is not None:
                            try:
                                await self.client.put(f"/api/admin/participation/{team_id}", json={"status": "Suspended"})
                            except Exception as exc:
                                logger.warning("自动封禁队伍 %s 失败: %s", team_id, exc)
                    await self._broadcast(f"【封禁】\n比赛: {title}\n题目: {(cheat.get('submission') or {}).get('challenge', '')}")
                self.last_cheats[gid] = cheats

    async def _broadcast(self, text: str):
        for group in self.config.get("send_list", []):
            origin = f"aiocqhttp:GroupMessage:{group}"
            try: await self.context.send_message(origin, MessageChain([Plain(text)]))
            except Exception as exc: logger.warning("发送 GZCTF 播报失败: %s", exc)
