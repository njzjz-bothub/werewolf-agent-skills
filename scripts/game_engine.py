#!/usr/bin/env python3
"""
狼人杀游戏引擎 - 管理游戏状态、角色分配、夜间/白天流程
由法官 session 调用
"""

import json
import random
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

class Role(Enum):
    WEREWOLF = "狼人"
    VILLAGER = "平民"
    SEER = "预言家"
    WITCH = "女巫"
    HUNTER = "猎人"
    GUARD = "守卫"
    IDIOT = "白痴"

class Team(Enum):
    WEREWOLF = "狼人阵营"
    VILLAGER = "好人阵营"

ROLE_TEAMS = {
    Role.WEREWOLF: Team.WEREWOLF,
    Role.VILLAGER: Team.VILLAGER,
    Role.SEER: Team.VILLAGER,
    Role.WITCH: Team.VILLAGER,
    Role.HUNTER: Team.VILLAGER,
    Role.GUARD: Team.VILLAGER,
    Role.IDIOT: Team.VILLAGER,
}

# 预设板子
BOARDS = {
    "6人": [Role.WEREWOLF, Role.WEREWOLF, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    "9人标准": [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF,
                Role.VILLAGER, Role.VILLAGER, Role.VILLAGER,
                Role.SEER, Role.WITCH, Role.HUNTER],
    "12人完整": [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF,
                 Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER,
                 Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD],
}

@dataclass
class Player:
    id: str
    name: str
    role: Optional[Role] = None
    team: Optional[Team] = None
    alive: bool = True
    can_vote: bool = True
    # 技能状态
    witch_antidote_used: bool = False
    witch_poison_used: bool = False
    hunter_can_shoot: bool = True
    idiot_revealed: bool = False
    last_guarded: Optional[str] = None

@dataclass
class GameState:
    day: int = 0  # 0=游戏未开始, 1=第一天
    phase: str = "setup"  # setup, night, day, ended
    players: list = None
    last_night_deaths: list = None
    last_day_voted: Optional[str] = None
    winner: Optional[str] = None

    def __post_init__(self):
        if self.players is None:
            self.players = []
        if self.last_night_deaths is None:
            self.last_night_deaths = []

class GameEngine:
    def __init__(self):
        self.state = GameState()
        self._night_actions = {}  # 存储夜间行动

    def setup_game(self, player_names: list[str], board_name: str = "9人标准") -> dict:
        """初始化游戏，分配角色"""
        if board_name not in BOARDS:
            available = ", ".join(BOARDS.keys())
            return {"error": f"未知板子: {board_name}. 可用: {available}"}

        board = BOARDS[board_name]
        if len(player_names) != len(board):
            return {"error": f"板子 {board_name} 需要 {len(board)} 人，但提供了 {len(player_names)} 人"}

        # 随机分配角色
        roles = board.copy()
        random.shuffle(roles)

        self.state.players = []
        for i, name in enumerate(player_names):
            role = roles[i]
            player = Player(
                id=f"player_{i}",
                name=name,
                role=role,
                team=ROLE_TEAMS[role]
            )
            self.state.players.append(player)

        self.state.phase = "night"
        self.state.day = 1

        return {
            "success": True,
            "assignments": [
                {"player": p.name, "role": p.role.value, "team": p.team.value}
                for p in self.state.players
            ]
        }

    def get_player_role(self, player_name: str) -> Optional[dict]:
        """获取玩家角色信息（用于告知玩家）"""
        for p in self.state.players:
            if p.name == player_name:
                return {
                    "name": p.name,
                    "role": p.role.value,
                    "team": p.team.value,
                    "teammates": [
                        {"name": other.name, "role": other.role.value}
                        for other in self.state.players
                        if other.name != p.name and other.team == p.team and p.team == Team.WEREWOLF
                    ] if p.team == Team.WEREWOLF else None
                }
        return None

    def get_werewolves(self) -> list[dict]:
        """获取所有狼人（用于狼人互相确认）"""
        return [
            {"name": p.name, "id": p.id}
            for p in self.state.players
            if p.role == Role.WEREWOLF and p.alive
        ]

    def process_night(self, actions: dict) -> dict:
        """
        处理夜间行动
        actions: {
            "werewolf_target": "玩家名",
            "witch_save": true/false,
            "witch_poison_target": "玩家名"/null,
            "seer_check": "玩家名",
            "guard_target": "玩家名"
        }
        """
        deaths = []
        results = {"seer_result": None}

        # 1. 处理守卫
        guarded = actions.get("guard_target")

        # 2. 处理狼人击杀
        werewolf_target = actions.get("werewolf_target")
        if werewolf_target:
            target_player = self._get_player(werewolf_target)
            if target_player and target_player.alive:
                # 检查是否被守护
                if guarded == werewolf_target:
                    # 被守护，不死
                    pass
                else:
                    # 被击杀
                    deaths.append(werewolf_target)

        # 3. 处理女巫
        if actions.get("witch_save") and werewolf_target:
            # 使用解药
            witch = self._get_witch()
            if witch and not witch.witch_antidote_used:
                # 检查奶穿
                if guarded == werewolf_target:
                    # 同守同救，死亡
                    pass  # 已经在deaths中
                else:
                    # 救活
                    if werewolf_target in deaths:
                        deaths.remove(werewolf_target)
                witch.witch_antidote_used = True

        if actions.get("witch_poison_target"):
            poison_target = actions.get("witch_poison_target")
            witch = self._get_witch()
            if witch and not witch.witch_poison_used:
                if poison_target not in deaths:
                    deaths.append(poison_target)
                witch.witch_poison_used = True
                # 被毒死的猎人不能开枪
                target = self._get_player(poison_target)
                if target and target.role == Role.HUNTER:
                    target.hunter_can_shoot = False

        # 4. 处理预言家查验
        seer_check = actions.get("seer_check")
        if seer_check:
            target = self._get_player(seer_check)
            if target:
                results["seer_result"] = {
                    "target": seer_check,
                    "is_werewolf": target.role == Role.WEREWOLF
                }

        # 应用死亡
        for death_name in deaths:
            player = self._get_player(death_name)
            if player:
                player.alive = False

        self.state.last_night_deaths = deaths
        self.state.phase = "day"

        results["deaths"] = deaths
        return results

    def process_day_vote(self, votes: dict) -> dict:
        """
        处理白天投票
        votes: {"投票者": "被投者", ...}
        """
        # 统计票数
        vote_count = {}
        for voter, target in votes.items():
            vote_count[target] = vote_count.get(target, 0) + 1

        if not vote_count:
            return {"error": "没有投票"}

        # 找出最高票
        max_votes = max(vote_count.values())
        candidates = [name for name, count in vote_count.items() if count == max_votes]

        # 平票则无人出局（简化规则）
        if len(candidates) > 1:
            return {
                "tie": True,
                "candidates": candidates,
                "votes": vote_count,
                "eliminated": None
            }

        eliminated = candidates[0]
        eliminated_player = self._get_player(eliminated)

        if eliminated_player:
            # 检查是否是白痴
            if eliminated_player.role == Role.IDIOT and not eliminated_player.idiot_revealed:
                eliminated_player.idiot_revealed = True
                eliminated_player.can_vote = False
                return {
                    "tie": False,
                    "eliminated": eliminated,
                    "is_idiot": True,
                    "votes": vote_count,
                    "message": f"{eliminated} 是白痴，亮明身份免于死亡但失去投票权"
                }
            else:
                eliminated_player.alive = False
                self.state.last_day_voted = eliminated

        self.state.phase = "night"
        self.state.day += 1

        return {
            "tie": False,
            "eliminated": eliminated,
            "is_idiot": False,
            "votes": vote_count,
            "hunter_can_shoot": eliminated_player.hunter_can_shoot if eliminated_player and eliminated_player.role == Role.HUNTER else False
        }

    def check_winner(self) -> Optional[str]:
        """检查游戏是否结束，返回获胜阵营"""
        alive_werewolves = len([p for p in self.state.players if p.alive and p.team == Team.WEREWOLF])
        alive_villagers = len([p for p in self.state.players if p.alive and p.team == Team.VILLAGER])
        alive_divine = len([p for p in self.state.players if p.alive and p.role in [Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD]])
        alive_civilian = len([p for p in self.state.players if p.alive and p.role == Role.VILLAGER])

        if alive_werewolves == 0:
            return "好人阵营"
        if alive_divine == 0 or alive_civilian == 0:
            return "狼人阵营"
        if alive_werewolves >= alive_villagers:
            return "狼人阵营"
        return None

    def get_alive_players(self) -> list[dict]:
        """获取所有存活玩家"""
        return [
            {"name": p.name, "id": p.id, "can_vote": p.can_vote}
            for p in self.state.players if p.alive
        ]

    def get_game_state(self) -> dict:
        """获取完整游戏状态（用于主 session 展示）"""
        return {
            "day": self.state.day,
            "phase": self.state.phase,
            "players": [
                {
                    "name": p.name,
                    "role": p.role.value if not p.alive else "?",
                    "alive": p.alive,
                    "can_vote": p.can_vote
                }
                for p in self.state.players
            ],
            "last_night_deaths": self.state.last_night_deaths,
            "last_day_voted": self.state.last_day_voted,
            "winner": self.state.winner
        }

    def _get_player(self, name: str) -> Optional[Player]:
        """通过名字获取玩家"""
        for p in self.state.players:
            if p.name == name:
                return p
        return None

    def _get_witch(self) -> Optional[Player]:
        """获取女巫玩家"""
        for p in self.state.players:
            if p.role == Role.WITCH and p.alive:
                return p
        return None


def main():
    """CLI 接口"""
    import sys
    command = sys.argv[1] if len(sys.argv) > 1 else None

    engine = GameEngine()

    if command == "setup":
        # python game_engine.py setup '["玩家1","玩家2",...]' '板子名'
        import json
        players = json.loads(sys.argv[2])
        board = sys.argv[3] if len(sys.argv) > 3 else "9人标准"
        result = engine.setup_game(players, board)
        print(json.dumps(result, ensure_ascii=False))

    elif command == "state":
        # 从文件读取状态
        import os
        state_file = os.path.expanduser("~/.werewolf_state.json")
        if os.path.exists(state_file):
            with open(state_file) as f:
                data = json.load(f)
                engine.state = GameState(**data)
        print(json.dumps(engine.get_game_state(), ensure_ascii=False))

    else:
        print(json.dumps({"error": f"未知命令: {command}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()