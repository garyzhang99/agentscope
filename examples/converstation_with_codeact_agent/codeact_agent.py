# -*- coding: utf-8 -*-
# pylint: disable=C0301
"""An agent class that implements the CodeAct agent.
This agent can execute code interactively as actions.
More details can be found at the paper of codeact agent
https://arxiv.org/abs/2402.01030
and the original repo of codeact https://github.com/xingyaoww/code-act
"""
import re
from typing import Union


from agentscope.agents import AgentBase
from agentscope.message import Msg
from agentscope.service import (
    ServiceResponse,
    ServiceExecStatus,
    NoteBookExecutor,
)

SYSTEM_MESSAGE = """system
You are a helpful assistant that gives helpful, detailed, and polite answers to the user's questions.
You should interact with the interactive Python (Jupyter Notebook) environment and receive the corresponding output when needed. The code written by assistant should be enclosed using [execute] tag, for example: [execute] print('Hello World!') [/execute].
You should attempt fewer things at a time instead of putting too much code in one [execute] block. You can install packages through PIP by [execute] !pip install [package needed] [/execute] and should always import packages and define variables before starting to use them.
You should stop [execute] and provide an answer when they have already obtained the answer from the execution result. Whenever possible, execute the code for the user using [execute] instead of providing it.
Your response should be concise, but do express their thoughts. Always write the code in [execute] block to execute them.
You should not ask for the user's input unless necessary. Solve the task on your own and leave no unanswered questions behind.
You should do every thing by your self.
"""  # noqa

EXAMPLE_MESSAGE = """
Additionally, you are provided with the following code available:
{example_code}
The above code is already available in your interactive Python (Jupyter Notebook) environment, allowing you to directly use these variables and functions without needing to redeclare them.
"""  # noqa


class CodeActAgent(AgentBase):
    """
    The implementation of CodeAct-agent
    """

    def __init__(
        self,
        name: str,
        model_config_name: str,
        example_code: str = "",
    ) -> None:
        """ """
        super().__init__(
            name=name,
            model_config_name=model_config_name,
        )
        self.n_max_executions = 5
        self.example_code = example_code
        self.code_executor = NoteBookExecutor()

        sys_msg = Msg(name="system", role="system", content=SYSTEM_MESSAGE)
        example_msg = Msg(
            name="user",
            role="user",
            content=EXAMPLE_MESSAGE.format(example_code=self.example_code),
        )

        self.memory.add(sys_msg)

        if self.example_code != "":
            code_execution_result = self.code_executor.run_code_on_notebook(
                self.example_code,
            )
            code_exec_msg = self.handle_code_result(
                code_execution_result,
                "Example Code excuted: ",
            )
            self.memory.add(example_msg)
            self.memory.add(code_exec_msg)
            self.speak(code_exec_msg)

    def handle_code_execution(
        self,
        response_text: str,
    ) -> Union[ServiceResponse, None]:
        """check if there are code execution block in the response,
        and execute them if exists"""
        code = re.search(
            r"\[execute\](.*)\[/execute\]",
            response_text,
            re.DOTALL,
        )
        if code is not None:
            code = code.group(1).strip()
            result = self.code_executor.run_code_on_notebook(code)
            return result
        return None

    def handle_code_result(
        self,
        code_execution_result: ServiceResponse,
        content_pre_sring: str = "",
    ) -> Msg:
        """return the message from code result"""
        code_exec_content = content_pre_sring
        if code_execution_result.status == ServiceExecStatus.SUCCESS:
            code_exec_content += "Excution Successful:\n"
        else:
            code_exec_content += "Excution Failed:\n"
        code_exec_content += "Execution Output:\n" + str(
            code_execution_result.content,
        )
        return Msg(name="user", role="user", content=code_exec_content)

    def reply(self, x: dict = None) -> None:
        """The reply function that implements the codeact agent."""

        self.memory.add(x)

        excution_count = 0
        while (
            self.memory.get_memory(1)[-1].role == "user"
            and excution_count < self.n_max_executions
        ):
            prompt = self.model.format(self.memory.get_memory())
            model_res = self.model(prompt)
            msg_res = Msg(
                name=self.name,
                content=model_res.text,
                role="assistant",
            )
            self.memory.add(msg_res)
            self.speak(msg_res)

            code_execution_result = self.handle_code_execution(model_res.text)
            if code_execution_result is not None:
                excution_count += 1
                code_exec_msg = self.handle_code_result(code_execution_result)
                self.memory.add(code_exec_msg)
                self.speak(code_exec_msg)

        if excution_count == self.n_max_executions:
            assert self.memory.get_memory(1)[-1].role == "user"
            code_max_exec_msg = Msg(
                name="assitant",
                role="assistant",
                content=(
                    "I have reached the maximum number "
                    f"of executions ({self.n_max_executions=}). "
                    "Can you assist me or ask me another question?"
                ),
            )
            self.memory.add(code_max_exec_msg)
            self.speak(code_max_exec_msg)
