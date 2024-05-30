# -*- coding: utf-8 -*-
"""Basic class and prompt for prompt optimization"""

import json

from abc import ABC, abstractmethod
from pathlib import Path

from typing import Any


OPT_SYSTEM_PROMPT = """
你是一个擅长写和优化system prompt的专家。你的任务是优化用户提供的prompt, 使得优化后的system prompt包含对agent的角色或者性格描述，agent的技能点，和一些限制。
请注意
1. 优化后的system prompt必须与用户原始prompt意图一致，可适当加入可调用的工具、具体关键词、时间框架、上下文或任何可以缩小范围并指导agent能够更好地理解完成任务的附加信息，对用户的prompt进行重构。
2. 请注意角色描述和技能点的描述不能缩小用户原始prompt定义的范围。例如用户原始prompt里描述的是文案大师，优化后的prompt描述不能缩小范围变成小红书文案大师。
3. 对技能点的描述应该尽量详细准确。用户原始的prompt会提到一些示例，技能点应该能覆盖这些案例，但注意不能只局限于用户prompt里给的示例。例如用户原始prompt里提到出题机器人可以出填空题的考题的示例，优化后的prompt里技能点不能只包括出填空题。
4. 技能范围不能超过大模型的能力，如果超过，请必须注明需要调用哪些工具,或者需要哪些知识库来帮助大模型拥有这个技能。比如大模型并没有搜索功能，如果需要搜索，则需要调用搜索工具来实现。
5. 请以markdown的格式输出优化后的prompt。
6. 优化后的prompt必须语言简练，字数不超过1000字。
7. 如果用户提供的prompt包含知识库或者Memory部分，优化后的system prompt也必须保留这些部分。
8. 如果prompt中含有如下标识符的变量：${{variable}}, 请确保改变量在优化后的prompt里只出现一次,在其他要使用该变量的地方直接使用该变量名。例如${{document}}再次出现的时候，请直接使用"检索内容"。
9. 优化后的prompt语言与用户提供的prompt一致，即用户提供的prompt使用中文写的，优化后的prompt也必须是中文, 如果用户提供的prompt使用英文写的，优化后的prompt也必须是英文。
"""  # noqa


OPT_PROMPT_TEMPLATE = """
用户提供的system prompt是：
{user_prompt}

现在，请输出你优化后的system prompt:
"""


class PromptOptMethodBase(ABC):
    """base class for prompt optmization methods"""

    @abstractmethod
    def optimize(self, user_prompt: str) -> str:
        """Optimize the user prompt."""


def read_json_same_dir(file_name: str) -> Any:
    """read the json file in the same dir"""
    current_file_path = Path(__file__)

    json_file_path = current_file_path.parent / file_name

    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data


SYS_OPT_EXAMPLES = read_json_same_dir("system_opt_example.json")
ROLE_OPT_EXAMPLES = read_json_same_dir("role_opt_example.json")
