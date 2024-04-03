# -*- coding: utf-8 -*-
"""A simple example of agent that can perform
SQL queries through natural language conversation.
"""
from sql_utils import (
    DailSQLPromptGenerator,
    query_sqlite,
    create_sqlite_db_from_schema
)

import agentscope
from agentscope.agents.user_agent import UserAgent

from agentscope.agents import AgentBase
from agentscope.message import Msg


def process_duplication(sql: str) -> str:
    """
    Process sql duplication of results
    """
    sql = sql.strip().split("/*")[0]
    return sql


class SQLAgent(AgentBase):
    """An agent able to preform SQL tasks
    base on natual language instructions."""

    def __init__(
        self,
        name: str,
        db_id: str,
        db_path: str,
        model_config_name: str,
    ) -> None:
        super().__init__(
            name=name,
            model_config_name=model_config_name,
            use_memory=False,
        )
        self.db_id = db_id
        self.db_path = db_path
        self.max_retries = 3
        self.prompt_helper = DailSQLPromptGenerator(self.db_id, self.db_path)

        self.self_intro = f"""Hi, I am an agent able to preform SQL querys
        base on natual language instructions.
        Below is a description of the database {self.db_id} provided."""

        self.start_intro = f"""Is there any you want to
        ask about the database {self.db_id}?"""

    def get_response_from_prompt(self, prompt: dict) -> str:
        """
        Generate response from prompt using LLM
        """
        messages = [{"role": "assistant", "content": prompt}]
        sql = self.model(messages).text
        sql = " ".join(sql.replace("\n", " ").split())
        sql = process_duplication(sql)
        if sql.startswith("SELECT"):
            response = sql + "\n"
        elif sql.startswith(" "):
            response = "SELECT" + sql + "\n"
        else:
            response = "SELECT " + sql + "\n"
        return response

    def answer_from_result(
        self,
        question: str,
        response_text: str,
    ) -> str:
        """Answer the user question in natural language"""
        prompt = f"""Given the sql query and and the result,
        answer the user's question.
        \n User question: {question} \n {response_text}"""

        messages = [{"role": "assistant", "content": prompt}]
        answer = self.model(messages).text
        return answer

    def is_question_related(self, question: str) -> str:
        """
        Whether the question is sql related.
        Return "YES" if is related.
        Return chat answer if is not.
        """
        is_sql_prompt = self.prompt_helper.is_sql_question_prompt(question)
        messages = [{"role": "assistant", "content": is_sql_prompt}]
        is_sql_response = self.model(messages).text
        return is_sql_response

    def reply(self, x: dict = None) -> dict:
        # this means that here is the first call
        # and we should describe the database for user
        if x is None:
            describe_prompt = self.prompt_helper.describe_sql()
            messages = [{"role": "assistant", "content": describe_prompt}]
            response = [
                self.self_intro,
                self.model(messages).text,
                self.start_intro,
            ]
            response = "\n\n".join(response)
            msg = Msg(self.name, response, role="sql assistant")
            self.speak(msg)
            return msg
            return {}

        is_sql_response = self.is_question_related(x["content"])

        if is_sql_response.lower() != "yes":
            response_text = is_sql_response
            result = response_text
            msg = Msg(self.name, result, role="sql assistant")
            self.speak(msg)
            return msg

        prepared_prompt = self.prompt_helper.generate_prompt(x)

        attempt = 0
        result = None

        while attempt < self.max_retries:
            try:
                sql_response = self.get_response_from_prompt(
                    prepared_prompt["prompt"],
                )
                exec_result = query_sqlite(sql_response, path_db=self.db_path)
                response_text = f"""Generated SQL query is: {sql_response} \n
                The execution result is: {exec_result}"""
                response_text += "\n\n" + self.answer_from_result(
                    x["content"],
                    response_text,
                )
                result = response_text
                msg = Msg(self.name, result, role="sql assistant")
                self.speak(msg)
                break
            except Exception:
                print(
                    f"We fail to execute the generated query."
                    f"Attempt {attempt+1} of {self.max_retries} "
                    f"failed. Retrying!",
                )
                attempt += 1

        if result is None:
            print(
                "Sorry, the agent failed to execute query after",
                self.max_retries,
                "attempts",
            )
        return msg


if __name__ == "__main__":
    agentscope.init(
        model_configs="./configs/model_configs.json",
    )
    db_id = "concert_singer"
    db_schema_path = "./database/concert_singer/schema.sql"
    db_sqlite_path = "./database/concert_singer/concert_singer.sqlite"
    create_sqlite_db_from_schema(db_schema_path, db_sqlite_path)
    sql_agent = SQLAgent(
        name="sql agent",
        db_id=db_id,
        db_path=db_sqlite_path,
        model_config_name="gpt-4",
    )
    user_agent = UserAgent()
    mss = None
    while True:
        mss = sql_agent(mss)
        mss = user_agent(mss)

        if mss.content == "exit":
            print("Exiting the conversation.")
            break
